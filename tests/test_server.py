import json
from pathlib import Path

import pytest

from gino_gate import server
from gino_gate.server import DEFAULT_SIGNING_KEY, main, signing_key_from_env


ROOT = Path(__file__).resolve().parents[1]
POLICY = str(ROOT / "config" / "policy.example.json")


def test_signing_key_warns_when_falling_back_to_dev_key(monkeypatch, capsys):
    monkeypatch.delenv(server.SIGNING_KEY_ENV, raising=False)
    assert signing_key_from_env() == DEFAULT_SIGNING_KEY
    assert "public dev key" in capsys.readouterr().err


def test_signing_key_uses_env_without_warning(monkeypatch, capsys):
    monkeypatch.setenv(server.SIGNING_KEY_ENV, "real-secret")
    assert signing_key_from_env() == b"real-secret"
    assert capsys.readouterr().err == ""


def test_cli_refuses_order_and_verifies_chain(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv(server.SIGNING_KEY_ENV, "cli-key")
    receipts = str(tmp_path / "r.jsonl")
    assert main(["--policy", POLICY, "--receipts", receipts, "--call-tool", "get_accounts"]) == 0
    assert main([
        "--policy", POLICY, "--receipts", receipts,
        "--call-tool", "place_equity_order", "--args-json", '{"symbol": "AAPL", "notional_usd": 10}',
    ]) == 0
    capsys.readouterr()

    assert main(["--receipts", receipts, "--verify-receipts"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report == {"ok": True, "count": 2, "problems": []}

    monkeypatch.setenv(server.SIGNING_KEY_ENV, "wrong-key")
    assert main(["--receipts", receipts, "--verify-receipts"]) == 1


def test_cli_rejects_non_object_args_json(tmp_path, monkeypatch):
    monkeypatch.setenv(server.SIGNING_KEY_ENV, "cli-key")
    for bad in ("not json", "[1, 2]"):
        with pytest.raises(SystemExit) as excinfo:
            main(["--policy", POLICY, "--receipts", str(tmp_path / "r.jsonl"), "--call-tool", "get_accounts", "--args-json", bad])
        assert excinfo.value.code == 2
