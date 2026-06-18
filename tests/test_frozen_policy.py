import json
from pathlib import Path

from gino_gate.scorer import simulate_signal
from gino_gate.scoring_policy import ScoringPolicy


ROOT = Path(__file__).resolve().parents[1]


def test_frozen_policy_hash_matches_anchor():
    policy = ScoringPolicy.from_file(ROOT / "config" / "scoring_policy.frozen.2026-06-18.json")
    anchor = json.loads((ROOT / "config" / "scoring_policy.frozen.2026-06-18.anchor.json").read_text(encoding="utf-8"))
    assert policy.policy_hash == "sha256:83474132582fc3f6ca947cfd7b71b3671228fea28a471d6434c7c72764c663ae"
    assert anchor["policy_hash"] == policy.policy_hash


def test_frozen_no_stop_variant_uses_position_cap_for_risk_sizing():
    policy = ScoringPolicy.from_file(ROOT / "config" / "scoring_policy.frozen.2026-06-18.json")
    signal = {
        "signal_id": "frozen-no-stop",
        "source": "own:test",
        "symbol": "ABC",
        "side": "buy",
        "posted_at": "2026-06-18T14:00:00Z",
        "captured_at": "2026-06-18T14:00:01Z",
        "posted_price": 100.0,
    }
    bars = [{"ts": "2026-06-18T14:00:30Z", "open": 100, "high": 128, "low": 99, "close": 127.5}]
    record = simulate_signal(signal, bars, policy, rule_name="tp_only_no_stop", sizing_name="risk_2pct")
    assert record["excluded"] is False
    assert record["entry"]["notional_usd"] == 750
