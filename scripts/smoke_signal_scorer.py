from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gino_gate.scorer import simulate_signal
from gino_gate.scoring_metrics import aggregate_records
from gino_gate.scoring_policy import ScoringPolicy


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    policy = ScoringPolicy.from_file(root / "config" / "scoring_policy.frozen.2026-06-18.json")
    signal = {
        "signal_id": "sig-001",
        "source": "discord:gino-test",
        "symbol": "NVDA",
        "side": "buy",
        "posted_at": "2026-06-18T14:00:00Z",
        "captured_at": "2026-06-18T14:00:02Z",
        "posted_price": 100.0
    }
    bars = [
        {"ts": "2026-06-18T14:00:30Z", "open": 101.0, "high": 110.0, "low": 99.0, "close": 105.0},
        {"ts": "2026-06-18T15:00:00Z", "open": 105.0, "high": 128.0, "low": 104.0, "close": 127.5}
    ]
    record = simulate_signal(signal, bars, policy, rule_name="tp_stop15", sizing_name="risk_1pct")
    report = aggregate_records([record], policy, started_at=None, as_of=None)
    print(json.dumps({"policy_hash": policy.policy_hash, "record": record, "report": report}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
