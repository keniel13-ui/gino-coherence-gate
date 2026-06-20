# Gino Coherence Gate

Read-only v0 skeleton for the Gino execution proof.

This project implements the local, deterministic gate that sits between an agent and a future Robinhood MCP client. It does not connect to Robinhood, does not hold credentials, and cannot place trades. The first job is to prove the gate spine: frozen policy, read-only tool filtering, deterministic verdicts, and signed chained receipts.

## Current Scope

- Load and hash a frozen `PolicyEnvelope`.
- Classify a live or sample MCP tool manifest into read, review, trade, and unknown tools.
- Expose read-only mode by filtering/refusing non-read tools.
- Bind confirmed Robinhood MCP read/data tool names while blocking all order and write tools.
- Recompute policy decisions from structured inputs, not model judgment.
- Emit append-only `DecisionReceipt` records with a hash chain and HMAC signature.
- Load and hash a frozen `ScoringPolicy`.
- Simulate captured signals against OHLC price paths with latency, slippage, fees, take-profit, stop, time-stop, MFE/MAE, and position sizing.
- Aggregate scorer metrics into action verdicts: `continue_collecting`, `advance`, `kill_source`, `rerun_one_correction`, or `unmeasurable`.
- Enforce the results gate: min settled N or decision timebox, one correction only, live-performance haircut, baseline-required advancement, late-call detector, and consecutive-loss survival metric.
- Normalize gate-mediated read-only market data into `PriceSeries` / `Quote` and feed owned signal sources.
- Assess whether a captured MCP manifest can support a read-only Gino setup visit.
- Normalize a user-authenticated MCP `tools/list` capture into the gate manifest shape.
- Keep the Gino visit checklist explicit: read-only first, customer feeds optional, no credentials handled by Keniel.

## Not Yet Implemented

- Robinhood OAuth.
- Live MCP upstream calls.
- Automated authenticated manifest dump from `https://agent.robinhood.com/mcp/trading`. The manual capture/normalize path exists; authentication still happens in an official MCP client with the account owner present.
- `review_equity_order` shadow execution.
- Paper fills or live order forwarding.
- Live gate-mediated market-data client. The read-only adapter is fixture-tested, but no live market-data tool call has been made from this repo yet.
- SPY/random baseline data adapters. The scorer already requires baseline comparison before advance; the data source still needs to be connected.

## Frozen Policy Anchor

Machine-readable frozen policy:

`config/scoring_policy.frozen.2026-06-18.json`

Current canonical hash:

`sha256:83474132582fc3f6ca947cfd7b71b3671228fea28a471d6434c7c72764c663ae`

Anchor file:

`config/scoring_policy.frozen.2026-06-18.anchor.json`

Public git receipt:

`https://github.com/keniel13-ui/gino-coherence-gate`

Freeze commit:

`8cf62509509dcdd96b7036d2b57e04a6b8080a2b`

Latest pushed commit at the time this README was updated:

`76495de872c90dcba0939b828558e67b47795615`

Authenticated live manifest verification is still pending.

## Smoke Test

```bash
python3 scripts/smoke_gino_gate.py
```

```bash
python3 scripts/smoke_signal_scorer.py
```

```bash
python3 scripts/smoke_market_data_adapter.py
```

```bash
python3 scripts/gino_visit_readiness.py
```

When a real authenticated manifest exists:

```bash
python3 scripts/normalize_manifest_capture.py manifests/robinhood_manifest.raw.json
```

```bash
python3 scripts/gino_visit_readiness.py --manifest-json path/to/manifest.json
```

Visit checklist:

`docs/gino_intake_checklist_2026-06-18.md`

Manifest capture checklist:

`docs/robinhood_manifest_capture.md`

Confirmed tool binding:

`docs/robinhood_confirmed_tool_binding_2026-06-19.md`

Read-only market-data path:

`docs/read_only_market_data_path_2026-06-19.md`

## Unit Tests

```bash
python3 -m pytest tests
```

## Boundary

No autonomous real-money movement before shadow and paper evidence prove edge and guardrails. The agent can propose; it cannot certify itself or reach the root.
