from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Callable, Iterator

from muffin_arb.market import Market
from muffin_arb.settings import ETH_ADDRESS, USDC_ADDRESS
from muffin_arb.token import Token


def gen_guess(x0: int, x1: int):
    """
    Generator that yields x0 and then a geometric sequence of x1
    """
    yield x0
    yield x1
    while True:
        x1 *= 2  # 2x per step
        yield x1


def maximize(fn: Callable[[int], int], gen: Iterator[int], xatol: int, xrtol: float, fatol: int) -> int:
    """
    Returns a value `x` that maximizes `fn(x)`, assuming `fn` is a strictly concave function.

    fn:     the objective function
    gen:    generator of the next guesses of x
    xatol:  absoluate tolerance of x
    xrtol:  relative tolerance of x
    fatol:  absoluate tolerance of fn(x)
    """
    bounds = (next(gen), next(gen))
    y_prev = 0
    while True:
        y = fn(bounds[-1])
        if y > y_prev:
            bounds = (bounds[-2], bounds[-1], next(gen))
            y_prev = y
        else:
            mid = (bounds[0]+bounds[-1])//2
            end = ((mid-bounds[0]) <= xatol or
                   (mid-bounds[0])/mid <= xrtol or
                   (y_prev-y) <= fatol)
            if end:
                return mid

            xs = [bounds[0], (bounds[0]+mid)//2, mid, (mid+bounds[-1])//2, bounds[-1]]
            return maximize(fn, iter(xs), xatol, xrtol, fatol)


def evaluate_arb(
    market1:        Market,
    market2:        Market,
    token_in:       Token,
    token_bridge:   Token,
    market1_kwargs: dict[str, Any],
    market2_kwargs: dict[str, Any],
    gas_price:      int = 0
):
    """
    Evaluate the arbitrage profit between two given markets.

    market1:            The first market we go to swap
    market2:            The next market which we swap using the output from the first market
    token_in:           The token currency sent to market1
    token_bridge:       The token currency sent from market1 to market2
    market1_kwargs:     Extra args to pass to market1.quote
    market2_kwargs:     Extra args to pass to market2.quote
    gas_price:          Current gas price (in wei)
    """

    @lru_cache(maxsize=None)
    def arbitrage(x: int):
        assert x >= 0
        amt_in = x
        amt_bridge = market1.quote(token_in, amt_in, **market1_kwargs) * -1
        amt_out = market2.quote(token_bridge, amt_bridge, **market2_kwargs) * -1
        return (amt_out-amt_in, amt_bridge, amt_out)

    """
    Step 1. Test if there is arb opportunity.
    """
    # test with an amount of 0.0001 tokens or 1000 base units
    test_amt_in = max(token_in.unit // 10**4, 1000)
    test_amt_net = arbitrage(test_amt_in)[0]
    if test_amt_net <= 0:
        raise EvaluationFailure(f'Not profitable ({test_amt_net})')

    """
    Step 2. Find a token input amount that maximizes arb profit.
    """
    fn = lambda x: arbitrage(x)[0]
    amt_in = maximize(fn, gen_guess(1, token_in.unit), xatol=1, xrtol=1/100_000, fatol=1)
    amt_net, amt_bridge, amt_out = arbitrage(amt_in)

    """
    Step 3. Guesstimate a gas cost.

    We'll `eth_estimateGas` and calculate fee more precisely later on, but here we still want to roughly estimate gas
    to reject any seemingly non-profitable arbs, such that we don't waste time handling them later on.
    """
    GAS_PER_ARB = 190_000  # rough guess
    gas_cost_wei = GAS_PER_ARB * gas_price

    # convert gas cost to the unit of the input token
    if token_in.address == ETH_ADDRESS:
        gas_cost = gas_cost_wei
    elif token_in.address == USDC_ADDRESS:
        gas_cost = gas_cost_wei * 2000 * 10**6 // 10**18  # treat 2000 usdc -> 1 eth
    else:
        raise NotImplementedError()

    profit = amt_net - gas_cost
    if profit <= 0:
        raise EvaluationFailure(f'Negative profit: {profit} ({amt_net} - {gas_cost})')

    return EvaluationResult(
        market1, market2, token_in, token_bridge, market1_kwargs, market2_kwargs,  # inputs
        amt_in, amt_bridge, amt_out, amt_net, gas_cost, gas_cost_wei, profit,  # outputs
    )


class EvaluationFailure(Exception):
    pass


@dataclass
class EvaluationResult:
    market1:        Market
    market2:        Market
    token_in:       Token
    token_bridge:   Token
    market1_kwargs: dict[str, Any]
    market2_kwargs: dict[str, Any]

    amt_in:         int
    amt_bridge:     int
    amt_out:        int
    amt_net:        int
    gas_cost:       int
    gas_cost_wei:   int
    profit:         int
