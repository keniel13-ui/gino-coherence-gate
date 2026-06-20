# Read-Only Market Data Path

Date: 2026-06-19

Purpose: feed owned signal sources from confirmed Robinhood MCP read tools without exposing any order/write tools.

Boundary: fixture-tested only. No live Robinhood market-data tool has been called from this repo yet. No orders, no funding, no trade review, no trade placement.

## Allowed Tool Calls

The adapter currently calls only:

- `get_equity_historicals`: OHLC bars for owned signal generation.
- `get_equity_quotes`: current quote/price normalization.

Both must pass through the policy gate before any upstream call is made.

## Blocked Tool Classes

The adapter has no method for:

- `review_*_order`
- `place_*_order`
- `cancel_*_order`
- watchlist mutation tools
- scan create/update tools

Those remain blocked by policy and by the adapter surface.

## Data Flow

1. `ReadOnlyMarketDataAdapter` receives a gate-mediated client.
2. It calls `get_equity_historicals` or `get_equity_quotes`.
3. The gate checks `PolicyEnvelope.allowed_tools_by_mode` and deterministic tool classification.
4. The adapter normalizes the returned data into:
   - `PriceSeries` / `Bar` for historicals
   - `Quote` for quotes
5. `generate_own_signals_from_market_data` feeds `PriceSeries` into:
   - `own:ts_momentum`
   - `own:rsi2`

## Verification

Fixture smoke:

```bash
python3 scripts/smoke_market_data_adapter.py
```

Unit tests:

```bash
python3 -m pytest tests
```

Expected test guarantees:

- Robinhood-like historical responses normalize into `PriceSeries`.
- Quote responses normalize into `Quote`.
- Owned signals can be generated through the read-only adapter.
- A fixture order call is refused by the same deterministic gate policy.
- Malformed historical data fails closed.

## Next Step

Replace the fixture client with the real gate-mediated MCP read client. The first live call should be `get_equity_quotes` or `get_equity_historicals` on a harmless symbol, with receipts/logging enabled, then stop and verify before any broader shadow scoring.
