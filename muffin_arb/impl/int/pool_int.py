from typing import Callable

import numpy as np
from muffin_arb.impl.int.math_utils import (MAX_TICK, MIN_TICK,
                                            calc_tier_amounts_in,
                                            calc_tier_amounts_out,
                                            compute_step, floor_div)


class Pool:
    """
    Muffin's swap logic implementation mirrored in python.
    """

    liquiditys:             np.ndarray
    sqrt_prices:            np.ndarray
    sqrt_gammas:            np.ndarray
    next_ticks_below:       np.ndarray
    next_ticks_above:       np.ndarray
    get_tick_data:          Callable[[int, int], tuple[int, int, int]]  # (tier_id, tick_index) -> (liquidity_delta, next_below, next_above) # nopep8

    def __init__(
        self,
        liquiditys: np.ndarray,
        sqrt_prices: np.ndarray,
        sqrt_gammas: np.ndarray,
        next_ticks_below: np.ndarray,
        next_ticks_above: np.ndarray,
        get_tick_data: Callable[[int, int], tuple[int, int, int]],
    ):
        # Recreate arrays to ensure correct type and prevent changing the source
        self.liquiditys = np.array(liquiditys, dtype=np.object_)
        self.sqrt_prices = np.array(sqrt_prices, dtype=np.object_)
        self.sqrt_gammas = np.array(sqrt_gammas, dtype=np.object_)
        self.next_ticks_below = np.array(next_ticks_below, dtype=np.int_)
        self.next_ticks_above = np.array(next_ticks_above, dtype=np.int_)
        self.get_tick_data = get_tick_data
        self.size = len(self.liquiditys)

    def swap(self, is_token0: bool, amount_desired: int, tier_choices: np.ndarray):
        # copy to prevent changing it directly
        tier_choices = tier_choices.copy()

        is_exact_in = amount_desired > 0
        is_token0_in = is_token0 == (amount_desired > 0)
        next_ticks = self.next_ticks_below if is_token0_in else self.next_ticks_above

        # return data
        res_amt_a = 0
        res_amt_b = 0
        res_fee_amt = 0
        res_amts_a = np.zeros(self.size, dtype=np.object_)
        res_amts_b = np.zeros(self.size, dtype=np.object_)
        res_fee_amts = np.zeros(self.size, dtype=np.object_)
        res_fee_growths = np.zeros(self.size, dtype=np.object_)
        res_step_count = 0

        while True:
            res_step_count += 1

            # compute amount for each tier
            if is_exact_in:
                (amts, enabled) = calc_tier_amounts_in(
                    is_token0,
                    amount_desired - res_amt_a,
                    tier_choices,
                    self.sqrt_gammas,
                    self.sqrt_prices,
                    self.liquiditys,
                )
            else:
                (amts, enabled) = calc_tier_amounts_out(
                    is_token0,
                    amount_desired - res_amt_a,
                    tier_choices,
                    self.sqrt_gammas,
                    self.sqrt_prices,
                    self.liquiditys,
                )

            # ------------------------------------------------
            # compute step
            is_cross = np.full(self.size, False)
            amts_a = np.zeros(self.size, dtype=np.object_)
            amts_b = np.zeros(self.size, dtype=np.object_)
            sqrt_prices_new = np.zeros(self.size, dtype=np.object_)
            fee_amts = np.zeros(self.size, dtype=np.object_)

            for i in np.arange(self.size)[enabled]:
                (enabled[i], is_cross[i], amts_a[i], amts_b[i], sqrt_prices_new[i], fee_amts[i]) = compute_step(
                    is_token0,
                    is_exact_in,
                    amts[i],
                    self.sqrt_gammas[i],
                    self.sqrt_prices[i],
                    self.liquiditys[i],
                    next_ticks[i],
                )

            # ------------------------------------------------

            # update local result
            res_amt_a += np.sum(amts_a)
            res_amt_b += np.sum(amts_b)
            res_fee_amt += np.sum(fee_amts)
            res_amts_a += amts_a
            res_amts_b += amts_b
            res_fee_amts += fee_amts
            res_fee_growths += floor_div(fee_amts * 2**64, self.liquiditys)

            # update sqrt price state # NOTE: effect
            self.sqrt_prices[enabled] = sqrt_prices_new[enabled]

            # handle cross tick
            for i in np.nonzero(is_cross)[0]:
                t_cross = next_ticks[i]  # type: int

                # reject tier and skip crossing tick if reached the last tick
                if t_cross == MIN_TICK or t_cross == MAX_TICK:
                    tier_choices[i] = False
                    continue

                # fetch next tick data
                (liquidity_delta, next_below, next_above) = self.get_tick_data(int(i), int(t_cross))

                # update current liquidity and next_ticks # NOTE: effect
                if is_token0_in:
                    self.liquiditys[i] += -liquidity_delta
                    self.next_ticks_below[i] = next_below
                    self.next_ticks_above[i] = t_cross
                else:
                    self.liquiditys[i] += liquidity_delta
                    self.next_ticks_above[i] = next_above
                    self.next_ticks_below[i] = t_cross

            # stopping criterion
            SWAP_AMOUNT_TOLERANCE = 100
            if not np.any(tier_choices) or (
                amount_desired - res_amt_a <= SWAP_AMOUNT_TOLERANCE if is_exact_in else
                amount_desired - res_amt_a >= -SWAP_AMOUNT_TOLERANCE
            ):
                break

        return (
            res_amt_a,
            res_amt_b,
            res_fee_amt,
            res_amts_a,
            res_amts_b,
            res_fee_amts,
            res_fee_growths,
            res_step_count,
            self.sqrt_prices.copy(),
            self.liquiditys.copy(),
            self.next_ticks_below.copy(),
            self.next_ticks_above.copy(),
        )

    def quote(self, is_token0: bool, amount_desired: int, tier_choices: np.ndarray):
        _liquiditys = self.liquiditys
        _sqrt_prices = self.sqrt_prices
        _next_ticks_below = self.next_ticks_below
        _next_ticks_above = self.next_ticks_above

        self.liquiditys = _liquiditys.copy()
        self.sqrt_prices = _sqrt_prices.copy()
        self.next_ticks_below = _next_ticks_below.copy()
        self.next_ticks_above = _next_ticks_above.copy()

        results = self.swap(is_token0, amount_desired, tier_choices)

        self.liquiditys = _liquiditys
        self.sqrt_prices = _sqrt_prices
        self.next_ticks_below = _next_ticks_below
        self.next_ticks_above = _next_ticks_above

        return results
