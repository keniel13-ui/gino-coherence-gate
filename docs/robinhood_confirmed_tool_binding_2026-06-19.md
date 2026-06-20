# Robinhood Confirmed Tool Binding

Date: 2026-06-19

Source: live Robinhood Trading MCP manifest captured after account-owner OAuth. No tools were called. The raw and normalized capture files live under `manifests/` and are gitignored.

Boundary: this binding enables read/data access only. It does not enable review, place, cancel, create, update, add, remove, follow, or unfollow tools.

## Exposed Read/Data Tools

These tools are allowed by `config/policy.example.json` because they are read-only account, market-data, or query tools needed for shadow scoring and signal evaluation:

- `get_accounts`
- `get_portfolio`
- `get_equity_positions`
- `get_option_positions`
- `get_equity_quotes`
- `get_equity_historicals`
- `get_equity_fundamentals`
- `get_equity_tradability`
- `get_equity_orders`
- `get_option_chains`
- `get_option_instruments`
- `get_option_quotes`
- `get_option_orders`
- `get_indexes`
- `get_index_quotes`
- `get_earnings_calendar`
- `get_earnings_results`
- `get_watchlists`
- `get_watchlist_items`
- `get_popular_watchlists`
- `get_option_watchlist`
- `get_scans`
- `run_scan`
- `search`

## Blocked Tools

These tools remain blocked because they are order/review tools or mutate account-side resources:

- `review_equity_order`
- `place_equity_order`
- `cancel_equity_order`
- `review_option_order`
- `place_option_order`
- `cancel_option_order`
- `create_watchlist`
- `add_to_watchlist`
- `remove_from_watchlist`
- `follow_watchlist`
- `unfollow_watchlist`
- `update_watchlist`
- `add_option_to_watchlist`
- `remove_option_from_watchlist`
- `create_scan`
- `update_scan_config`
- `update_scan_filters`

## Scan Classification

- `get_scans`: read. Lists scan data.
- `run_scan`: read/query. Executes a scan query and returns market data; allowed for signal discovery only.
- `create_scan`: write. Blocked.
- `update_scan_config`: write. Blocked.
- `update_scan_filters`: write. Blocked.

## Verification

Readiness on the captured manifest:

```bash
python3 scripts/gino_visit_readiness.py --manifest-json manifests/robinhood_manifest.normalized.json
```

Expected state:

- `ready_for_visit: true`
- `unknown_tools: []`
- 24 exposed read/data tools
- 17 blocked order/write tools

Unit tests:

```bash
python3 -m pytest tests
```
