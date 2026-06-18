from __future__ import annotations

from dataclasses import dataclass
from typing import Any


READ_PREFIXES = ("get_", "list_", "search", "fetch_", "read_")
READ_HINTS = ("quote", "quotes", "position", "positions", "portfolio", "account", "accounts", "balance", "orders", "history", "watchlist")
REVIEW_HINTS = ("review", "preview", "dry_run", "dryrun", "estimate")
PLACE_HINTS = ("place", "submit", "create_order", "buy", "sell")
CANCEL_HINTS = ("cancel", "void")


@dataclass(frozen=True)
class ToolClassification:
    name: str
    kind: str
    reason: str


def classify_tool(name: str) -> ToolClassification:
    lowered = name.lower()

    if any(hint in lowered for hint in CANCEL_HINTS):
        return ToolClassification(name, "trade_cancel", "cancel-like tool name")

    if any(hint in lowered for hint in PLACE_HINTS) and "order" in lowered:
        return ToolClassification(name, "trade_place", "order-placement-like tool name")

    if any(hint in lowered for hint in REVIEW_HINTS):
        return ToolClassification(name, "review", "review/preview-like tool name")

    if lowered.startswith(READ_PREFIXES) or any(hint in lowered for hint in READ_HINTS):
        return ToolClassification(name, "read", "read-like tool name")

    return ToolClassification(name, "unknown", "unclassified; block until manually bound")


def extract_tool_names(manifest: dict[str, Any] | list[Any]) -> list[str]:
    if isinstance(manifest, list):
        items = manifest
    else:
        items = manifest.get("tools", [])

    names: list[str] = []
    for item in items:
        if isinstance(item, str):
            names.append(item)
        elif isinstance(item, dict) and "name" in item:
            names.append(str(item["name"]))
    return names


def filter_manifest(manifest: dict[str, Any] | list[Any], allowed_tools: set[str]) -> dict[str, list[dict[str, str]]]:
    exposed: list[dict[str, str]] = []
    blocked: list[dict[str, str]] = []

    for name in extract_tool_names(manifest):
        classification = classify_tool(name)
        entry = {"name": name, "kind": classification.kind, "reason": classification.reason}
        if name in allowed_tools and classification.kind == "read":
            exposed.append(entry)
        else:
            blocked.append(entry)

    return {"exposed": exposed, "blocked": blocked}
