from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .scorer import Bar, parse_ts


@dataclass(frozen=True)
class PriceSeries:
    symbol: str
    bars: list[Bar]

    def between(self, start: datetime, end: datetime) -> "PriceSeries":
        start_utc = parse_ts(start)
        end_utc = parse_ts(end)
        return PriceSeries(self.symbol, [bar for bar in self.bars if start_utc <= bar.ts <= end_utc])

    def before_or_at(self, ts: datetime) -> list[Bar]:
        cutoff = parse_ts(ts)
        return [bar for bar in self.bars if bar.ts <= cutoff]


def load_ohlc_csv(path: str | Path, *, symbol: str | None = None) -> PriceSeries:
    rows: list[dict[str, str]]
    with Path(path).open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise ValueError("empty OHLC CSV")

    resolved_symbol = symbol or rows[0].get("symbol") or Path(path).stem.upper()
    bars = [
        Bar(
            ts=parse_ts(row.get("ts") or row.get("timestamp") or row.get("time") or ""),
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
        )
        for row in rows
    ]
    return PriceSeries(str(resolved_symbol).upper(), sorted(bars, key=lambda bar: bar.ts))


def rolling_sma(values: list[float], window: int) -> list[float | None]:
    output: list[float | None] = []
    total = 0.0
    for idx, value in enumerate(values):
        total += value
        if idx >= window:
            total -= values[idx - window]
        output.append(total / window if idx + 1 >= window else None)
    return output


def rsi(values: list[float], period: int) -> list[float | None]:
    if period <= 0:
        raise ValueError("period must be positive")
    output: list[float | None] = [None]
    gains: list[float] = []
    losses: list[float] = []
    for idx in range(1, len(values)):
        change = values[idx] - values[idx - 1]
        gains.append(max(change, 0.0))
        losses.append(abs(min(change, 0.0)))
        if len(gains) > period:
            gains.pop(0)
            losses.pop(0)
        if len(gains) < period:
            output.append(None)
            continue
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        if avg_loss == 0:
            output.append(100.0)
        else:
            rs = avg_gain / avg_loss
            output.append(100.0 - (100.0 / (1.0 + rs)))
    return output


def closes(bars: Iterable[Bar]) -> list[float]:
    return [bar.close for bar in bars]
