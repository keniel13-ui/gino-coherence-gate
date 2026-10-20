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


@dataclass(frozen=True)
class ChainVerification:
    ok: bool
    count: int
    problems: list[str]


def verify_chain(path: str | Path, signing_key: bytes) -> ChainVerification:
    """Recompute every hash link and HMAC signature in a receipt file.

    The chain is only tamper-evident if someone checks it. This walks the file in
    order and reports unparseable lines, sequence gaps,
    broken `prev_hash` links, `this_hash` mismatches, and bad signatures.
    """
    path = Path(path)
    problems: list[str] = []
    if not path.exists():
        return ChainVerification(ok=True, count=0, problems=[])

    expected_prev = ZERO_HASH
    count = 0
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            count += 1
            try:
                receipt = json.loads(line)
            except json.JSONDecodeError as exc:
                problems.append(f"line {line_no}: not valid JSON ({exc.msg})")
                expected_prev = None
                continue
            if not isinstance(receipt, dict):
                problems.append(f"line {line_no}: receipt is not a JSON object")
                expected_prev = None
                continue
            if receipt.get("seq") != count:
                problems.append(f"line {line_no}: seq {receipt.get('seq')!r} != expected {count}")
            if expected_prev is not None and receipt.get("prev_hash") != expected_prev:
                problems.append(f"line {line_no}: prev_hash does not link to the previous receipt")
            body = dict(receipt)
            body.pop("signature", None)
            claimed_hash = body.pop("this_hash", None)
            if sha256_json(body) != claimed_hash:
                problems.append(f"line {line_no}: this_hash does not match receipt content")
            signed = dict(receipt)
            signed.pop("signature", None)
            expected_sig = "hmac-sha256:" + hmac.new(
                signing_key, canonical_json(signed).encode("utf-8"), hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(str(receipt.get("signature", "")), expected_sig):
                problems.append(f"line {line_no}: signature does not verify with the supplied key")
            expected_prev = claimed_hash if isinstance(claimed_hash, str) else None
    return ChainVerification(ok=not problems, count=count, problems=problems)
