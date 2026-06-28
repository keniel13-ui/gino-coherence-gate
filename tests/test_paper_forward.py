from datetime import date

from gino_gate.paper_forward import replay_rows


def row(
    idx,
    ticker="COIN",
    event_type="ENTRY",
    pnl_pct="",
    trader="glacierboy300",
    direction="Call",
    commentary="SL 143",
    contract="200c 3/20 @4.90",
):
    return {
        "#": str(idx),
        "Trader": trader,
        "Date": "1/1/26",
        "Time": "9:30 AM",
        "Ticker": ticker,
        "Direction": direction,
        "Contract / Fill": contract,
        "Event Type": event_type,
        "Mark": "",
        "P/L %": pnl_pct,
        "P/L $": "",
        "Trader Commentary": commentary,
    }


def test_replay_opens_updates_and_closes_position():
    positions = replay_rows([
        row(1, event_type="ENTRY", commentary="TP 208; SL 143"),
        row(2, event_type="Update", pnl_pct="40%"),
        row(3, event_type="FINAL SELL — WIN", pnl_pct="247.96%"),
    ])

    assert len(positions) == 1
    position = positions[0]
    assert position.status == "CLOSED"
    assert position.opened_row == "1"
    assert position.closed_row == "3"
    assert position.intent_verdict == "PAPER_READY"
    assert position.last_pnl_pct == "247.96%"
    assert position.event_count == 3


def test_replay_marks_close_without_entry_as_untracked():
    positions = replay_rows([
        row(1, ticker="RIVN", event_type="Final Sell", pnl_pct="725%"),
    ])

    assert len(positions) == 1
    assert positions[0].status == "UNTRACKED_CLOSE_NO_ENTRY"
    assert positions[0].closed_row == "1"


def test_replay_keeps_incomplete_entry_open():
    positions = replay_rows([
        row(1, ticker="NVDA", event_type="ENTRY", pnl_pct="", commentary="new trade"),
        row(2, ticker="NVDA", event_type="Trim", pnl_pct="110%", commentary="trim NVDA"),
    ])

    assert len(positions) == 1
    assert positions[0].status == "OPEN"
    assert positions[0].intent_verdict == "PAPER_ONLY"
    assert positions[0].last_pnl_pct == "110%"


def test_replay_marks_expired_open_option_as_expired_no_close():
    positions = replay_rows(
        [
            row(1, ticker="NVDA", event_type="ENTRY", pnl_pct="", commentary="new trade", contract="225c 6/12 @2.37"),
            row(2, ticker="NVDA", event_type="Trim", pnl_pct="110%", commentary="trim NVDA", contract="225c 6/12"),
        ],
        as_of=date(2026, 6, 25),
    )

    assert len(positions) == 1
    assert positions[0].status == "EXPIRED_NO_CLOSE"
    assert positions[0].expiry_date == "2026-06-12"


def test_replay_keeps_traders_separate():
    positions = replay_rows([
        row(1, ticker="MSFT", trader="glacierboy300", direction="Put", event_type="ENTRY", commentary="SL 490", contract="450p 1/30 @4.33"),
        row(2, ticker="MSFT", trader="Robby4C", direction="Call", event_type="ENTRY", commentary="small position"),
        row(3, ticker="MSFT", trader="glacierboy300", direction="Put", event_type="FINAL SELL — WIN", pnl_pct="122%", contract="450p 1/30"),
    ])

    assert len(positions) == 2
    statuses = {(position.trader, position.direction): position.status for position in positions}
    assert statuses[("glacierboy300", "Put")] == "CLOSED"
    assert statuses[("Robby4C", "Call")] == "OPEN"


def test_replay_keeps_same_ticker_different_contracts_separate():
    positions = replay_rows([
        row(1, ticker="SPY", contract="688c 2/17 @1.45", event_type="ENTRY", commentary="small position"),
        row(2, ticker="SPY", contract="691c 2/17 @.88", event_type="ENTRY", commentary="small position"),
        row(3, ticker="SPY", contract="688c 2/17", event_type="FINAL SELL — WIN", pnl_pct="100%"),
    ])

    assert len(positions) == 2
    statuses = {position.key: position.status for position in positions}
    assert any(key.endswith("2026-02-17|688|call") and status == "CLOSED" for key, status in statuses.items())
    assert any(key.endswith("2026-02-17|691|call") and status == "OPEN" for key, status in statuses.items())


def test_replay_matches_entry_and_close_across_contract_date_formats():
    positions = replay_rows([
        row(1, ticker="PYPL", contract="70c 3/20 @0.62", event_type="ENTRY", commentary="SL sub-54"),
        row(2, ticker="PYPL", contract="20 MAR 26 70C (+30)", event_type="CLOSE — LOSS", pnl_pct="-44.35%"),
    ])

    assert len(positions) == 1
    assert positions[0].status == "CLOSED"
    assert positions[0].opened_row == "1"
    assert positions[0].closed_row == "2"
