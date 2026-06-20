import json
from pathlib import Path

import pytest

from gino_gate.market_data_adapter import normalize_historicals_response
from gino_gate.scoring_policy import ScoringPolicy
from gino_gate.shadow_score import shadow_score_series, shadow_score_universe
from tests.test_market_data_adapter import _historicals


def _policy() -> ScoringPolicy:
    return ScoringPolicy.from_file("config/scoring_policy.frozen.2026-06-18.json")


def test_shadow_score_marks_single_symbol_preview_insufficient_sample():
    series = normalize_historicals_response("ABC", _historicals(260))

    result = shadow_score_series(series, _policy())

    assert result["status"] == "measurement_preview_insufficient_sample"
    assert result["bar_count"] == 260
    assert result["signal_count"] >= 1
    assert result["record_count"] >= result["signal_count"]
    assert result["measurement_gate"]["ready"] is False
    assert result["measurement_gate"]["reason"] == "waiting_for_min_unique_signals"
    assert result["measurement_gate"]["note"] == "Variant records are not independent signals."


def test_shadow_score_real_aapl_historicals_if_present():
    path = Path("manifests/aapl_hist.raw.json")
    if not path.exists():
        pytest.skip("live AAPL historicals capture is local/gitignored")

    series = normalize_historicals_response("AAPL", json.loads(path.read_text()))
    result = shadow_score_series(series, _policy())

    assert result["symbol"] == "AAPL"
    assert result["bar_count"] == 251
    assert result["status"] == "measurement_preview_insufficient_sample"
    assert result["measurement_gate"]["unique_signal_count"] < _policy().min_settled_n


def test_universe_shadow_score_requires_spy_baseline_before_verdict():
    policy = _policy()
    series_by_symbol = {
        f"S{idx:02d}": normalize_historicals_response(f"S{idx:02d}", _historicals(260))
        for idx in range(policy.min_settled_n)
    }

    result = shadow_score_universe(series_by_symbol, policy)

    assert result["measurement_gate"]["ready"] is True
    assert result["measurement_gate"]["unique_signal_count"] == policy.min_settled_n
    assert result["record_count"] > result["signal_count"]
    assert result["status"] == "measurement_preview_missing_spy_baseline"
    assert result["baseline"]["spy_baseline_status"] == "missing_spy_series"
    assert result["action_verdict"] == "unmeasurable"
    assert result["decision_ready"] is False


def test_universe_shadow_score_with_spy_baseline_is_decision_eligible():
    policy = _policy()
    series_by_symbol = {
        f"S{idx:02d}": normalize_historicals_response(f"S{idx:02d}", _historicals(260))
        for idx in range(policy.min_settled_n)
    }
    spy_series = normalize_historicals_response("SPY", _historicals(260))

    result = shadow_score_universe(series_by_symbol, policy, spy_series=spy_series)

    assert result["measurement_gate"]["ready"] is True
    assert result["measurement_gate"]["unique_signal_count"] == policy.min_settled_n
    assert result["baseline"]["spy_baseline_status"] == "present"
    assert result["baseline"]["spy_buy_hold_same_window_expectancy_usd"] is not None
    assert result["status"] == "measurement_preview_ready_for_verdict"
    assert result["decision_ready"] is True
    assert result["action_verdict"] in {"advance", "kill_source", "rerun_one_correction", "unmeasurable"}
    assert result["pooled_report_note"] == "Diagnostic only. Top-level verdict never pools rule/sizing variants."
    assert result["by_source_variant"]
    for variant_report in result["by_source_variant"].values():
        assert variant_report["baseline_unit"] == "average_net_pnl_usd_per_signal_for_this_exact_variant"
        assert variant_report["baseline_comparison_rule"] == "max(spy_buy_hold_same_window, random_timed_entry)"
        assert variant_report["baseline_comparison_expectancy_usd"] is not None
        assert variant_report["baseline_spy_buy_hold_same_window_expectancy_usd"] is not None
        assert variant_report["beats_baseline"] is not None
    if result["action_verdict"] == "advance":
        assert result["qualifying_variants"]
        assert all(item["beats_baseline"] is True for item in result["qualifying_variants"])
