# Live Read Once Path

Date: 2026-06-19

Purpose: perform the first real read-only market-data step with a signed receipt while keeping Robinhood authentication outside this repo.

Boundary: this path does not authenticate to Robinhood and does not call orders. The account owner uses an official MCP client. This repo receipts and normalizes the captured read response.

## What Exists

- `ReceiptingReadToolClient`: wraps an upstream read call with deterministic gate checks and signed receipts.
- `scripts/live_read_once.py`: receipts and normalizes one captured read response.
- Supported tools:
  - `get_equity_quotes`
  - `get_equity_historicals`

## Safety Properties

- Verdict is computed before any upstream call.
- If the tool is refused, upstream is never called.
- Order tools such as `place_equity_order` produce a refusal receipt and no upstream call.
- Allowed read responses are hashed into the receipt via `result_hash`.

## First Live Procedure

1. Account owner authenticates through an official MCP client.
2. Make exactly one read-only call:
   - preferred first call: `get_equity_quotes` for one harmless symbol.
3. Save the raw response locally, for example:

   ```text
   manifests/live_quote_response.raw.json
   ```

4. Run:

   ```bash
   python3 scripts/live_read_once.py \
     --tool get_equity_quotes \
     --symbol AAPL \
     --response-json manifests/live_quote_response.raw.json \
     --receipts var/live_read_receipts.jsonl \
     --run-id first-live-quote
   ```

5. Stop and verify:
   - normalized quote looks correct,
   - receipt was appended,
   - receipt includes `result_hash`,
   - no order/review/place/cancel tool was called.

## First Live Shape Finding

The first captured Robinhood quote response used this nested shape:

```text
data.results[].quote
data.results[].close
```

The active quote fields live under `quote`; `close` is a separate object and must not be parsed as a numeric quote price. The quote normalizer therefore:

- drills into `data.results[].quote`,
- prefers the freshest actual trade price from `last_trade_price` / `last_non_reg_trade_price`,
- falls back to bid/ask only if no trade price exists,
- carries the selected trade timestamp as `Quote.ts`,
- keeps bid/ask as separate fields.

## Verification

Fixture smoke:

```bash
python3 scripts/live_read_once.py \
  --tool get_equity_quotes \
  --symbol AAPL \
  --response-json /path/to/captured_quote.json \
  --receipts /tmp/gino-live-read/receipts.jsonl \
  --run-id smoke-live-read
```

Tests:

```bash
python3 -m pytest tests
```

## Next Step

After one quote succeeds with a receipt, repeat the same stop-and-verify flow for one `get_equity_historicals` response. Only after both read calls are verified should the system attempt shadow scoring.
