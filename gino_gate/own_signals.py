from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .price_data import PriceSeries, closes, rolling_sma, rsi


@dataclass(frozen=True)
class Signal:
    signal_id: str
    source: str
    symbol: str
    side: str
    posted_at: str
    captured_at: str
    posted_price: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "source": self.source,
            "symbol": self.symbol,
            "side": self.side,
            "posted_at": self.posted_at,
            "captured_at": self.captured_at,
            "posted_price": self.posted_price,
        }


def generate_ts_momentum_signals(series: PriceSeries, *, lookback_bars: int = 252, sma_fast: int = 50, sma_slow: int = 200) -> list[dict[str, Any]]:
    bars = series.bars
    close_values = closes(bars)
    fast = rolling_sma(close_values, sma_fast)
    slow = rolling_sma(close_values, sma_slow)
    signals: list[dict[str, Any]] = []
    active = False

    for idx, bar in enumerate(bars):
        if idx < max(lookback_bars, sma_fast, sma_slow):
            continue
        lookback_return = (bar.close - close_values[idx - lookback_bars]) / close_values[idx - lookback_bars]
        in_trend = lookback_return > 0 and slow[idx] is not None and fast[idx] is not None and bar.close > slow[idx] and fast[idx] > slow[idx]
        if in_trend and not active:
            signal = Signal(
                signal_id=f"own-ts-momentum-{series.symbol}-{bar.ts.date().isoformat()}",
                source="own:ts_momentum",
                symbol=series.symbol,
                side="buy",
                posted_at=bar.ts.isoformat().replace("+00:00", "Z"),
                captured_at=bar.ts.isoformat().replace("+00:00", "Z"),
                posted_price=bar.close,
            )
            signals.append(signal.as_dict())
            active = True
        elif not in_trend:
            active = False
    return signals


def generate_rsi2_signals(series: PriceSeries, *, threshold: float = 10.0, sma_slow: int = 200) -> list[dict[str, Any]]:
    bars = series.bars
    close_values = closes(bars)
    slow = rolling_sma(close_values, sma_slow)
    rsi2 = rsi(close_values, 2)
    signals: list[dict[str, Any]] = []

    for idx, bar in enumerate(bars):
        if idx < sma_slow or slow[idx] is None or rsi2[idx] is None:
            continue
        if bar.close > slow[idx] and rsi2[idx] < threshold:
            signal = Signal(
                signal_id=f"own-rsi2-{series.symbol}-{bar.ts.date().isoformat()}",
                source="own:rsi2",
                symbol=series.symbol,
                side="buy",
                posted_at=bar.ts.isoformat().replace("+00:00", "Z"),
                captured_at=bar.ts.isoformat().replace("+00:00", "Z"),
                posted_price=bar.close,
            )
            signals.append(signal.as_dict())
    return signals
