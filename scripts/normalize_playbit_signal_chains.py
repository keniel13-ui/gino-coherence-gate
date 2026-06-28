from __future__ import annotations

import argparse
import csv
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path


ENTRY_TERMS = ("ENTRY", "ADD")
FINAL_TERMS = ("FINAL", "CLOSE", "EXIT")
PARTIAL_TERMS = ("TRIM", "UPDATE", "DRAWDOWN", "HOLD", "ROLL")


@dataclass(frozen=True)
class MessageRow:
    source_row: str
    trader: str
    date: str
    time: str
    ticker: str
    direction: str
    contract: str
    event_type: str
    mark: str
    pnl_pct: str
    pnl_dollars: str
    commentary: str


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def _money_to_float(value: str) -> float | None:
    text = _norm(value)
    if not text:
        return None
    neg = text.startswith("(") and text.endswith(")")
    text = text.strip("()").replace("$", "").replace(",", "")
    try:
        parsed = float(text)
    except ValueError:
        return None
    return -parsed if neg else parsed


def _pct_to_float(value: str) -> float | None:
    raw = _norm(value)
    if not raw:
        return None
    has_percent_sign = "%" in raw
    text = raw.replace("%", "")
    if not text:
        return None
    try:
        parsed = float(text)
    except ValueError:
        return None
    if not has_percent_sign and abs(parsed) <= 10:
        return None
    return parsed


def _chain_key(row: MessageRow) -> tuple[str, str, str]:
    # Keep the first implementation intentionally conservative: each trader/ticker/
    # direction is one strategy chain until the source export gives stable trade IDs.
    return (row.trader, row.ticker, row.direction)


