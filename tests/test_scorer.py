from datetime import datetime, timezone

from gino_gate.scorer import simulate_signal
from gino_gate.scoring_metrics import aggregate_records
from gino_gate.scoring_policy import ScoringPolicy


def _policy(min_settled_n=2):
    return ScoringPolicy.from_dict({
        "policy_id": "test-scorer",
        "entry_latency_sec": 30,
        "account_equity_usd": 5000,
        "rule_variants": [
            {"name": "tp10_stop5", "take_profit_pct": 10, "stop_pct": -5, "time_stop_sec": 3600},
            {"name": "tp10_no_stop", "take_profit_pct": 10, "stop_pct": None, "time_stop_sec": 3600},
        ],
        "sizing_variants": [
            {"name": "fixed_250", "kind": "fixed_notional", "notional_usd": 250},
            {"name": "risk_1pct", "kind": "risk_pct_of_equity", "risk_pct": 1.0, "max_notional_usd": 2000},
        ],
        "fees_model": {"per_trade_usd": 0.0, "slippage_bps": 0},
        "late_call_detector": {"max_move_pct_before_entry": 3.0},
        "live_haircut": {"stress_pct": 50.0, "min_expectancy_usd_after_haircut": 1.0},
        "require_baseline_for_advance": True,
        "min_settled_n": min_settled_n,
        "decision_timebox_days": 21,
        "one_correction_only": True,
        "baselines": ["spy_buy_hold_same_window", "random_timed_entry"],
    })


def _signal(signal_id="sig-1", posted_price=100):
    return {
        "signal_id": signal_id,
        "source": "discord:test",
        "symbol": "ABC",
        "side": "buy",
        "posted_at": "2026-06-18T14:00:00Z",
        "captured_at": "2026-06-18T14:00:02Z",
        "posted_price": posted_price,
    }


def test_simulates_take_profit_and_mfe_mae():
    bars = [
        {"ts": "2026-06-18T14:00:30Z", "open": 100, "high": 105, "low": 98, "close": 103},
        {"ts": "2026-06-18T14:05:00Z", "open": 103, "high": 112, "low": 102, "close": 111},
    ]
    record = simulate_signal(_signal(), bars, _policy(), rule_name="tp10_stop5", sizing_name="fixed_250")
    assert record["settled"] is True
    assert record["exit"]["reason"] == "take_profit"
    assert record["outcome"]["win"] is True
    assert record["path"]["mfe_pct"] == 12
    assert record["path"]["mae_pct"] == -2


def test_risk_sizing_is_primary_profit_dial():
    bars = [{"ts": "2026-06-18T14:00:30Z", "open": 100, "high": 111, "low": 99, "close": 110}]
    fixed = simulate_signal(_signal("fixed"), bars, _policy(), rule_name="tp10_stop5", sizing_name="fixed_250")
    risk = simulate_signal(_signal("risk"), bars, _policy(), rule_name="tp10_stop5", sizing_name="risk_1pct")
    assert fixed["entry"]["notional_usd"] == 250
    assert risk["entry"]["notional_usd"] == 1000
    assert risk["outcome"]["net_pnl_usd"] > fixed["outcome"]["net_pnl_usd"]


def test_late_call_detector_flags_moved_signal():
    bars = [{"ts": "2026-06-18T14:00:30Z", "open": 105, "high": 112, "low": 104, "close": 111}]
    record = simulate_signal(_signal(posted_price=100), bars, _policy(), rule_name="tp10_stop5", sizing_name="fixed_250")
    assert record["detectors"]["late_call"] is True
    assert record["detectors"]["pre_entry_move_pct"] == 5


def test_live_haircut_kills_barely_positive_source():
    policy = _policy(min_settled_n=1)
    record = {
        "signal_id": "x",
        "source": "discord:test",
        "posted_at": "2026-06-18T14:00:00Z",
        "rule_variant": "tp10_stop5",
        "sizing_variant": "fixed_250",
        "settled": True,
        "excluded": False,
        "outcome": {"net_pnl_usd": 0.01, "net_return_pct": 0.004},
        "detectors": {},
    }
    report = aggregate_records([record], policy, baseline_expectancy_usd=0)
    assert report["decision_ready"] is True
    assert report["action_verdict"] == "kill_source"


def test_advance_requires_haircut_and_baseline():
    policy = _policy(min_settled_n=1)
    record = {
        "signal_id": "x",
        "source": "discord:test",
        "posted_at": "2026-06-18T14:00:00Z",
        "rule_variant": "tp10_stop5",
        "sizing_variant": "fixed_250",
        "settled": True,
        "excluded": False,
        "outcome": {"net_pnl_usd": 10, "net_return_pct": 4},
        "detectors": {},
    }
    missing_baseline = aggregate_records([record], policy)
    with_baseline = aggregate_records([record], policy, baseline_expectancy_usd=0)
    assert missing_baseline["action_verdict"] == "unmeasurable"
    assert with_baseline["action_verdict"] == "advance"


def test_negative_after_haircut_kills_source():
    policy = _policy(min_settled_n=1)
    record = {
        "signal_id": "x",
        "source": "discord:test",
        "posted_at": "2026-06-18T14:00:00Z",
        "rule_variant": "tp10_stop5",
        "sizing_variant": "fixed_250",
        "settled": True,
        "excluded": False,
        "outcome": {"net_pnl_usd": -1, "net_return_pct": -0.4},
        "detectors": {},
    }
    report = aggregate_records([record], policy)
    assert report["action_verdict"] == "kill_source"


def test_survivorship_guard_counts_exclusions():
    policy = _policy(min_settled_n=1)
    records = [
        {"signal_id": "bad", "source": "discord:test", "posted_at": "2026-06-18T14:00:00Z", "settled": False, "excluded": True, "exclusion_reason": "no price data"},
        {"signal_id": "win", "source": "discord:test", "posted_at": "2026-06-18T14:01:00Z", "settled": True, "excluded": False, "outcome": {"net_pnl_usd": 10, "net_return_pct": 4}, "detectors": {}},
    ]
    report = aggregate_records(records, policy)
    assert report["captured_n"] == 2
    assert report["excluded_n"] == 1
    assert report["exclusion_reasons"] == {"no price data": 1}


def test_timebox_forces_decision_even_before_min_n():
    policy = _policy(min_settled_n=50)
    record = {
        "signal_id": "x",
        "source": "discord:test",
        "posted_at": "2026-06-18T14:00:00Z",
        "settled": True,
        "excluded": False,
        "outcome": {"net_pnl_usd": 5, "net_return_pct": 2},
        "detectors": {},
    }
    report = aggregate_records(
        [record],
        policy,
        started_at=datetime(2026, 6, 18, tzinfo=timezone.utc),
        as_of=datetime(2026, 7, 10, tzinfo=timezone.utc),
    )
    assert report["decision_ready"] is True
    assert report["decision_reason"] == "decision_timebox_days"
