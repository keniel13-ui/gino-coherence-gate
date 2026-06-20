#!/usr/bin/env python3
"""Smoke the read-only market-data adapter with fixture MCP responses."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gino_gate.market_data_adapter import ReadOnlyMarketDataAdapter, generate_own_signals_from_market_data
from gino_gate.policy import PolicyEnvelope
from gino_gate.verdict import decide


class FixtureGateClient:
    def __init__(self, policy: PolicyEnvelope, fixtures: dict[str, Any]):
        self.policy = policy
        self.fixtures = fixtures
        self.calls: list[dict[str, Any]] = []

    def call_tool(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        verdict = decide({"tool": tool, "args": args}, self.policy)
        self.calls.append({"tool": tool, "args": args, "verdict": verdict.verdict, "rule_fired": verdict.rule_fired})
        if verdict.verdict != "ALLOW":
            return {"ok": False, "rule_fired": verdict.rule_fired}
        return {"ok": True, "data": self.fixtures[tool]}


def _historicals() -> dict[str, Any]:
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    rows = []
    price = 100.0
    for idx in range(260):
        price += 1.0
        rows.append(
            {
                "begins_at": (start + timedelta(days=idx)).isoformat().replace("+00:00", "Z"),
                "open_price": str(price),
                "high_price": str(price + 1),
                "low_price": str(price - 1),
                "close_price": str(price),
            }
        )
    return {"historicals": rows}


def main() -> int:
    policy = PolicyEnvelope.from_file("config/policy.example.json")
    client = FixtureGateClient(
        policy,
        {
            "get_equity_historicals": _historicals(),
            "get_equity_quotes": {"quotes": [{"symbol": "ABC", "last_trade_price": "360.0"}]},
        },
    )
    adapter = ReadOnlyMarketDataAdapter(client)
    quote = adapter.get_equity_quote("ABC")
    signals = generate_own_signals_from_market_data(adapter, ["ABC"], ts_momentum=True, rsi2=False)
    refused_order = client.call_tool("place_equity_order", {"symbol": "ABC", "notional_usd": 10})

    print(
        json.dumps(
            {
                "quote": quote.__dict__,
                "signals": signals[:3],
                "signal_count": len(signals),
                "calls": client.calls,
                "refused_order": refused_order,
                "boundary": "fixture_only_no_live_connection_no_orders",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
