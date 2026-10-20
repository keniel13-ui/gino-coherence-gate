# CLAUDE.md

Guidance for Claude Code (and other agents) working in this repo.

## What this is

A research and evidence bundle for the Gino execution proof: a deterministic,
read-only coherence gate between an agent and a future Robinhood MCP client, a scorer
that replays signals under a frozen, hash-anchored policy, and a paper/shadow operator
agent (Telegram/Discord). It never authenticates to Robinhood and has no order path.
See `docs/architecture.md` for the module map and diagrams.

## Commands

Python 3.11+ is required (the macOS system `python3` 3.9 is too old). Run from the repo root.

```bash
python -m pytest tests -q          # 115 passed, 3 skipped on a clean checkout
python scripts/smoke_gino_gate.py  # offline gate smoke
python -m gino_gate.server         # prints policy id, hash, mode
```

Setup details: `docs/development.md`.

## Rules that protect the research

- **Never edit frozen or dated artifacts.** `config/scoring_policy.frozen.2026-06-18.json`
  and its anchor are pinned by hash in the README, the anchor file, and
  `tests/test_frozen_policy.py`. `config/validation_universe.frozen.2026-06-20.json` is
  also frozen. Do not run `scripts/freeze_policy.py` to "fix" a mismatch; a mismatch means
  something changed that should not have.
- **Do not change scoring math or verdict thresholds** in `scorer.py`,
  `scoring_metrics.py`, `shadow_score.py`, `trade_intent.py`, `live_eligibility.py`,
  `stop_enforcement.py`, or `scorecard.py` as a side effect of other work. Outputs of the
  PlayBit pipeline back recorded conclusions. If you think the math is wrong, flag it.
- **Dated docs are records.** `docs/*_2026-06-1*.md` describe what was true on that date.
  Add new dated docs rather than rewriting old ones.
- **Keep the boundary.** No Robinhood auth, no order/review/cancel tool calls, no live
  execution path. Agent code proposes; `verdict.decide` and the rule modules decide. An
  LLM, if used (`watchlist.py` via local Ollama), only structures text.

## Code conventions

- Standard library only for runtime code. `pytest` is the only dev dependency.
- `from __future__ import annotations` at the top of modules; frozen dataclasses for records.
- Scripts insert the repo root on `sys.path` and are run as `python scripts/<name>.py`.
- Hashes use `policy.canonical_json` (sorted keys, compact separators, ASCII) and are
  written as `sha256:<hex>`. Reuse `sha256_json`; do not hand-roll JSON hashing.
- Receipts are append-only JSONL under `var/` (gitignored). Never rewrite them.
- Tests run offline. Network fetchers (`fetch_yahoo_*`, Telegram, Discord, Ollama) are
  injected or monkeypatched in tests.

## Secrets and local data

- Tokens come from env vars (`GINO_TELEGRAM_BOT_TOKEN`, `GINO_DISCORD_BOT_TOKEN`,
  `GINO_GATE_LOG_KEY`). Never write them to files in the repo; `.gitignore` blocks common
  token filenames.
- `manifests/*.json` and `var/` hold captured account data and logs. They are gitignored
  on purpose; do not add them.
- `chat_agent.DEFAULT_SOURCE_CSV` points at a file on the author's machine; pass
  `--source-csv` elsewhere.

## Writing style

No em dashes or en dashes in code, docs, or commit messages.
