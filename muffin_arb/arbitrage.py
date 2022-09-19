from typing import Any, Union

import numpy as np
from eth_abi.abi import encode_abi
from eth_account.datastructures import SignedTransaction
from eth_account.signers.local import LocalAccount
from eth_utils.hexadecimal import decode_hex
from flashbots.flashbots import FlashbotsBundleResponse
from flashbots.types import FlashbotsBundleRawTx, FlashbotsBundleTx
from requests import RequestException
from termcolor import cprint
from web3.contract import ContractFunction
from web3.types import Wei

from muffin_arb.market import Market, MuffinPool, UniV2Pool
from muffin_arb.settings import (BRIBE_PERCENTAGE_POST_BASE_FEE, ETH_ADDRESS,
                                 NETWORK, USDC_ADDRESS, USE_FLASH_BOT,
                                 arber_contract, hub_contract, tx_sender,
                                 univ2_interface, w3, w3_flashbots)
from muffin_arb.token import Token
from muffin_arb.utils.logging import pprint_dict


class Skip(Exception):
    pass


def send_arb(
    market1:        Market,
    market2:        Market,
    token_in:       Token,
    token_bridge:   Token,
    market1_kwargs: dict[str, Any],
    market2_kwargs: dict[str, Any],
    amt_in:         int,
    amt_bridge:     int,
    amt_out:        int,
    **kwargs
):
    """
    Construct and send an arb transaction.
    You may want to `evaluate_arb` first before calling this function.

    market1:            The first market we go to swap
    market2:            The next market which we swap using the output from the first market
    token_in:           The token currency sent to market1
    token_bridge:       The token currency sent from market1 to market2
    market1_kwargs:     Extra args to pass to market1.quote
    market2_kwargs:     Extra args to pass to market2.quote
    amt_in:             Amount of `token_in` to send to market1
    amt_bridge:         Amount of `token_bridge` to request from market1 to send to market2
    amt_out:            Amount of `token_in` to request from market2
    """

    """
    Step 1. Prepare calldata
    """
    amt_net = amt_out - amt_in

    if isinstance(market1, MuffinPool) and isinstance(market2, UniV2Pool):
        arb_call = muffin_first(
            token_in_address=token_in.address,
            token_bridge_address=token_bridge.address,
            amt_in=amt_in,
            amt_out=amt_out,
            univ2_pool_address=market2.address,
            tier_choices=tier_choices_arr_to_mask(market1_kwargs['tier_choices']),
            min_amt_net=amt_net,
            tx_fee_wei=0,  # we pay miner by maxPriorityFeePerGas
        )
    elif isinstance(market1, UniV2Pool) and isinstance(market2, MuffinPool):
        arb_call = univ2_first(
            token_in_address=token_in.address,
            token_bridge_address=token_bridge.address,
            amt_in=amt_in,
            amt_bridge=amt_bridge,
            univ2_pool_address=market1.address,
            tier_choices=tier_choices_arr_to_mask(market2_kwargs['tier_choices']),
            min_amt_net=amt_net,
            tx_fee_wei=0,  # we pay miner by maxPriorityFeePerGas
        )
    else:
        raise NotImplementedError(f'unknown market pair: {market1.__class__}, {market2.__class__}')

    if NETWORK == 'rinkeby' or not USE_FLASH_BOT:
        send_tx_directly(arb_call, tx_sender, wait=True)
        return

    """
    Step 2. Estimate gas needed for the arb
    """
    try:
        gas = arb_call.estimateGas({'from': tx_sender.address})
        print('Estimated gas: ', gas)
    except Exception as e:
        raise Skip(f'Failed to estimate gas: {e}')

    if gas > 1_000_000:
        raise Skip("pretty sus gas")

    """
    Step 3. Calculate the acceptable gas fee.
    """
    latest_block = w3.eth.get_block('latest')
    assert 'baseFeePerGas' in latest_block and 'number' in latest_block

    # convert the net token amounts to eth
    if token_in.address == ETH_ADDRESS:
        amt_net_eth = amt_net
    elif token_in.address == USDC_ADDRESS:
        amt_net_eth = amt_net * 10**18 // (1000 * 10**6)  # treat 1 eth -> 1000 USDC
    else:
        raise NotImplementedError()

    profit_per_gas = amt_net_eth // gas

    # `mpf` means "max priority fee per gas" here
    breakeven_mpf = profit_per_gas - latest_block['baseFeePerGas']
    mpf = breakeven_mpf * BRIBE_PERCENTAGE_POST_BASE_FEE // 100

    # skip if our maxPriorityFeePerGas is not reasonable
    if mpf <= 0:
        raise Skip('Not profitable')
    if mpf <= w3.eth.max_priority_fee:
        raise Skip(f'Max priority fee probably not enough: {mpf}, {w3.eth.max_priority_fee}')

    if NETWORK == 'goerli':
        # override setting for testnet
        mpf = min(mpf, w3.eth.max_priority_fee * 200 // 100)

    """
    Step 4. Build transaction
    """
    tx_params = arb_call.buildTransaction({
        'from': tx_sender.address,
        'nonce': w3.eth.get_transaction_count(tx_sender.address),
        'type': 2,
        'maxFeePerGas': Wei(profit_per_gas),
        'maxPriorityFeePerGas': Wei(mpf),
        'gas': Wei(gas),
    })
    pprint_dict(tx_params, omit_keys=['data'])
    print()

    """
    Step 5. Send transaction
    """
    next_block_num = latest_block['number'] + 1
    bundle = [{"signer": tx_sender, "transaction": tx_params}]  # type: list[Union[FlashbotsBundleTx, FlashbotsBundleRawTx]] # nopep8

    try:
        simulation = w3_flashbots.simulate(bundle, next_block_num)
        print('Simulation success:')
        pprint_dict(simulation, omit_keys=['signedBundledTransactions'])
        print()
    except Exception as e:
        print(e.response.content if isinstance(e, RequestException) else e)
        raise Skip('simulation error')

    retry_times = 5 if NETWORK == 'goerli' else 2
    responses: list[FlashbotsBundleResponse] = [
        w3_flashbots.send_bundle(bundle, target_block_number=next_block_num + i)  # type: ignore
        for i in range(retry_times)
    ]

    for i, resp in enumerate(responses):
        try:
            resp.wait()
            receipts = resp.receipts()
            cprint(f"Bundle was mined in block {next_block_num + i}", on_color='on_green')
            pprint_dict(receipts)
            print('\n\n\n\n\n\n\n')
            return
        except Exception as e:
            print(e)
            cprint(f"Bundle not found in block {next_block_num + i}", on_color='on_red')
            print()
            if i == 0:
                bundle_stats = w3_flashbots.get_bundle_stats(simulation['bundleHash'], resp.target_block_number)  # type: ignore # nopep8
                print('bundle_stats:    ', bundle_stats, '\n')
                # user_stats = w3_flashbots.get_user_stats()  # type: ignore
                # print('user_stats:      ', user_stats, '\n')


def tier_choices_arr_to_mask(tier_choices_arr: np.ndarray) -> int:
    """
    Convert a numpy array of boolean to bit mask, e.g. np.array([False, False, True]) -> 0b100
    """
    return int(np.sum((1 << np.arange(0, len(tier_choices_arr)))[tier_choices_arr]))


def send_tx_directly(prepared_fn: ContractFunction, sender: LocalAccount, wait=True):
    # build tx params
    nonce = w3.eth.get_transaction_count(sender.address)
    tx_params = prepared_fn.buildTransaction({
        'from': sender.address,
        'nonce': nonce,
    })

    # sign tx
    signed_tx: SignedTransaction = sender.sign_transaction(tx_params)
    print(tx_params)

    # send tx
    tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
    print('tx_hash: ', tx_hash.hex())

    # wait for receipt
    if wait:
        tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        print('gasUsed: ', tx_receipt['gasUsed'])


# ****************************************************************************


def muffin_first(
    token_in_address: str,
    token_bridge_address: str,
    amt_in: int,
    amt_out: int,
    univ2_pool_address: str,
    tier_choices: int,
    min_amt_net: int,
    tx_fee_wei: int
) -> ContractFunction:
    """
    Prepare calldata for an arb with the token flow "Arbitrageur -> Muffin -> UniV2 -> Arbitrageur".
    """

    """
    . Note:
    . - The dashed path (e.g. "A ─ ─ ─ ─ ─ ─ ─ ▶ B") means "A calls B"
    . - The solid path  (e.g. "A ─────token────▶ B") means "A transfers `token` to B"
    . - The number on the path (e.g. ───1───▶) means the order in which it happens
    .
    .     ┌──1──────────────token_bridge──────────────────┐
    .     │                                               ▼
    . ┌──────┐                                         ┌─────┐
    . │Muffin│─ ─ ─ ─ 2 ─ ─ ─ ─ ┐  ┌ ─ ─ ─ ─ 3 ─ ─ ─ ▶ │UniV2│
    . └──────┘                  ▼  |                   └─────┘
    .     ▲                  ┌────────┐                   │
    .     └───token_in───5───│ Arber  │◀────token_in────4─┘
    .                        └────────┘
    .
    . Explanation:
    . 0. Arbitrageur calls Muffin's `swap` with the recipient set to UniV2.
    . 1. Muffin sends output tokens to UniV2, and now Arbitrageur owes Muffin's input tokens to finish the swap.
    . 2. Muffin calls Arbitrageur's `muffinSwapCallback`.
    . 3. In the callback, Arbitrageur calls `swap` on UniV2.
    . 4. UniV2 sends an output to Arbitrageur. Note that UniV2 already received an input on #1.
    . 5. Arbitrageur uses a part of the output from UniV2 to pay Muffin.
    .    Hence, profit = (`token_in` received on path #4) - (`token_in` sent on path #5)
    """

    univ2_amt0_out, univ2_amt1_out = (
        (amt_out, 0) if token_in_address.lower() < token_bridge_address.lower() else
        (0, amt_out)
    )
    univ2_swap_calldata = univ2_interface.encodeABI('swap', args=[
        univ2_amt0_out,             # uint256 amount0Out
        univ2_amt1_out,             # uint256 amount1Out
        arber_contract.address,     # address to
        b'',                        # bytes calldata data
    ])
    muffin_callback_data = encode_abi(
        ['address', 'bytes', 'uint256'],
        [univ2_pool_address, decode_hex(univ2_swap_calldata), 0]
    )
    hub_swap_calldata = hub_contract.encodeABI('swap', args=[
        token_in_address,           # address tokenIn
        token_bridge_address,       # address tokenOut
        tier_choices,               # uint256 tierChoices
        amt_in,                     # int256 amountDesired
        univ2_pool_address,         # address recipient
        0,                          # uint256 recipientAccRefId (0 means not sending from caller's internal account)
        0,                          # uint256 senderAccRefId    (0 means not sending to recipient's internal account)
        muffin_callback_data,       # bytes calldata data
    ])
    return arber_contract.functions.work(
        token_in_address,           # address tokenIn,
        min_amt_net,                # uint256 amtNetMin,
        tx_fee_wei,                 # uint256 txFeeEth,
        hub_swap_calldata           # bytes calldata data
    )


def univ2_first(
    token_in_address: str,
    token_bridge_address: str,
    amt_in: int,
    amt_bridge: int,
    univ2_pool_address: str,
    tier_choices: int,
    min_amt_net: int,
    tx_fee_wei: int
) -> ContractFunction:
    """
    Prepare calldata for an arb with the token flow "Arbitrageur -> UniV2 -> Muffin -> Arbitrageur".
    """

    """
    . Note:
    . - The dashed path (e.g. "A ─ ─ ─ ─ ─ ─ ─ ▶ B") means "A calls B"
    . - The solid path  (e.g. "A ─────token────▶ B") means "A transfers `token` to B"
    . - The number on the path (e.g. ───1───▶) means the order in which it happens
    .
    .     ┌─────────────────token_bridge──────────────5───┐
    .     ▼                                               │
    . ┌──────┐                                         ┌─────┐
    . │Muffin│─ ─ ─ ─ 2 ─ ─ ─ ─ ┐  ┌ ─ ─ ─ ─ 4 ─ ─ ─ ▶ │UniV2│
    . └──────┘                  ▼  |                   └─────┘
    .     │                  ┌────────┐                   ▲
    .     └─1────token_in───▶│ Arber  │───3───token_in────┘
    .                        └────────┘
    .
    . Explanation:
    . 0. Arbitrageur calls Muffin's `swap` with the recipient set to Arbitrageur itself.
    . 1. Muffin sends output tokens to Arbitrageur, and now Arbitrageur owes Muffin's input tokens to finish the swap.
    . 2. Muffin calls Arbitrageur's `muffinSwapCallback`.
    . 3. In the callback, Arbitrageur sends a part of the output from Muffin to UniV2.
    . 4. Arbitrageur calls `swap` on UniV2 with the recipient set to Muffin.
    . 5. UniV2 sends an output to Muffin. This completes the initial swap on Muffin
    .    Hence, profit = (`token_in` received on path #1) - (`token_in` sent on path #3)
    """

    univ2_amt0_out, univ2_amt1_out = (
        (0, amt_bridge) if token_in_address.lower() < token_bridge_address.lower() else
        (amt_bridge, 0)
    )
    univ2_swap_calldata = univ2_interface.encodeABI('swap', args=[
        univ2_amt0_out,             # uint256 amount0Out
        univ2_amt1_out,             # uint256 amount1Out
        hub_contract.address,       # address to
        b'',                        # bytes calldata data
    ])
    muffin_callback_data = encode_abi(
        ['address', 'bytes', 'uint256'],
        [univ2_pool_address, decode_hex(univ2_swap_calldata), amt_in]
    )
    hub_swap_calldata = hub_contract.encodeABI('swap', args=[
        token_bridge_address,       # address tokenIn
        token_in_address,           # address tokenOut
        tier_choices,               # uint256 tierChoices
        amt_bridge,                 # int256 amountDesired
        arber_contract.address,     # address recipient
        0,                          # uint256 recipientAccRefId (0 means not sending from caller's internal account)
        0,                          # uint256 senderAccRefId    (0 means not sending to recipient's internal account)
        muffin_callback_data,       # bytes calldata data
    ])
    return arber_contract.functions.work(
        token_in_address,           # address tokenIn,
        min_amt_net,                # uint256 amtNetMin,
        tx_fee_wei,                 # uint256 txFeeEth,
        hub_swap_calldata           # bytes calldata data
    )
