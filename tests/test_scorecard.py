from gino_gate.paper_forward import PaperPosition
from gino_gate.scorecard import parse_reported_pct, score_positions, trim_aware_realized_pct


def position(**overrides):
    base = {
        "key": "trader|COIN|call",
        "trader": "trader",
        "ticker": "COIN",
        "direction": "Call",
        "status": "CLOSED",
        "opened_row": "1",
        "closed_row": "3",
        "expiry_date": "2026-03-20",
        "intent_verdict": "PAPER_READY",
        "intent_reason": "ok",
        "last_event_type": "FINAL SELL — WIN",
        "last_pnl_pct": "300%",
        "last_pnl_dollars": "",
        "event_count": 3,
        "events": [
            {"event_type": "ENTRY", "pnl_pct": "", "pnl_dollars": "", "commentary": ""},
            {"event_type": "Trim", "pnl_pct": "100%", "pnl_dollars": "", "commentary": "selling half"},
            {"event_type": "FINAL SELL — WIN", "pnl_pct": "300%", "pnl_dollars": "", "commentary": "selling all"},
        ],
    }
    base.update(overrides)
    return PaperPosition(**base)


def test_parse_reported_pct_rejects_dirty_decimal_fragments():
    assert parse_reported_pct("0.88") is None
    assert parse_reported_pct("2.5") is None
    assert parse_reported_pct("88%") == 88
    assert parse_reported_pct("250") == 250


def test_trim_aware_realized_pct_blends_half_then_final():
    realized, quality, reason = trim_aware_realized_pct(position())
    assert realized == 200
    assert quality == "estimated"
    assert "trim-aware" in reason


def test_unknown_trim_fraction_does_not_invent_full_realized_return():
    realized, quality, reason = trim_aware_realized_pct(position(events=[
        {"event_type": "ENTRY", "pnl_pct": "", "pnl_dollars": "", "commentary": ""},
        {"event_type": "Trim", "pnl_pct": "100%", "pnl_dollars": "", "commentary": "trimming"},
        {"event_type": "FINAL SELL — WIN", "pnl_pct": "300%", "pnl_dollars": "", "commentary": "selling all"},
    ]))

    assert realized == 300
    assert quality == "partial_estimate"
    assert "missing" in reason or "ambiguous" in reason


def test_scorecard_excludes_not_agent_takeable_closed_win():
    rows = score_positions([position(intent_verdict="NEEDS_REVIEW")])
    assert rows[0].agent_takeable == "no"
    assert rows[0].score_status == "EXCLUDED_NOT_AGENT_TAKEABLE"
    assert rows[0].realized_return_pct == ""
    assert rows[0].return_quality == "excluded"


def test_scorecard_requires_external_settlement_for_expired_no_close():
    rows = score_positions([position(status="EXPIRED_NO_CLOSE", closed_row=None)])
    assert rows[0].score_status == "NEEDS_PRICE_SETTLEMENT"
    assert rows[0].realized_return_pct == ""
