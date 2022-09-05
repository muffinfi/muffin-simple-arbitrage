import numpy as np
from numba import njit


E5 = 10. ** 5
E10 = 10. ** 10
Q72 = 2. ** 72

MIN_TICK = -776363
MAX_TICK = 776363


@njit(cache=True, fastmath=True)
def tick_to_sqrt_price(tick):
    return np.sqrt(1.0001 ** tick) * Q72


# @njit(cache=True, fastmath=True)
# def sqrt_price_to_tick(sqrt_price: float):
#     tick = np.floor(np.log((sqrt_price / 2**72)**2) / np.log(1.0001))
#     assert tick_to_sqrt_price(tick) <= sqrt_price
#     return int(tick)


# -----

@njit(cache=True, fastmath=True)
def calc_amt0_from_sqrt_p(sqrt_p0: float, sqrt_p1: float, liquidity: float) -> float:
    """
    Δx = L (√P0 - √P1) / (√P0 √P1)
    """
    return liquidity * (sqrt_p0 - sqrt_p1) * Q72 / (sqrt_p0 * sqrt_p1)


@njit(cache=True, fastmath=True)
def calc_amt1_from_sqrt_p(sqrt_p0: float, sqrt_p1: float, liquidity: float) -> float:
    """
    Δy = L (√P0 - √P1)
    """
    return liquidity * (sqrt_p1 - sqrt_p0) / Q72


@njit(cache=True, fastmath=True)
def calc_sqrt_p_from_amt(is_token0: bool, sqrt_p0: float, liquidity: float, amt: float) -> float:
    if is_token0:
        # √P1 = L √P0 / (L + √P0 * Δx)
        return (liquidity * sqrt_p0 * Q72) / ((liquidity * Q72) + (amt * sqrt_p0))
    else:
        # √P1 = √P0 + (Δy / L)
        return sqrt_p0 + ((amt * Q72) / liquidity)


# -----

@njit(cache=True, fastmath=True)
def calc_tier_amounts_in(
    is_token0: bool,
    amount: float,
    tier_choices: np.ndarray,
    sqrt_gammas: np.ndarray,
    sqrt_prices: np.ndarray,
    liquiditys: np.ndarray,
):
    assert amount > 0

    # lsg: array of liquidity divided by sqrt_gamma
    # res: array of token reserve divided by gamma
    lsg = liquiditys * E5 / sqrt_gammas
    res = ((liquiditys * Q72 * E10) / (sqrt_prices * sqrt_gammas**2) if is_token0 else
           (liquiditys * sqrt_prices) / (Q72 * sqrt_gammas**2 / E10))

    # mask: array of boolean of whether the tier will be used
    # amts: array of input amount routed to each tier
    mask = tier_choices.copy()
    amts = np.zeros(sqrt_gammas.size, dtype=np.float64)

    # calculate input amts, then reject the tiers with negative input amts.
    # repeat until all input amts are non-negative
    while True:
        lambda_num = np.sum(lsg[mask])
        lambda_denom = np.sum(res[mask]) + amount
        amts[mask] = (lsg[mask] * lambda_denom / lambda_num) - res[mask]
        if np.all(amts[mask] >= 0):
            amts[~mask] = 0
            break
        mask &= (amts >= 0)
    return amts, mask


@njit(cache=True, fastmath=True)
def calc_tier_amounts_out(
    is_token0: bool,
    amount: float,
    tier_choices: np.ndarray,
    sqrt_gammas: np.ndarray,
    sqrt_prices: np.ndarray,
    liquiditys: np.ndarray,
):
    assert amount < 0

    # lsg: array of liquidity divided by sqrt_gamma
    # res: array of token reserve
    lsg = liquiditys * E5 / sqrt_gammas
    res = (liquiditys * Q72 / sqrt_prices if is_token0 else
           liquiditys * sqrt_prices / Q72)

    # mask: array of boolean of whether the tier will be used
    # amts: array of input amount routed to each tier
    mask = tier_choices.copy()
    amts = np.zeros(sqrt_gammas.size, dtype=np.float64)

    # calculate input amts, then reject the tiers with negative input amts.
    # repeat until all input amts are non-negative
    while True:
        lambda_num = np.sum(lsg[mask])
        lambda_denom = np.sum(res[mask]) + amount
        amts[mask] = (lsg[mask] * lambda_denom / lambda_num) - res[mask]
        if np.all(amts[mask] <= 0):
            amts[~mask] = 0
            break
        mask &= (amts <= 0)
    return amts, mask


@njit(cache=True, fastmath=True)
def compute_step(
    is_token0: bool,
    is_exact_in: bool,
    amount: float,
    sqrt_gamma: float,
    sqrt_p: float,
    liquidity: float,
    next_tick: int,
):
    amt_a = amount

    # calculate tick's sqrt price
    sqrt_p_tick = tick_to_sqrt_price(next_tick)

    # calculate amt needed to reach to the tick
    amt_tick = (calc_amt0_from_sqrt_p(sqrt_p, sqrt_p_tick, liquidity) if is_token0 else
                calc_amt1_from_sqrt_p(sqrt_p, sqrt_p_tick, liquidity))

    # calculate percentage fee (precision: 1e10)
    gamma = sqrt_gamma ** 2

    if is_exact_in:
        # amtA: the input amt (positive)
        # amtB: the output amt (negative)

        # calculate input amt excluding fee
        amt_in_excl_fee = amt_a * gamma / E10

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
            amt_a = amt_in_excl_fee * E10 / gamma

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
        amt_b = amt_in_excl_fee * E10 / gamma

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
        allowed,    # boolean
        is_cross,   # boolean
        amt_a,      # float64
        amt_b,      # float64
        sqrt_p_new,  # float64
        fee_amt,    # float64
    )
