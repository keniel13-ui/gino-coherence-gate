from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from .paper_forward import PaperPosition


@dataclass(frozen=True)
class UnderlyingClose:
    symbol: str
    close_date: str
    close: float
    source: str
    fetched_at: str


@dataclass(frozen=True)
class ExpirySettlement:
    key: str
    trader: str
    ticker: str
    option_type: str
    strike: str
    expiry_date: str
    last_pnl_pct: str
    last_pnl_dollars: str
    underlying_close_date: str
    underlying_close: str
    moneyness: str
    settlement_status: str
    settled_return_pct: str
    return_quality: str
    source: str
    fetched_at: str
    reason: str


def _split_option_key(position: PaperPosition) -> tuple[str, float, str] | None:
    parts = position.key.split("|")
    if len(parts) < 6:
        return None
    expiry, strike_raw, option_type = parts[-3], parts[-2], parts[-1].lower()
    if option_type not in {"call", "put"}:
        return None
    try:
        strike = float(strike_raw)
    except ValueError:
        return None
    return expiry, strike, option_type


def yahoo_chart_url(symbol: str, expiry: date) -> str:
    start = int(datetime(expiry.year, expiry.month, expiry.day, tzinfo=UTC).timestamp()) - 9 * 86400
    end = int(datetime(expiry.year, expiry.month, expiry.day, tzinfo=UTC).timestamp()) + 3 * 86400
    return f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?period1={start}&period2={end}&interval=1d"


def fetch_yahoo_underlying_close(symbol: str, expiry: date) -> UnderlyingClose:
    url = yahoo_chart_url(symbol, expiry)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=25) as response:
        payload = json.loads(response.read().decode("utf-8"))

    result = payload["chart"]["result"][0]
    timestamps = result.get("timestamp") or []
    closes = result["indicators"]["quote"][0].get("close") or []
    best_date: str | None = None
    best_close: float | None = None
    for ts, close in zip(timestamps, closes):
        if close is None:
            continue
        close_date = datetime.fromtimestamp(ts, UTC).date()
        if close_date <= expiry:
            best_date = close_date.isoformat()
            best_close = float(close)

    if best_date is None or best_close is None:
        raise ValueError(f"no close on or before expiry for {symbol} near {expiry.isoformat()}")

    return UnderlyingClose(
        symbol=symbol.upper(),
        close_date=best_date,
        close=best_close,
        source=url,
        fetched_at=datetime.now(UTC).isoformat(),
    )


def settle_expired_option(
    position: PaperPosition,
    *,
    close: UnderlyingClose,
) -> ExpirySettlement:
    parsed = _split_option_key(position)
    if parsed is None:
        return ExpirySettlement(
            key=position.key,
            trader=position.trader,
            ticker=position.ticker,
            option_type="",
            strike="",
            expiry_date=position.expiry_date,
            last_pnl_pct=position.last_pnl_pct,
            last_pnl_dollars=position.last_pnl_dollars,
            underlying_close_date=close.close_date,
            underlying_close=f"{close.close:.4f}",
            moneyness="unknown",
            settlement_status="UNSETTLED",
            settled_return_pct="",
            return_quality="unsettled",
            source=close.source,
            fetched_at=close.fetched_at,
            reason="position key does not contain a parseable option contract",
        )

    expiry, strike, option_type = parsed
    if option_type == "call":
        intrinsic = max(0.0, close.close - strike)
    else:
        intrinsic = max(0.0, strike - close.close)

    if intrinsic <= 0:
        return ExpirySettlement(
            key=position.key,
            trader=position.trader,
            ticker=position.ticker,
            option_type=option_type,
            strike=f"{strike:g}",
            expiry_date=expiry,
            last_pnl_pct=position.last_pnl_pct,
            last_pnl_dollars=position.last_pnl_dollars,
            underlying_close_date=close.close_date,
            underlying_close=f"{close.close:.4f}",
            moneyness="OTM",
            settlement_status="SETTLED_WORTHLESS",
            settled_return_pct="-100.00",
            return_quality="held_to_expiry_underlying_close",
            source=close.source,
            fetched_at=close.fetched_at,
            reason="expired out-of-the-money with no captured close; held-to-expiry long option value is zero",
        )

    return ExpirySettlement(
        key=position.key,
        trader=position.trader,
        ticker=position.ticker,
        option_type=option_type,
        strike=f"{strike:g}",
        expiry_date=expiry,
        last_pnl_pct=position.last_pnl_pct,
        last_pnl_dollars=position.last_pnl_dollars,
        underlying_close_date=close.close_date,
        underlying_close=f"{close.close:.4f}",
        moneyness="ITM",
        settlement_status="NEEDS_OPTION_PRICE_SETTLEMENT",
        settled_return_pct="",
        return_quality="needs_option_price",
        source=close.source,
        fetched_at=close.fetched_at,
        reason="expired in-the-money; do not infer realized return without option premium/settlement pricing",
    )


def settle_expired_no_close_positions(
    positions: list[PaperPosition],
    *,
    fetch_close=fetch_yahoo_underlying_close,
) -> list[ExpirySettlement]:
    settlements: list[ExpirySettlement] = []
    for position in positions:
        if position.status != "EXPIRED_NO_CLOSE" or position.intent_verdict != "PAPER_READY":
            continue
        if not position.expiry_date:
            continue
        close = fetch_close(position.ticker, date.fromisoformat(position.expiry_date))
        settlements.append(settle_expired_option(position, close=close))
    return settlements
