from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from .paper_forward import PaperPosition
from .stop_enforcement import DailyBar, parse_source_date, parse_stop_rule, fetch_yahoo_daily_bars


@dataclass(frozen=True)
class TargetRule:
    status: str
    raw: str
    trigger: str
    price: str
    reason: str


@dataclass(frozen=True)
class LiveEligibilityResult:
    key: str
    trader: str
    ticker: str
    direction: str
    status: str
    entry_date: str
    end_date: str
    live_eligible: str
    stop_status: str
    stop_raw: str
    stop_trigger: str
    stop_price: str
    target_status: str
    target_raw: str
    target_trigger: str
    target_price: str
    discipline_outcome: str
    outcome_date: str
    outcome_bar_high: str
    outcome_bar_low: str
    source: str
    fetched_at: str
    reason: str


def _norm(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def _numbers(text: str) -> list[float]:
    return [float(value) for value in re.findall(r"(?<![\w.])(\d+(?:\.\d+)?)(?![\w.])", text)]


def _target_fragment(commentary: str) -> str:
    text = _norm(commentary)
    patterns = [
        r"\bTP\s+(.+?)(?=\bSL\b|\bstop\b|[,;]|$)",
        r"\btarget(?:ing)?\s+(.+?)(?=\bSL\b|\bstop\b|[,;]|$)",
    ]
    for pattern in patterns:
        found = re.search(pattern, text, flags=re.IGNORECASE)
        if found:
            return _norm(found.group(0))
    return ""


def parse_target_rule(position: PaperPosition) -> TargetRule:
    entry = position.events[0] if position.events else {}
    commentary = _norm(entry.get("commentary", ""))
    fragment = _target_fragment(commentary)
    if not fragment:
        return TargetRule("NO_TARGET_FOUND", "", "", "", "entry commentary has no target phrase")

    values = _numbers(fragment)
    if not values:
        lowered = fragment.lower()
        if any(token in lowered for token in ("fvg", "ema", "vwap", "lod", "hod", "breakout", "support", "resistance")):
            return TargetRule(
                "UNENFORCEABLE_TARGET",
                fragment,
                "",
                "",
                "target depends on semantic or indicator data not available in daily underlying bars",
            )
        return TargetRule("NO_NUMERIC_TARGET", fragment, "", "", "target phrase has no parseable numeric level")

    direction = position.direction.lower()
    if "put" in direction:
        trigger = "below"
        price = max(values)
    elif "call" in direction or "equity" in direction or "shares" in direction:
        trigger = "above"
        price = min(values)
    else:
        return TargetRule("NO_TRIGGER_DIRECTION", fragment, "", f"{values[0]:g}", "numeric target exists but trigger direction is ambiguous")

    return TargetRule("ENFORCEABLE", fragment, trigger, f"{price:g}", "numeric underlying target can be checked against daily bars")


def _close_date(position: PaperPosition) -> date | None:
    if not position.closed_row:
        return None
    for event in position.events:
        if event.get("source_row") == position.closed_row:
            return parse_source_date(event.get("date", ""))
    return None


def _end_date(position: PaperPosition) -> date | None:
    closed = _close_date(position)
    if closed:
        return closed
    if position.expiry_date:
        return date.fromisoformat(position.expiry_date)
    return None


def _crossed(bar: DailyBar, trigger: str, price: float) -> bool:
    return bar.high >= price if trigger == "above" else bar.low <= price


def evaluate_position_eligibility(position: PaperPosition, *, bars: list[DailyBar], source: str = "", fetched_at: str = "") -> LiveEligibilityResult:
    entry = position.events[0] if position.events else {}
    entry_date = parse_source_date(entry.get("date", ""))
    end_date = _end_date(position)
    stop = parse_stop_rule(position)
    target = parse_target_rule(position)
    base_reason_parts: list[str] = []

    if position.intent_verdict != "PAPER_READY":
        base_reason_parts.append("not PAPER_READY")
    if stop.status != "ENFORCEABLE":
        base_reason_parts.append(stop.reason)
    if target.status != "ENFORCEABLE":
        base_reason_parts.append(target.reason)
    if entry_date is None or end_date is None:
        base_reason_parts.append("missing entry or end date")

    if base_reason_parts:
        return LiveEligibilityResult(
            key=position.key,
            trader=position.trader,
            ticker=position.ticker,
            direction=position.direction,
            status=position.status,
            entry_date="" if entry_date is None else entry_date.isoformat(),
            end_date="" if end_date is None else end_date.isoformat(),
            live_eligible="no",
            stop_status=stop.status,
            stop_raw=stop.raw,
            stop_trigger=stop.trigger,
            stop_price=stop.price,
            target_status=target.status,
            target_raw=target.raw,
            target_trigger=target.trigger,
            target_price=target.price,
            discipline_outcome="EXCLUDED",
            outcome_date="",
            outcome_bar_high="",
            outcome_bar_low="",
            source=source,
            fetched_at=fetched_at,
            reason="; ".join(base_reason_parts),
        )

    stop_price = float(stop.price)
    target_price = float(target.price)
    for bar in bars:
        stop_hit = _crossed(bar, stop.trigger, stop_price)
        target_hit = _crossed(bar, target.trigger, target_price)
        if stop_hit and target_hit:
            outcome = "AMBIGUOUS_SAME_DAY"
        elif target_hit:
            outcome = "TARGET_FIRST"
        elif stop_hit:
            outcome = "STOP_FIRST"
        else:
            continue
        return LiveEligibilityResult(
            key=position.key,
            trader=position.trader,
            ticker=position.ticker,
            direction=position.direction,
            status=position.status,
            entry_date=entry_date.isoformat(),
            end_date=end_date.isoformat(),
            live_eligible="yes",
            stop_status=stop.status,
            stop_raw=stop.raw,
            stop_trigger=stop.trigger,
            stop_price=stop.price,
            target_status=target.status,
            target_raw=target.raw,
            target_trigger=target.trigger,
            target_price=target.price,
            discipline_outcome=outcome,
            outcome_date=bar.date,
            outcome_bar_high=f"{bar.high:.4f}",
            outcome_bar_low=f"{bar.low:.4f}",
            source=source,
            fetched_at=fetched_at,
            reason="daily underlying bars show first discipline event",
        )

    return LiveEligibilityResult(
        key=position.key,
        trader=position.trader,
        ticker=position.ticker,
        direction=position.direction,
        status=position.status,
        entry_date=entry_date.isoformat(),
        end_date=end_date.isoformat(),
        live_eligible="yes",
        stop_status=stop.status,
        stop_raw=stop.raw,
        stop_trigger=stop.trigger,
        stop_price=stop.price,
        target_status=target.status,
        target_raw=target.raw,
        target_trigger=target.trigger,
        target_price=target.price,
        discipline_outcome="NEITHER_BY_END",
        outcome_date="",
        outcome_bar_high="",
        outcome_bar_low="",
        source=source,
        fetched_at=fetched_at,
        reason="neither stop nor target crossed by close/expiry endpoint",
    )


def evaluate_live_eligible_positions(
    positions: list[PaperPosition],
    *,
    fetch_bars=fetch_yahoo_daily_bars,
) -> list[LiveEligibilityResult]:
    rows: list[LiveEligibilityResult] = []
    for position in positions:
        if position.intent_verdict != "PAPER_READY":
            rows.append(evaluate_position_eligibility(position, bars=[]))
            continue
        entry = position.events[0] if position.events else {}
        entry_date = parse_source_date(entry.get("date", ""))
        end_date = _end_date(position)
        if entry_date is None or end_date is None:
            rows.append(evaluate_position_eligibility(position, bars=[]))
            continue
        bars, source, fetched_at = fetch_bars(position.ticker, entry_date, end_date)
        rows.append(evaluate_position_eligibility(position, bars=bars, source=source, fetched_at=fetched_at))
    return rows
