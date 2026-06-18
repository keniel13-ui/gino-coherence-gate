from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .policy import canonical_json, sha256_json
from .receipts import ZERO_HASH
from .scoring_policy import ScoringPolicy


@dataclass(frozen=True)
class ScoringRecordChain:
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

    def append(self, record: dict[str, Any], policy: ScoringPolicy) -> dict[str, Any]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        body = dict(record)
        body["policy_hash"] = policy.policy_hash
        body["prev_hash"] = self.last_hash()
        body["this_hash"] = sha256_json(body)
        body["signature"] = self._sign(body)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(canonical_json(body) + "\n")
        return body

    def _sign(self, record: dict[str, Any]) -> str:
        body = dict(record)
        body.pop("signature", None)
        digest = hmac.new(self.signing_key, canonical_json(body).encode("utf-8"), hashlib.sha256).hexdigest()
        return "hmac-sha256:" + digest
