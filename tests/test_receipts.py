from pathlib import Path

from gino_gate.policy import PolicyEnvelope
from gino_gate.receipts import ReceiptChain, ZERO_HASH
from gino_gate.verdict import Verdict


def _policy():
    return PolicyEnvelope.from_dict({
        "policy_id": "test",
        "mode": "read_only",
        "purpose": {"objective": "capital_preservation"},
        "authority": {},
        "allowed_tools_by_mode": {"read_only": ["get_accounts"]},
    })


def test_receipt_chain_links_hashes(tmp_path: Path):
    chain = ReceiptChain(tmp_path / "receipts.jsonl", b"test-key")
    policy = _policy()
    first = chain.append(
        run_id="run",
        policy=policy,
        does={"tool": "get_accounts", "args": {}},
        knows_ref="snap",
        recompute={},
        verdict=Verdict("ALLOW", "read_allowed", "ok"),
    )
    second = chain.append(
        run_id="run",
        policy=policy,
        does={"tool": "place_equity_order", "args": {"symbol": "AAPL"}},
        knows_ref="snap",
        recompute={},
        verdict=Verdict("REFUSE", "read_only_mode", "blocked"),
    )

    assert first["prev_hash"] == ZERO_HASH
    assert second["prev_hash"] == first["this_hash"]
    assert first["signature"].startswith("hmac-sha256:")
    assert second["signature"].startswith("hmac-sha256:")
