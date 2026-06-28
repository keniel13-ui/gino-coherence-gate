from gino_gate.live_eligibility import (
    evaluate_live_eligible_positions,
    evaluate_position_eligibility,
    parse_target_rule,
)
from gino_gate.paper_forward import PaperPosition
from gino_gate.stop_enforcement import DailyBar


def position(**overrides):
    base = {
        "key": "trader|COIN|Call|2026-03-20|200|call",
        "trader": "trader",
        "ticker": "COIN",
        "direction": "Call",
        "status": "CLOSED",
        "opened_row": "1",
        "closed_row": "2",
        "expiry_date": "2026-03-20",
        "intent_verdict": "PAPER_READY",
        "intent_reason": "ok",
        "last_event_type": "FINAL SELL — WIN",
        "last_pnl_pct": "247.96%",
        "last_pnl_dollars": "$6,075",
        "event_count": 2,
        "events": [
            {
                "source_row": "1",
                "date": "2/9/26",
                "time": "9:30 AM",
                "event_type": "ENTRY",
                "pnl_pct": "",
                "pnl_dollars": "",
                "commentary": "TP 208; SL 143; ER in 3 days",
            },
            {
                "source_row": "2",
                "date": "3/4/26",
                "time": "9:30 AM",
                "event_type": "FINAL SELL — WIN",
                "pnl_pct": "247.96%",
                "pnl_dollars": "$6,075",
                "commentary": "selling all",
            },
        ],
    }
    base.update(overrides)
    return PaperPosition(**base)


def test_parse_target_rule_uses_first_call_target():
    rule = parse_target_rule(position())

    assert rule.status == "ENFORCEABLE"
    assert rule.trigger == "above"
    assert rule.price == "208"


def test_parse_target_rule_uses_first_put_target_as_below_level():
    rule = parse_target_rule(position(direction="Put", events=[
        {
            "source_row": "1",
            "date": "3/25/26",
            "time": "9:30 AM",
            "event_type": "ENTRY",
            "pnl_pct": "",
            "pnl_dollars": "",
            "commentary": "TP 365 then .618 (320); SL above 404",
        }
    ]))

    assert rule.status == "ENFORCEABLE"
    assert rule.trigger == "below"
    assert rule.price == "365"


def test_parse_target_rule_keeps_numeric_target_before_semantic_second_target():
    rule = parse_target_rule(position(direction="Put", events=[
        {
            "source_row": "1",
            "date": "1/9/26",
            "time": "9:30 AM",
            "event_type": "ENTRY",
            "pnl_pct": "",
            "pnl_dollars": "",
            "commentary": "SL 490-493; TP 465 then FVG 420",
        }
    ]))

    assert rule.status == "ENFORCEABLE"
    assert rule.trigger == "below"
    assert rule.price == "465"


def test_live_eligibility_marks_target_first():
    result = evaluate_position_eligibility(
        position(),
        bars=[
            DailyBar("2026-02-10", high=205, low=180, close=200),
            DailyBar("2026-02-11", high=209, low=190, close=208),
        ],
    )

    assert result.live_eligible == "yes"
    assert result.discipline_outcome == "TARGET_FIRST"


def test_live_eligibility_marks_stop_first():
    result = evaluate_position_eligibility(
        position(),
        bars=[DailyBar("2026-02-10", high=205, low=140, close=150)],
    )

    assert result.live_eligible == "yes"
    assert result.discipline_outcome == "STOP_FIRST"


def test_missing_target_excludes_from_live_eligible_set():
    result = evaluate_position_eligibility(
        position(events=[
            {
                "source_row": "1",
                "date": "5/27/26",
                "time": "9:30 AM",
                "event_type": "ENTRY",
                "pnl_pct": "",
                "pnl_dollars": "",
                "commentary": "lotto position; SL 200",
            }
        ]),
        bars=[],
    )

    assert result.live_eligible == "no"
    assert result.target_status == "NO_TARGET_FOUND"


def test_evaluate_live_eligible_positions_fetches_only_needed_bars():
    rows = evaluate_live_eligible_positions(
        [position(), position(intent_verdict="PAPER_ONLY")],
        fetch_bars=lambda symbol, start, end: ([DailyBar(start.isoformat(), high=209, low=180, close=208)], "fixture", "now"),
    )

    assert len(rows) == 2
    assert rows[0].live_eligible == "yes"
    assert rows[1].live_eligible == "no"
