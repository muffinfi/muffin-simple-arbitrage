from typing import Any, Optional, TypedDict, Union
import numpy as np
from muffin_arb.market import Market, MuffinPool, UniV2Pool
from muffin_arb.evaluate import EvaluationResult
from muffin_arb.token import Token
from muffin_arb.utils.color import Color
from web3.datastructures import AttributeDict
from pprint import pprint


def print_optim_result_brief(res: EvaluationResult):
    """
    pool:            tETH / USDC
    token path:      tETH -> USDC -> tETH
    market path:     MuffinPool -> UniV2Pool -> MuffinPool
    """
    token0, token1 = ((res.token_in, res.token_bridge) if res.token_in.address.lower() < res.token_bridge.address.lower() else
                      (res.token_bridge, res.token_in))
    market1_class = res.market1.__class__.__name__
    market2_class = res.market2.__class__.__name__

    print(Color.CYELLOW2)
    print(f'pool:           ', f'{token0.symbol} / {token1.symbol}')
    print(f'token path:     ', f'{res.token_in.symbol} -> {res.token_bridge.symbol} -> {res.token_in.symbol}')
    print(f'market path:    ', f'{market1_class} -> {market2_class} -> {market1_class}')
    print(Color.CEND)


def print_optim_result_detail(res: EvaluationResult, invert_price: Optional[bool] = None):
    """
    pool:            tETH / USDC
    token path:      tETH -> USDC -> tETH
    market path:     MuffinPool -> UniV2Pool -> MuffinPool

    price unit:      USDC per tETH

    1st market:      MuffinPool
    tier_choices:    0b011111
    before:          1756.224 | 1755.346 | 1755.576 | 1757.334 | 1759.096
    after:           1707.432 | 1708.286 | 1709.997 | 1711.71  | 1713.425
    input_amts (%):  34.67%   | 43.34%   | 12.97%   | 3.80%    | 5.22%

    2nd market:      UniV2Pool
    before:          1699.514
    after:           1701.459

    input_amt:       33.1581  tETH        33158081054687500000
    bridge_amt:      57365.5  USDC        57365460090
    output_amt:      33.6335  tETH        33633531827260053535
    gas cost:        0        tETH

    profit:          0.475451 tETH
    profit (%):      1.434%
    """

    token0, token1 = ((res.token_in, res.token_bridge) if res.token_in.address.lower() < res.token_bridge.address.lower() else
                      (res.token_bridge, res.token_in))

    if invert_price is None:
        invert_price = False
        symbol0, symbol1 = token0.symbol, token1.symbol
        prefer_as_quote = ['USDC', 'DAI', 'USDT', 'WETH', 'tETH']
        for s in prefer_as_quote:
            if symbol0 == s or symbol1 == s:
                if symbol0 == s:
                    invert_price = True
                break

    def _print_market_summary(market: Market, is_market1: bool):
        token_in = res.token_in if is_market1 else res.token_bridge
        amt_in = res.amt_in if is_market1 else res.amt_bridge
        kwarg = res.market1_kwargs if is_market1 else res.market2_kwargs

        if isinstance(market, MuffinPool):
            _print_muffin(market, token_in, amt_in, kwarg)
        elif isinstance(market, UniV2Pool):
            _print_univ2(market, token_in, amt_in, kwarg)

    def _print_muffin(mkt: MuffinPool, token_in: Token, amt_in: int, kwarg: dict[str, Any]):
        # simulate swap
        tier_choices = kwarg.get('tier_choices', np.full(mkt.tier_count, True))  # type: np.ndarray
        quote_res = mkt.impl.quote(mkt.token0 == token_in, amt_in, tier_choices)
        amts_in = quote_res[3]
        sqrt_prices_after = quote_res[-4]

        prices_before = invert(sqrt_price_x72_to_price_float(mkt.impl.sqrt_prices, mkt.token0.unit, mkt.token1.unit), invert_price)  # nopep8
        prices_after = invert(sqrt_price_x72_to_price_float(sqrt_prices_after, mkt.token0.unit, mkt.token1.unit), invert_price)  # nopep8

        print(f'tier_choices:   ', f'{tier_choices_arr_to_mask(tier_choices):#08b}')
        print(f'before:         ', ' | '.join(format_price(prices_before)))
        print(f'after:          ', ' | '.join(format_price(prices_after)))
        print(f'input_amts (%): ', ' | '.join(f'{x:<8.2%}' for x in (amts_in / amt_in)))

    def _print_univ2(market: UniV2Pool, token_in: Token, amt_in: int, kwarg: dict[str, Any]):
        prices_before = invert(market.price(), invert_price)
        prices_after = invert(market.price_after(token_in, amt_in), invert_price)
        print(f'before:         ', f'{format_price(prices_before)}')
        print(f'after:          ', f'{format_price(prices_after)}')

    ###

    base, quote = (token1, token0) if invert_price else (token0, token1)
    market1_class = res.market1.__class__.__name__
    market2_class = res.market2.__class__.__name__

    """
    print path
    """
    print(Color.CYELLOW2)
    print(f'pool:           ', f'{token0.symbol} / {token1.symbol}')
    print(f'token path:     ', f'{res.token_in.symbol} -> {res.token_bridge.symbol} -> {res.token_in.symbol}')
    print(f'market path:    ', f'{market1_class} -> {market2_class} -> {market1_class}')

    """
    print markets
    """
    print(Color.CYELLOW)
    print(f'price unit:     ', f'{quote.symbol} per {base.symbol}')
    print()
    print(f'1st market:     ', market1_class)
    _print_market_summary(res.market1, True)
    print()
    print(f'2nd market:     ', market2_class)
    _print_market_summary(res.market2, False)

    """
    print arb info
    """
    print(Color.CYELLOW)
    print(f'input_amt:      ', f'{res.token_in.format_raw_amount(res.amt_in):<20} {res.amt_in}')
    print(f'bridge_amt:     ', f'{res.token_bridge.format_raw_amount(res.amt_bridge):<20} {res.amt_bridge}')
    print(f'output_amt:     ', f'{res.token_in.format_raw_amount(res.amt_out):<20} {res.amt_out}')
    print(f'net_amt:        ', f'{res.token_in.format_raw_amount(res.amt_net):<20} {res.amt_net}')
    print()
    print(f'base_gas_cost:  ', f'{res.token_in.format_raw_amount(res.gas_cost):<20} {res.gas_cost_wei} wei')
    print(f'profit:         ', f'{res.token_in.format_raw_amount(res.profit)}')
    print(f'profit (%):     ', f'{res.profit / res.amt_in:.3%}')
    print(Color.CEND)


def format_price(price):
    if isinstance(price, (list, np.ndarray)):
        return [format_price(p) for p in price]
    return '{:<8.7g}'.format(price)


def sqrt_price_x72_to_price_float(sqrt_price, token0_unit: int, token1_unit: int):
    return (sqrt_price ** 2) * token0_unit / (token1_unit * (2**144))


def invert(x, yes: bool):
    return 1 / x if yes else x


def tier_choices_arr_to_mask(tier_choices_arr: np.ndarray) -> int:
    return int(np.sum((1 << np.arange(0, len(tier_choices_arr)))[tier_choices_arr]))


# -----

def pprint_attr_dict(x, omit_keys: list[Any] = []):
    def parse_attr_dict(x, _omit_keys=[]):
        if isinstance(x, (AttributeDict, dict)):
            return {k: parse_attr_dict(v) for k, v in x.items() if k not in _omit_keys}
        if isinstance(x, list):
            return [parse_attr_dict(v) for v in x]
        return x

    pprint(parse_attr_dict(x, omit_keys))


def omit(x: Union[dict, TypedDict], keys: list[Any] = []):
    return {k: v for k, v in x.items() if k not in keys}