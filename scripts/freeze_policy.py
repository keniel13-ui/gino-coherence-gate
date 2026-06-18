from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gino_gate.policy import canonical_json
from gino_gate.scoring_policy import ScoringPolicy


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    policy_path = root / "config" / "scoring_policy.frozen.2026-06-18.json"
    anchor_path = root / "config" / "scoring_policy.frozen.2026-06-18.anchor.json"
    policy = ScoringPolicy.from_file(policy_path)
    anchor = {
        "policy_path": str(policy_path.relative_to(root)),
        "policy_id": policy.policy_id,
        "policy_hash": policy.policy_hash,
        "anchor_note": "Machine-readable frozen scoring policy hash. Git commit anchor pending because gino-coherence-gate is not currently a git repo.",
    }
    anchor_path.write_text(canonical_json(anchor) + "\n", encoding="utf-8")
    print(json.dumps(anchor, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
