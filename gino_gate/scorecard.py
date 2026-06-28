from __future__ import annotations

import re
from dataclasses import dataclass

from .paper_forward import PaperPosition


@dataclass(frozen=True)
class ScorecardRow:
    key: str
    trader: str
    ticker: str
    direction: str
    status: str
    agent_takeable: str
    score_status: str
    realized_return_pct: str
    return_quality: str
    reason: str


def parse_reported_pct(value: str) -> float | None:
    raw = (value or "").strip()
    if not raw:
        return None
    has_percent = "%" in raw
    text = raw.replace("%", "").replace(",", "").strip()
    try:
        parsed = float(text)
    except ValueError:
        return None
    if not has_percent and abs(parsed) <= 10:
        return None
    return parsed


def _fraction_from_text(text: str) -> float | None:
    lowered = text.lower()
    if any(phrase in lowered for phrase in ("all but 1", "runner", "hold 1")):
        return None
    if re.search(r"\b(half|1/2)\b", lowered):
        return 0.5
    if re.search(r"\b(1/3|third)\b", lowered):
        return 1 / 3
    if re.search(r"\b(2/3|two thirds|2 thirds)\b", lowered):
        return 2 / 3
    return None


def _is_trim(event_type: str) -> bool:
    event = event_type.upper()
    return any(term in event for term in ("TRIM", "SELL"))


def _is_final(event_type: str) -> bool:
    event = event_type.upper()
    return any(term in event for term in ("FINAL", "CLOSE", "EXIT"))


def trim_aware_realized_pct(position: PaperPosition) -> tuple[float | None, str, str]:
    if position.status != "CLOSED":
        return None, "not_realized", f"{position.status} is not a realized closed trade"

    remaining = 1.0
    realized = 0.0
    used_any = False
    unknown_trim = False

    for event in position.events:
        event_type = event.get("event_type", "")
        pct = parse_reported_pct(event.get("pnl_pct", ""))
        if pct is None:
            continue

        if _is_final(event_type):
            fraction = remaining
        elif _is_trim(event_type):
            fraction = _fraction_from_text(" ".join([event_type, event.get("commentary", "")]))
            if fraction is None:
                unknown_trim = True
                continue
            fraction = min(fraction, remaining)
        else:
            continue

        realized += fraction * pct
        remaining = max(0.0, remaining - fraction)
        used_any = True

    if not used_any:
        return None, "unknown", "no parseable realized trim/final P/L percentage"
    if unknown_trim:
        return realized, "partial_estimate", "some trim fractions were missing or ambiguous"
    if remaining > 0.001:
        return realized, "partial_estimate", f"{remaining:.2%} of position has no realized exit fraction"
    return realized, "estimated", "trim-aware realized return from explicit trim/final events"


def score_positions(positions: list[PaperPosition]) -> list[ScorecardRow]:
    rows: list[ScorecardRow] = []
    for position in positions:
        agent_takeable = position.intent_verdict == "PAPER_READY"
        realized, quality, reason = trim_aware_realized_pct(position)
        if not agent_takeable:
            score_status = "EXCLUDED_NOT_AGENT_TAKEABLE"
            realized = None
            quality = "excluded"
            reason = "position was not PAPER_READY, so it is not credited to the agent scorecard"
        elif position.status == "EXPIRED_NO_CLOSE":
            score_status = "NEEDS_PRICE_SETTLEMENT"
            reason = "expired without captured close; settle against external price data before scoring"
        elif position.status != "CLOSED":
            score_status = "NOT_REALIZED"
        elif realized is None:
            score_status = "UNSCORED_DIRTY_OR_INCOMPLETE_PNL"
        else:
            score_status = "SCORED"

        rows.append(
            ScorecardRow(
                key=position.key,
                trader=position.trader,
                ticker=position.ticker,
                direction=position.direction,
                status=position.status,
                agent_takeable="yes" if agent_takeable else "no",
                score_status=score_status,
                realized_return_pct="" if realized is None else f"{realized:.2f}",
                return_quality=quality,
                reason=reason,
            )
        )
    return rows
