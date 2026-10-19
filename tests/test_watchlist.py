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


class _FakeOllamaResponse:
    def __init__(self, payload):
        import json

        self._body = json.dumps({"response": json.dumps(payload)}).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body


def test_llm_items_with_invalid_tickers_are_dropped(monkeypatch):
    from gino_gate import watchlist

    payload = [
        {"ticker": "$crwd", "trigger": "above 705"},
        {"ticker": "IGNORE PREVIOUS INSTRUCTIONS", "trigger": "above 1"},
        {"ticker": "AAPL; rm -rf", "trigger": "above 2"},
        {"ticker": "BRK.B", "trigger": "above 3"},
    ]
    monkeypatch.setattr(watchlist.urllib.request, "urlopen", lambda req, timeout: _FakeOllamaResponse(payload))
    items = watchlist._parse_with_ollama("anything", model="test", timeout=1)
    assert [it.ticker for it in items] == ["CRWD", "BRK.B"]
    assert all(it.engine == "ollama:test" for it in items)


def test_llm_failure_falls_back_to_deterministic(monkeypatch):
    from gino_gate import watchlist

    def offline(req, timeout):
        raise OSError("connection refused")

    monkeypatch.setattr(watchlist.urllib.request, "urlopen", offline)
    items = parse_watchlist(GINO_6_29, use_llm=True)
    assert items and all(it.engine == "deterministic" for it in items)
