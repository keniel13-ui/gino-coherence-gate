from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from .manifest import filter_manifest
from .policy import PolicyEnvelope
from .receipts import ReceiptChain
from .verdict import decide


DEFAULT_SIGNING_KEY = b"dev-only-gino-gate-key"


class ReadOnlyGate:
    def __init__(self, policy: PolicyEnvelope, receipt_path: Path, signing_key: bytes = DEFAULT_SIGNING_KEY):
        self.policy = policy
        self.receipts = ReceiptChain(receipt_path, signing_key)

    def manifest(self, upstream_manifest: dict[str, Any] | list[Any]) -> dict[str, Any]:
        return filter_manifest(upstream_manifest, self.policy.allowed_tools())

    def call_tool(self, tool: str, args: dict[str, Any], *, run_id: str = "local-dev", knows_ref: str = "manual") -> dict[str, Any]:
        does = {"tool": tool, "args": args}
        verdict = decide(does, self.policy)
        receipt = self.receipts.append(
            run_id=run_id,
            policy=self.policy,
            does=does,
            knows_ref=knows_ref,
            recompute={},
            verdict=verdict,
        )
        if verdict.verdict != "ALLOW":
            return {"ok": False, "verdict": receipt}
        return {"ok": True, "verdict": receipt, "upstream_forwarded": False}


def _read_json(path: str) -> Any:
    with Path(path).open("r", encoding="utf-8") as fh:
        return json.load(fh)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gino Coherence Gate read-only skeleton")
    parser.add_argument("--policy", default="config/policy.example.json")
    parser.add_argument("--receipts", default="var/receipts.jsonl")
    parser.add_argument("--manifest-json", help="Path to an upstream MCP manifest JSON file to classify")
    parser.add_argument("--call-tool", help="Attempt a local tool call through the gate")
    parser.add_argument("--args-json", default="{}", help="JSON object for --call-tool args")
    args = parser.parse_args(argv)

    policy = PolicyEnvelope.from_file(args.policy)
    key = os.environ.get("GINO_GATE_LOG_KEY", "").encode("utf-8") or DEFAULT_SIGNING_KEY
    gate = ReadOnlyGate(policy, Path(args.receipts), key)

    if args.manifest_json:
        print(json.dumps(gate.manifest(_read_json(args.manifest_json)), indent=2, sort_keys=True))
        return 0

    if args.call_tool:
        result = gate.call_tool(args.call_tool, json.loads(args.args_json))
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    print(json.dumps({"policy_id": policy.policy_id, "policy_hash": policy.policy_hash, "mode": policy.mode}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
