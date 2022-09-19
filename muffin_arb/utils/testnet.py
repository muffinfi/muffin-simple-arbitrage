import json
from typing import TypedDict
from muffin_arb.arbitrage import send_tx_directly
from muffin_arb.market import UniV2Pool
from muffin_arb.settings import CMC_PRO_API_KEY, UNIV2_MARKETS, arber_contract, tx_sender
from muffin_arb.token import Token
from multicall import Signature
from requests import Session


ResetPoolPriceArg = TypedDict('ResetPoolPriceArg', {
    'token0': Token,
    'token1': Token,
    'price': float,
    'amount1_float': float
})


def reset_pool_price(args: list[ResetPoolPriceArg]):
    """
    Reset a UniV2Pool price, for internal testing only.

    To use it, please deploy your own test tokens with the function "setBalance(address account, uint256 balance)",
    and create a pool manually on univ2 on testnet.

    Example usage:
    ```
    from muffin_arb.utils.testnet import reset_pool_price, fetch_market_price, Token

    reset_pool_price([{
        'token0': Token.get('0x2C03fF2a384b5CbB93998be296adE0Ed2d9E60f9'),
        'token1': Token.get('0xb6136C36610d4d5374030AC0Ec0021fB1F04aaAa'),
        'price': fetch_market_price('ETH', 'USDC'),
        'amount1_float': 20_000_000
    }])
    ```
    """
    calldatas: list[tuple[str, int, bytes]] = []

    for arg in args:
        token0, token1 = arg['token0'], arg['token1']
        print(token0.symbol, token1.symbol, arg['price'])

        reserve1 = int(arg['amount1_float'] * token1.unit) or 1
        reserve0 = int(arg['amount1_float'] / arg['price'] * token0.unit) or 1

        pool_address = UniV2Pool.compute_pool_address(token0.address, token1.address, UNIV2_MARKETS[0])
        calldatas.extend([
            (token0.address, 0, Signature('setBalance(address,uint256)()').encode_data((pool_address, reserve0))),
            (token1.address, 0, Signature('setBalance(address,uint256)()').encode_data((pool_address, reserve1))),
            (pool_address, 0, Signature('sync()()').encode_data()),
        ])

        pair_name = f"{token0.symbol}-{token1.symbol}"
        print(f"reset {pair_name} univ2 reserves:\t {arg['price']}\t{(reserve0, reserve1)}")

    prepared_fn = arber_contract.functions.multicall(True, calldatas)
    send_tx_directly(prepared_fn, tx_sender, wait=True)


def fetch_market_price(base_symbol: str, quote_symbol: str) -> float:
    session = Session()
    session.headers.update({'Accepts': 'application/json', 'X-CMC_PRO_API_KEY': CMC_PRO_API_KEY})
    response = session.get('https://pro-api.coinmarketcap.com/v2/cryptocurrency/quotes/latest', params={
        'symbol': base_symbol,
        'convert': quote_symbol,
    })
    data = json.loads(response.text)
    try:
        assert len(data['data'][base_symbol]) == 1
        return float(data['data'][base_symbol][0]['quote'][quote_symbol]['price'])
    except Exception as err:
        print(data)
        raise err
