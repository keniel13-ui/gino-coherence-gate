from scripts.summarize_playbit_settled_scorecard import combine_rows


def test_combine_rows_scores_settled_worthless_position():
    rows = combine_rows(
        [
            {
                "key": "a",
                "score_status": "NEEDS_PRICE_SETTLEMENT",
                "realized_return_pct": "",
                "return_quality": "not_realized",
                "reason": "needs settlement",
            }
        ],
        [
            {
                "key": "a",
                "settlement_status": "SETTLED_WORTHLESS",
                "underlying_close": "99.00",
                "settled_return_pct": "-100.00",
                "return_quality": "held_to_expiry_underlying_close",
                "reason": "expired out-of-the-money",
            }
        ],
    )

    assert rows[0]["score_status"] == "SCORED_HELD_TO_EXPIRY"
    assert rows[0]["realized_return_pct"] == "-100.00"
    assert rows[0]["settlement_status"] == "SETTLED_WORTHLESS"


def test_combine_rows_does_not_invent_itm_return():
    rows = combine_rows(
        [
            {
                "key": "a",
                "score_status": "NEEDS_PRICE_SETTLEMENT",
                "realized_return_pct": "",
                "return_quality": "not_realized",
                "reason": "needs settlement",
            }
        ],
        [
            {
                "key": "a",
                "settlement_status": "NEEDS_OPTION_PRICE_SETTLEMENT",
                "underlying_close": "101.00",
                "settled_return_pct": "",
                "return_quality": "needs_option_price",
                "reason": "expired in-the-money",
            }
        ],
    )

    assert rows[0]["score_status"] == "NEEDS_OPTION_PRICE_SETTLEMENT"
    assert rows[0]["realized_return_pct"] == ""
    assert rows[0]["return_quality"] == "needs_option_price"
