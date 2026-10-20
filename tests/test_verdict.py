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


def _live(args, recompute=None, **kwargs):
    return decide(
        {"tool": "place_equity_order", "args": {"symbol": "AAPL", **args}},
        _policy("gated_live"),
        recompute if recompute is not None else {"rolling_window_after_usd": 10, "position_after_usd": 10},
        now_et=datetime(2026, 6, 18, 10, 0),
        **kwargs,
    )


def test_nan_notional_is_refused_not_allowed():
    # Regression: NaN compares False against every cap, so it used to reach policy_pass.
    verdict = _live({"notional_usd": float("nan")})
    assert verdict.verdict == "REFUSE"
    assert verdict.rule_fired == "invalid_numeric_input"


def test_infinite_and_unparseable_notional_are_refused():
    assert _live({"notional_usd": float("inf")}).rule_fired == "invalid_numeric_input"
    assert _live({"notional_usd": "abc"}).rule_fired == "invalid_numeric_input"


def test_negative_quantity_cannot_shrink_notional_under_cap():
    # Regression: qty=-1000 at $500 produced a negative notional that passed every cap.
    verdict = _live({"qty": -1000, "price_usd": 500})
    assert verdict.verdict == "REFUSE"
    assert verdict.rule_fired == "invalid_numeric_input"


def test_nan_recompute_values_are_refused():
    for key in ("position_after_usd", "rolling_window_after_usd", "daily_pnl_usd"):
        verdict = _live({"notional_usd": 10}, {key: float("nan")})
        assert verdict.rule_fired == "invalid_numeric_input", key


def test_negative_daily_pnl_still_reaches_loss_limit():
    verdict = _live({"notional_usd": 10}, {"daily_pnl_usd": -30})
    assert verdict.rule_fired == "daily_loss_limit"


def test_valid_small_order_still_passes():
    verdict = _live({"notional_usd": 10})
    assert verdict.verdict == "ALLOW"
    assert verdict.rule_fired == "policy_pass"


def test_nan_input_age_is_treated_as_stale():
    verdict = decide({"tool": "get_accounts", "args": {}}, _policy(), input_ages_sec=[float("nan")])
    assert verdict.verdict == "REFUSE"
    assert verdict.rule_fired == "stale_input"
