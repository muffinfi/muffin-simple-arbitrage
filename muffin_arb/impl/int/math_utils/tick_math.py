import numpy as np

__all__ = [
    'MIN_TICK',
    'MAX_TICK',
    'tick_to_sqrt_price',
    'sqrt_price_to_tick',
]


MIN_TICK = -776363
MAX_TICK = 776363
NFRAC = 72


def _tick_to_sqrt_p(tick: int) -> int:
    assert MIN_TICK <= tick <= MAX_TICK
    x = abs(tick)
    r = 1 << 128
    if x & 0x1 > 0:
        r = (r * 0xFFFCB933BD6FAD37AA2D162D1A594001) >> 128     # [0]
    if x & 0x2 > 0:
        r = (r * 0xFFF97272373D413259A46990580E213A) >> 128     # [1]
    if x & 0x4 > 0:
        r = (r * 0xFFF2E50F5F656932EF12357CF3C7FDCC) >> 128     # [2]
    if x & 0x8 > 0:
        r = (r * 0xFFE5CACA7E10E4E61C3624EAA0941CD0) >> 128     # [3]
    if x & 0x10 > 0:
        r = (r * 0xFFCB9843D60F6159C9DB58835C926644) >> 128     # [4]
    if x & 0x20 > 0:
        r = (r * 0xFF973B41FA98C081472E6896DFB254C0) >> 128     # [5]
    if x & 0x40 > 0:
        r = (r * 0xFF2EA16466C96A3843EC78B326B52861) >> 128     # [6]
    if x & 0x80 > 0:
        r = (r * 0xFE5DEE046A99A2A811C461F1969C3053) >> 128     # [7]
    if x & 0x100 > 0:
        r = (r * 0xFCBE86C7900A88AEDCFFC83B479AA3A4) >> 128     # [8]
    if x & 0x200 > 0:
        r = (r * 0xF987A7253AC413176F2B074CF7815E54) >> 128     # [9]
    if x & 0x400 > 0:
        r = (r * 0xF3392B0822B70005940C7A398E4B70F3) >> 128     # [10]
    if x & 0x800 > 0:
        r = (r * 0xE7159475A2C29B7443B29C7FA6E889D9) >> 128     # [11]
    if x & 0x1000 > 0:
        r = (r * 0xD097F3BDFD2022B8845AD8F792AA5825) >> 128     # [12]
    if x & 0x2000 > 0:
        r = (r * 0xA9F746462D870FDF8A65DC1F90E061E5) >> 128     # [13]
    if x & 0x4000 > 0:
        r = (r * 0x70D869A156D2A1B890BB3DF62BAF32F7) >> 128     # [14]
    if x & 0x8000 > 0:
        r = (r * 0x31BE135F97D08FD981231505542FCFA6) >> 128     # [15]
    if x & 0x10000 > 0:
        r = (r * 0x9AA508B5B7A84E1C677DE54F3E99BC9) >> 128      # [16]
    if x & 0x20000 > 0:
        r = (r * 0x5D6AF8DEDB81196699C329225EE604) >> 128       # [17]
    if x & 0x40000 > 0:
        r = (r * 0x2216E584F5FA1EA926041BEDFE98) >> 128         # [18]
    if x & 0x80000 > 0:
        r = (r * 0x48A170391F7DC42444E8FA2) >> 128              # [19]

    if tick >= 0:
        r = (2**256 - 1) // r  # type: int

    nshift = 128 - NFRAC
    return (r >> nshift) + int((r % (1 << nshift)) > 0)


def _sqrt_p_to_tick(sqrt_p: int):
    assert 0 < sqrt_p <= 2**128 - 1
    x = sqrt_p

    msb = 0
    xc = sqrt_p
    if xc >= 0x10000000000000000:
        xc >>= 64
        msb += 64
    if xc >= 0x100000000:
        xc >>= 32
        msb += 32
    if xc >= 0x10000:
        xc >>= 16
        msb += 16
    if xc >= 0x100:
        xc >>= 8
        msb += 8
    if xc >= 0x10:
        xc >>= 4
        msb += 4
    if xc >= 0x4:
        xc >>= 2
        msb += 2
    if xc >= 0x2:
        xc >>= 1
        msb += 1

    res = (msb - NFRAC) << 64
    y = x << (127 - msb)

    for i in range(63, 45, -1):
        y = (y * y) >> 127
        if y >= (1 << 128):
            y >>= 1
            res |= (1 << i)

    res *= 255738958999603826347141
    tick_upper = (res + 17996007701288367970265332090599899137) >> 128
    tick_lower = (res - 98577143636729737466164032634120830977 if res < (-676363 << 128) else
                  res - 527810000259722480933883300202676225 if res < (-476363 << 128) else
                  res) >> 128

    if tick_upper == tick_lower:
        return tick_upper
    if sqrt_p >= _tick_to_sqrt_p(tick_upper):
        return tick_upper
    return tick_lower


tick_to_sqrt_price = np.vectorize(_tick_to_sqrt_p, otypes=[np.object_])
sqrt_price_to_tick = np.vectorize(_sqrt_p_to_tick, otypes=[np.object_])
