from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from .manifest import filter_manifest
from .policy import PolicyEnvelope
from .receipts import ReceiptChain, verify_chain
from .verdict import decide


DEFAULT_SIGNING_KEY = b"dev-only-gino-gate-key"
SIGNING_KEY_ENV = "GINO_GATE_LOG_KEY"


def signing_key_from_env(*, warn: bool = True) -> bytes:
    """Return the receipt HMAC key from the environment, or the public dev key.

    The dev key is committed to this repo, so anyone can forge receipts signed with
    it. Falling back keeps local smoke runs working, but say so on stderr so a real
    run does not silently produce receipts that prove nothing.
    """
    key = os.environ.get(SIGNING_KEY_ENV, "").encode("utf-8")
    if key:
        return key
    if warn:
        print(
            f"warning: {SIGNING_KEY_ENV} is not set; receipts are signed with the public dev key "
            "and are not tamper-evident against anyone who has read this repo.",
            file=sys.stderr,
        )
    return DEFAULT_SIGNING_KEY


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
    parser.add_argument(
        "--verify-receipts",
        action="store_true",
        help="Recompute the hash chain and signatures in --receipts and exit non-zero on any problem",
    )
    args = parser.parse_args(argv)

    key = signing_key_from_env()
    if args.verify_receipts:
        result = verify_chain(Path(args.receipts), key)
        print(json.dumps({"ok": result.ok, "count": result.count, "problems": result.problems}, indent=2))
        return 0 if result.ok else 1

    policy = PolicyEnvelope.from_file(args.policy)
    gate = ReadOnlyGate(policy, Path(args.receipts), key)

    if args.manifest_json:
        print(json.dumps(gate.manifest(_read_json(args.manifest_json)), indent=2, sort_keys=True))
        return 0

    if args.call_tool:
        try:
            call_args = json.loads(args.args_json)
        except json.JSONDecodeError as exc:
            parser.error(f"--args-json is not valid JSON: {exc}")
        if not isinstance(call_args, dict):
            parser.error("--args-json must be a JSON object")
        result = gate.call_tool(args.call_tool, call_args)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    print(json.dumps({"policy_id": policy.policy_id, "policy_hash": policy.policy_hash, "mode": policy.mode}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
