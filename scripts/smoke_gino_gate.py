from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gino_gate.policy import PolicyEnvelope
from gino_gate.server import ReadOnlyGate


SAMPLE_MANIFEST = {
    "tools": [
        {"name": "get_accounts"},
        {"name": "get_equity_positions"},
        {"name": "get_equity_quotes"},
        {"name": "review_equity_order"},
        {"name": "place_equity_order"},
        {"name": "cancel_equity_order"},
    ]
}


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    policy = PolicyEnvelope.from_file(root / "config" / "policy.example.json")

    with tempfile.TemporaryDirectory() as tmp:
        gate = ReadOnlyGate(policy, Path(tmp) / "receipts.jsonl", b"smoke-key")
        manifest = gate.manifest(SAMPLE_MANIFEST)
        read_result = gate.call_tool("get_accounts", {})
        trade_result = gate.call_tool("place_equity_order", {"symbol": "AAPL", "notional_usd": 50})

    print(json.dumps({
        "policy_hash": policy.policy_hash,
        "manifest": manifest,
        "read_result": read_result,
        "trade_result": trade_result,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
