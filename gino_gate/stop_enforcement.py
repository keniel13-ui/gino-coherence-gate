from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from .paper_forward import PaperPosition


@dataclass(frozen=True)
class DailyBar:
    date: str
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class StopRule:
    status: str
    raw: str
    trigger: str
    price: str
    reason: str


@dataclass(frozen=True)
class StopEnforcement:
    key: str
    trader: str
    ticker: str
    direction: str
    expiry_date: str
    entry_date: str
    stop_status: str
    stop_raw: str
    stop_trigger: str
    stop_price: str
    triggered_date: str
    triggered_bar_high: str
    triggered_bar_low: str
    source: str
    fetched_at: str
    reason: str


def _norm(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def parse_source_date(value: str) -> date | None:
    raw = _norm(value)
    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _stop_level_number(text: str) -> float | None:
    numbers = re.findall(r"(?<![\w.])(\d+(?:\.\d+)?)(?![\w.])", text)
    if not numbers:
        return None
    # Stop fragments can include dates like "3/16 high 189"; the level is the final number.
    return float(numbers[-1])


def _stop_fragment(commentary: str) -> str:
    text = _norm(commentary)
    patterns = [
        r"\brisk off above\s+([^;,]+)",
        r"\bSL\s+([^;,]+)",
        r"\bstop(?: loss)?\s*:?\s*([^;,]+)",
    ]
    for pattern in patterns:
        found = re.search(pattern, text, flags=re.IGNORECASE)
        if found:
            return _norm(found.group(0))
    return ""


def parse_stop_rule(position: PaperPosition) -> StopRule:
    entry = position.events[0] if position.events else {}
    commentary = _norm(entry.get("commentary", ""))
    fragment = _stop_fragment(commentary)
    if not fragment:
        return StopRule("NO_STOP_FOUND", "", "", "", "entry commentary has no stop phrase")

    lowered = fragment.lower()
    if any(token in lowered for token in ("daily", "lod", "es1", "ema", "vwap", "close under")):
        return StopRule(
            "UNENFORCEABLE_STOP",
            fragment,
            "",
            "",
            "stop depends on semantic, intraday, indicator, or cross-instrument data not available in daily underlying bars",
        )

    price = _stop_level_number(fragment)
    if price is None:
        return StopRule("NO_NUMERIC_STOP", fragment, "", "", "stop phrase has no parseable numeric level")

    direction = position.direction.lower()
    if "above" in lowered or "+" in lowered:
        trigger = "above"
    elif "under" in lowered or "sub" in lowered or "below" in lowered:
        trigger = "below"
    elif "put" in direction:
        trigger = "above"
    elif "call" in direction:
        trigger = "below"
    else:
        trigger = "unknown"

    if trigger == "unknown":
        return StopRule("NO_TRIGGER_DIRECTION", fragment, "", f"{price:g}", "numeric stop exists but trigger direction is ambiguous")
    return StopRule("ENFORCEABLE", fragment, trigger, f"{price:g}", "numeric underlying stop can be checked against daily bars")


def yahoo_chart_url(symbol: str, start_date: date, end_date: date) -> str:
    start = int(datetime(start_date.year, start_date.month, start_date.day, tzinfo=UTC).timestamp()) - 86400
    end = int(datetime(end_date.year, end_date.month, end_date.day, tzinfo=UTC).timestamp()) + 2 * 86400
    return f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?period1={start}&period2={end}&interval=1d"


def fetch_yahoo_daily_bars(symbol: str, start_date: date, end_date: date) -> tuple[list[DailyBar], str, str]:
    url = yahoo_chart_url(symbol, start_date, end_date)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=25) as response:
        payload = json.loads(response.read().decode("utf-8"))
    result = payload["chart"]["result"][0]
    timestamps = result.get("timestamp") or []
    quote = result["indicators"]["quote"][0]
    bars: list[DailyBar] = []
    for ts, high, low, close in zip(timestamps, quote.get("high") or [], quote.get("low") or [], quote.get("close") or []):
        if high is None or low is None or close is None:
            continue
        bar_date = datetime.fromtimestamp(ts, UTC).date()
        if start_date <= bar_date <= end_date:
            bars.append(DailyBar(bar_date.isoformat(), float(high), float(low), float(close)))
    return bars, url, datetime.now(UTC).isoformat()


