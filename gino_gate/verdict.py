from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from typing import Any

from .manifest import classify_tool
from .policy import PolicyEnvelope


@dataclass(frozen=True)
class Verdict:
    verdict: str
    rule_fired: str
    detail: str


def _parse_time(value: str) -> time:
    hour, minute = value.split(":", 1)
    return time(int(hour), int(minute))


def _notional(args: dict[str, Any]) -> float:
    if "notional_usd" in args:
        return float(args["notional_usd"])
    qty = float(args.get("qty", args.get("quantity", 0)) or 0)
    price = float(args.get("price_usd", args.get("limit_price", 0)) or 0)
    return qty * price


def decide(
    does: dict[str, Any],
    policy: PolicyEnvelope,
    recompute: dict[str, Any] | None = None,
    *,
    input_ages_sec: list[float] | None = None,
    kill_switch: bool = False,
    now_et: datetime | None = None,
) -> Verdict:
    recompute = recompute or {}
    input_ages_sec = input_ages_sec or []
    authority = policy.authority
    tool = str(does.get("tool", ""))
    args = dict(does.get("args", {}))
    tool_kind = classify_tool(tool).kind

    if kill_switch:
        return Verdict("REFUSE", "kill_switch", "Kill switch is engaged")

    if tool not in policy.allowed_tools():
        return Verdict("REFUSE", f"{policy.mode}_mode", f"{tool} is not exposed in {policy.mode} mode")

    if policy.mode == "read_only" and tool_kind != "read":
        return Verdict("REFUSE", "read_only_mode", f"{tool} is not a read tool")

    if policy.mode in {"shadow", "paper"} and tool_kind in {"trade_place", "trade_cancel"}:
        return Verdict("REFUSE", "non_executing_mode", f"{policy.mode} cannot forward place/cancel tools")

    max_age = float(authority.get("freshness_max_age_sec", 0) or 0)
    if max_age and any(age > max_age for age in input_ages_sec):
        return Verdict("REFUSE", "stale_input", f"Input age exceeds {max_age} seconds")

    if tool_kind == "read":
        return Verdict("ALLOW", "read_allowed", f"{tool} allowed in {policy.mode} mode")

    instrument = args.get("instrument", "equities")
    allowed_instruments = set(authority.get("instrument_allowlist", []))
    if allowed_instruments and instrument not in allowed_instruments:
        return Verdict("REFUSE", "instrument_not_allowed", f"{instrument} not in instrument allowlist")

    symbol_allowlist = authority.get("symbol_allowlist")
    symbol = args.get("symbol")
    if symbol_allowlist is not None and symbol not in set(symbol_allowlist):
        return Verdict("REFUSE", "symbol_not_allowed", f"{symbol} not in symbol allowlist")

    order_notional = _notional(args)
    max_order = float(authority.get("max_order_notional_usd", 0) or 0)
    if max_order and order_notional > max_order:
        return Verdict("REFUSE", "order_cap", f"Order notional {order_notional:.2f} > cap {max_order:.2f}")

    position_after = float(recompute.get("position_after_usd", 0) or 0)
    position_cap = float(authority.get("max_position_notional_usd_per_symbol", 0) or 0)
    if position_cap and position_after > position_cap:
        return Verdict("REFUSE", "position_cap", f"Position after {position_after:.2f} > cap {position_cap:.2f}")

    rolling_after = float(recompute.get("rolling_window_after_usd", 0) or 0)
    rolling_cap = float(authority.get("rolling_exposure", {}).get("max_cumulative_notional_usd", 0) or 0)
    if rolling_cap and rolling_after > rolling_cap:
        return Verdict("REFUSE", "rolling_exposure", f"Rolling exposure {rolling_after:.2f} > cap {rolling_cap:.2f}")

    daily_pnl = float(recompute.get("daily_pnl_usd", 0) or 0)
    daily_loss_limit = float(authority.get("daily_loss_limit_usd", 0) or 0)
    if daily_loss_limit and daily_pnl <= -daily_loss_limit:
        return Verdict("REFUSE", "daily_loss_limit", f"Daily PnL {daily_pnl:.2f} <= -{daily_loss_limit:.2f}")

    hours = authority.get("trading_hours_et", {})
    if now_et and hours and not hours.get("allow_extended", False):
        open_t = _parse_time(str(hours["open"]))
        close_t = _parse_time(str(hours["close"]))
        if not (open_t <= now_et.time() <= close_t):
            return Verdict("REFUSE", "trading_hours", "Attempt outside configured trading hours")

    ticket_threshold = float(policy.raw.get("human_ticket_required_above", {}).get("order_notional_usd", 0) or 0)
    if ticket_threshold and order_notional >= ticket_threshold:
        return Verdict("REQUIRE_TICKET", "ticket_required", f"Order notional {order_notional:.2f} requires human ticket")

    return Verdict("ALLOW", "policy_pass", "All deterministic checks passed")
