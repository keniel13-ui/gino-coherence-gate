from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gino_gate.trade_intent import propose_trade_intent


def _read_signal_rows(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with path.open("r", newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if str(row.get("#", "")).strip().isdigit():
                rows.append(row)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert PlayBit entry rows into paper/live trade intents.")
    parser.add_argument("source_csv", type=Path)
    parser.add_argument("--out-csv", type=Path, required=True)
    parser.add_argument("--mode", choices=["paper", "live"], default="paper")
    args = parser.parse_args()

    output_rows: list[dict[str, str]] = []
    for row in _read_signal_rows(args.source_csv):
        intent = propose_trade_intent(row, mode=args.mode)
        if intent.action == "log_only" and intent.verdict == "BLOCK":
            continue
        body = asdict(intent)
        order_args = body.pop("order_args") or {}
        output_rows.append({
            "source_row": str(row.get("#", "")),
            "date": str(row.get("Date", "")),
            "time": str(row.get("Time", "")),
            "event_type": str(row.get("Event Type", "")),
            "contract": str(row.get("Contract / Fill", "")),
            "commentary": str(row.get("Trader Commentary", "")),
            **{key: "" if value is None else str(value) for key, value in body.items()},
            "order_args": str(order_args),
        })

    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "source_row",
        "date",
        "time",
        "event_type",
        "contract",
        "commentary",
        "verdict",
        "action",
        "trader",
        "ticker",
        "reason",
        "instrument",
        "robinhood_tool",
        "order_args",
    ]
    with args.out_csv.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)

    counts: dict[str, int] = {}
    for row in output_rows:
        counts[row["verdict"]] = counts.get(row["verdict"], 0) + 1
    print(f"mode={args.mode}")
    print(f"entry_intents={len(output_rows)}")
    for verdict, count in sorted(counts.items()):
        print(f"{verdict}={count}")
    print(f"out_csv={args.out_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
