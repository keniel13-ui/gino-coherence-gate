#!/usr/bin/env python3
"""Normalize an MCP tools/list capture and run the read-only readiness check."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gino_gate.manifest_capture import ManifestCaptureError, normalize_manifest_payload
from gino_gate.policy import PolicyEnvelope
from gino_gate.setup_status import assess_manifest_for_read_only_visit


def _read_json(path: str) -> object:
    raw = sys.stdin.read() if path == "-" else Path(path).read_text()
    return json.loads(raw)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Normalize a captured MCP tools/list response into a gate manifest."
    )
    parser.add_argument(
        "capture_json",
        help="Raw captured JSON path, or '-' for stdin. Never include tokens or secrets.",
    )
    parser.add_argument(
        "--output",
        default="manifests/robinhood_manifest.normalized.json",
        help="Where to write the normalized manifest. This path is gitignored by default.",
    )
    parser.add_argument(
        "--policy",
        default="config/policy.example.json",
        help="PolicyEnvelope JSON path for readiness assessment.",
    )
    args = parser.parse_args()

    try:
        manifest = normalize_manifest_payload(_read_json(args.capture_json))
    except (json.JSONDecodeError, ManifestCaptureError) as exc:
        raise SystemExit(f"manifest capture failed: {exc}") from exc

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    policy = PolicyEnvelope.from_file(args.policy)
    status = assess_manifest_for_read_only_visit(manifest, policy)
    summary = status.as_dict()
    summary["normalized_manifest_path"] = str(output_path)
    summary["boundary"] = "manifest_normalization_only_no_auth_no_orders"
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
