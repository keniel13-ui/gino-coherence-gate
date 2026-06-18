# Gino Coherence Gate

Read-only v0 skeleton for the Gino execution proof.

This project implements the local, deterministic gate that sits between an agent and a future Robinhood MCP client. It does not connect to Robinhood, does not hold credentials, and cannot place trades. The first job is to prove the gate spine: frozen policy, read-only tool filtering, deterministic verdicts, and signed chained receipts.

## Current Scope

- Load and hash a frozen `PolicyEnvelope`.
- Classify a live or sample MCP tool manifest into read, review, trade, and unknown tools.
- Expose read-only mode by filtering/refusing non-read tools.
- Recompute policy decisions from structured inputs, not model judgment.
- Emit append-only `DecisionReceipt` records with a hash chain and HMAC signature.
- Load and hash a frozen `ScoringPolicy`.
- Simulate captured signals against OHLC price paths with latency, slippage, fees, take-profit, stop, time-stop, MFE/MAE, and position sizing.
- Aggregate scorer metrics into action verdicts: `continue_collecting`, `advance`, `kill_source`, `rerun_one_correction`, or `unmeasurable`.
- Enforce the results gate: min settled N or decision timebox, one correction only, live-performance haircut, baseline-required advancement, late-call detector, and consecutive-loss survival metric.

## Not Yet Implemented

- Robinhood OAuth.
- Live MCP upstream calls.
- Authenticated manifest dump from `https://agent.robinhood.com/mcp/trading`.
- `review_equity_order` shadow execution.
- Paper fills or live order forwarding.
- Historical market-data adapter for backlog scoring.
- SPY/random baseline data adapters. The scorer already requires baseline comparison before advance; the data source still needs to be connected.

## Frozen Policy Anchor

Machine-readable frozen policy:

`config/scoring_policy.frozen.2026-06-18.json`

Current canonical hash:

`sha256:83474132582fc3f6ca947cfd7b71b3671228fea28a471d6434c7c72764c663ae`

Anchor file:

`config/scoring_policy.frozen.2026-06-18.anchor.json`

The git commit anchor is still pending because this folder is not currently a git repository.

Those remain gated on authenticated manifest verification.

## Smoke Test

```bash
python3 scripts/smoke_gino_gate.py
```

```bash
python3 scripts/smoke_signal_scorer.py
```

## Unit Tests

```bash
python3 -m pytest tests
```

## Boundary

No autonomous real-money movement before shadow and paper evidence prove edge and guardrails. The agent can propose; it cannot certify itself or reach the root.
