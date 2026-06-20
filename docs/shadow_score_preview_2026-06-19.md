# Shadow Score Preview

Date: 2026-06-19

Purpose: run the owned signal engine and scorer on saved, receipted, read-only historical data.

Boundary: this is a measurement preview, not an edge verdict and not a financial milestone. No orders, no funding, no trades.

## Input

Saved local response:

```text
manifests/aapl_hist.raw.json
```

The file is gitignored and contains a real Robinhood `get_equity_historicals` response for AAPL:

- 251 daily regular-session bars
- 2025-06-20 through 2026-06-18
- split-adjusted

## Command

```bash
python3 scripts/shadow_score_saved_historicals.py \
  --symbol AAPL \
  --historicals-json manifests/aapl_hist.raw.json \
  --output var/aapl_shadow_score_report.json \
  --receipts var/shadow_score_receipts.jsonl \
  --run-id first-aapl-shadow-score-preview-final
```

## Result

The preview generated:

- 8 unique owned signals
- 128 variant records from those signals across rule/sizing combinations
- top-level `status`: `measurement_preview_insufficient_sample`
- top-level `action_verdict`: `continue_collecting`
- measurement gate: 8 unique signals < frozen 50-signal minimum

Receipt:

```text
sha256:2841eaf144637ac41a58deec0eba47db53db24dabcd6d0d418f5419ea53b05a3
```

## Important Correction Caught

The first shadow-score run revealed a measurement bug: variant records were counted as if they were independent settled signals. That made `8 signals x 16 variants = 128 records`, incorrectly tripping the frozen 50-sample gate.

Fix:

- track a separate `measurement_gate`,
- count unique signal IDs for readiness,
- keep variant-level metrics labeled as variant-level,
- top-level action remains `continue_collecting` until the unique-signal count clears the frozen bar.

The report now states:

```text
Variant records are not independent signals.
```

## Next Step

Feed a broader symbol universe through the same read-only capture/score path until the system reaches at least 50 unique settled signals. Only then can the scorer produce a real edge verdict.
