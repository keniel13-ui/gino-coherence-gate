from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from .scoring_policy import ScoringPolicy


@dataclass(frozen=True)
class Bar:
    ts: datetime
    open: float
    high: float
    low: float
    close: float


def parse_ts(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def normalize_bars(raw_bars: list[dict[str, Any] | Bar]) -> list[Bar]:
    bars: list[Bar] = []
    for raw in raw_bars:
        if isinstance(raw, Bar):
            bars.append(raw)
        else:
            bars.append(Bar(
                ts=parse_ts(raw["ts"]),
                open=float(raw["open"]),
                high=float(raw["high"]),
                low=float(raw["low"]),
                close=float(raw["close"]),
            ))
    return sorted(bars, key=lambda bar: bar.ts)


def _slip(price: float, bps: float, *, side: str, entry: bool) -> float:
    adjustment = bps / 10000.0
    if side == "buy":
        return price * (1 + adjustment) if entry else price * (1 - adjustment)
    return price * (1 - adjustment) if entry else price * (1 + adjustment)


def _direction(side: str) -> int:
    if side == "buy":
        return 1
    if side == "sell":
        return -1
    raise ValueError(f"unsupported side: {side}")


def position_notional(policy: ScoringPolicy, sizing: dict[str, Any], rule: dict[str, Any]) -> float:
    kind = sizing.get("kind")
    cap = float(sizing.get("max_notional_usd", policy.raw.get("caps", {}).get("max_position_per_symbol_usd", 0)) or 0)
    if kind == "fixed_notional":
        notional = float(sizing["notional_usd"])
        return min(notional, cap) if cap else notional

    if kind == "risk_pct_of_equity":
        stop_pct = effective_stop_pct(rule)
        if stop_pct is None:
            if rule.get("allow_no_stop_sizing_cap"):
                return float(sizing.get("fallback_notional_usd", cap) or cap)
            return 0.0
        risk_dollars = policy.account_equity_usd * (float(sizing["risk_pct"]) / 100.0)
        notional = risk_dollars / (abs(float(stop_pct)) / 100.0)
        max_notional = cap or float(sizing.get("max_notional_usd", notional))
        return min(notional, max_notional)

    raise ValueError(f"unsupported sizing kind: {kind}")


def effective_stop_pct(rule: dict[str, Any]) -> float | None:
    if rule.get("stop_pct") is not None:
        return float(rule["stop_pct"])
    if rule.get("stop_kind") == "atr":
        # ATR stop distance is computed from price data in a later adapter.
        # For frozen-policy sizing, reserve risk math with a conservative
        # placeholder until the ATR data adapter supplies per-symbol ATR.
        return -15.0
    if rule.get("stop_kind") == "atr_trailing":
        return -15.0
    return None


def simulate_signal(
    signal: dict[str, Any],
    raw_bars: list[dict[str, Any] | Bar],
    policy: ScoringPolicy,
    *,
    rule_name: str,
    sizing_name: str,
) -> dict[str, Any]:
    bars = normalize_bars(raw_bars)
    rule = policy.rule_variant(rule_name)
    sizing = policy.sizing_variant(sizing_name)
    posted_at = parse_ts(signal["posted_at"])
    captured_at = parse_ts(signal.get("captured_at", signal["posted_at"]))
    entry_after = posted_at + timedelta(seconds=float(policy.raw.get("entry_latency_sec", 0) or 0))
    side = str(signal.get("side", "buy")).lower()
    direction = _direction(side)

    if not bars:
        return _excluded_record(signal, policy, rule_name, sizing_name, "no price data")

    entry_index = next((idx for idx, bar in enumerate(bars) if bar.ts >= entry_after), None)
    if entry_index is None:
        return _excluded_record(signal, policy, rule_name, sizing_name, "no price data after entry latency")

    fees = policy.raw.get("fees_model", {})
    slippage_bps = float(fees.get("slippage_bps", 0) or 0)
    per_trade_fee = float(fees.get("per_trade_usd", 0) or 0)
    entry_bar = bars[entry_index]
    entry_base = entry_bar.open
    entry_price = _slip(entry_base, slippage_bps, side=side, entry=True)
    notional = position_notional(policy, sizing, rule)
    if notional <= 0:
        return _excluded_record(signal, policy, rule_name, sizing_name, "sizing requires stop")

    late_call = _late_call(signal, entry_base, policy, direction)
    take_profit_pct = None if rule.get("take_profit_pct") is None else float(rule["take_profit_pct"])
    stop_pct = effective_stop_pct(rule)
    time_stop_sec = rule.get("time_stop_sec")
    tp_price = None if take_profit_pct is None else entry_price * (1 + direction * take_profit_pct / 100.0)
    stop_price = None if stop_pct is None else entry_price * (1 + direction * abs(float(stop_pct)) / -100.0)
    if side == "sell" and stop_pct is not None:
        stop_price = entry_price * (1 + abs(float(stop_pct)) / 100.0)

    mfe_pct = -math.inf
    mae_pct = math.inf
    exit_bar = bars[-1]
    exit_base = bars[-1].close
    exit_reason = "end_of_path"

    for bar in bars[entry_index:]:
        if side == "buy":
            mfe_pct = max(mfe_pct, (bar.high - entry_price) / entry_price * 100.0)
            mae_pct = min(mae_pct, (bar.low - entry_price) / entry_price * 100.0)
            stop_hit = stop_price is not None and bar.low <= stop_price
            tp_hit = tp_price is not None and bar.high >= tp_price
        else:
            mfe_pct = max(mfe_pct, (entry_price - bar.low) / entry_price * 100.0)
            mae_pct = min(mae_pct, (entry_price - bar.high) / entry_price * 100.0)
            stop_hit = stop_price is not None and bar.high >= stop_price
            tp_hit = tp_price is not None and bar.low <= tp_price

        if stop_hit:
            exit_bar = bar
            exit_base = float(stop_price)
            exit_reason = "stop"
            break
        if tp_hit:
            exit_bar = bar
            exit_base = float(tp_price)
            exit_reason = "take_profit"
            break
        if time_stop_sec is not None and (bar.ts - entry_bar.ts).total_seconds() >= float(time_stop_sec):
            exit_bar = bar
            exit_base = bar.close
            exit_reason = "time_stop"
            break

    exit_price = _slip(exit_base, slippage_bps, side=side, entry=False)
    gross_return_pct = direction * (exit_base - entry_base) / entry_base * 100.0
    net_return_pct_before_fees = direction * (exit_price - entry_price) / entry_price * 100.0
    gross_pnl_usd = notional * gross_return_pct / 100.0
    net_pnl_usd = notional * net_return_pct_before_fees / 100.0 - (per_trade_fee * 2)
    net_return_pct = net_pnl_usd / notional * 100.0

    return {
        "signal_id": str(signal["signal_id"]),
        "source": str(signal.get("source", "unknown")),
        "symbol": str(signal["symbol"]).upper(),
        "side": side,
        "posted_at": posted_at.isoformat().replace("+00:00", "Z"),
        "captured_at": captured_at.isoformat().replace("+00:00", "Z"),
        "rule_variant": rule_name,
        "sizing_variant": sizing_name,
        "entry": {
            "ts": entry_bar.ts.isoformat().replace("+00:00", "Z"),
            "price": round(entry_price, 6),
            "base_price": round(entry_base, 6),
            "latency_sec": policy.raw.get("entry_latency_sec", 0),
            "fees_usd": per_trade_fee,
            "slippage_bps": slippage_bps,
            "notional_usd": round(notional, 2),
        },
        "exit": {
            "ts": exit_bar.ts.isoformat().replace("+00:00", "Z"),
            "price": round(exit_price, 6),
            "base_price": round(exit_base, 6),
            "reason": exit_reason,
            "fees_usd": per_trade_fee,
        },
        "path": {
            "mfe_pct": round(mfe_pct if mfe_pct != -math.inf else 0.0, 6),
            "mae_pct": round(mae_pct if mae_pct != math.inf else 0.0, 6),
        },
        "outcome": {
            "gross_return_pct": round(gross_return_pct, 6),
            "net_return_pct": round(net_return_pct, 6),
            "gross_pnl_usd": round(gross_pnl_usd, 6),
            "net_pnl_usd": round(net_pnl_usd, 6),
            "win": net_pnl_usd > 0,
            "hold_sec": int((exit_bar.ts - entry_bar.ts).total_seconds()),
        },
        "detectors": {
            "late_call": late_call["late_call"],
            "pre_entry_move_pct": round(late_call["pre_entry_move_pct"], 6),
        },
        "settled": True,
        "excluded": False,
        "exclusion_reason": None,
    }


def _late_call(signal: dict[str, Any], entry_base: float, policy: ScoringPolicy, direction: int) -> dict[str, Any]:
    posted_price = signal.get("posted_price")
    if posted_price is None:
        return {"late_call": False, "pre_entry_move_pct": 0.0}
    posted = float(posted_price)
    move = direction * (entry_base - posted) / posted * 100.0
    threshold = float(policy.raw.get("late_call_detector", {}).get("max_move_pct_before_entry", 0) or 0)
    return {"late_call": threshold > 0 and move > threshold, "pre_entry_move_pct": move}


def _excluded_record(signal: dict[str, Any], policy: ScoringPolicy, rule_name: str, sizing_name: str, reason: str) -> dict[str, Any]:
    posted_at = parse_ts(signal["posted_at"])
    captured_at = parse_ts(signal.get("captured_at", signal["posted_at"]))
    return {
        "signal_id": str(signal["signal_id"]),
        "source": str(signal.get("source", "unknown")),
        "symbol": str(signal.get("symbol", "")).upper(),
        "side": str(signal.get("side", "buy")).lower(),
        "posted_at": posted_at.isoformat().replace("+00:00", "Z"),
        "captured_at": captured_at.isoformat().replace("+00:00", "Z"),
        "rule_variant": rule_name,
        "sizing_variant": sizing_name,
        "entry": None,
        "exit": None,
        "path": None,
        "outcome": None,
        "detectors": {},
        "settled": False,
        "excluded": True,
        "exclusion_reason": reason,
        "policy_hash": policy.policy_hash,
    }