def _read_rows(path: Path) -> list[MessageRow]:
    rows: list[MessageRow] = []
    with path.open("r", newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            source_row = _norm(row.get("#", ""))
            if not source_row.isdigit():
                continue
            rows.append(
                MessageRow(
                    source_row=source_row,
                    trader=_norm(row.get("Trader", "")),
                    date=_norm(row.get("Date", "")),
                    time=_norm(row.get("Time", "")),
                    ticker=_norm(row.get("Ticker", "")),
                    direction=_norm(row.get("Direction", "")),
                    contract=_norm(row.get("Contract / Fill", "")),
                    event_type=_norm(row.get("Event Type", "")),
                    mark=_norm(row.get("Mark", "")),
                    pnl_pct=_norm(row.get("P/L %", "")),
                    pnl_dollars=_norm(row.get("P/L $", "")),
                    commentary=_norm(row.get("Trader Commentary", "")),
                )
            )
    return rows


def _has_entry(rows: list[MessageRow]) -> bool:
    for row in rows:
        event = row.event_type.upper()
        if any(term in event for term in ENTRY_TERMS):
            return True
    return False


def _has_realized_outcome(rows: list[MessageRow]) -> bool:
    for row in rows:
        event = row.event_type.upper()
        if any(term in event for term in FINAL_TERMS):
            return True
    return False


def _outcome_label(rows: list[MessageRow]) -> str:
    events = " | ".join(row.event_type.upper() for row in rows)
    if "LOSS" in events:
        return "LOSS"
    if "WIN" in events or "FINAL" in events or "CLOSE" in events or "EXIT" in events:
        return "WIN_OR_EXIT"
    return "PENDING_OR_PARTIAL"


def _chain_completeness(rows: list[MessageRow]) -> str:
    entry = _has_entry(rows)
    outcome = _has_realized_outcome(rows)
    if entry and outcome:
        return "COMPLETE"
    if entry and not outcome:
        return "PARTIAL_ENTRY_NO_REALIZED_OUTCOME"
    if not entry and outcome:
        return "PARTIAL_OUTCOME_NO_ENTRY"
    return "PARTIAL_MIDSTREAM_ONLY"


def _latest_nonempty(values: list[str]) -> str:
    for value in reversed(values):
        if value:
            return value
    return ""


def build_trade_ledger(rows: list[MessageRow]) -> list[dict[str, str]]:
    chains: dict[tuple[str, str, str], list[MessageRow]] = defaultdict(list)
    for row in rows:
        chains[_chain_key(row)].append(row)

    ledger: list[dict[str, str]] = []
    for (trader, ticker, direction), chain_rows in sorted(chains.items()):
        chain_rows.sort(key=lambda row: int(row.source_row))
        completeness = _chain_completeness(chain_rows)
        countable = completeness == "COMPLETE"
        pnl_values = [_money_to_float(row.pnl_dollars) for row in chain_rows]
        pnl_values = [value for value in pnl_values if value is not None]
        pct_values = [_pct_to_float(row.pnl_pct) for row in chain_rows]
        pct_values = [value for value in pct_values if value is not None]
        entry_rows = [row.source_row for row in chain_rows if any(term in row.event_type.upper() for term in ENTRY_TERMS)]
        outcome_rows = [row.source_row for row in chain_rows if any(term in row.event_type.upper() for term in FINAL_TERMS)]
        ledger.append(
            {
                "trader": trader,
                "ticker": ticker,
                "direction": direction,
                "message_count": str(len(chain_rows)),
                "first_row": chain_rows[0].source_row,
                "last_row": chain_rows[-1].source_row,
                "first_date": chain_rows[0].date,
                "last_date": chain_rows[-1].date,
                "entry_present": "yes" if _has_entry(chain_rows) else "no",
                "realized_outcome_present": "yes" if _has_realized_outcome(chain_rows) else "no",
                "chain_completeness": completeness,
                "countable_now": "yes" if countable else "no",
                "outcome_label": _outcome_label(chain_rows),
                "max_reported_pnl_pct": f"{max(pct_values):.2f}" if pct_values else "",
                "min_reported_pnl_pct": f"{min(pct_values):.2f}" if pct_values else "",
                "last_reported_pnl_pct": f"{pct_values[-1]:.2f}" if pct_values else "",
                "max_reported_pnl_dollars": f"{max(pnl_values):.2f}" if pnl_values else "",
                "min_reported_pnl_dollars": f"{min(pnl_values):.2f}" if pnl_values else "",
                "last_reported_pnl_dollars": f"{pnl_values[-1]:.2f}" if pnl_values else "",
                "entry_rows": ";".join(entry_rows),
                "outcome_rows": ";".join(outcome_rows),
                "contracts_seen": " | ".join(dict.fromkeys(row.contract for row in chain_rows if row.contract)),
                "event_types_seen": " | ".join(dict.fromkeys(row.event_type for row in chain_rows if row.event_type)),
                "latest_commentary": _latest_nonempty([row.commentary for row in chain_rows]),
            }
        )
    return ledger


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_summary(path: Path, source: Path, messages: list[MessageRow], ledger: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    trader_messages = Counter(row.trader for row in messages)
    trader_chains = Counter(row["trader"] for row in ledger)
    completeness = Counter(row["chain_completeness"] for row in ledger)
    countable = [row for row in ledger if row["countable_now"] == "yes"]
    lines = [
        "# PlayBit Signal Chain Normalization — 2026-06-25",
        "",
        f"Source CSV: `{source}`",
        "",
        "## What Ran",
        "",
        "- Input rows are Discord/PlayBit message events.",
        "- Output rows are conservative trade chains grouped by trader, ticker, and direction.",
        "- A chain counts only when it has both an entry and a realized outcome.",
        "- Partial green updates, open positions, and outcome-only posts are quarantined from hit-rate/proof claims.",
        "",
        "## Counts",
        "",
        f"- Message rows parsed: {len(messages)}",
        f"- Approximate trade chains: {len(ledger)}",
        f"- Countable complete chains now: {len(countable)}",
        "",
        "## Messages By Trader",
        "",
    ]
    for trader, count in trader_messages.most_common():
        lines.append(f"- {trader}: {count} message rows")
    lines.extend(["", "## Chains By Trader", ""])
    for trader, count in trader_chains.most_common():
        lines.append(f"- {trader}: {count} chains")
    lines.extend(["", "## Completeness", ""])
    for status, count in completeness.most_common():
        lines.append(f"- {status}: {count}")
    lines.extend(["", "## Countable Chains", ""])
    if not countable:
        lines.append("- None yet.")
    else:
        for row in countable:
            lines.append(
                f"- {row['trader']} {row['ticker']} {row['direction']}: "
                f"{row['outcome_label']}, rows {row['first_row']}-{row['last_row']}, "
                f"last reported P/L {row['last_reported_pnl_pct']}%"
            )
    lines.extend(
        [
            "",
            "## Verdict",
            "",
            "This is enough to run the Gino v0 evidence gate and show how the agent separates countable chains from hype.",
            "It is not enough to claim that any trader or source is proven profitable.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize PlayBit signal-chain CSV into trade-level evidence.")
    parser.add_argument("source_csv", type=Path)
    parser.add_argument("--out-csv", type=Path, required=True)
    parser.add_argument("--summary-md", type=Path, required=True)
    args = parser.parse_args()

    messages = _read_rows(args.source_csv)
    if not messages:
        raise SystemExit(f"No message rows found in {args.source_csv}")
    ledger = build_trade_ledger(messages)
    write_csv(args.out_csv, ledger)
    write_summary(args.summary_md, args.source_csv, messages, ledger)
    print(f"parsed_messages={len(messages)}")
    print(f"trade_chains={len(ledger)}")
    print(f"complete_countable={sum(1 for row in ledger if row['countable_now'] == 'yes')}")
    print(f"out_csv={args.out_csv}")
    print(f"summary_md={args.summary_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
