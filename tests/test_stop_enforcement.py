from datetime import date

from gino_gate.paper_forward import PaperPosition
from gino_gate.stop_enforcement import (
    DailyBar,
    enforce_expired_no_close_stops,
    enforce_stop,
    parse_stop_rule,
)


def position(**overrides):
    base = {
        "key": "trader|TSLA|Put|2026-04-17|350|put",
        "trader": "trader",
        "ticker": "TSLA",
        "direction": "Put",
        "status": "EXPIRED_NO_CLOSE",
        "opened_row": "1",
        "closed_row": None,
        "expiry_date": "2026-04-17",
        "intent_verdict": "PAPER_READY",
        "intent_reason": "ok",
        "last_event_type": "Update",
        "last_pnl_pct": "33.52%",
        "last_pnl_dollars": "$885",
        "event_count": 2,
        "events": [
            {
                "source_row": "1",
                "date": "3/25/26",
                "time": "9:30 AM",
                "event_type": "ENTRY",
                "pnl_pct": "",
                "pnl_dollars": "",
                "commentary": "daily 200 retest; SL above 404",
            }
        ],
    }
    base.update(overrides)
    return PaperPosition(**base)


def test_parse_stop_rule_infers_put_stop_above():
    rule = parse_stop_rule(position())

    assert rule.status == "ENFORCEABLE"
    assert rule.trigger == "above"
    assert rule.price == "404"


def test_parse_stop_rule_uses_level_not_date_fragment():
    rule = parse_stop_rule(position(events=[
        {
            "source_row": "1",
            "date": "3/24/26",
            "time": "9:30 AM",
            "event_type": "ENTRY",
            "pnl_pct": "",
            "pnl_dollars": "",
            "commentary": "loss of daily 200; risk off above 3/16 high 189",
        }
    ]))

    assert rule.status == "ENFORCEABLE"
    assert rule.trigger == "above"
    assert rule.price == "189"


def test_parse_stop_rule_flags_semantic_stop():
    rule = parse_stop_rule(position(direction="Call", events=[
        {
            "source_row": "1",
            "date": "1/22/26",
            "time": "9:30 AM",
            "event_type": "ENTRY",
            "pnl_pct": "",
            "pnl_dollars": "",
            "commentary": "SL under daily 200; TP 120",
        }
    ]))

    assert rule.status == "UNENFORCEABLE_STOP"
    assert "daily" in rule.reason


def test_enforce_stop_marks_triggered_when_daily_high_crosses_put_stop():
    result = enforce_stop(
        position(),
        bars=[
            DailyBar("2026-03-25", high=390, low=370, close=380),
            DailyBar("2026-03-26", high=405, low=380, close=400),
        ],
        source="fixture",
        fetched_at="now",
    )

    assert result.stop_status == "STOP_TRIGGERED"
    assert result.triggered_date == "2026-03-26"


def test_enforce_stop_marks_not_triggered():
    result = enforce_stop(
        position(),
        bars=[DailyBar("2026-03-25", high=390, low=370, close=380)],
    )

    assert result.stop_status == "STOP_NOT_TRIGGERED"


def test_enforce_expired_no_close_stops_filters_to_paper_ready_expired_positions():
    rows = enforce_expired_no_close_stops(
        [
            position(ticker="TSLA"),
            position(ticker="NVDA", status="OPEN"),
            position(ticker="QQQ", intent_verdict="PAPER_ONLY"),
        ],
        fetch_bars=lambda symbol, start, end: ([DailyBar(start.isoformat(), high=999, low=1, close=2)], "fixture", "now"),
    )

    assert len(rows) == 1
    assert rows[0].ticker == "TSLA"
    assert rows[0].stop_status == "STOP_TRIGGERED"
