from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .policy import PolicyEnvelope, canonical_json, sha256_json
from .verdict import Verdict


ZERO_HASH = "sha256:" + ("0" * 64)


@dataclass(frozen=True)
class ReceiptChain:
    path: Path
    signing_key: bytes

    def last_hash(self) -> str:
        if not self.path.exists():
            return ZERO_HASH
        last = ""
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    last = line
        if not last:
            return ZERO_HASH
        return str(json.loads(last)["this_hash"])

    def next_seq(self) -> int:
        if not self.path.exists():
            return 1
        count = 0
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    count += 1
        return count + 1

    def append(
        self,
        *,
        run_id: str,
        policy: PolicyEnvelope,
        does: dict[str, Any],
        knows_ref: str,
        recompute: dict[str, Any],
        verdict: Verdict,
    ) -> dict[str, Any]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        receipt = {
            "seq": self.next_seq(),
            "run_id": run_id,
            "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "policy_hash": policy.policy_hash,
            "purpose_ref": policy.purpose_ref,
            "does": does,
            "knows_ref": knows_ref,
            "recompute": recompute,
            "verdict": verdict.verdict,
            "rule_fired": verdict.rule_fired,
            "detail": verdict.detail,
            "prev_hash": self.last_hash(),
        }
        receipt["this_hash"] = sha256_json(receipt)
        receipt["signature"] = self._sign(receipt)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(canonical_json(receipt) + "\n")
        return receipt

    def _sign(self, receipt: dict[str, Any]) -> str:
        body = dict(receipt)
        body.pop("signature", None)
        digest = hmac.new(self.signing_key, canonical_json(body).encode("utf-8"), hashlib.sha256).hexdigest()
        return "hmac-sha256:" + digest
