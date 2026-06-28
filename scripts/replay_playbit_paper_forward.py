from __future__ import annotations

import argparse
import csv
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gino_gate.paper_forward import positions_as_dicts, replay_rows


def _read_rows(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with path.open("r", newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if str(row.get("#", "")).strip().isdigit():
                rows.append(row)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay PlayBit rows as a paper-forward position ledger.")
    parser.add_argument("source_csv", type=Path)
    parser.add_argument("--out-csv", type=Path, required=True)
    parser.add_argument("--as-of-date", default="2026-06-25", help="YYYY-MM-DD date used to resolve expired open options")
    args = parser.parse_args()

    positions = replay_rows(_read_rows(args.source_csv), as_of=date.fromisoformat(args.as_of_date))
    rows = positions_as_dicts(positions)
    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "key",
        "trader",
        "ticker",
        "direction",
        "status",
        "opened_row",
        "closed_row",
        "expiry_date",
        "intent_verdict",
        "intent_reason",
        "last_event_type",
        "last_pnl_pct",
        "last_pnl_dollars",
        "event_count",
    ]
    with args.out_csv.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    counts: dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    print(f"positions={len(rows)}")
    for status, count in sorted(counts.items()):
        print(f"{status}={count}")
    print(f"out_csv={args.out_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
