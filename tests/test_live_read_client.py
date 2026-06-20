import json

from gino_gate.live_read_client import ReceiptingReadToolClient
from gino_gate.policy import PolicyEnvelope


def _policy() -> PolicyEnvelope:
    return PolicyEnvelope.from_file("config/policy.example.json")


def test_receipting_read_client_calls_allowed_upstream_and_hashes_result(tmp_path):
    calls = []

    def upstream(tool, args):
        calls.append((tool, args))
        return {"quotes": [{"symbol": "ABC", "last_trade_price": "123.45"}]}

    client = ReceiptingReadToolClient(
        policy=_policy(),
        receipt_path=tmp_path / "receipts.jsonl",
        upstream_call=upstream,
        signing_key=b"test",
    )

    result = client.call_tool("get_equity_quotes", {"symbols": ["ABC"]})

    assert result["ok"] is True
    assert calls == [("get_equity_quotes", {"symbols": ["ABC"]})]
    assert result["verdict"]["verdict"] == "ALLOW"
    assert result["verdict"]["recompute"]["upstream_called"] is True
    assert result["verdict"]["recompute"]["result_hash"].startswith("sha256:")


def test_receipting_read_client_refuses_order_without_upstream_call(tmp_path):
    calls = []

    def upstream(tool, args):
        calls.append((tool, args))
        return {}

    client = ReceiptingReadToolClient(
        policy=_policy(),
        receipt_path=tmp_path / "receipts.jsonl",
        upstream_call=upstream,
        signing_key=b"test",
    )

    result = client.call_tool("place_equity_order", {"symbol": "ABC", "notional_usd": 10})

    assert result["ok"] is False
    assert calls == []
    assert result["verdict"]["verdict"] == "REFUSE"
    assert result["verdict"]["rule_fired"] == "read_only_mode"
    assert result["verdict"]["recompute"] == {"upstream_called": False}

    receipt_lines = (tmp_path / "receipts.jsonl").read_text().splitlines()
    assert len(receipt_lines) == 1
    assert json.loads(receipt_lines[0])["does"]["tool"] == "place_equity_order"
