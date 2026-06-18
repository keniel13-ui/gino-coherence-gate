from gino_gate.baselines import random_timed_entry_expectancy, spy_buy_hold_same_window
from gino_gate.scoring_policy import ScoringPolicy


def _policy():
    return ScoringPolicy.from_dict({
        "policy_id": "baseline-test",
        "entry_latency_sec": 0,
        "account_equity_usd": 5000,
        "rule_variants": [{"name": "tp10_stop5", "take_profit_pct": 10, "stop_pct": -5, "time_stop_sec": 3600}],
        "sizing_variants": [{"name": "fixed_250", "kind": "fixed_notional", "notional_usd": 250}],
        "fees_model": {"per_trade_usd": 0, "slippage_bps": 0},
    })


def test_spy_buy_hold_same_window():
    record = {"entry": {"ts": "2026-06-18T14:00:00Z", "notional_usd": 250}, "exit": {"ts": "2026-06-18T15:00:00Z"}}
    bars = [
        {"ts": "2026-06-18T14:00:00Z", "open": 100, "high": 101, "low": 99, "close": 100},
        {"ts": "2026-06-18T15:00:00Z", "open": 100, "high": 111, "low": 99, "close": 110},
    ]
    assert spy_buy_hold_same_window(record, bars) == 25


def test_random_timed_entry_expectancy_runs():
    signal = {
        "signal_id": "sig",
        "source": "own:test",
        "symbol": "ABC",
        "side": "buy",
        "posted_at": "2026-06-18T14:00:00Z",
        "captured_at": "2026-06-18T14:00:00Z",
        "posted_price": 100,
    }
    bars = [
        {"ts": "2026-06-18T14:00:00Z", "open": 100, "high": 104, "low": 99, "close": 102},
        {"ts": "2026-06-18T14:30:00Z", "open": 102, "high": 108, "low": 101, "close": 107},
        {"ts": "2026-06-18T15:00:00Z", "open": 107, "high": 112, "low": 106, "close": 111},
    ]
    assert random_timed_entry_expectancy(signal, bars, _policy(), rule_name="tp10_stop5", sizing_name="fixed_250", trials=3) is not None
