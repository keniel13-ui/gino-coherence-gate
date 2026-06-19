"""Read-only visit readiness checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .manifest import filter_manifest
from .policy import PolicyEnvelope


@dataclass(frozen=True)
class SetupStatus:
    ready_for_visit: bool
    manifest_loaded: bool
    read_tools: list[str] = field(default_factory=list)
    blocked_tools: list[str] = field(default_factory=list)
    unknown_tools: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ready_for_visit": self.ready_for_visit,
            "manifest_loaded": self.manifest_loaded,
            "read_tools": self.read_tools,
            "blocked_tools": self.blocked_tools,
            "unknown_tools": self.unknown_tools,
            "blockers": self.blockers,
        }


def assess_manifest_for_read_only_visit(
    manifest: dict[str, Any] | None,
    policy: PolicyEnvelope,
) -> SetupStatus:
    """Assess whether a manifest can support a no-trade Gino setup visit."""
    if manifest is None:
        return SetupStatus(
            ready_for_visit=False,
            manifest_loaded=False,
            blockers=["no_manifest_loaded"],
        )

    filtered = filter_manifest(manifest, policy.allowed_tools("read_only"))
    exposed = [tool["name"] for tool in filtered["exposed"]]
    blocked = [tool["name"] for tool in filtered["blocked"]]
    unknown = [tool["name"] for tool in filtered["blocked"] if tool["kind"] == "unknown"]

    blockers: list[str] = []
    if not exposed:
        blockers.append("no_read_tools_exposed")
    if not blocked:
        blockers.append("no_trade_or_review_tools_observed")

    return SetupStatus(
        ready_for_visit=not blockers,
        manifest_loaded=True,
        read_tools=exposed,
        blocked_tools=blocked,
        unknown_tools=unknown,
        blockers=blockers,
    )
