# Robinhood Manifest Capture

Date: 2026-06-19

Purpose: capture the real Robinhood Trading MCP tool manifest so the gate can bind actual tool names instead of reported names.

Boundary: this is read-only setup work. Do not fund an Agentic account, do not place orders, and do not enable unattended trading. The account owner authenticates through an official MCP client. This repo never handles Robinhood credentials.

## Official Endpoint

Robinhood's official Agentic Trading overview lists the Trading MCP URL:

```text
https://agent.robinhood.com/mcp/trading
```

It also states that connection and Agentic account setup happen on desktop.

## Capture Goal

Stop after these facts are captured:

- The MCP connection authenticates.
- The real `tools/list` manifest is visible or exported.
- The manifest is saved locally.
- The readiness script shows which read tools are exposed and which trade/review tools are blocked.

No order review, no order placement, no live trading.

## Safe Capture Flow

1. In an official MCP client, add the Robinhood Trading MCP.

   Codex app:

   ```text
   Settings -> MCP servers -> Streamable HTTP -> https://agent.robinhood.com/mcp/trading
   ```

   Codex CLI:

   ```bash
   codex mcp add robinhood-trading --url https://agent.robinhood.com/mcp/trading
   ```

   Claude Code:

   ```bash
   claude mcp add robinhood-trading --transport http https://agent.robinhood.com/mcp/trading
   ```

2. The account owner authenticates on desktop and approves the connection.

3. Use the MCP client's tool-list view or export to capture the tool list JSON.

   Preferred raw shape, if the client exposes it:

   ```json
   {
     "jsonrpc": "2.0",
     "id": 1,
     "result": {
       "tools": [
         { "name": "get_accounts" }
       ]
     }
   }
   ```

   If the client only displays names, put them in this minimal shape:

   ```json
   {
     "tools": [
       { "name": "get_accounts" },
       { "name": "place_equity_order" }
     ]
   }
   ```

4. Save the raw capture somewhere local under `manifests/`.

   Example:

   ```text
   manifests/robinhood_manifest.raw.json
   ```

   Files in `manifests/*.json` are ignored by git so live captures do not get committed by accident.

5. Normalize and assess:

   ```bash
   python3 scripts/normalize_manifest_capture.py manifests/robinhood_manifest.raw.json
   ```

   Or pipe from stdin:

   ```bash
   pbpaste | python3 scripts/normalize_manifest_capture.py -
   ```

6. Confirm readiness:

   ```bash
   python3 scripts/gino_visit_readiness.py --manifest-json manifests/robinhood_manifest.normalized.json
   ```

## Success Criteria

The setup is ready for a read-only visit only if:

- at least one read tool is exposed,
- trade/review tools are blocked by the gate,
- unknown tools are visible and manually reviewed before use,
- no credentials, tokens, or account secrets are present in the captured JSON.

## Stop Conditions

Stop immediately if:

- the client asks to grant unattended trade execution,
- the capture contains tokens, cookies, account secrets, or credentials,
- the manifest shows unexpected write/trade tools that are not blocked,
- the account owner is not present to authenticate.

## Next Step After Capture

Bind confirmed read tool names into the policy and keep all trade/review/order tools refused until a separate shadow/paper milestone justifies wiring them.
