import json
from pathlib import Path

from gino_gate.policy import PolicyEnvelope
from gino_gate.server import ReadOnlyGate


ROOT = Path(__file__).resolve().parents[1]


def _gate(tmp_path):
    policy = PolicyEnvelope.from_file(ROOT / "config" / "policy.example.json")
    return ReadOnlyGate(policy, tmp_path / "receipts.jsonl", b"test-key")


def test_every_call_is_receipted_and_nothing_is_forwarded(tmp_path):
    gate = _gate(tmp_path)
    allowed = gate.call_tool("get_accounts", {})
    refused = gate.call_tool("cancel_equity_order", {"order_id": "x"})

    assert allowed == {"ok": True, "verdict": allowed["verdict"], "upstream_forwarded": False}
    assert refused["ok"] is False and "upstream_forwarded" not in refused
    lines = [json.loads(line) for line in (tmp_path / "receipts.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [r["seq"] for r in lines] == [1, 2]
    assert lines[1]["prev_hash"] == lines[0]["this_hash"]
    assert lines[1]["verdict"] == "REFUSE"


def test_manifest_exposes_only_allowlisted_read_tools(tmp_path):
    gate = _gate(tmp_path)
    result = gate.manifest({"tools": [
        {"name": "get_accounts"},
        {"name": "get_unlisted_thing"},
        {"name": "review_equity_order"},
        {"name": "place_equity_order"},
        "mystery_tool",
    ]})
    assert [t["name"] for t in result["exposed"]] == ["get_accounts"]
    blocked = {t["name"]: t["kind"] for t in result["blocked"]}
    assert blocked == {
        "get_unlisted_thing": "read",
        "review_equity_order": "review",
        "place_equity_order": "trade_place",
        "mystery_tool": "unknown",
    }


def test_policy_hash_ignores_embedded_policy_hash_field():
    raw = json.loads((ROOT / "config" / "policy.example.json").read_text(encoding="utf-8"))
    with_hash = {**raw, "policy_hash": "sha256:whatever"}
    assert PolicyEnvelope.from_dict(raw).policy_hash == PolicyEnvelope.from_dict(with_hash).policy_hash
