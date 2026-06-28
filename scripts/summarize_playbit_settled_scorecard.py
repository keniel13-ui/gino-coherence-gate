from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def combine_rows(scorecard_rows: list[dict[str, str]], settlement_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    settlements = {row["key"]: row for row in settlement_rows}
    combined: list[dict[str, str]] = []
    for row in scorecard_rows:
        out = dict(row)
        out["settlement_status"] = ""
        out["settlement_underlying_close"] = ""
        out["settlement_reason"] = ""
        settlement = settlements.get(row["key"])
        if row.get("score_status") == "NEEDS_PRICE_SETTLEMENT" and settlement:
            out["settlement_status"] = settlement["settlement_status"]
            out["settlement_underlying_close"] = settlement["underlying_close"]
            out["settlement_reason"] = settlement["reason"]
            if settlement["settlement_status"] == "SETTLED_WORTHLESS":
                out["score_status"] = "SCORED_HELD_TO_EXPIRY"
                out["realized_return_pct"] = settlement["settled_return_pct"]
                out["return_quality"] = settlement["return_quality"]
                out["reason"] = "expired/no-close settled against underlying expiry close"
            elif settlement["settlement_status"] == "NEEDS_OPTION_PRICE_SETTLEMENT":
                out["score_status"] = "NEEDS_OPTION_PRICE_SETTLEMENT"
                out["return_quality"] = settlement["return_quality"]
                out["reason"] = settlement["reason"]
        combined.append(out)
    return combined


def _summary(rows: list[dict[str, str]]) -> list[str]:
    counts = Counter(row["score_status"] for row in rows)
    scored_rows = [
        row for row in rows
        if row["score_status"] in {"SCORED", "SCORED_HELD_TO_EXPIRY"} and row.get("realized_return_pct")
    ]
    returns = [float(row["realized_return_pct"]) for row in scored_rows]
    settled_worthless = [row for row in rows if row["score_status"] == "SCORED_HELD_TO_EXPIRY"]
    lines = [
        "# PlayBit Settled Agent-Takeable Scorecard",
        "",
        "This combines the original agent-takeable scorecard with expired/no-close settlement.",
        "",
        "Important boundary: this is an equal-position percent-unit blind-follow readout, not a final dollar P/L model.",
        "It still does not include stop enforcement, full option-price settlement, or complete trim/quantity math.",
        "",
        "## Counts",
        "",
        f"- Positions reviewed: {len(rows)}",
    ]
    for status, count in counts.most_common():
        lines.append(f"- {status}: {count}")
    lines.extend(["", "## Blind-Follow Snapshot", ""])
    if returns:
        wins = [value for value in returns if value > 0]
        losses = [value for value in returns if value <= 0]
        lines.extend([
            f"- Scored/settled trades: {len(returns)}",
            f"- Wins: {len(wins)}",
            f"- Losses: {len(losses)}",
            f"- Expired/no-close settled worthless: {len(settled_worthless)}",
            f"- Average return pct units: {sum(returns) / len(returns):.2f}",
            f"- Net return pct units: {sum(returns):.2f}",
        ])
    else:
        lines.append("- No scored/settled trades yet.")
    lines.extend([
        "",
        "## Verdict",
        "",
        "Blind-following the captured agent-takeable sample does not survive the expired/no-close settlement pass.",
        "That does not prove a disciplined version cannot work; it proves the visible Discord record was not enough evidence to act on.",
    ])
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description="Combine agent scorecard with expired/no-close settlements.")
    parser.add_argument("--scorecard-csv", type=Path, required=True)
    parser.add_argument("--settlement-csv", type=Path, required=True)
    parser.add_argument("--out-csv", type=Path, required=True)
    parser.add_argument("--summary-md", type=Path, required=True)
    args = parser.parse_args()

    rows = combine_rows(_read_csv(args.scorecard_csv), _read_csv(args.settlement_csv))
    _write_csv(args.out_csv, rows)
    args.summary_md.write_text("\n".join(_summary(rows)) + "\n", encoding="utf-8")

    print(f"positions={len(rows)}")
    for status, count in sorted(Counter(row["score_status"] for row in rows).items()):
        print(f"{status}={count}")
    print(f"out_csv={args.out_csv}")
    print(f"summary_md={args.summary_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
