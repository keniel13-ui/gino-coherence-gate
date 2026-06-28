from __future__ import annotations

import re
from datetime import date, datetime
from dataclasses import asdict, dataclass, field

from .trade_intent import parse_option_leg
from .trade_intent import propose_trade_intent


@dataclass
class PaperPosition:
    key: str
    trader: str
    ticker: str
    direction: str
    status: str
    opened_row: str
    closed_row: str | None = None
    expiry_date: str = ""
    intent_verdict: str = ""
    intent_reason: str = ""
    last_event_type: str = ""
    last_pnl_pct: str = ""
    last_pnl_dollars: str = ""
    event_count: int = 0
    events: list[dict[str, str]] = field(default_factory=list)


def _norm(value: str | None) -> str:
    return (value or "").strip()


def _key(row: dict[str, str]) -> str:
    contract_key = "shares"
    leg = parse_option_leg(_norm(row.get("Contract / Fill")))
    if leg:
        expiry = _expiry_date(row)
        expiry_key = expiry.isoformat() if expiry else leg.expiry
        contract_key = f"{expiry_key}|{leg.strike:g}|{leg.option_type}"
    elif _norm(row.get("Contract / Fill")):
        contract_key = re.sub(r"\s+", " ", _norm(row.get("Contract / Fill")).lower())
    return "|".join([
        _norm(row.get("Trader")),
        _norm(row.get("Ticker")).upper(),
        _norm(row.get("Direction")).lower(),
        contract_key,
    ])


def _is_entry(row: dict[str, str]) -> bool:
    return "ENTRY" in _norm(row.get("Event Type")).upper()


def _is_close(row: dict[str, str]) -> bool:
    event = _norm(row.get("Event Type")).upper()
    return any(term in event for term in ("FINAL", "CLOSE", "EXIT"))


def _row_year(row: dict[str, str]) -> int | None:
    raw = _norm(row.get("Date"))
    match = re.search(r"/(\d{2,4})$", raw)
    if not match:
        return None
    year = int(match.group(1))
    return 2000 + year if year < 100 else year


def _expiry_date(row: dict[str, str]) -> date | None:
    leg = parse_option_leg(_norm(row.get("Contract / Fill")))
    if not leg:
        return None
    expiry = leg.expiry
    year = _row_year(row) or date.today().year
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%d %b %Y", "%d %b %y"):
        candidate = expiry
        if fmt in {"%m/%d/%Y", "%m/%d/%y"} and expiry.count("/") == 1:
            candidate = f"{expiry}/{year}"
            fmt = "%m/%d/%Y"
        try:
            return datetime.strptime(candidate.title(), fmt).date()
        except ValueError:
            continue
    return None


def _tracked_event(row: dict[str, str]) -> dict[str, str]:
    return {
        "source_row": _norm(row.get("#")),
        "date": _norm(row.get("Date")),
        "time": _norm(row.get("Time")),
        "event_type": _norm(row.get("Event Type")),
        "pnl_pct": _norm(row.get("P/L %")),
        "pnl_dollars": _norm(row.get("P/L $")),
        "commentary": _norm(row.get("Trader Commentary")),
    }


def replay_rows(rows: list[dict[str, str]], *, as_of: date | None = None) -> list[PaperPosition]:
    positions: dict[str, PaperPosition] = {}
    closed: list[PaperPosition] = []

    for row in rows:
        key = _key(row)
        event = _tracked_event(row)

        if _is_entry(row):
            intent = propose_trade_intent(row, mode="paper")
            if intent.verdict == "BLOCK":
                continue
            expiry = _expiry_date(row)
            positions[key] = PaperPosition(
                key=key,
                trader=_norm(row.get("Trader")),
                ticker=_norm(row.get("Ticker")).upper(),
                direction=_norm(row.get("Direction")),
                status="OPEN" if intent.verdict in {"PAPER_READY", "PAPER_ONLY"} else "NEEDS_REVIEW",
                opened_row=_norm(row.get("#")),
                expiry_date="" if expiry is None else expiry.isoformat(),
                intent_verdict=intent.verdict,
                intent_reason=intent.reason,
                last_event_type=_norm(row.get("Event Type")),
                event_count=1,
                events=[event],
            )
            continue

        position = positions.get(key)
        if position is None:
            if _is_close(row):
                closed.append(
                    PaperPosition(
                        key=key,
                        trader=_norm(row.get("Trader")),
                        ticker=_norm(row.get("Ticker")).upper(),
                        direction=_norm(row.get("Direction")),
                        status="UNTRACKED_CLOSE_NO_ENTRY",
                        opened_row="",
                        closed_row=_norm(row.get("#")),
                        last_event_type=_norm(row.get("Event Type")),
                        last_pnl_pct=_norm(row.get("P/L %")),
                        last_pnl_dollars=_norm(row.get("P/L $")),
                        event_count=1,
                        events=[event],
                    )
                )
            continue

        position.events.append(event)
        position.event_count += 1
        position.last_event_type = _norm(row.get("Event Type"))
        if _norm(row.get("P/L %")):
            position.last_pnl_pct = _norm(row.get("P/L %"))
        if _norm(row.get("P/L $")):
            position.last_pnl_dollars = _norm(row.get("P/L $"))
        if _is_close(row):
            position.status = "CLOSED"
            position.closed_row = _norm(row.get("#"))
            closed.append(position)
            positions.pop(key, None)

    remaining = list(positions.values())
    if as_of is not None:
        for position in remaining:
            if position.status != "OPEN" or not position.expiry_date:
                continue
            if date.fromisoformat(position.expiry_date) < as_of:
                position.status = "EXPIRED_NO_CLOSE"

    return closed + remaining


def positions_as_dicts(positions: list[PaperPosition]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for position in positions:
        body = asdict(position)
        body.pop("events", None)
        rows.append({key: "" if value is None else str(value) for key, value in body.items()})
    return rows
