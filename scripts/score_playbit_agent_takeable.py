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
from gino_gate.scorecard import score_positions


def _read_rows(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with path.open("r", newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if str(row.get("#", "")).strip().isdigit():
                rows.append(row)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Score agent-takeable PlayBit paper positions without inflated P/L.")
    parser.add_argument("source_csv", type=Path)
    parser.add_argument("--out-csv", type=Path, required=True)
    parser.add_argument("--summary-md", type=Path, required=True)
    parser.add_argument("--as-of-date", default="2026-06-25")
    args = parser.parse_args()

    positions = replay_rows(_read_rows(args.source_csv), as_of=date.fromisoformat(args.as_of_date))
    scored = score_positions(positions)
    rows = [asdict(row) for row in scored]
    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.out_csv.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    status_counts = Counter(row.score_status for row in scored)
    scored_rows = [row for row in scored if row.score_status == "SCORED" and row.realized_return_pct]
    returns = [float(row.realized_return_pct) for row in scored_rows]
    summary = [
        "# PlayBit Agent-Takeable Scorecard — 2026-06-25",
        "",
        "This scorecard is intentionally stricter than the trader-history ledger.",
        "",
        "Rules:",
        "",
        "- Only `PAPER_READY` entries are agent-takeable.",
        "- Expired/no-close positions are not scored until settled against external price data.",
        "- Dirty P/L fragments are not guessed into returns.",
        "- Trim-aware returns are calculated only from explicit trim/final events with parseable P/L.",
        "",
        "## Counts",
        "",
        f"- Positions reviewed: {len(scored)}",
    ]
    for status, count in status_counts.most_common():
        summary.append(f"- {status}: {count}")
    summary.extend(["", "## Scored Return Snapshot", ""])
    if returns:
        wins = [value for value in returns if value > 0]
        losses = [value for value in returns if value <= 0]
        summary.extend([
            f"- Scored trades: {len(returns)}",
            f"- Wins: {len(wins)}",
            f"- Losses: {len(losses)}",
            f"- Average scored return pct: {sum(returns) / len(returns):.2f}",
            f"- Net scored return pct units: {sum(returns):.2f}",
        ])
    else:
        summary.append("- No scored trades yet.")
    summary.extend([
        "",
        "## Verdict",
        "",
        "This is an agent-readiness scorecard, not a profitability proof.",
        "The denominator is still too incomplete until expired/no-close trades are settled and trim math is verified.",
    ])
    args.summary_md.write_text("\n".join(summary) + "\n", encoding="utf-8")

    print(f"positions={len(scored)}")
    for status, count in sorted(status_counts.items()):
        print(f"{status}={count}")
    print(f"scored={len(scored_rows)}")
    print(f"out_csv={args.out_csv}")
    print(f"summary_md={args.summary_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
