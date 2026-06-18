from datetime import datetime, timedelta, timezone

from gino_gate.own_signals import generate_rsi2_signals, generate_ts_momentum_signals
from gino_gate.price_data import PriceSeries, load_ohlc_csv, rsi, rolling_sma
from gino_gate.scorer import Bar


def _bars(count=260):
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    bars = []
    price = 100.0
    for idx in range(count):
        price += 1.0
        bars.append(Bar(start + timedelta(days=idx), price, price + 1, price - 1, price))
    return bars


def test_load_ohlc_csv(tmp_path):
    path = tmp_path / "abc.csv"
    path.write_text("ts,open,high,low,close\n2026-06-18T14:00:00Z,1,2,0.5,1.5\n", encoding="utf-8")
    series = load_ohlc_csv(path, symbol="ABC")
    assert series.symbol == "ABC"
    assert series.bars[0].close == 1.5


def test_rolling_sma_and_rsi():
    assert rolling_sma([1, 2, 3], 2) == [None, 1.5, 2.5]
    values = rsi([3, 2, 1], 2)
    assert values[-1] == 0.0


def test_ts_momentum_generates_signal_on_confirmed_uptrend():
    series = PriceSeries("ABC", _bars())
    signals = generate_ts_momentum_signals(series, lookback_bars=20, sma_fast=5, sma_slow=10)
    assert signals
    assert signals[0]["source"] == "own:ts_momentum"


def test_rsi2_generates_pullback_signal_in_uptrend():
    bars = _bars(220)
    # Create a sharp two-day pullback while still above the long SMA.
    last_ts = bars[-1].ts
    bars.extend([
        Bar(last_ts + timedelta(days=1), 320, 321, 313, 315),
        Bar(last_ts + timedelta(days=2), 315, 316, 310, 312),
    ])
    series = PriceSeries("ABC", bars)
    signals = generate_rsi2_signals(series, threshold=10, sma_slow=20)
    assert signals
    assert signals[-1]["source"] == "own:rsi2"
