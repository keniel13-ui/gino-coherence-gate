from __future__ import annotations

import csv
from pathlib import Path

from scripts.normalize_playbit_signal_chains import _pct_to_float, _read_rows, build_trade_ledger


HEADERS = [
    "#",
    "Trader",
    "Date",
    "Time",
    "Ticker",
    "Direction",
    "Contract / Fill",
    "Event Type",
    "Mark",
    "P/L %",
    "P/L $",
    "Trader Commentary",
]


def write_source(path: Path, rows: list[list[str]]) -> Path:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(HEADERS)
        writer.writerows(rows)
    return path


def ledger_by_ticker(path: Path) -> dict[str, dict[str, str]]:
    messages = _read_rows(path)
    ledger = build_trade_ledger(messages)
    return {row["ticker"]: row for row in ledger}


def test_complete_chain_counts_only_when_entry_and_realized_outcome_exist(tmp_path: Path) -> None:
    source = write_source(
        tmp_path / "source.csv",
        [
            ["1", "glacier", "1/1/26", "9:30 AM", "COIN", "Call", "200c @4.90", "ENTRY", "", "", "", "new trade"],
            ["2", "glacier", "1/2/26", "10:00 AM", "COIN", "Call", "200c", "Update", "7.00", "40%", "", "+40%"],
            ["3", "glacier", "1/3/26", "11:00 AM", "COIN", "Call", "200c", "FINAL SELL — WIN", "17.05", "247.96%", "$6,075", "selling all"],
        ],
    )

    coin = ledger_by_ticker(source)["COIN"]

    assert coin["chain_completeness"] == "COMPLETE"
    assert coin["countable_now"] == "yes"
    assert coin["outcome_label"] == "WIN_OR_EXIT"


def test_green_update_without_realized_close_is_quarantined(tmp_path: Path) -> None:
    source = write_source(
        tmp_path / "source.csv",
        [
            ["1", "robby", "1/1/26", "9:30 AM", "NVDA", "Call", "225c @2.37", "ENTRY", "", "", "", "new trade"],
            ["2", "robby", "1/1/26", "11:00 AM", "NVDA", "Call", "225c", "Trim", "", "170%", "", "huge green"],
        ],
    )

    nvda = ledger_by_ticker(source)["NVDA"]

    assert nvda["chain_completeness"] == "PARTIAL_ENTRY_NO_REALIZED_OUTCOME"
    assert nvda["countable_now"] == "no"


def test_outcome_without_entry_is_quarantined(tmp_path: Path) -> None:
    source = write_source(
        tmp_path / "source.csv",
        [
            ["1", "glacier", "1/1/26", "9:30 AM", "RIVN", "Call", "20c", "Final Sell", "3.30", "725%", "$290", "last contract"],
        ],
    )

    rivn = ledger_by_ticker(source)["RIVN"]

    assert rivn["chain_completeness"] == "PARTIAL_OUTCOME_NO_ENTRY"
    assert rivn["countable_now"] == "no"


def test_loss_with_entry_counts_as_realized_loss(tmp_path: Path) -> None:
    source = write_source(
        tmp_path / "source.csv",
        [
            ["1", "glacier", "1/1/26", "9:30 AM", "PYPL", "Call", "70c @0.62", "ENTRY", "", "", "", "new trade"],
            ["2", "glacier", "1/2/26", "10:00 AM", "PYPL", "Call", "70c", "CLOSE — LOSS", "0.345", "-44.35%", "($825)", "cutting"],
        ],
    )

    pypl = ledger_by_ticker(source)["PYPL"]

    assert pypl["chain_completeness"] == "COMPLETE"
    assert pypl["countable_now"] == "yes"
    assert pypl["outcome_label"] == "LOSS"
    assert pypl["last_reported_pnl_dollars"] == "-825.00"


def test_same_ticker_different_traders_do_not_pool(tmp_path: Path) -> None:
    source = write_source(
        tmp_path / "source.csv",
        [
            ["1", "glacier", "1/1/26", "9:30 AM", "MSFT", "Put", "450p @4.33", "ENTRY", "", "", "", "new trade"],
            ["2", "glacier", "1/2/26", "10:00 AM", "MSFT", "Put", "450p", "FINAL SELL — WIN", "9.90", "122%", "$2,725", "done"],
            ["3", "robby", "1/1/26", "9:45 AM", "MSFT", "Call", "420c @5.98", "ENTRY", "", "", "", "new trade"],
            ["4", "robby", "1/2/26", "11:00 AM", "MSFT", "Call", "420c", "Update", "", "400%", "", "runner"],
        ],
    )

    messages = _read_rows(source)
    ledger = build_trade_ledger(messages)

    assert len(ledger) == 2
    statuses = {(row["trader"], row["direction"]): row["chain_completeness"] for row in ledger}
    assert statuses[("glacier", "Put")] == "COMPLETE"
    assert statuses[("robby", "Call")] == "PARTIAL_ENTRY_NO_REALIZED_OUTCOME"


def test_pnl_percent_parser_rejects_decimal_fragments_without_percent_sign() -> None:
    assert _pct_to_float("0.88") is None
    assert _pct_to_float("2.5") is None
    assert _pct_to_float("88%") == 88
    assert _pct_to_float("250") == 250
