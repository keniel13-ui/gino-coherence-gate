from gino_gate.trade_intent import parse_option_leg, propose_trade_intent


def row(**overrides):
    base = {
        "#": "1",
        "Trader": "glacierboy300",
        "Date": "3/24/26",
        "Time": "1:31 PM",
        "Ticker": "NVDA",
        "Direction": "Put",
        "Contract / Fill": "150p 5/15 @2.62",
        "Event Type": "ENTRY",
        "Mark": "",
        "P/L %": "",
        "P/L $": "",
        "Trader Commentary": "loss of daily 200 to Fib; risk off above 189",
    }
    base.update(overrides)
    return base


def test_parse_option_leg_supports_strike_first_contract():
    leg = parse_option_leg("150p 5/15 @2.62")
    assert leg is not None
    assert leg.expiry == "5/15"
    assert leg.strike == 150
    assert leg.option_type == "put"
    assert leg.entry_price == 2.62


def test_parse_option_leg_supports_expiry_first_contract():
    leg = parse_option_leg("6/18 $420c @5.98")
    assert leg is not None
    assert leg.expiry == "6/18"
    assert leg.strike == 420
    assert leg.option_type == "call"
    assert leg.entry_price == 5.98


def test_parse_option_leg_supports_written_month_with_position_size_suffix():
    leg = parse_option_leg("20 MAR 26 70C (+30)")
    assert leg is not None
    assert leg.expiry == "20 MAR 26"
    assert leg.strike == 70
    assert leg.option_type == "call"


def test_parse_option_leg_supports_leading_decimal_price():
    leg = parse_option_leg("2/17 $691c @.88")
    assert leg is not None
    assert leg.entry_price == 0.88


def test_entry_with_parseable_contract_and_risk_is_paper_ready():
    intent = propose_trade_intent(row(), mode="paper")
    assert intent.verdict == "PAPER_READY"
    assert intent.action == "paper_option_order"
    assert intent.robinhood_tool == "review_option_order"
    assert intent.order_args["symbol"] == "NVDA"
    assert intent.order_args["option_type"] == "put"
    assert intent.order_args["stop"] == "189"


def test_parseable_entry_without_stop_or_risk_is_paper_only():
    intent = propose_trade_intent(row(**{"Trader Commentary": "new trade"}), mode="paper")
    assert intent.verdict == "PAPER_ONLY"
    assert "stop/risk" in intent.reason


def test_multi_leg_contract_needs_manual_review():
    intent = propose_trade_intent(row(**{"Contract / Fill": "175c 2/20 @1.84 + 190c 3/20 @0.88"}), mode="paper")
    assert intent.verdict == "NEEDS_REVIEW"
    assert intent.action == "manual_parse_required"


def test_sell_to_open_credit_strategy_needs_manual_review():
    intent = propose_trade_intent(
        row(
            **{
                "Direction": "Put (STO)",
                "Contract / Fill": "$12.5p 5/15 @3.60 credit",
                "Event Type": "ENTRY (sell-to-open)",
            }
        ),
        mode="paper",
    )
    assert intent.verdict == "NEEDS_REVIEW"
    assert "sell-to-open" in intent.reason


def test_call_spread_sold_bought_strategy_needs_manual_review():
    intent = propose_trade_intent(
        row(
            **{
                "Direction": "Call spread",
                "Contract / Fill": "Sold 1/30 370c / Bought 380c",
                "Event Type": "ENTRY (bearish)",
            }
        ),
        mode="paper",
    )
    assert intent.verdict == "NEEDS_REVIEW"


def test_non_entry_event_blocks_from_action():
    intent = propose_trade_intent(row(**{"Event Type": "Update"}), mode="paper")
    assert intent.verdict == "BLOCK"
    assert intent.action == "log_only"


def test_live_mode_requires_human_approval_not_place_order():
    intent = propose_trade_intent(row(), mode="live")
    assert intent.verdict == "REQUIRE_HUMAN_APPROVAL"
    assert intent.action == "review_option_order"
    assert intent.robinhood_tool == "review_option_order"
    assert "live Robinhood execution disabled" in intent.reason
