import numpy as np
from .tick_math import tick_to_sqrt_price
from .pool_math import calc_amt0_from_sqrt_p, calc_amt1_from_sqrt_p, calc_sqrt_p_from_amt
from .basic_math import *


def calc_tier_amounts_in(
    is_token0: bool,
    amount: int,
    tier_choices: np.ndarray,
    sqrt_gammas: np.ndarray,
    sqrt_prices: np.ndarray,
    liquiditys: np.ndarray,
):
    assert amount > 0

    # lsg: array of liquidity divided by sqrt_gamma
    # res: array of token reserve divided by gamma
    lsg = ceil_div(liquiditys * E5, sqrt_gammas)
    res = (ceil_div(liquiditys * Q72 * E10, sqrt_prices * sqrt_gammas**2) if is_token0 else
           ceil_div(liquiditys * sqrt_prices, floor_div(Q72 * sqrt_gammas**2, E10)))

    # mask: array of boolean of whether the tier will be used
    # amts: array of input amount routed to each tier
    mask = tier_choices.copy()
    amts = np.zeros(sqrt_gammas.size, dtype=np.object_)  # type: np.ndarray

    # calculate input amts, then reject the tiers with negative input amts.
    # repeat until all input amts are non-negative
    while True:
        lambda_num = np.sum(lsg[mask])
        lambda_denom = np.sum(res[mask]) + amount
        amts[mask] = floor_div(lsg[mask] * lambda_denom, lambda_num) - res[mask]
        if np.all(amts[mask] >= 0):
            amts[~mask] = 0
            break
        mask &= (amts >= 0)
    return amts, mask


def calc_tier_amounts_out(
    is_token0: bool,
    amount: int,
    tier_choices: np.ndarray,
    sqrt_gammas: np.ndarray,
    sqrt_prices: np.ndarray,
    liquiditys: np.ndarray,
):
    assert amount < 0

    # lsg: array of liquidity divided by sqrt_gamma
    # res: array of token reserve
    lsg = floor_div(liquiditys * E5, sqrt_gammas)
    res = (floor_div(liquiditys * Q72, sqrt_prices) if is_token0 else
           floor_div(liquiditys * sqrt_prices, Q72))

    # mask: array of boolean of whether the tier will be used
    # amts: array of input amount routed to each tier
    mask = tier_choices.copy()
    amts = np.zeros(sqrt_gammas.size, dtype=np.object_)  # type: np.ndarray

    # calculate output amts, then reject the tiers with positive input amts.
    # repeat until all input amts are non-positive
    while True:
        lambda_num = np.sum(lsg[mask])
        lambda_denom = np.sum(res[mask]) + amount
        amts[mask] = ceil_div(lsg[mask] * lambda_denom, lambda_num) - res[mask]
        if np.all(amts[mask] <= 0):
            amts[~mask] = 0
            break
        mask &= (amts <= 0)
    return amts, mask


def compute_step(
    is_token0: bool,
    is_exact_in: bool,
    amount: int,
    sqrt_gamma: int,
    sqrt_p: int,
    liquidity: int,
    next_tick: int,
):
    amt_a = amount

    # calculate tick's sqrt price
    sqrt_p_tick = int(tick_to_sqrt_price(next_tick))  # unwrap to scalar int

    # calculate amt needed to reach to the tick
    amt_tick = (calc_amt0_from_sqrt_p(sqrt_p, sqrt_p_tick, liquidity) if is_token0 else
                calc_amt1_from_sqrt_p(sqrt_p, sqrt_p_tick, liquidity))

    # calculate percentage fee (precision: 1e10)
    gamma = sqrt_gamma ** 2

    if is_exact_in:
        # amtA: the input amt (positive)
        # amtB: the output amt (negative)

        # calculate input amt excluding fee
        amt_in_excl_fee = floor_div(amt_a * gamma, E10)

        # check if crossing tick
        is_cross = amt_in_excl_fee >= amt_tick
        if not is_cross:
            # no cross tick: calculate new sqrt price after swap
            sqrt_p_new = (calc_sqrt_p_from_amt(is_token0, sqrt_p, liquidity, amt_in_excl_fee))
        else:
            # cross tick: replace new sqrt price and input amt
            sqrt_p_new = sqrt_p_tick
            amt_in_excl_fee = amt_tick

            # re-calculate input amt _including_ fee
            amt_a = ceil_div(amt_in_excl_fee * E10, gamma)

        # calculate output amt
        amt_b = (calc_amt1_from_sqrt_p(sqrt_p, sqrt_p_new, liquidity) if is_token0 else
                 calc_amt0_from_sqrt_p(sqrt_p, sqrt_p_new, liquidity))

        # calculate fee amt
        fee_amt = amt_a - amt_in_excl_fee

    else:
        # amtA: the output amt (negative)
        # amtB: the input amt (positive)

        # check if crossing tick
        is_cross = amt_a <= amt_tick
        if amt_a > amt_tick:
            # no cross tick: calculate new sqrt price after swap
            sqrt_p_new = (calc_sqrt_p_from_amt(is_token0, sqrt_p, liquidity, amt_a))
        else:
            # cross tick: replace new sqrt price and output amt
            sqrt_p_new = sqrt_p_tick
            amt_a = amt_tick

        # calculate input amt excluding fee
        amt_in_excl_fee = (calc_amt1_from_sqrt_p(sqrt_p, sqrt_p_new, liquidity) if is_token0 else
                           calc_amt0_from_sqrt_p(sqrt_p, sqrt_p_new, liquidity))

        # calculate input amt
        amt_b = ceil_div(amt_in_excl_fee * E10, gamma)

        # calculate fee amt
        fee_amt = amt_b - amt_in_excl_fee

    # reject tier if zero input amt and not crossing tick
    if amt_in_excl_fee == 0 and sqrt_p_new != sqrt_p_tick:
        allowed = False
        is_cross = False
        amt_a = 0
        amt_b = 0
        sqrt_p_new = sqrt_p
        fee_amt = 0
    else:
        allowed = True

    return (
        allowed,
        is_cross,
        amt_a,
        amt_b,
        sqrt_p_new,
        fee_amt,
    )
