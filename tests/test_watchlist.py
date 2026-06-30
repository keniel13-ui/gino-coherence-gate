from __future__ import annotations

from gino_gate.watchlist import WatchlistItem, parse_watchlist, summarize_watchlist
from gino_gate.watchlist_ledger import WatchlistLedger

GINO_6_29 = """Watch List 6/29
$CRWD (CrowdStrike) – Looking very strong. Watching for a break above 705. If momentum continues, a move toward 740 this week is possible.
$MU (Micron) – Still bullish. Can pop hard at any moment.
$APP (AppLovin) – Looking much better. Needs to clear 509. If it does, 540 is possible.
$TSLA (Tesla) – Needs 444 to confirm more upside.
$NET (Cloudflare) – Continues to look great. 250 has written all over it.
Notes: Use next week's contracts whenever possible. Short trading week.
"""


def test_deterministic_parse_finds_tickers_and_triggers():
    items = parse_watchlist(GINO_6_29, use_llm=False)
    tickers = {it.ticker for it in items}
    assert {"CRWD", "MU", "APP", "TSLA", "NET"}.issubset(tickers)
    crwd = next(it for it in items if it.ticker == "CRWD")
    assert crwd.trigger and "705" in crwd.trigger
    assert crwd.target == "740"
    assert crwd.timeframe == "this week"


def test_missing_fields_flag_watchlist_as_hypothesis():
    items = parse_watchlist(GINO_6_29, use_llm=False)
    for it in items:
        # a watch list always lacks stop and sizing, and never an exact contract
        assert "stop" in it.missing_fields
        assert "sizing" in it.missing_fields
        assert "exact_contract" in it.missing_fields
    # MU has no trigger level -> entry_confirmation missing too
    mu = next(it for it in items if it.ticker == "MU")
    assert "entry_confirmation" in mu.missing_fields


def test_summary_is_honest_never_calls_it_good():
    items = parse_watchlist(GINO_6_29, use_llm=False)
    summary = summarize_watchlist(items)
    assert "hypotheses, not trade-ready signals" in summary
    assert "not a verdict" in summary
    assert "paper mode" in summary
    # never claims a setup is good / a buy / an edge
    lowered = summary.lower()
    assert "edge" not in lowered or "no claim of edge" in lowered


def test_empty_input_is_handled():
    assert parse_watchlist("", use_llm=False) == []
    assert "No watch list items" in summarize_watchlist([])


def test_ledger_records_with_price_pending(tmp_path):
    ledger = WatchlistLedger(tmp_path / "wl.jsonl")
    items = parse_watchlist(GINO_6_29, use_llm=False)
    recs = ledger.record_watchlist(items)
    assert ledger.count() == len(items)
    rows = ledger.tail()
    assert rows[0]["price_source"] == "pending"
    assert rows[0]["price_at_receipt"] is None
    assert rows[0]["outcome"] is None
    assert "ts" in rows[0]


def test_ledger_uses_price_lookup_when_given(tmp_path):
    ledger = WatchlistLedger(tmp_path / "wl.jsonl")
    items = [WatchlistItem(ticker="CRWD", trigger="above 705")]
    ledger.record_watchlist(items, price_lookup=lambda t: (701.5, "test_quote"))
    row = ledger.tail()[0]
    assert row["price_at_receipt"] == 701.5
    assert row["price_source"] == "test_quote"
