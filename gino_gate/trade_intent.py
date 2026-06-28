from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


ENTRY_TERMS = ("ENTRY", "NEW TRADE", "ADD")
LIVE_DISABLED_DETAIL = "live Robinhood execution disabled until paper-forward proof and explicit approval boundary exist"


@dataclass(frozen=True)
class OptionLeg:
    expiry: str
    strike: float
    option_type: str
    entry_price: float | None


@dataclass(frozen=True)
class TradeIntent:
    verdict: str
    action: str
    trader: str
    ticker: str
    reason: str
    instrument: str | None = None
    robinhood_tool: str | None = None
    order_args: dict[str, Any] | None = None


def _norm(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def _is_entry(row: dict[str, str]) -> bool:
    event = _norm(row.get("Event Type")).upper()
    return any(term in event for term in ENTRY_TERMS)


def _direction(row: dict[str, str]) -> str:
    raw = _norm(row.get("Direction")).lower()
    if "put" in raw:
        return "put"
    if "call" in raw:
        return "call"
    if "equity" in raw or "shares" in raw:
        return "equity"
    return raw or "unknown"


def parse_option_leg(contract: str) -> OptionLeg | None:
    text = re.sub(r"\(\+?[-0-9, ]+\)", "", _norm(contract)).strip()
    lowered = text.lower()
    if not text or "spread" in lowered or "+" in text or "sold " in lowered or "bought " in lowered or "credit" in lowered:
        return None

    patterns = [
        # 150p 5/15 @2.62, 450p 1/30 @4.33
        r"(?P<strike>\d+(?:\.\d+)?)\s*(?P<kind>[cCpP])\s+(?P<expiry>\d{1,2}/\d{1,2}(?:/\d{2,4})?)(?:\s*@\s*(?P<price>\d*(?:\.\d+)?))?",
        # 6/18 $420c @5.98, 2/20 $11p @$140 credit
        r"(?P<expiry>\d{1,2}/\d{1,2}(?:/\d{2,4})?)\s+\$?(?P<strike>\d+(?:\.\d+)?)\s*(?P<kind>[cCpP])(?:\s*@\$?\s*(?P<price>\d*(?:\.\d+)?))?",
        # 20 MAR 26 70C
        r"(?P<expiry>\d{1,2}\s+[A-Za-z]{3}\s+\d{2,4})\s+(?P<strike>\d+(?:\.\d+)?)\s*(?P<kind>[cCpP])",
    ]
    for pattern in patterns:
        found = re.search(pattern, text)
        if not found:
            continue
        price = found.groupdict().get("price")
        return OptionLeg(
            expiry=_norm(found.group("expiry")),
            strike=float(found.group("strike")),
            option_type="call" if found.group("kind").lower() == "c" else "put",
            entry_price=float(price) if price and price != "." else None,
        )
    return None


def _extract_stop(commentary: str) -> str | None:
    text = _norm(commentary)
    patterns = [
        r"\bSL\s+(?P<stop>[^;,]+)",
        r"\bstop(?: loss)?\s*:?\s*(?P<stop>[^;,]+)",
        r"\brisk off above\s+(?P<stop>[^;,]+)",
    ]
    for pattern in patterns:
        found = re.search(pattern, text, flags=re.IGNORECASE)
        if found:
            return _norm(found.group("stop"))
    return None


def _risk_units(commentary: str) -> str | None:
    found = re.search(r"\b(?P<risk>(?:half\s+)?\d+(?:\.\d+)?R|half R|small position|lotto)\b", commentary, flags=re.IGNORECASE)
    return _norm(found.group("risk")) if found else None


def propose_trade_intent(row: dict[str, str], *, mode: str = "paper") -> TradeIntent:
    trader = _norm(row.get("Trader"))
    ticker = _norm(row.get("Ticker")).upper()
    contract = _norm(row.get("Contract / Fill"))
    commentary = _norm(row.get("Trader Commentary"))

    if not _is_entry(row):
        return TradeIntent(
            verdict="BLOCK",
            action="log_only",
            trader=trader,
            ticker=ticker,
            reason="not an entry event",
        )

    direction = _direction(row)
    event = _norm(row.get("Event Type")).lower()
    lowered_contract = contract.lower()
    if "sell-to-open" in event or "credit" in lowered_contract or "sold " in lowered_contract:
        return TradeIntent(
            verdict="NEEDS_REVIEW",
            action="manual_parse_required",
            trader=trader,
            ticker=ticker,
            reason="sell-to-open, credit, or spread strategy is not safe to auto-convert into a simple Robinhood buy order",
            instrument="option",
        )

    if direction == "equity":
        if mode == "live":
            return TradeIntent(
                verdict="REQUIRE_HUMAN_APPROVAL",
                action="review_equity_order",
                trader=trader,
                ticker=ticker,
                reason=LIVE_DISABLED_DETAIL,
                instrument="equity",
                robinhood_tool="review_equity_order",
                order_args={"symbol": ticker, "side": "buy", "source": trader},
            )
        return TradeIntent(
            verdict="PAPER_ONLY",
            action="paper_equity_order",
            trader=trader,
            ticker=ticker,
            reason="equity entry can be paper-tracked; live execution disabled",
            instrument="equity",
            robinhood_tool="review_equity_order",
            order_args={"symbol": ticker, "side": "buy", "source": trader},
        )

    leg = parse_option_leg(contract)
    if not leg:
        return TradeIntent(
            verdict="NEEDS_REVIEW",
            action="manual_parse_required",
            trader=trader,
            ticker=ticker,
            reason="option contract is missing, multi-leg, or not parseable into one Robinhood leg",
            instrument="option",
        )

    if leg.option_type != direction:
        return TradeIntent(
            verdict="BLOCK",
            action="log_only",
            trader=trader,
            ticker=ticker,
            reason=f"direction {direction} conflicts with parsed option type {leg.option_type}",
            instrument="option",
        )

    stop = _extract_stop(commentary)
    risk = _risk_units(commentary)
    if not stop and not risk:
        return TradeIntent(
            verdict="PAPER_ONLY",
            action="paper_option_order",
            trader=trader,
            ticker=ticker,
            reason="entry is parseable, but stop/risk is not explicit enough for live action",
            instrument="option",
            robinhood_tool="review_option_order",
            order_args={
                "symbol": ticker,
                "side": "buy",
                "option_type": leg.option_type,
                "strike": leg.strike,
                "expiry": leg.expiry,
                "entry_price": leg.entry_price,
                "source": trader,
            },
        )

    args = {
        "symbol": ticker,
        "side": "buy",
        "option_type": leg.option_type,
        "strike": leg.strike,
        "expiry": leg.expiry,
        "entry_price": leg.entry_price,
        "stop": stop,
        "risk_unit": risk,
        "source": trader,
    }
    if mode == "live":
        return TradeIntent(
            verdict="REQUIRE_HUMAN_APPROVAL",
            action="review_option_order",
            trader=trader,
            ticker=ticker,
            reason=LIVE_DISABLED_DETAIL,
            instrument="option",
            robinhood_tool="review_option_order",
            order_args=args,
        )
    return TradeIntent(
        verdict="PAPER_READY",
        action="paper_option_order",
        trader=trader,
        ticker=ticker,
        reason="parseable entry with stop/risk; eligible for paper-forward tracking",
        instrument="option",
        robinhood_tool="review_option_order",
        order_args=args,
    )
