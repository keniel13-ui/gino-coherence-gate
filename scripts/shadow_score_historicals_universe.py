#!/usr/bin/env python3
"""Run a money-safe shadow-score preview over a saved historicals universe."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gino_gate.policy import PolicyEnvelope, sha256_json
from gino_gate.receipts import ReceiptChain
from gino_gate.scoring_policy import ScoringPolicy
from gino_gate.server import DEFAULT_SIGNING_KEY
from gino_gate.shadow_score import shadow_score_historicals_universe_payloads
from gino_gate.verdict import Verdict


def main() -> int:
    parser = argparse.ArgumentParser(description="Shadow-score saved Robinhood historicals across a symbol universe.")
    parser.add_argument("--symbol-json", action="append", default=[], help="Repeat as SYMBOL=path/to/historicals.json")
    parser.add_argument("--historicals-dir", help="Directory containing SYMBOL*.json saved historical responses")
    parser.add_argument("--spy-json", help="Saved SPY historicals JSON for buy-hold baseline")
    parser.add_argument("--scoring-policy", default="config/scoring_policy.frozen.2026-06-18.json")
    parser.add_argument("--gate-policy", default="config/policy.example.json")
    parser.add_argument("--receipts", default="var/shadow_score_universe_receipts.jsonl")
    parser.add_argument("--output", default="var/shadow_score_universe_report.json")
    parser.add_argument("--run-id", default="shadow-score-universe-preview")
    args = parser.parse_args()

    payloads = _load_payloads(args.symbol_json, args.historicals_dir)
    if not payloads:
        raise SystemExit("no symbol historicals supplied")

    spy_payload = json.loads(Path(args.spy_json).read_text()) if args.spy_json else None
    scoring_policy = ScoringPolicy.from_file(args.scoring_policy)
    gate_policy = PolicyEnvelope.from_file(args.gate_policy)
    report = shadow_score_historicals_universe_payloads(payloads, scoring_policy, spy_payload=spy_payload)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

    signing_key = os.environ.get("GINO_GATE_LOG_KEY", "").encode("utf-8") or DEFAULT_SIGNING_KEY
    receipt = ReceiptChain(Path(args.receipts), signing_key).append(
        run_id=args.run_id,
        policy=gate_policy,
        does={
            "tool": "shadow_score_historicals_universe",
            "args": {
                "symbols": sorted(payloads),
                "spy_json": args.spy_json,
                "scoring_policy_hash": scoring_policy.policy_hash,
            },
        },
        knows_ref="saved_receipted_historicals_universe",
        recompute={
            "status": report["status"],
            "symbol_count": report["symbol_count"],
            "signal_count": report["signal_count"],
            "record_count": report["record_count"],
            "measurement_gate": report["measurement_gate"],
            "report_hash": sha256_json(report),
        },
        verdict=Verdict("ALLOW", "shadow_score_universe_preview", "Money-safe universe shadow score generated from saved read-only data"),
    )

    summary = {
        "status": report["status"],
        "symbols": report["symbols"],
        "symbol_count": report["symbol_count"],
        "signal_count": report["signal_count"],
        "record_count": report["record_count"],
        "measurement_gate": report["measurement_gate"],
        "baseline": report["baseline"],
        "action_verdict": report["action_verdict"],
        "decision_ready": report["decision_ready"],
        "output": str(output_path),
        "receipt_path": args.receipts,
        "receipt_hash": receipt["this_hash"],
        "boundary": "shadow_score_universe_preview_no_orders_no_money",
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def _load_payloads(symbol_json_args: list[str], historicals_dir: str | None) -> dict[str, Any]:
    payloads: dict[str, Any] = {}
    for item in symbol_json_args:
        if "=" not in item:
            raise SystemExit(f"--symbol-json must be SYMBOL=path, got: {item}")
        symbol, path = item.split("=", 1)
        payloads[symbol.upper()] = json.loads(Path(path).read_text())

    if historicals_dir:
        root = Path(historicals_dir)
        if not root.exists():
            raise SystemExit(f"historicals dir does not exist: {root}")
        for path in sorted(root.glob("*.json")):
            symbol = _symbol_from_path(path)
            if symbol == "SPY":
                continue
            payloads.setdefault(symbol, json.loads(path.read_text()))
    return payloads


def _symbol_from_path(path: Path) -> str:
    stem = path.stem.upper()
    for suffix in ("_HIST", ".HIST", "_RAW", ".RAW"):
        stem = stem.replace(suffix, "")
    return stem.split("_")[0].split(".")[0]


if __name__ == "__main__":
    raise SystemExit(main())
