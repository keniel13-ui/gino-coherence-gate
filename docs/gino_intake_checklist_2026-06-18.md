# Gino Intake Checklist — Read-Only Visit

Date: 2026-06-18

Purpose: make the Gino setup practical without repeating the Discord over-coupling mistake. The product is the general coherence gate plus exit/risk engine. Gino's Discord is an optional customer feed adapter, not the foundation.

## What We Are Showing Up With

- Public pre-registration receipt: `https://github.com/keniel13-ui/gino-coherence-gate`
- Frozen $5k scoring policy hash: `sha256:83474132582fc3f6ca947cfd7b71b3671228fea28a471d6434c7c72764c663ae`
- Read-only gate skeleton, scorer, price adapters, baselines, and own signal sources.
- A readiness script that classifies a Robinhood MCP manifest into read/review/trade/unknown tools and confirms whether a read-only visit path is viable.

## What We Are Not Doing

- No real trades.
- No order forwarding.
- No funded-account automation.
- No "no-confirmation" execution.
- No Discord-shaped architecture.
- No claims of revenue, impact, or proof before real outcomes exist.

## Required From Gino

- His PC, if he wants it to run from his machine.
- His own Robinhood login and authorization. Keniel does not take or store credentials.
- Confirmation that Robinhood Agentic Trading / MCP access is available on his account.
- Agreement that the first session is read-only/shadow only.

## Optional From Gino

- Discord access for live capture.
- Exported Discord signal history, if available.
- Manual copy/paste of selected historical signals, if export is impossible.

Optional means optional. If Gino has no Discord data, the system still stands.

## Visit Flow

1. Confirm Gino understands the first session is read-only.
2. Have Gino authenticate Robinhood himself on his own machine.
3. Dump the live MCP tool manifest if the authenticated connection is available.
4. Classify tools into read/review/trade/unknown.
5. Expose read tools only.
6. Block review/trade/cancel tools.
7. Emit a readiness receipt/report.
8. Stop there unless the team has deliberately agreed on the next shadow step.

## Success For The Visit

- Live manifest captured, or a clear blocker recorded.
- Read tools identified.
- Trade tools identified and blocked.
- No credentials handled by Keniel or stored in the repo.
- No money moved.

## Message To Gino

First setup is read-only. You log in on your PC, we confirm what tools Robinhood exposes, and we make sure the gate blocks anything trade-related before any money moves. Your Discord data can help later, but it is not required for the system to stand.
