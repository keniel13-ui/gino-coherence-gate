#!/usr/bin/env python3
"""Run a money-safe shadow-score preview on a saved historicals response."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gino_gate.policy import PolicyEnvelope
from gino_gate.policy import sha256_json
from gino_gate.receipts import ReceiptChain
from gino_gate.scoring_policy import ScoringPolicy
from gino_gate.server import DEFAULT_SIGNING_KEY
from gino_gate.shadow_score import shadow_score_historicals_payload
from gino_gate.verdict import Verdict


def main() -> int:
    parser = argparse.ArgumentParser(description="Shadow-score saved read-only historicals.")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--historicals-json", required=True)
    parser.add_argument("--scoring-policy", default="config/scoring_policy.frozen.2026-06-18.json")
    parser.add_argument("--gate-policy", default="config/policy.example.json")
    parser.add_argument("--receipts", default="var/shadow_score_receipts.jsonl")
    parser.add_argument("--output", default="var/shadow_score_report.json")
    parser.add_argument("--run-id", default="shadow-score-preview")
    args = parser.parse_args()

    scoring_policy = ScoringPolicy.from_file(args.scoring_policy)
    gate_policy = PolicyEnvelope.from_file(args.gate_policy)
    payload = json.loads(Path(args.historicals_json).read_text())
    report = shadow_score_historicals_payload(args.symbol, payload, scoring_policy)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

    signing_key = os.environ.get("GINO_GATE_LOG_KEY", "").encode("utf-8") or DEFAULT_SIGNING_KEY
    receipt = ReceiptChain(Path(args.receipts), signing_key).append(
        run_id=args.run_id,
        policy=gate_policy,
        does={
            "tool": "shadow_score_saved_historicals",
            "args": {
                "symbol": args.symbol.upper(),
                "historicals_json": args.historicals_json,
                "scoring_policy_hash": scoring_policy.policy_hash,
            },
        },
        knows_ref="saved_receipted_historicals",
        recompute={
            "status": report["status"],
            "bar_count": report["bar_count"],
            "signal_count": report["signal_count"],
            "record_count": report["record_count"],
            "report_hash": sha256_json(report),
        },
        verdict=Verdict("ALLOW", "shadow_score_preview", "Money-safe shadow score generated from saved read-only data"),
    )

    summary = {
        "status": report["status"],
        "symbol": report["symbol"],
        "bar_count": report["bar_count"],
        "signal_count": report["signal_count"],
        "record_count": report["record_count"],
        "measurement_gate": report["measurement_gate"],
        "settled_n": report["report"]["settled_n"],
        "variant_action_verdict": report["report"]["action_verdict"],
        "action_verdict": "continue_collecting" if not report["measurement_gate"]["ready"] else report["report"]["action_verdict"],
        "decision_ready": report["measurement_gate"]["ready"],
        "decision_reason": report["measurement_gate"]["reason"],
        "variant_decision_ready": report["report"]["decision_ready"],
        "variant_decision_reason": report["report"]["decision_reason"],
        "net_expectancy_per_variant_record_usd": report["report"]["net_expectancy_per_signal_usd"],
        "live_haircut_expectancy_per_variant_record_usd": report["report"]["live_haircut_expectancy_usd"],
        "baseline": report["baseline"],
        "output": str(output_path),
        "receipt_path": args.receipts,
        "receipt_hash": receipt["this_hash"],
        "boundary": "shadow_score_preview_no_orders_no_money",
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
