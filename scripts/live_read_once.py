#!/usr/bin/env python3
"""Receipt and normalize one gate-mediated live read response.

This script does not authenticate to Robinhood. Until a Python MCP auth client is
wired, capture the raw read-tool response from an official MCP client and pass it
with --response-json. The gate still verifies the tool is allowed and emits a
signed receipt before normalization.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gino_gate.live_read_client import ReceiptingReadToolClient
from gino_gate.market_data_adapter import ReadOnlyMarketDataAdapter
from gino_gate.policy import PolicyEnvelope
from gino_gate.server import DEFAULT_SIGNING_KEY


def _read_json(path: str) -> Any:
    return json.loads(Path(path).read_text())


def _captured_upstream(response: Any):
    def call(_tool: str, _args: dict[str, Any]) -> Any:
        return response

    return call


def main() -> int:
    parser = argparse.ArgumentParser(description="Receipt one read-only market-data response.")
    parser.add_argument("--tool", required=True, choices=["get_equity_quotes", "get_equity_historicals"])
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--response-json", required=True, help="Raw response captured from an official MCP client.")
    parser.add_argument("--policy", default="config/policy.example.json")
    parser.add_argument("--receipts", default="var/live_read_receipts.jsonl")
    parser.add_argument("--run-id", default="live-read-once")
    args = parser.parse_args()

    policy = PolicyEnvelope.from_file(args.policy)
    signing_key = os.environ.get("GINO_GATE_LOG_KEY", "").encode("utf-8") or DEFAULT_SIGNING_KEY
    client = ReceiptingReadToolClient(
        policy=policy,
        receipt_path=args.receipts,
        upstream_call=_captured_upstream(_read_json(args.response_json)),
        signing_key=signing_key,
        run_id=args.run_id,
    )
    adapter = ReadOnlyMarketDataAdapter(client)

    if args.tool == "get_equity_quotes":
        quote = adapter.get_equity_quote(args.symbol)
        result = {"kind": "quote", "quote": quote.__dict__}
    else:
        series = adapter.get_equity_historicals(args.symbol)
        result = {
            "kind": "historicals",
            "symbol": series.symbol,
            "bar_count": len(series.bars),
            "first_bar": series.bars[0].__dict__ if series.bars else None,
            "last_bar": series.bars[-1].__dict__ if series.bars else None,
        }

    last_receipt = client.receipts.last_hash()
    print(
        json.dumps(
            {
                "result": result,
                "receipt_path": args.receipts,
                "last_receipt_hash": last_receipt,
                "boundary": "captured_response_only_no_auth_no_orders",
            },
            indent=2,
            sort_keys=True,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
