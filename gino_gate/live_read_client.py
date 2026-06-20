"""Gate-mediated read client with receipts for the first live market-data calls."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .policy import PolicyEnvelope, sha256_json
from .receipts import ReceiptChain
from .server import DEFAULT_SIGNING_KEY
from .verdict import Verdict, decide


UpstreamCall = Callable[[str, dict[str, Any]], Any]


class ReceiptingReadToolClient:
    """Wrap an upstream MCP read-call function with gate checks and receipts."""

    def __init__(
        self,
        *,
        policy: PolicyEnvelope,
        receipt_path: str | Path,
        upstream_call: UpstreamCall,
        signing_key: bytes = DEFAULT_SIGNING_KEY,
        run_id: str = "live-read-once",
    ):
        self.policy = policy
        self.upstream_call = upstream_call
        self.receipts = ReceiptChain(Path(receipt_path), signing_key)
        self.run_id = run_id

    def call_tool(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        does = {"tool": tool, "args": args}
        verdict = decide(does, self.policy)
        if verdict.verdict != "ALLOW":
            receipt = self._append_receipt(
                does=does,
                verdict=verdict,
                recompute={"upstream_called": False},
            )
            return {"ok": False, "verdict": receipt}

        try:
            data = self.upstream_call(tool, args)
        except Exception as exc:  # pragma: no cover - defensive boundary
            receipt = self._append_receipt(
                does=does,
                verdict=verdict,
                recompute={"upstream_called": True, "upstream_error": str(exc)},
            )
            return {"ok": False, "verdict": receipt, "error": str(exc)}

        receipt = self._append_receipt(
            does=does,
            verdict=verdict,
            recompute={"upstream_called": True, "result_hash": sha256_json(data)},
        )
        return {"ok": True, "data": data, "verdict": receipt}

    def _append_receipt(self, *, does: dict[str, Any], verdict: Verdict, recompute: dict[str, Any]) -> dict[str, Any]:
        return self.receipts.append(
            run_id=self.run_id,
            policy=self.policy,
            does=does,
            knows_ref="gate_mediated_read_call",
            recompute=recompute,
            verdict=verdict,
        )
