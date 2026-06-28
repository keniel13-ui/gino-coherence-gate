from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from dataclasses import asdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gino_gate.expiry_settlement import settle_expired_no_close_positions
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


def _summary_lines(rows: list[dict[str, str]], *, as_of: str) -> list[str]:
    statuses = Counter(row["settlement_status"] for row in rows)
    settled_loss_rows = [row for row in rows if row["settlement_status"] == "SETTLED_WORTHLESS"]
    prior_green = [
        row for row in settled_loss_rows
        if row["last_pnl_pct"] or row["last_pnl_dollars"]
    ]
    lines = [
        f"# PlayBit Expired/No-Close Settlement — {as_of}",
        "",
        "Purpose: settle agent-takeable expired option positions that had no captured close message.",
        "",
        "Method:",
        "",
        "- Replayed PlayBit rows into paper positions.",
        "- Selected only `PAPER_READY` positions marked `EXPIRED_NO_CLOSE`.",
        "- Fetched the underlying daily close on or before option expiry.",
        "- If a long option finished out-of-the-money, settled it as `SETTLED_WORTHLESS` / `-100%` under held-to-expiry accounting.",
        "- If a long option finished in-the-money, left it as `NEEDS_OPTION_PRICE_SETTLEMENT` rather than inventing a return.",
        "",
        "## Counts",
        "",
        f"- Positions settled/reviewed: {len(rows)}",
    ]
    for status, count in statuses.most_common():
        lines.append(f"- {status}: {count}")
    lines.extend([
        f"- Prior visible green/update rows that settled worthless: {len(prior_green)}",
        "",
        "## Boundary",
        "",
        "This is a blind-follow / held-to-expiry survivorship check, not a final disciplined-agent profitability verdict.",
        "Stops, trims, and option-price settlement still need separate enforcement before any money claim.",
    ])
    if prior_green:
        lines.extend(["", "## Green Marks That Became Worthless", ""])
        for row in prior_green:
            visible = row["last_pnl_pct"] or row["last_pnl_dollars"]
            lines.append(
                f"- {row['trader']} {row['ticker']} {row['strike']}{row['option_type'][0].upper()} "
                f"{row['expiry_date']}: last visible `{visible}`, expiry close {row['underlying_close']} -> -100%"
            )
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description="Settle PlayBit expired/no-close PAPER_READY options with underlying expiry prices.")
    parser.add_argument("source_csv", type=Path)
    parser.add_argument("--out-csv", type=Path, required=True)
    parser.add_argument("--summary-md", type=Path, required=True)
    parser.add_argument("--as-of-date", default="2026-06-25")
    args = parser.parse_args()

    positions = replay_rows(_read_rows(args.source_csv), as_of=date.fromisoformat(args.as_of_date))
    settlements = settle_expired_no_close_positions(positions)
    rows = [asdict(row) for row in settlements]
    _write_csv(args.out_csv, rows)
    args.summary_md.write_text("\n".join(_summary_lines(rows, as_of=args.as_of_date)) + "\n", encoding="utf-8")

    print(f"settlements={len(rows)}")
    for status, count in sorted(Counter(row['settlement_status'] for row in rows).items()):
        print(f"{status}={count}")
    print(f"out_csv={args.out_csv}")
    print(f"summary_md={args.summary_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
