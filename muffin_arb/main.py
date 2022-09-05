import asyncio
import itertools
import json
import time
import numpy as np
from pprint import pprint
from termcolor import cprint
from websockets.legacy.client import connect
from muffin_arb.arbitrage import Skip, send_arb
from muffin_arb.market import Market, MuffinPool, UniV2Pool
from muffin_arb.evaluate import EvaluationFailure, EvaluationResult, evaluate_arb
from muffin_arb.settings import ETH_ADDRESS, TOKEN_ADDRESSES, WEBSOCKET_PROVIDER_URI, w3
from muffin_arb.token import Token
from muffin_arb.utils.logging import print_optim_result_detail, print_optim_result_brief


def get_eth_addr_pairs() -> list[tuple[str, str]]:
    """
    Return a list of (address, address) which involes eth
    """
    addr_pairs = list(itertools.product([ETH_ADDRESS], TOKEN_ADDRESSES))
    return [
        tuple(sorted([addr0, addr1], key=str.lower))
        for addr0, addr1 in addr_pairs
        if addr0 != addr1
    ]


def run_once():
    """
    1.  Load ETH pairs from muffin and uniswapv2
    2.  Evaluate if there're arb opportunities and estimate profit
    3.  Send out the arb with the largest profit
    """

    # load tokens
    token_map = Token.from_addresses(TOKEN_ADDRESSES)

    # form token pairs with eth
    addr_pairs = get_eth_addr_pairs()
    pairs = [(token_map[addr0], token_map[addr1]) for addr0, addr1 in addr_pairs]
    pprint(list(addr_pairs))

    # load all pool data
    muffin_pools = MuffinPool.from_pairs(pairs)
    univ2_pools = UniV2Pool.from_pairs(pairs)
    market_pairs = [(muffin, univ2) for muffin, univ2 in zip(muffin_pools, univ2_pools) if muffin and univ2]

    # get current base fee per gas
    pending_block = w3.eth.get_block('pending')
    assert 'baseFeePerGas' in pending_block

    # find all arb opportunities
    results: list[EvaluationResult] = []
    for muffin, univ2 in market_pairs:

        # determine input token and bridge token
        token0, token1 = muffin.token0, muffin.token1
        token_in, token_bridge = (token0, token1) if token0.address == ETH_ADDRESS else (token1, token0)

        # try both directions
        markets: list[tuple[Market, Market]] = [(muffin, univ2), (univ2, muffin)]
        for m1, m2 in markets:
            note = f'ME --{token_in.symbol}--> [{m1.__class__.__name__:<10}] --{token_bridge.symbol}--> [{m2.__class__.__name__:<10}]: '
            try:
                # evaluate if there's arb opportunity
                # todo: determine which tiers to swap to maximize profit
                m1_kwargs = {'tier_choices': np.full(m1.tier_count, True)} if isinstance(m1, MuffinPool) else {}
                m2_kwargs = {'tier_choices': np.full(m2.tier_count, True)} if isinstance(m2, MuffinPool) else {}
                res = evaluate_arb(m1, m2, token_in, token_bridge, m1_kwargs, m2_kwargs, pending_block['baseFeePerGas'])
                results.append(res)

                cprint(note, on_color='on_magenta')
                print_optim_result_detail(res)
            except EvaluationFailure as err:
                print(note, err)
                pass

    # send the most profitable arb
    if results:
        print('\n-------------\n')
        results = sorted(results, key=lambda x: x.profit)
        for res in results:
            try:
                print_optim_result_brief(res)
                send_arb(**res.__dict__)
                break
            except Skip as e:
                print(f'skipping: {e}')


async def subscribe():
    async with connect(WEBSOCKET_PROVIDER_URI, ping_interval=None) as ws:
        await ws.send(json.dumps({"id": 1, "method": "eth_subscribe", "params": ["newHeads"]}))
        await ws.recv()
        print('Subscribed to new block.')

        while True:
            message = await asyncio.wait_for(ws.recv(), timeout=None)
            block = json.loads(message)['params']['result']
            cprint(f'Block_number: {int(block["number"], 16)}', on_color='on_cyan')

            # skip if there's already another new block in the queue
            if len(ws.messages) >= 1:
                print('skipping minted block')
                continue

            start = time.time()
            run_once()
            print('Time spent: ', f'{time.time() - start:.4f} sec', '\n')


def main():
    asyncio.run(subscribe())
