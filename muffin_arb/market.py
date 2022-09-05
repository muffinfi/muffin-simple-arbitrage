from __future__ import annotations
from collections import defaultdict
from typing import Optional
import numpy as np
from eth_abi.abi import encode_abi
from eth_abi.packed import encode_abi_packed
from hexbytes import HexBytes
from multicall import Call, Multicall
from web3 import Web3
from muffin_arb.impl import PoolImplInt
from muffin_arb.settings import HUB_ADDRESS, UNISWAP_V2_FACTORY_ADDRESS, hub_contract, w3
from muffin_arb.token import Token


class Market:
    """
    An abstract class for a token exchange market
    """

    def quote(self, token: Token, amt_desired: int, **kwargs) -> int:
        """
        token:          The token that `amt_desired` refers to.
        amt_desired:    The desired change in the token balance of the market.
                        Positive means an input to the market; negative means an output from the market.

        Returns the amount delta of the other token required for the desired token amount change.
        """
        raise NotImplementedError()


# ****************************************************************************


class MuffinPool(Market):
    pool_id:    HexBytes
    token0:     Token
    token1:     Token
    impl:       PoolImplInt
    tier_count: int

    @staticmethod
    def compute_pool_id(token0_addr: str, token1_addr: str) -> HexBytes:
        return Web3.keccak(encode_abi(['address', 'address'], [token0_addr, token1_addr]))

    @classmethod
    def from_pairs(cls, pairs: list[tuple[Token, Token]]) -> list[Optional[MuffinPool]]:
        """
        Fetch tier data of the given token pairs, then return a list of MuffinPool
        """
        def to_call(index: int, pair: tuple[Token, Token]):
            def to_pool(tier_data):
                if not tier_data:
                    return None
                (liquiditys, sqrt_prices, sqrt_gammas, _, next_ticks_below,
                 next_ticks_above, _, _) = np.array(tier_data, dtype=np.object_).T
                return cls(
                    token0=pair[0],
                    token1=pair[1],
                    liquiditys=liquiditys,
                    sqrt_prices=sqrt_prices,
                    sqrt_gammas=sqrt_gammas,
                    next_ticks_below=next_ticks_below,
                    next_ticks_above=next_ticks_above
                )
            pool_id = cls.compute_pool_id(pair[0].address, pair[1].address)
            SIG = 'getAllTiers(bytes32)((uint128,uint128,uint24,int24,int24,int24,uint80,uint80)[])'
            return Call(HUB_ADDRESS, [SIG, pool_id], [(index, to_pool)])  # type: ignore

        calls = [to_call(i, pair) for i, pair in enumerate(pairs)]
        data = Multicall(calls, _w3=w3)()
        return list(dict(sorted(data.items())).values())

    def __init__(
        self,
        token0:             Token,
        token1:             Token,
        liquiditys:         np.ndarray,
        sqrt_prices:        np.ndarray,
        sqrt_gammas:        np.ndarray,
        next_ticks_below:   np.ndarray,
        next_ticks_above:   np.ndarray,
    ):
        self.token0 = token0
        self.token1 = token1
        self.pool_id = self.compute_pool_id(token0.address, token1.address)
        self.impl = PoolImplInt(
            liquiditys,
            sqrt_prices,
            sqrt_gammas,
            next_ticks_below,
            next_ticks_above,
            self._get_tick_data,
        )
        self.tick_cache = defaultdict(lambda: defaultdict(tuple))
        self.tier_count = len(sqrt_gammas)

    def _get_tick_data(self, tier_id: int, tick: int) -> tuple[int, int, int]:
        """
        Return a tuple of (liquidity_delta, next_tick_below, next_tick_above) of the requested tick
        """
        cached = self.tick_cache[tier_id][tick]
        if not cached:
            data = hub_contract.functions.getTick(self.pool_id, tier_id, tick).call()
            liquidity_delta = (data[0] - data[1]) << 8
            next_tick_below = data[2]
            next_tick_above = data[3]
            self.tick_cache[tier_id][tick] = cached = (liquidity_delta, next_tick_below, next_tick_above)
        return cached

    def quote(self, token: Token, amt_desired: int, tier_choices: Optional[np.ndarray] = None, **kwargs) -> int:
        if tier_choices is None:
            tier_choices = np.full(self.tier_count, True)
        res = self.impl.quote(token == self.token0, amt_desired, tier_choices)
        return res[1]


# ****************************************************************************


class UniV2Pool(Market):
    address:    str
    token0:     Token
    token1:     Token
    reserve0:   int
    reserve1:   int

    @staticmethod
    def compute_pool_address(token0_addr: str, token1_addr: str, init_code_hash='96e8ac4277198ff8b6f785478aa9a39f403cb768dd02cbee326c3e7da348845f') -> str:
        salt = Web3.keccak(encode_abi_packed(['address', 'address'], [token0_addr, token1_addr]))
        encoded = Web3.keccak(encode_abi_packed(
            ['bytes1', 'address', 'bytes32', 'bytes'],
            [b'\xff', UNISWAP_V2_FACTORY_ADDRESS, salt, bytearray.fromhex(init_code_hash)]
        ))
        return Web3.toChecksumAddress(encoded[12:].hex())

    @classmethod
    def from_pairs(cls, pairs: list[tuple[Token, Token]]) -> list[Optional[UniV2Pool]]:
        """
        Fetch pool reserves of the given token pairs, then return a list of UniV2Pool
        """
        def to_call(index: int, pair: tuple[Token, Token]):
            pool_addr = cls.compute_pool_address(pair[0].address, pair[1].address)
            to_pool = lambda data: cls(pair[0], pair[1], data[0], data[1]) if data else None
            return Call(pool_addr, ['getReserves()((uint112,uint112,uint32))'], [(index, to_pool)])  # type: ignore

        calls = [to_call(i, pair) for i, pair in enumerate(pairs)]
        data = Multicall(calls, _w3=w3)()
        return list(dict(sorted(data.items())).values())

    def __init__(self, token0: Token, token1: Token, reserve0: int, reserve1: int):
        self.address = self.compute_pool_address(token0.address, token1.address)
        self.token0 = token0
        self.token1 = token1
        self.reserve0 = reserve0
        self.reserve1 = reserve1

    def quote(self, token: Token, amt_desired: int, **kwargs) -> int:
        res_in, res_out = (
            (self.reserve0, self.reserve1) if (token == self.token0) == (amt_desired > 0) else
            (self.reserve1, self.reserve0)
        )
        if amt_desired > 0:
            amt_in_with_fee = amt_desired * 997
            amt_out = (amt_in_with_fee * res_out) // (res_in * 1000 + amt_in_with_fee)
            return -amt_out
        else:
            amt_out = -amt_desired
            amt_in = ((res_in * amt_out * 1000) // ((res_out - amt_out) * 997)) + 1
            return amt_in

    """
    For logging
    """

    def price(self) -> float:
        return (self.reserve1/self.token1.unit) / (self.reserve0/self.token0.unit)

    def price_after(self, token: Token, amt_desired: int, **kwargs) -> float:
        amt_b = self.quote(token, amt_desired, **kwargs)
        amt_a_float = amt_desired * (0.997 if amt_desired > 0 else 1.0)
        amt_b_float = amt_b * (0.997 if amt_b > 0 else 1.0)
        amt0, amt1 = (amt_a_float, amt_b_float) if token == self.token0 else (amt_b_float, amt_a_float)
        res0, res1 = (self.reserve0 + amt0, self.reserve1 + amt1)
        return (res1/self.token1.unit) / (res0/self.token0.unit)
