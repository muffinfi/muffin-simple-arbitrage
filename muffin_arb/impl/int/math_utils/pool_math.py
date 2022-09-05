from .basic_math import *


def div(a: int, b: int, round_up: bool) -> int:
    if round_up:
        return ceil_div(a, b)
    return floor_div(a, b)


def calc_amt0_from_sqrt_p(sqrt_p0: int, sqrt_p1: int, liquidity: int) -> int:
    """
    Δx = L (√P0 - √P1) / (√P0 √P1)
    """
    price_up = sqrt_p1 > sqrt_p0
    if price_up:
        sqrt_p0, sqrt_p1 = sqrt_p1, sqrt_p0
    amt0 = div(
        liquidity * (sqrt_p0 - sqrt_p1) * Q72,
        sqrt_p0 * sqrt_p1,
        round_up=not price_up
    )
    if price_up:
        amt0 *= -1
    return amt0


def calc_amt1_from_sqrt_p(sqrt_p0: int, sqrt_p1: int, liquidity: int) -> int:
    """
    Δy = L (√P0 - √P1)
    """
    price_down = sqrt_p1 < sqrt_p0
    if price_down:
        sqrt_p0, sqrt_p1 = sqrt_p1, sqrt_p0
    amt1 = div(
        liquidity * (sqrt_p1 - sqrt_p0),
        Q72,
        round_up=not price_down
    )
    if price_down:
        amt1 *= -1
    return amt1


def calc_sqrt_p_from_amt(is_token0: bool, sqrt_p0: int, liquidity: int, amt: int) -> int:
    if is_token0:
        if abs(amt) * sqrt_p0 >= (1 << 256):
            return ceil_div(liquidity * Q72, floor_div(liquidity * Q72, sqrt_p0) + amt)
        else:
            return ceil_div(liquidity * sqrt_p0 * Q72, (liquidity * Q72) + (amt * sqrt_p0))
    else:
        if amt >= 0:
            return sqrt_p0 + floor_div(amt * Q72, liquidity)
        else:
            return sqrt_p0 - ceil_div(abs(amt) * Q72, liquidity)
