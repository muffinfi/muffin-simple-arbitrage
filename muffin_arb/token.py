from __future__ import annotations
from dataclasses import dataclass
from multicall import Call, Multicall
from muffin_arb.settings import w3


TOKEN_CACHE: dict[str, Token] = {}


def get_tokens(addresses: list[str]) -> dict[str, Token]:
    result: dict[str, Token] = {}

    new_addrs: list[str] = []
    for addr in addresses:
        if addr in TOKEN_CACHE:
            result[addr] = TOKEN_CACHE[addr]
        else:
            new_addrs.append(addr)

    if new_addrs:
        calls: list[Call] = []

        for addr in new_addrs:
            calls.extend([
                Call(addr, ['decimals()(uint8)'], [(f'{addr}::decimals', lambda x: x)]),
                Call(addr, ['symbol()(string)'], [(f'{addr}::symbol', lambda x: x)]),
            ])

        data = Multicall(calls, _w3=w3)()
        for addr in addresses:
            symbol = data[f'{addr}::symbol']
            decimals = data[f'{addr}::decimals']
            assert symbol is not None and decimals, 'Token not found: {addr} {symbol} {decimals}'
            TOKEN_CACHE[addr] = result[addr] = Token(addr, symbol, decimals)

    return result


@dataclass
class Token:
    address:    str
    symbol:     str
    decimals:   int

    @staticmethod
    def sort(token_a: Token, token_b: Token):
        return (token_a, token_b) if token_a.address.lower() < token_b.address.lower() else (token_b, token_a)

    @staticmethod
    def get(address: str) -> Token:
        return get_tokens([address])[address]

    @staticmethod
    def from_addresses(addresses: list[str]) -> dict[str, Token]:
        return get_tokens(addresses)

    @property
    def unit(self) -> int:
        return 10**self.decimals

    def format_raw_amount(self, amt: int):
        return f'{(amt / self.unit):<8.6g} {self.symbol:<4}'
