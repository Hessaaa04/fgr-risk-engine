"""In-memory data structures the calculations work on.

These mirror the four data domains the engine needs for risk work:
holdings (with their sleeve and liquidity), monthly values and returns per
holding, and market series (factors, benchmarks, indices, signals).
Missing data is always None, never zero.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


def norm(s: object) -> str:
    """Name key used for matching: lower case, letters and digits only."""
    return re.sub(r"[^a-z0-9]+", "", str(s or "").lower())


@dataclass
class Observation:
    """One holding in one month. val = month-end value; ret = return over the month."""

    val: float | None
    ret: float | None


@dataclass
class Holding:
    name: str
    sleeve: str
    liquid: bool
    data: dict[str, Observation] = field(default_factory=dict)


@dataclass
class Series:
    """A market series. kind 'return' holds monthly returns; signals hold levels."""

    name: str
    type: str  # 'factor' | 'benchmark' | 'index' | 'signal' | 'holding'
    ticker: str = ""
    ret: dict[str, float] = field(default_factory=dict)
    lvl: dict[str, float] = field(default_factory=dict)


@dataclass
class Dataset:
    holdings: list[Holding]
    sleeves: list[str]
    months: list[str]
    has_return: dict[str, bool]
    series: dict[str, Series] = field(default_factory=dict)  # keyed by norm(name), insertion order kept
    sleeve_returns: dict[str, dict[str, float | None]] = field(default_factory=dict)  # reported, optional
    total_returns: dict[str, float | None] = field(default_factory=dict)  # reported, optional

    def find_series(self, name: str | None) -> Series | None:
        return self.series.get(norm(name)) if name else None

    def series_of(self, *types: str) -> list[Series]:
        return [s for s in self.series.values() if s.type in types]
