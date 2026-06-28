from gino_gate.operator_verdict import explain_call


def row(**overrides):
    base = {
        "#": "1",
        "Trader": "glacierboy300",
        "Date": "2/9/26",
        "Time": "9:30 AM",
        "Ticker": "COIN",
        "Direction": "Call",
        "Contract / Fill": "200c 3/20 @4.90 (1R)",
        "Event Type": "ENTRY",
        "Mark": "",
        "P/L %": "",
        "P/L $": "",
        "Trader Commentary": "TP 208; SL 143; ER in 3 days",
    }
    base.update(overrides)
    return base


def test_operator_verdict_review_eligible_for_clean_call():
    verdict = explain_call(row())

    assert verdict.verdict == "REVIEW_ELIGIBLE"
    assert verdict.action == "prepare_review_order_only"
    assert any("stop:" in reason for reason in verdict.reasons)
    assert any("target:" in reason for reason in verdict.reasons)


def test_operator_verdict_paper_only_when_stop_and_target_missing():
    verdict = explain_call(row(
        Ticker="ORCL",
        **{
            "Contract / Fill": "180c 3/20 @3.10",
            "Trader Commentary": "small position",
        },
    ))

    assert verdict.verdict == "PAPER_ONLY"
    assert verdict.action == "track_in_paper"
    assert any("stop not live-enforceable" in reason for reason in verdict.reasons)
    assert any("target not live-enforceable" in reason for reason in verdict.reasons)


def test_operator_verdict_paper_only_for_complex_credit_or_spread():
    verdict = explain_call(row(
        Ticker="MU",
        Direction="Call spread",
        **{
            "Contract / Fill": "sold 1/30 370c / bought 380c",
            "Event Type": "ENTRY (bearish)",
            "Trader Commentary": "risk $685 to make $315",
        },
    ))

    assert verdict.verdict == "PAPER_ONLY"
    assert verdict.action == "manual_review_before_any_trade"
