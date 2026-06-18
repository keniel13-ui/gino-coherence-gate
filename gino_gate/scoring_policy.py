from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .policy import sha256_json


@dataclass(frozen=True)
class ScoringPolicy:
    raw: dict[str, Any]
    policy_hash: str

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ScoringPolicy":
        body = dict(raw)
        body.pop("policy_hash", None)
        return cls(raw=body, policy_hash=sha256_json(body))

    @classmethod
    def from_file(cls, path: str | Path) -> "ScoringPolicy":
        with Path(path).open("r", encoding="utf-8") as fh:
            return cls.from_dict(json.load(fh))

    @property
    def policy_id(self) -> str:
        return str(self.raw["policy_id"])

    @property
    def account_equity_usd(self) -> float:
        return float(self.raw.get("account_equity_usd", 0) or 0)

    @property
    def min_settled_n(self) -> int:
        return int(self.raw.get("min_settled_n", 0) or 0)

    @property
    def decision_timebox_days(self) -> int:
        return int(self.raw.get("decision_timebox_days", 0) or 0)

    @property
    def rule_variants(self) -> list[dict[str, Any]]:
        return list(self.raw.get("rule_variants", []))

    @property
    def sizing_variants(self) -> list[dict[str, Any]]:
        return list(self.raw.get("sizing_variants", []))

    def rule_variant(self, name: str) -> dict[str, Any]:
        for variant in self.rule_variants:
            if variant.get("name") == name:
                return dict(variant)
        raise KeyError(f"unknown rule variant: {name}")

    def sizing_variant(self, name: str) -> dict[str, Any]:
        for variant in self.sizing_variants:
            if variant.get("name") == name:
                return dict(variant)
        raise KeyError(f"unknown sizing variant: {name}")
