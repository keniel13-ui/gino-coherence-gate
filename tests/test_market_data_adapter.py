from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from gino_gate.market_data_adapter import (
    MarketDataAdapterError,
    ReadOnlyMarketDataAdapter,
    generate_own_signals_from_market_data,
    normalize_historicals_response,
    normalize_quote_response,
)
from gino_gate.policy import PolicyEnvelope
from gino_gate.verdict import decide


class FixtureGateClient:
    def __init__(self, policy: PolicyEnvelope, fixtures: dict[str, Any]):
        self.policy = policy
        self.fixtures = fixtures
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def call_tool(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((tool, args))
        verdict = decide({"tool": tool, "args": args}, self.policy)
        if verdict.verdict != "ALLOW":
            return {"ok": False, "verdict": verdict.verdict, "rule_fired": verdict.rule_fired}
        return {"ok": True, "data": self.fixtures[tool]}


def _policy() -> PolicyEnvelope:
    return PolicyEnvelope.from_file("config/policy.example.json")


def _historicals(count: int = 260) -> dict[str, Any]:
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    rows = []
    price = 100.0
    for idx in range(count):
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


def test_normalizes_robinhood_like_historicals_response():
    series = normalize_historicals_response("abc", _historicals(3))

    assert series.symbol == "ABC"
    assert len(series.bars) == 3
    assert series.bars[0].open == 101.0
    assert series.bars[-1].close == 103.0


def test_normalizes_quote_response():
    quote = normalize_quote_response(
        "abc",
        {"quotes": [{"symbol": "ABC", "last_trade_price": "123.45", "bid_price": "123.4", "ask_price": "123.5"}]},
    )

    assert quote.symbol == "ABC"
    assert quote.price == 123.45
    assert quote.bid == 123.4
    assert quote.ask == 123.5


def test_adapter_feeds_owned_signal_engine_through_read_only_gate():
    client = FixtureGateClient(
        _policy(),
        {
            "get_equity_historicals": _historicals(),
            "get_equity_quotes": {"quotes": [{"symbol": "ABC", "last_trade_price": "360.0"}]},
        },
    )
    adapter = ReadOnlyMarketDataAdapter(client)

    quote = adapter.get_equity_quote("abc")
    signals = generate_own_signals_from_market_data(
        adapter,
        ["abc"],
        ts_momentum=True,
        rsi2=False,
    )

    assert quote.price == 360.0
    assert signals
    assert signals[0]["source"] == "own:ts_momentum"
    assert ("get_equity_quotes", {"symbols": ["ABC"]}) in client.calls
    assert client.calls[-1][0] == "get_equity_historicals"


def test_order_tool_still_refused_by_fixture_gate():
    client = FixtureGateClient(_policy(), {})

    result = client.call_tool("place_equity_order", {"symbol": "ABC", "notional_usd": 10})

    assert result["ok"] is False
    assert result["rule_fired"] == "read_only_mode"


def test_historicals_fail_closed_when_required_fields_missing():
    with pytest.raises(MarketDataAdapterError, match="missing numeric field"):
        normalize_historicals_response("ABC", {"historicals": [{"begins_at": "2026-06-19T14:00:00Z"}]})
