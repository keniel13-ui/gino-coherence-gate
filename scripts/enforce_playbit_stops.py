from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from dataclasses import asdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gino_gate.paper_forward import replay_rows
from gino_gate.stop_enforcement import enforce_expired_no_close_stops


def _read_rows(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with path.open("r", newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if str(row.get("#", "")).strip().isdigit():
                rows.append(row)
    return rows


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _summary(rows: list[dict[str, str]], *, as_of: str) -> list[str]:
    counts = Counter(row["stop_status"] for row in rows)
    lines = [
        f"# PlayBit Stop-Enforcement Pass — {as_of}",
        "",
        "Purpose: test whether the expired/no-close losses had mechanically enforceable stops before expiry.",
        "",
        "Method:",
        "",
        "- Replayed PlayBit rows into paper positions.",
        "- Selected only `PAPER_READY` positions marked `EXPIRED_NO_CLOSE`.",
        "- Parsed numeric stop levels from entry commentary.",
        "- Fetched underlying daily bars from entry date through expiry.",
        "- Marked stops as triggered only when daily high/low crossed the stated stop level.",
        "- Flagged semantic, intraday, indicator, or cross-instrument stops instead of guessing.",
        "",
        "## Counts",
        "",
        f"- Positions reviewed: {len(rows)}",
    ]
    for status, count in counts.most_common():
        lines.append(f"- {status}: {count}")
    lines.extend([
        "",
        "## Boundary",
        "",
        "This pass can show whether discipline would have interrupted a terminal loss.",
        "It still cannot compute exact option exit P/L without option price history at the stop timestamp.",
    ])
    triggered = [row for row in rows if row["stop_status"] == "STOP_TRIGGERED"]
    if triggered:
        lines.extend(["", "## Triggered Stops", ""])
        for row in triggered:
            lines.append(
                f"- {row['trader']} {row['ticker']} {row['direction']} exp {row['expiry_date']}: "
                f"{row['stop_raw']} crossed on {row['triggered_date']} "
                f"(high {row['triggered_bar_high']}, low {row['triggered_bar_low']})"
            )
    unenforceable = [row for row in rows if row["stop_status"] not in {"STOP_TRIGGERED", "STOP_NOT_TRIGGERED"}]
    if unenforceable:
        lines.extend(["", "## Not Mechanically Enforceable From Daily Underlying Bars", ""])
        for row in unenforceable:
            lines.append(f"- {row['trader']} {row['ticker']}: `{row['stop_raw']}` — {row['reason']}")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description="Check PlayBit expired/no-close PAPER_READY trades against stated stops.")
    parser.add_argument("source_csv", type=Path)
    parser.add_argument("--out-csv", type=Path, required=True)
    parser.add_argument("--summary-md", type=Path, required=True)
    parser.add_argument("--as-of-date", default="2026-06-25")
    args = parser.parse_args()

    positions = replay_rows(_read_rows(args.source_csv), as_of=date.fromisoformat(args.as_of_date))
    rows = [asdict(row) for row in enforce_expired_no_close_stops(positions)]
    _write_csv(args.out_csv, rows)
    args.summary_md.write_text("\n".join(_summary(rows, as_of=args.as_of_date)) + "\n", encoding="utf-8")

    print(f"positions={len(rows)}")
    for status, count in sorted(Counter(row["stop_status"] for row in rows).items()):
        print(f"{status}={count}")
    print(f"out_csv={args.out_csv}")
    print(f"summary_md={args.summary_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
