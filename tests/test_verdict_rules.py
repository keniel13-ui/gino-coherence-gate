"""Cover each deterministic rule in verdict.decide that test_verdict.py does not."""

from datetime import datetime

from gino_gate.policy import PolicyEnvelope
from gino_gate.verdict import decide


def _policy(**authority_overrides):
    authority = {
        "instrument_allowlist": ["equities"],
        "symbol_allowlist": None,
        "max_order_notional_usd": 50,
        "max_position_notional_usd_per_symbol": 150,
        "daily_loss_limit_usd": 30,
        "rolling_exposure": {"max_cumulative_notional_usd": 400},
        "trading_hours_et": {"open": "09:30", "close": "16:00", "allow_extended": False},
        "freshness_max_age_sec": 15,
    }
    authority.update(authority_overrides)
    return PolicyEnvelope.from_dict({
        "policy_id": "rules",
        "mode": "gated_live",
        "purpose": {"objective": "capital_preservation"},
        "authority": authority,
        "human_ticket_required_above": {"order_notional_usd": 50},
        "allowed_tools_by_mode": {"gated_live": ["get_accounts", "place_equity_order"]},
    })


MARKET_OPEN = datetime(2026, 6, 18, 10, 0)


def _order(args=None, recompute=None, policy=None, **kwargs):
    kwargs.setdefault("now_et", MARKET_OPEN)
    return decide(
        {"tool": "place_equity_order", "args": {"symbol": "AAPL", "notional_usd": 10, **(args or {})}},
        policy or _policy(),
        recompute or {},
        **kwargs,
    )


def test_kill_switch_beats_everything_including_reads():
    verdict = decide({"tool": "get_accounts", "args": {}}, _policy(), kill_switch=True)
    assert (verdict.verdict, verdict.rule_fired) == ("REFUSE", "kill_switch")


def test_tool_not_in_mode_allowlist_is_refused():
    verdict = decide({"tool": "get_portfolio", "args": {}}, _policy())
    assert (verdict.verdict, verdict.rule_fired) == ("REFUSE", "gated_live_mode")


def test_stale_input_is_refused():
    assert _order(input_ages_sec=[1, 16]).rule_fired == "stale_input"
    assert _order(input_ages_sec=[15]).verdict == "ALLOW"


def test_instrument_and_symbol_allowlists():
    assert _order({"instrument": "options"}).rule_fired == "instrument_not_allowed"
    restricted = _policy(symbol_allowlist=["MSFT"])
    assert _order(policy=restricted).rule_fired == "symbol_not_allowed"
    assert _order({"symbol": "MSFT"}, policy=restricted).verdict == "ALLOW"


def test_order_cap_uses_qty_times_price_when_notional_absent():
    verdict = decide(
        {"tool": "place_equity_order", "args": {"symbol": "AAPL", "qty": 2, "limit_price": 30}},
        _policy(),
        now_et=MARKET_OPEN,
    )
    assert verdict.rule_fired == "order_cap"


def test_position_cap_and_daily_loss_limit():
    assert _order(recompute={"position_after_usd": 151}).rule_fired == "position_cap"
    assert _order(recompute={"daily_pnl_usd": -30}).rule_fired == "daily_loss_limit"
    assert _order(recompute={"daily_pnl_usd": -29.99}).verdict == "ALLOW"


def test_trading_hours_are_inclusive_and_extended_flag_lifts_them():
    assert _order(now_et=datetime(2026, 6, 18, 9, 29)).rule_fired == "trading_hours"
    assert _order(now_et=datetime(2026, 6, 18, 9, 30)).verdict == "ALLOW"
    assert _order(now_et=datetime(2026, 6, 18, 16, 0)).verdict == "ALLOW"
    extended = _policy(trading_hours_et={"open": "09:30", "close": "16:00", "allow_extended": True})
    assert _order(policy=extended, now_et=datetime(2026, 6, 18, 20, 0)).verdict == "ALLOW"


def test_trading_hours_skipped_when_no_clock_is_supplied():
    # Documented current behavior: without now_et the hours rule does not run.
    assert _order(now_et=None).verdict == "ALLOW"
