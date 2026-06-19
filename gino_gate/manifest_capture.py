"""Normalize captured MCP tool-list payloads into the gate manifest shape."""

from __future__ import annotations

from typing import Any


class ManifestCaptureError(ValueError):
    """Raised when a captured payload does not contain a usable tools list."""


def normalize_manifest_payload(payload: Any) -> dict[str, list[dict[str, Any]]]:
    """Return a canonical ``{"tools": [...]}`` manifest from common MCP dumps.

    The Robinhood MCP client owns authentication. This function only normalizes
    the tool-list JSON after a user-authenticated MCP client has displayed or
    exported it.
    """
    raw_tools = _extract_raw_tools(payload)
    tools: list[dict[str, Any]] = []

    for item in raw_tools:
        if isinstance(item, str):
            tools.append({"name": item})
            continue

        if isinstance(item, dict) and item.get("name"):
            copied = dict(item)
            copied["name"] = str(copied["name"])
            tools.append(copied)
            continue

        raise ManifestCaptureError(f"tool entry lacks a name: {item!r}")

    if not tools:
        raise ManifestCaptureError("tools list is empty")

    return {"tools": tools}


def _extract_raw_tools(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload

    if not isinstance(payload, dict):
        raise ManifestCaptureError("manifest payload must be a JSON object or list")

    # MCP JSON-RPC tools/list response.
    result = payload.get("result")
    if isinstance(result, dict) and isinstance(result.get("tools"), list):
        return result["tools"]

    # Already-normalized or direct client export.
    if isinstance(payload.get("tools"), list):
        return payload["tools"]

    # Some clients wrap per-server manifests.
    servers = payload.get("servers")
    if isinstance(servers, dict):
        for server in servers.values():
            if isinstance(server, dict) and isinstance(server.get("tools"), list):
                return server["tools"]

    raise ManifestCaptureError("no tools list found in manifest payload")
