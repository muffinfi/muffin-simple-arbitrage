from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Iterator
from muffin_arb.market import Market
from muffin_arb.settings import ETH_ADDRESS, USDC_ADDRESS
from muffin_arb.token import Token


def gen_guess(x0: int, x1: int):
    yield x0
    yield x1
    while True:
        x1 *= 2  # 2x per step
        yield x1


def maximize(fn, gen: Iterator[int], xatol: int, xrtol: float, fatol: int) -> int:
    """
    Returns a `x` that maximizes `fn(x)`, assuming `fn` is a strictly concave function.

    fn:     the objective function
    gen:    generator of the next guesses of x
    xatol:  absoluate tolerance of x
    xrtol:  relative tolerance of x
    fatol:  absoluate tolerance of fn(x)
    """
    memo = (next(gen), next(gen))
    prev_amt_net = 0
    while True:
        amt_net = fn(memo[-1])
        if amt_net > prev_amt_net:
            memo = (memo[-2], memo[-1], next(gen))
            prev_amt_net = amt_net
        else:
            mid = (memo[0]+memo[-1])//2
            end = ((mid-memo[0]) <= xatol or
                   (mid-memo[0])/mid <= xrtol or
                   (prev_amt_net-amt_net) <= fatol)
            if end:
                return mid

            xs = [memo[0], (memo[0]+mid)//2, mid, (mid+memo[-1])//2, memo[-1]]
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
        assert x > 0
        amt_a1 = x
        amt_b = market1.quote(token_in, amt_a1, **market1_kwargs) * -1
        amt_a2 = market2.quote(token_bridge, amt_b, **market2_kwargs) * -1
        return (amt_a2-amt_a1, amt_b, amt_a2)

    """
    Step 1. Test if there is arb opportunity.
    """
    test_amt_in = max(token_in.unit // 10**6, 1000)
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
    to reject any seemingly non-profitable arbs, so we don't waste time handling them later on.
    """
    GAS_PER_ARB = 200_000
    gas_cost_wei = GAS_PER_ARB * gas_price
    if token_in.address == ETH_ADDRESS:
        gas_cost = gas_cost_wei
    elif token_in.address == USDC_ADDRESS:
        gas_cost = gas_cost_wei * 2000 * 10**6 // 10**18  # treat 2000 usdc -> 1 eth
    else:
        raise NotImplementedError()

    profit = amt_net - gas_cost
    if profit <= 0:
        raise EvaluationFailure(f'Negative profit: {profit} ({amt_in} -> {amt_bridge} -> {amt_out})')

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
