import csv

import pytest

from scripts.gino_operator_verdict import _read_row


def test_read_row_requires_filter_when_row_id_is_ambiguous(tmp_path):
    path = tmp_path / "rows.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["#", "Trader", "Ticker", "Event Type"])
        writer.writeheader()
        writer.writerow({"#": "16", "Trader": "glacierboy300", "Ticker": "CVX", "Event Type": "Update"})
        writer.writerow({"#": "16", "Trader": "Robby4C", "Ticker": "ORCL", "Event Type": "ENTRY"})

    with pytest.raises(SystemExit):
        _read_row(path, "16")

    row = _read_row(path, "16", trader="Robby4C", ticker="ORCL")
    assert row["Ticker"] == "ORCL"
