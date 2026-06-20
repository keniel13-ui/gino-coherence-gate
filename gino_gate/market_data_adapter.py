"""Read-only market-data adapter for feeding owned signal sources."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from .own_signals import generate_rsi2_signals, generate_ts_momentum_signals
from .price_data import PriceSeries
from .scorer import Bar, parse_ts


class GateToolClient(Protocol):
    """Minimal interface for a gate-mediated MCP client."""

    def call_tool(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        """Call a tool through the gate and return a structured response."""


@dataclass(frozen=True)
class Quote:
    symbol: str
    price: float
    bid: float | None = None
    ask: float | None = None
    ts: str | None = None


class MarketDataAdapterError(ValueError):
    """Raised when read-only market data cannot be normalized."""


class ReadOnlyMarketDataAdapter:
    """Fetch and normalize Robinhood MCP market data through a gate client."""

    def __init__(self, client: GateToolClient):
        self.client = client

    def get_equity_historicals(
        self,
        symbol: str,
        *,
        interval: str = "day",
        span: str = "year",
        bounds: str = "regular",
    ) -> PriceSeries:
        payload = self.client.call_tool(
            "get_equity_historicals",
            {"symbol": symbol.upper(), "interval": interval, "span": span, "bounds": bounds},
        )
        return normalize_historicals_response(symbol, _unwrap_tool_payload(payload))

    def get_equity_quote(self, symbol: str) -> Quote:
        payload = self.client.call_tool("get_equity_quotes", {"symbols": [symbol.upper()]})
        return normalize_quote_response(symbol, _unwrap_tool_payload(payload))


def generate_own_signals_from_market_data(
    adapter: ReadOnlyMarketDataAdapter,
    symbols: list[str],
    *,
    ts_momentum: bool = True,
    rsi2: bool = True,
) -> list[dict[str, Any]]:
    """Generate owned source signals from read-only historical market data."""
    signals: list[dict[str, Any]] = []
    for symbol in symbols:
        series = adapter.get_equity_historicals(symbol)
        if ts_momentum:
            signals.extend(generate_ts_momentum_signals(series))
        if rsi2:
            signals.extend(generate_rsi2_signals(series))
    return signals


def normalize_historicals_response(symbol: str, payload: Any) -> PriceSeries:
    rows = _extract_rows(payload, preferred_keys=("historicals", "bars", "results", "data"))
    bars = [_bar_from_row(row) for row in rows]
    if not bars:
        raise MarketDataAdapterError("historicals response contained no bars")
    return PriceSeries(symbol.upper(), sorted(bars, key=lambda bar: bar.ts))


def normalize_quote_response(symbol: str, payload: Any) -> Quote:
    rows = _extract_rows(payload, preferred_keys=("quotes", "results", "data"))
    if not rows:
        raise MarketDataAdapterError("quote response contained no quote rows")

    wanted = symbol.upper()
    quote_rows = [_quote_row(candidate) for candidate in rows]
    row = next((candidate for candidate in quote_rows if str(candidate.get("symbol", wanted)).upper() == wanted), quote_rows[0])
    price, ts = _freshest_quote_price(row)
    return Quote(
        symbol=str(row.get("symbol", wanted)).upper(),
        price=price,
        bid=_optional_float(row, "bid", "bid_price"),
        ask=_optional_float(row, "ask", "ask_price"),
        ts=ts or _first_optional_str(row, "ts", "timestamp", "updated_at", "last_trade_at"),
    )


def _unwrap_tool_payload(payload: dict[str, Any]) -> Any:
    if not payload.get("ok", False):
        raise MarketDataAdapterError(f"gate refused tool call: {payload}")
    for key in ("data", "result", "payload", "response"):
        if key in payload:
            return payload[key]
    return payload


def _extract_rows(payload: Any, *, preferred_keys: tuple[str, ...]) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return _ensure_dict_rows(payload)

    if isinstance(payload, dict):
        for key in preferred_keys:
            value = payload.get(key)
            if isinstance(value, list):
                return _ensure_dict_rows(value)
            if isinstance(value, dict):
                nested = _extract_rows(value, preferred_keys=preferred_keys)
                if nested:
                    return nested
        if all(key in payload for key in ("open", "high", "low", "close")):
            return [payload]

    raise MarketDataAdapterError("response did not contain a supported row list")


def _ensure_dict_rows(rows: list[Any]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise MarketDataAdapterError(f"row is not an object: {row!r}")
        output.append(row)
    return output


def _bar_from_row(row: dict[str, Any]) -> Bar:
    return Bar(
        ts=parse_ts(_first_str(row, "ts", "timestamp", "time", "begins_at", "date")),
        open=_first_float(row, "open", "open_price"),
        high=_first_float(row, "high", "high_price"),
        low=_first_float(row, "low", "low_price"),
        close=_first_float(row, "close", "close_price", "last_price"),
    )


def _quote_row(row: dict[str, Any]) -> dict[str, Any]:
    quote = row.get("quote")
    if isinstance(quote, dict):
        return quote
    return row


def _freshest_quote_price(row: dict[str, Any]) -> tuple[float, str | None]:
    trade_candidates = [
        ("last_trade_price", "venue_last_trade_time"),
        ("last_non_reg_trade_price", "venue_last_non_reg_trade_time"),
        ("price", "ts"),
        ("last_price", "last_trade_at"),
        ("mark_price", "updated_at"),
    ]
    fallback_candidates = [
        ("ask_price", "venue_ask_time"),
        ("bid_price", "venue_bid_time"),
    ]

    observed = _price_candidates(row, trade_candidates)
    if not observed:
        observed = _price_candidates(row, fallback_candidates)
    if not observed:
        raise MarketDataAdapterError("quote response missing usable price")

    observed.sort(key=lambda item: (item[0] is not None, item[0] or datetime.min, item[1]), reverse=True)
    _, _, price, ts = observed[0]
    return price, ts


def _price_candidates(
    row: dict[str, Any],
    candidates: list[tuple[str, str]],
) -> list[tuple[datetime | None, int, float, str | None]]:
    observed: list[tuple[datetime | None, int, float, str | None]] = []
    for idx, (price_key, ts_key) in enumerate(candidates):
        value = row.get(price_key)
        if value is None or isinstance(value, (dict, list)):
            continue
        ts = _first_optional_str(row, ts_key)
        observed.append((_safe_parse_ts(ts), -idx, float(value), ts))
    return observed


def _safe_parse_ts(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        return parse_ts(value)
    except (TypeError, ValueError):
        return None


def _first_str(row: dict[str, Any], *keys: str) -> str:
    value = _first_optional_str(row, *keys)
    if value is None:
        raise MarketDataAdapterError(f"missing required field from {keys}")
    return value


def _first_optional_str(row: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = row.get(key)
        if value is not None:
            return str(value)
    return None


def _first_float(row: dict[str, Any], *keys: str) -> float:
    for key in keys:
        value = row.get(key)
        if value is not None and not isinstance(value, (dict, list)):
            return float(value)
    raise MarketDataAdapterError(f"missing numeric field from {keys}")


def _optional_float(row: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = row.get(key)
        if value is not None and not isinstance(value, (dict, list)):
            return float(value)
    return None
