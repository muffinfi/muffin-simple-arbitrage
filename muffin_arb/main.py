import asyncio
import itertools
import json
import time
import traceback
from datetime import datetime
import numpy as np
from termcolor import cprint
from websockets.legacy.client import connect
from muffin_arb.arbitrage import Skip, send_arb
from muffin_arb.market import Market, MuffinPool, UniV2Pool
from muffin_arb.evaluate import EvaluationFailure, EvaluationResult, evaluate_arb
from muffin_arb.settings import ETH_ADDRESS, TOKEN_ADDRESSES, UNIV2_MARKETS, WEBSOCKET_PROVIDER_URI, w3, ERROR_LOG_FILE
from muffin_arb.token import Token
from muffin_arb.utils.logging import print_optim_result_detail, print_optim_result_brief, print_pool_prices


def get_eth_addr_pairs() -> list[tuple[str, str]]:
    """
    Return a list of (address, address) which either one is weth
    """
    addr_pairs = itertools.product([ETH_ADDRESS], TOKEN_ADDRESSES)
    return [
        tuple(sorted([addr0, addr1], key=str.lower))
        for addr0, addr1 in addr_pairs
        if addr0 != addr1
    ]


def run_once():
    """
    1.  Load ETH-token pairs from muffin and other uniswapv2 markets.
    2.  For each pair, evaluate if there're arb opportunities and estimate profit.
    3.  Send the arb with the highest estimated profit.
    """

    # load tokens
    token_map = Token.from_addresses(TOKEN_ADDRESSES)

    # form token pairs with eth
    addr_pairs = get_eth_addr_pairs()
    pairs = [(token_map[addr0], token_map[addr1]) for addr0, addr1 in addr_pairs]

    # load all pool data
    muffin_pools = MuffinPool.from_pairs(pairs)
    market_pairs: list[tuple[MuffinPool, UniV2Pool]] = []
    for source in UNIV2_MARKETS:
        univ2_pools = UniV2Pool.from_pairs(pairs, source)
        market_pairs.extend([
            (muffin, univ2)
            for muffin, univ2 in zip(muffin_pools, univ2_pools)
            if muffin and univ2
        ])

    # get current base fee per gas
    latest_block = w3.eth.get_block('latest')
    assert 'baseFeePerGas' in latest_block and 'number' in latest_block

    # find all arb opportunities
    results: list[EvaluationResult] = []
    for muffin, univ2 in market_pairs:
        # for every 20 blocks, print all pool prices for records
        if latest_block['number'] % 20 == 0:
            print_pool_prices(muffin, univ2)

        # determine input token and bridge token
        token0, token1 = muffin.token0, muffin.token1
        token_in, token_bridge = (token0, token1) if token0.address == ETH_ADDRESS else (token1, token0)

        # try both directions
        markets: list[tuple[Market, Market]] = [(muffin, univ2), (univ2, muffin)]
        for m1, m2 in markets:
            note = f'--{token_in.symbol}--> {str(m1):<12} --{token_bridge.symbol}--> {str(m2):<12}: '

            try:
                # evaluate if there's arb opportunity
                # todo: determine which tiers to use so as to maximize profit. now use all tiers by default.
                m1_kwargs = {'tier_choices': np.full(m1.tier_count, True)} if isinstance(m1, MuffinPool) else {}
                m2_kwargs = {'tier_choices': np.full(m2.tier_count, True)} if isinstance(m2, MuffinPool) else {}
                res = evaluate_arb(m1, m2, token_in, token_bridge, m1_kwargs, m2_kwargs, latest_block['baseFeePerGas'])
                results.append(res)

                cprint(note, on_color='on_magenta')
                print_optim_result_detail(res)
            except EvaluationFailure as err:
                print(note, err)
                pass

    # send the most profitable arb
    if results:
        results = sorted(results, key=lambda x: x.profit)  # FIXME:
        for res in results:
            try:
                print('\n----- send arb ------\n')
                print_optim_result_brief(res)
                send_arb(**res.__dict__)
                break
            except Skip as e:
                print(f'skipping: {e}')


async def subscribe():
    """
    Subscribe to new blocks and run arb per block
    """
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


async def subscribe_and_reconnect_on_failed():
    while True:
        try:
            await subscribe()
        except Exception as e:
            print(e)
            print(f'\n\n\nTry to reconnect\n\n\n')

            with open(ERROR_LOG_FILE, 'a') as f:
                f.write('\n\n\n')
                f.write(datetime.now().replace(microsecond=0).isoformat(' ') + '\n')
                f.write(traceback.format_exc())


def main():
    asyncio.run(subscribe_and_reconnect_on_failed())
