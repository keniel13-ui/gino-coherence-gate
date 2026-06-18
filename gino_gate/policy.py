from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_json(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PolicyEnvelope:
    raw: dict[str, Any]
    policy_hash: str

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "PolicyEnvelope":
        body = dict(raw)
        body.pop("policy_hash", None)
        return cls(raw=body, policy_hash=sha256_json(body))

    @classmethod
    def from_file(cls, path: str | Path) -> "PolicyEnvelope":
        with Path(path).open("r", encoding="utf-8") as fh:
            return cls.from_dict(json.load(fh))

    @property
    def policy_id(self) -> str:
        return str(self.raw["policy_id"])

    @property
    def mode(self) -> str:
        return str(self.raw["mode"])

    @property
    def purpose_ref(self) -> str:
        return str(self.raw.get("purpose", {}).get("objective", "unknown"))

    @property
    def authority(self) -> dict[str, Any]:
        return dict(self.raw.get("authority", {}))

    def allowed_tools(self, mode: str | None = None) -> set[str]:
        selected = mode or self.mode
        matrix = self.raw.get("allowed_tools_by_mode", {})
        return set(matrix.get(selected, []))
