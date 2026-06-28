from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gino_gate.operator_verdict import explain_call


def _read_row(path: Path, row_id: str, *, trader: str = "", ticker: str = "") -> dict[str, str]:
    matches: list[dict[str, str]] = []
    with path.open("r", newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if str(row.get("#", "")).strip() != row_id:
                continue
            if trader and str(row.get("Trader", "")).strip().lower() != trader.lower():
                continue
            if ticker and str(row.get("Ticker", "")).strip().upper() != ticker.upper():
                continue
            matches.append(row)
    if not matches:
        raise SystemExit(f"row {row_id} not found in {path} with the provided filters")
    if len(matches) > 1:
        options = ", ".join(f"{row.get('Trader')} {row.get('Ticker')} {row.get('Event Type')}" for row in matches[:8])
        raise SystemExit(f"row {row_id} is ambiguous; add --trader/--ticker. Matches: {options}")
    return matches[0]


def main() -> int:
    parser = argparse.ArgumentParser(description="Explain one trading call the way Gino's agent would.")
    parser.add_argument("source_csv", type=Path)
    parser.add_argument("--row-id", required=True)
    parser.add_argument("--trader", default="")
    parser.add_argument("--ticker", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    verdict = explain_call(_read_row(args.source_csv, args.row_id, trader=args.trader, ticker=args.ticker))
    if args.json:
        print(json.dumps(asdict(verdict), indent=2, sort_keys=True))
        return 0

    print(f"Verdict: {verdict.verdict}")
    print(f"Action: {verdict.action}")
    print(f"Trader: {verdict.trader}")
    print(f"Ticker: {verdict.ticker}")
    print("")
    print(verdict.summary)
    print("")
    print("Reasons:")
    for reason in verdict.reasons:
        print(f"- {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
