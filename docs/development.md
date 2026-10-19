# Local Development

## Requirements

- Python 3.11 or newer (`pyproject.toml` sets `requires-python = ">=3.11"`; some modules use
  `datetime.UTC`). The macOS system `python3` is 3.9 and is too old for the test suite.
- `pytest` is the only development dependency. The package itself uses only the
  standard library.

## Setup

With a Python 3.11+ interpreter on your PATH:

```bash
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install pytest
```

Or with [uv](https://docs.astral.sh/uv/), which can download the interpreter:

```bash
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python pytest
. .venv/bin/activate
```

Run every command from the repo root. Several defaults (`config/policy.example.json`,
`var/...`) are relative paths.

## Tests

```bash
python -m pytest tests -q
```

On a clean checkout this reports `115 passed, 3 skipped`. The skips are tests that need
local, gitignored captures under `manifests/`.

## Offline smoke commands

These need no credentials and make no network calls:

```bash
python scripts/smoke_gino_gate.py
python scripts/smoke_signal_scorer.py
python scripts/smoke_market_data_adapter.py
python scripts/gino_visit_readiness.py
python -m gino_gate.server
python -m gino_gate.server --call-tool place_equity_order --args-json '{"symbol": "AAPL", "notional_usd": 10}'
```

The last command prints a `REFUSE` verdict and appends a receipt to `var/receipts.jsonl`.

## Chat agent without Telegram

```bash
python scripts/gino_chat_agent.py --source-csv path/to/calls.csv --message "what can you do?"
python scripts/gino_chat_agent.py --source-csv path/to/calls.csv --message "AAPL 7/19 200c @2.50 TP 210 SL 190"
```

`--source-csv` defaults to a path on the author's machine. Pass your own CSV with the
PlayBit header (`#,Trader,Date,Time,Ticker,Direction,Contract / Fill,Event Type,Mark,P/L %,P/L $,Trader Commentary`).
Pasted calls do not need any rows in it.

## Environment variables

| Variable | Used by | Notes |
| --- | --- | --- |
| `GINO_GATE_LOG_KEY` | `gino_gate.server`, `live_read_once.py`, shadow score scripts | HMAC key for receipts. Unset falls back to a public dev key. |
| `GINO_TELEGRAM_BOT_TOKEN` | Telegram bot, Discord monitor, stack runner | Never commit it. |
| `GINO_TELEGRAM_CHAT_ID` | Discord monitor | Where alerts go. |
| `GINO_DISCORD_BOT_TOKEN` | Discord monitor | Read-only bot. |
| `GINO_DISCORD_CHANNEL_IDS` | Discord monitor | Comma-separated. |

The Mac mini runbook is in `docs/mac_mini_setup.md`.
