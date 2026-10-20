"""Run the offline smoke/readiness scripts the README documents, as subprocesses.

These scripts never touch the network or Robinhood. Running them here keeps the
documented commands working and pins the safety facts they print.
"""

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _run(*args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ, "GINO_GATE_LOG_KEY": "test-key"}
    return subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        input=stdin,
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
        check=False,
    )


def _json(proc: subprocess.CompletedProcess):
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_smoke_gino_gate_refuses_order_and_never_forwards():
    out = _json(_run("scripts/smoke_gino_gate.py"))
    assert out["read_result"]["ok"] is True
    assert out["read_result"]["upstream_forwarded"] is False
    assert out["trade_result"]["ok"] is False
    assert out["trade_result"]["verdict"]["verdict"] == "REFUSE"
    exposed = {tool["name"] for tool in out["manifest"]["exposed"]}
    assert not exposed & {"review_equity_order", "place_equity_order", "cancel_equity_order"}


def test_smoke_signal_scorer_runs():
    proc = _run("scripts/smoke_signal_scorer.py")
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip()


def test_smoke_market_data_adapter_runs():
    proc = _run("scripts/smoke_market_data_adapter.py")
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip()


def test_visit_readiness_with_reported_sample():
    out = _json(_run("scripts/gino_visit_readiness.py"))
    assert out["manifest_source"] == "reported_sample_manifest_not_live"
    assert out["boundary"] == "read_only_readiness_only_no_auth_no_orders"


def test_server_cli_prints_policy_identity():
    out = _json(_run("-m", "gino_gate.server"))
    assert out["mode"] == "read_only"
    assert out["policy_hash"].startswith("sha256:")


def test_server_cli_refuses_order_tool(tmp_path):
    out = _json(_run(
        "-m", "gino_gate.server",
        "--receipts", str(tmp_path / "r.jsonl"),
        "--call-tool", "place_equity_order",
        "--args-json", '{"symbol": "AAPL", "notional_usd": 10}',
    ))
    assert out["ok"] is False
    assert out["verdict"]["verdict"] == "REFUSE"
    assert (tmp_path / "r.jsonl").read_text(encoding="utf-8").count("\n") == 1


def test_normalize_manifest_capture_from_stdin(tmp_path):
    capture = {"jsonrpc": "2.0", "id": 1, "result": {"tools": [
        {"name": "get_accounts"}, {"name": "get_equity_quotes"}, {"name": "place_equity_order"},
    ]}}
    output = tmp_path / "normalized.json"
    out = _json(_run("scripts/normalize_manifest_capture.py", "-", "--output", str(output), stdin=json.dumps(capture)))
    assert out["boundary"] == "manifest_normalization_only_no_auth_no_orders"
    assert json.loads(output.read_text(encoding="utf-8"))["tools"][2]["name"] == "place_equity_order"


def test_normalize_manifest_capture_rejects_garbage(tmp_path):
    proc = _run("scripts/normalize_manifest_capture.py", "-", "--output", str(tmp_path / "x.json"), stdin="not json")
    assert proc.returncode != 0
    assert "manifest capture failed" in proc.stderr


def test_live_read_once_receipts_a_captured_quote(tmp_path):
    response = tmp_path / "quote.json"
    response.write_text(json.dumps({"quotes": [{"symbol": "ABC", "last_trade_price": "123.45"}]}), encoding="utf-8")
    receipts = tmp_path / "receipts.jsonl"
    out = _json(_run(
        "scripts/live_read_once.py",
        "--tool", "get_equity_quotes", "--symbol", "ABC",
        "--response-json", str(response), "--receipts", str(receipts),
    ))
    assert out["boundary"] == "captured_response_only_no_auth_no_orders"
    assert out["result"]["kind"] == "quote"
    receipt = json.loads(receipts.read_text(encoding="utf-8").splitlines()[-1])
    assert receipt["verdict"] == "ALLOW"
    assert receipt["recompute"]["result_hash"].startswith("sha256:")
    assert out["last_receipt_hash"] == receipt["this_hash"]
