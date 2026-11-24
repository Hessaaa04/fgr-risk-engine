"""Month arithmetic on 'YYYY-MM' strings (the engine's unit of time)."""

from __future__ import annotations

import calendar as _cal


def ym_add(ym: str, k: int) -> str:
    """Shift a 'YYYY-MM' month by k months."""
    y, m = int(ym[:4]), int(ym[5:7]) - 1 + k
    y += m // 12
    m %= 12
    return f"{y}-{m + 1:02d}"


def ym_range(a: str, b: str) -> list[str]:
    """All months from a to b inclusive."""
    out, m = [], a
    while m <= b:
        out.append(m)
        m = ym_add(m, 1)
    return out


def month_end(ym: str) -> str:
    """Last calendar day of the month, as 'YYYY-MM-DD'."""
    y, m = int(ym[:4]), int(ym[5:7])
    return f"{ym}-{_cal.monthrange(y, m)[1]:02d}"


def month_open(ym: str, today: str) -> bool:
    """A month is still open through its last day; it counts from the day after."""
    return month_end(ym) >= today
