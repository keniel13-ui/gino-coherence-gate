import json
from pathlib import Path

import pytest

from gino_gate.market_data_adapter import normalize_historicals_response
from gino_gate.scoring_policy import ScoringPolicy
from gino_gate.shadow_score import shadow_score_series
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
