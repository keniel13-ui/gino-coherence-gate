from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from dataclasses import asdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gino_gate.live_eligibility import evaluate_live_eligible_positions
from gino_gate.paper_forward import replay_rows


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
    eligible = [row for row in rows if row["live_eligible"] == "yes"]
    outcome_counts = Counter(row["discipline_outcome"] for row in eligible)
    exclusion_counts = Counter(row["reason"] for row in rows if row["live_eligible"] == "no")
    lines = [
        f"# PlayBit Live-Eligibility Discipline Pass — {as_of}",
        "",
        "Purpose: separate trades the agent could actually take live from trades it should refuse.",
        "",
        "Live-eligible requires:",
        "",
        "- `PAPER_READY` entry.",
        "- Machine-checkable numeric stop.",
        "- Machine-checkable numeric target.",
        "- Underlying daily bars available from entry to close/expiry endpoint.",
        "",
        "## Counts",
        "",
        f"- Positions reviewed: {len(rows)}",
        f"- Live-eligible: {len(eligible)}",
        f"- Refused / paper-only: {len(rows) - len(eligible)}",
        "",
        "## Discipline Outcomes On Live-Eligible Set",
        "",
    ]
    if outcome_counts:
        for outcome, count in outcome_counts.most_common():
            lines.append(f"- {outcome}: {count}")
    else:
        lines.append("- None.")

    lines.extend(["", "## Live-Eligible Trades", ""])
    if not eligible:
        lines.append("- None.")
    else:
        for row in eligible:
            lines.append(
                f"- {row['trader']} {row['ticker']} {row['direction']} "
                f"({row['entry_date']}->{row['end_date']}): {row['discipline_outcome']} "
                f"on {row['outcome_date'] or 'n/a'}; stop `{row['stop_raw']}`, target `{row['target_raw']}`"
            )

    lines.extend(["", "## Top Refusal Reasons", ""])
    if not exclusion_counts:
        lines.append("- None.")
    else:
        for reason, count in exclusion_counts.most_common(10):
            lines.append(f"- {count}: {reason}")

    lines.extend([
        "",
        "## Boundary",
        "",
        "This is a disciplined eligibility/outcome pass, not exact option P/L.",
        "Exact P/L requires option-price history at stop/target timestamps and position sizing.",
    ])
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate PlayBit positions under the stricter live-eligibility policy.")
    parser.add_argument("source_csv", type=Path)
    parser.add_argument("--out-csv", type=Path, required=True)
    parser.add_argument("--summary-md", type=Path, required=True)
    parser.add_argument("--as-of-date", default="2026-06-25")
    args = parser.parse_args()

    positions = replay_rows(_read_rows(args.source_csv), as_of=date.fromisoformat(args.as_of_date))
    rows = [asdict(row) for row in evaluate_live_eligible_positions(positions)]
    _write_csv(args.out_csv, rows)
    args.summary_md.write_text("\n".join(_summary(rows, as_of=args.as_of_date)) + "\n", encoding="utf-8")

    print(f"positions={len(rows)}")
    print(f"live_eligible={sum(1 for row in rows if row['live_eligible'] == 'yes')}")
    for outcome, count in sorted(Counter(row["discipline_outcome"] for row in rows).items()):
        print(f"{outcome}={count}")
    print(f"out_csv={args.out_csv}")
    print(f"summary_md={args.summary_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