def enforce_stop(position: PaperPosition, *, bars: list[DailyBar], source: str = "", fetched_at: str = "") -> StopEnforcement:
    entry = position.events[0] if position.events else {}
    entry_date = parse_source_date(entry.get("date", ""))
    rule = parse_stop_rule(position)
    if rule.status != "ENFORCEABLE":
        return StopEnforcement(
            key=position.key,
            trader=position.trader,
            ticker=position.ticker,
            direction=position.direction,
            expiry_date=position.expiry_date,
            entry_date="" if entry_date is None else entry_date.isoformat(),
            stop_status=rule.status,
            stop_raw=rule.raw,
            stop_trigger=rule.trigger,
            stop_price=rule.price,
            triggered_date="",
            triggered_bar_high="",
            triggered_bar_low="",
            source=source,
            fetched_at=fetched_at,
            reason=rule.reason,
        )

    stop_price = float(rule.price)
    for bar in bars:
        triggered = bar.high >= stop_price if rule.trigger == "above" else bar.low <= stop_price
        if triggered:
            return StopEnforcement(
                key=position.key,
                trader=position.trader,
                ticker=position.ticker,
                direction=position.direction,
                expiry_date=position.expiry_date,
                entry_date="" if entry_date is None else entry_date.isoformat(),
                stop_status="STOP_TRIGGERED",
                stop_raw=rule.raw,
                stop_trigger=rule.trigger,
                stop_price=rule.price,
                triggered_date=bar.date,
                triggered_bar_high=f"{bar.high:.4f}",
                triggered_bar_low=f"{bar.low:.4f}",
                source=source,
                fetched_at=fetched_at,
                reason="daily underlying bar crossed the stated stop level before expiry",
            )

    return StopEnforcement(
        key=position.key,
        trader=position.trader,
        ticker=position.ticker,
        direction=position.direction,
        expiry_date=position.expiry_date,
        entry_date="" if entry_date is None else entry_date.isoformat(),
        stop_status="STOP_NOT_TRIGGERED",
        stop_raw=rule.raw,
        stop_trigger=rule.trigger,
        stop_price=rule.price,
        triggered_date="",
        triggered_bar_high="",
        triggered_bar_low="",
        source=source,
        fetched_at=fetched_at,
        reason="daily underlying bars did not cross the stated stop level before expiry",
    )


def enforce_expired_no_close_stops(
    positions: list[PaperPosition],
    *,
    fetch_bars=fetch_yahoo_daily_bars,
) -> list[StopEnforcement]:
    rows: list[StopEnforcement] = []
    for position in positions:
        if position.status != "EXPIRED_NO_CLOSE" or position.intent_verdict != "PAPER_READY":
            continue
        entry = position.events[0] if position.events else {}
        entry_date = parse_source_date(entry.get("date", ""))
        if entry_date is None or not position.expiry_date:
            rows.append(
                StopEnforcement(
                    key=position.key,
                    trader=position.trader,
                    ticker=position.ticker,
                    direction=position.direction,
                    expiry_date=position.expiry_date,
                    entry_date="",
                    stop_status="MISSING_DATE",
                    stop_raw="",
                    stop_trigger="",
                    stop_price="",
                    triggered_date="",
                    triggered_bar_high="",
                    triggered_bar_low="",
                    source="",
                    fetched_at="",
                    reason="entry date or expiry date is missing, so stop cannot be checked",
                )
            )
            continue
        expiry = date.fromisoformat(position.expiry_date)
        bars, source, fetched_at = fetch_bars(position.ticker, entry_date, expiry)
        rows.append(enforce_stop(position, bars=bars, source=source, fetched_at=fetched_at))
    return rows
