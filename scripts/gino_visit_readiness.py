#!/usr/bin/env python3
"""Check whether a manifest supports a read-only Gino setup visit.

This script does not authenticate to Robinhood and does not call any upstream MCP
server. Pass a captured manifest when one exists. Without a manifest, it uses the
reported public tool surface only as a local readiness example.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gino_gate.policy import PolicyEnvelope
from gino_gate.setup_status import assess_manifest_for_read_only_visit


REPORTED_SAMPLE_MANIFEST = {
    "tools": [
        {"name": "get_accounts"},
        {"name": "get_portfolio"},
        {"name": "get_equity_positions"},
        {"name": "get_equity_quotes"},
        {"name": "get_equity_orders"},
        {"name": "search"},
        {"name": "review_equity_order"},
        {"name": "place_equity_order"},
        {"name": "cancel_equity_order"},
    ]
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--policy",
        default="config/policy.example.json",
        help="PolicyEnvelope JSON path.",
    )
    parser.add_argument(
        "--manifest-json",
        help="Captured MCP manifest JSON path. If omitted, uses a reported sample.",
    )
    args = parser.parse_args()

    policy = PolicyEnvelope.from_file(args.policy)
    if args.manifest_json:
        manifest = json.loads(Path(args.manifest_json).read_text())
        source = args.manifest_json
    else:
        manifest = REPORTED_SAMPLE_MANIFEST
        source = "reported_sample_manifest_not_live"

    status = assess_manifest_for_read_only_visit(manifest, policy)
    output = status.as_dict()
    output["manifest_source"] = source
    output["boundary"] = "read_only_readiness_only_no_auth_no_orders"
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
