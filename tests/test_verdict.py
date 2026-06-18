from datetime import datetime

from gino_gate.policy import PolicyEnvelope
from gino_gate.verdict import decide


def _policy(mode="read_only"):
    return PolicyEnvelope.from_dict({
        "policy_id": "test",
        "mode": mode,
        "purpose": {"objective": "capital_preservation"},
        "authority": {
            "instrument_allowlist": ["equities"],
            "max_order_notional_usd": 50,
            "max_position_notional_usd_per_symbol": 150,
            "daily_loss_limit_usd": 30,
            "rolling_exposure": {"max_cumulative_notional_usd": 400},
            "trading_hours_et": {"open": "09:30", "close": "16:00", "allow_extended": False},
            "freshness_max_age_sec": 15,
        },
        "human_ticket_required_above": {"order_notional_usd": 50},
        "allowed_tools_by_mode": {
            "read_only": ["get_accounts"],
            "shadow": ["get_accounts", "review_equity_order", "place_equity_order"],
            "gated_live": ["get_accounts", "review_equity_order", "place_equity_order"],
        },
    })


def test_read_only_allows_read_tool():
    verdict = decide({"tool": "get_accounts", "args": {}}, _policy())
    assert verdict.verdict == "ALLOW"
    assert verdict.rule_fired == "read_allowed"


def test_read_only_refuses_trade_tool():
    verdict = decide({"tool": "place_equity_order", "args": {"symbol": "AAPL", "notional_usd": 50}}, _policy())
    assert verdict.verdict == "REFUSE"
    assert verdict.rule_fired == "read_only_mode"


def test_shadow_refuses_place_tool_even_if_named_in_future_policy():
    verdict = decide({"tool": "place_equity_order", "args": {"symbol": "AAPL", "notional_usd": 10}}, _policy("shadow"))
    assert verdict.verdict == "REFUSE"
    assert verdict.rule_fired == "non_executing_mode"


def test_live_refuses_rolling_exposure_before_ticket():
    verdict = decide(
        {"tool": "place_equity_order", "args": {"symbol": "AAPL", "notional_usd": 10}},
        _policy("gated_live"),
        {"rolling_window_after_usd": 401},
        now_et=datetime(2026, 6, 18, 10, 0),
    )
    assert verdict.verdict == "REFUSE"
    assert verdict.rule_fired == "rolling_exposure"


def test_live_requires_ticket_at_threshold():
    verdict = decide(
        {"tool": "place_equity_order", "args": {"symbol": "AAPL", "notional_usd": 50}},
        _policy("gated_live"),
        {"rolling_window_after_usd": 50, "position_after_usd": 50},
        now_et=datetime(2026, 6, 18, 10, 0),
    )
    assert verdict.verdict == "REQUIRE_TICKET"
    assert verdict.rule_fired == "ticket_required"
