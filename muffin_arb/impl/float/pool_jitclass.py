import numpy as np
from numba import prange, types
from numba.experimental import jitclass
from muffin_arb.impl.float.math_utils import MAX_TICK, MIN_TICK, calc_tier_amounts_in, calc_tier_amounts_out, compute_step


"""
## How to use?

```
ticks_type = types.DictType(types.int64, types.DictType(types.int64, types.UniTuple(types.float64, 3)))
ticks = typed.Dict(dcttype=ticks_type)


# initialize a tick dict for each tier
for tier_id in range(3):
    ticks[tier_id] = typed.Dict(dcttype=ticks_type.value_type)


# define tick data for each tick in each tier
for tier_id in range(3):
    ticks[tier_id][MIN_TICK] = (+25600., MIN_TICK, MAX_TICK)  # (liquidity_delta, next_tick_below, next_tick_upper)
    ticks[tier_id][MAX_TICK] = (-25600., MIN_TICK, MAX_TICK)  # (liquidity_delta, next_tick_below, next_tick_upper)


pool = Pool(
    liquiditys=         np.array([25600, 25600, 25600],             dtype=np.float64),
    sqrt_prices=        np.array([2**72, 2**72, 2**72],             dtype=np.float64),
    sqrt_gammas=        np.array([99850, 99900, 99950],             dtype=np.float64),
    next_ticks_below=   np.array([MIN_TICK, MIN_TICK, MIN_TICK],    dtype=np.int64),
    next_ticks_above=   np.array([MAX_TICK, MAX_TICK, MAX_TICK],    dtype=np.int64),
    ticks=              ticks,
)

pool.quote(True, 10000000, np.array([True, True, True]))
```
"""


@jitclass([
    ('liquiditys',          types.float64[:]),
    ('sqrt_prices',         types.float64[:]),
    ('sqrt_gammas',         types.float64[:]),
    ('next_ticks_below',    types.int64[:]),
    ('next_ticks_above',    types.int64[:]),
    ('ticks',               types.DictType(types.int64, types.DictType(types.int64, types.UniTuple(types.float64, 3)))),
])
class Pool:
    liquiditys:             np.ndarray
    sqrt_prices:            np.ndarray
    sqrt_gammas:            np.ndarray
    next_ticks_below:       np.ndarray
    next_ticks_above:       np.ndarray
    ticks:                  dict[int, dict[int, tuple[float, float, float]]]

    def __init__(
        self,
        liquiditys: np.ndarray,
        sqrt_prices: np.ndarray,
        sqrt_gammas: np.ndarray,
        next_ticks_below: np.ndarray,
        next_ticks_above: np.ndarray,
        ticks,
    ):
        self.liquiditys = liquiditys
        self.sqrt_prices = sqrt_prices
        self.sqrt_gammas = sqrt_gammas
        self.next_ticks_below = next_ticks_below
        self.next_ticks_above = next_ticks_above
        self.ticks = ticks

    @property
    def size(self):
        return len(self.liquiditys)

    def get_tick(self, tier_id: int, tick: int):
        return self.ticks[tier_id][tick]

    def swap(self, is_token0: bool, amount_desired: float, tier_choices: np.ndarray):
        # copy to prevent changing it directly
        tier_choices = tier_choices.copy()

        is_exact_in = amount_desired > 0
        is_token0_in = is_token0 == (amount_desired > 0)
        next_ticks = self.next_ticks_below if is_token0_in else self.next_ticks_above

        # return data
        res_amt_a = 0
        res_amt_b = 0
        res_fee_amt = 0
        res_amts_a = np.zeros(self.size, dtype=np.float64)
        res_amts_b = np.zeros(self.size, dtype=np.float64)
        res_fee_amts = np.zeros(self.size, dtype=np.float64)
        res_fee_growths = np.zeros(self.size, dtype=np.float64)
        res_step_count = 0

        last_step_amt_a = None

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
                    self.liquiditys
                )

            # ------------------------------------------------
            # compute step
            is_cross = np.full(self.size, False)
            amts_a = np.full(self.size, 0.)
            amts_b = np.full(self.size, 0.)
            sqrt_prices_new = np.full(self.size, 0.)
            fee_amts = np.full(self.size, 0.)

            for i in prange(self.size):
                if not enabled[i]:
                    continue
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
            res_fee_growths += (fee_amts * 2.**64) / self.liquiditys

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
                (liquidity_delta, next_below, next_above) = self.ticks[int(i)][int(t_cross)]

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

            # since it is a float version, if remaining amount is too small, it stucks forever
            step_amt_a = np.sum(amts_a)
            amt_remaining_pct = (amount_desired - res_amt_a) / amount_desired
            if step_amt_a == last_step_amt_a and (step_amt_a == 0 or amt_remaining_pct < 1e-7):
                break
            last_step_amt_a = step_amt_a

            if res_step_count > 100:
                raise Exception(f'Too many steps: {[step_amt_a, amt_remaining_pct]}')

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
