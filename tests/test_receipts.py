from pathlib import Path

from gino_gate.policy import PolicyEnvelope
from gino_gate.receipts import ReceiptChain, ZERO_HASH, verify_chain
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


def _append_two(path: Path, key: bytes = b"test-key") -> ReceiptChain:
    chain = ReceiptChain(path, key)
    for tool, verdict in (("get_accounts", "ALLOW"), ("place_equity_order", "REFUSE")):
        chain.append(
            run_id="run",
            policy=_policy(),
            does={"tool": tool, "args": {}},
            knows_ref="snap",
            recompute={},
            verdict=Verdict(verdict, "rule", "detail"),
        )
    return chain


def test_verify_chain_accepts_untouched_chain(tmp_path: Path):
    path = tmp_path / "receipts.jsonl"
    _append_two(path)
    result = verify_chain(path, b"test-key")
    assert result.ok, result.problems
    assert result.count == 2


def test_verify_chain_missing_file_is_empty_and_ok(tmp_path: Path):
    result = verify_chain(tmp_path / "absent.jsonl", b"test-key")
    assert result.ok and result.count == 0


def test_verify_chain_detects_edited_verdict(tmp_path: Path):
    path = tmp_path / "receipts.jsonl"
    _append_two(path)
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[1] = lines[1].replace('"verdict":"REFUSE"', '"verdict":"ALLOW"')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = verify_chain(path, b"test-key")
    assert not result.ok
    assert any("this_hash" in problem for problem in result.problems)


def test_verify_chain_detects_deleted_receipt(tmp_path: Path):
    path = tmp_path / "receipts.jsonl"
    _append_two(path)
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text(lines[1] + "\n", encoding="utf-8")
    result = verify_chain(path, b"test-key")
    assert not result.ok
    assert any("prev_hash" in problem for problem in result.problems)


def test_verify_chain_detects_wrong_key_and_garbage_line(tmp_path: Path):
    path = tmp_path / "receipts.jsonl"
    _append_two(path)
    assert any("signature" in p for p in verify_chain(path, b"other-key").problems)
    with path.open("a", encoding="utf-8") as fh:
        fh.write("{truncated\n")
    assert any("not valid JSON" in p for p in verify_chain(path, b"test-key").problems)
