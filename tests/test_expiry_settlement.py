from gino_gate.expiry_settlement import (
    UnderlyingClose,
    settle_expired_no_close_positions,
    settle_expired_option,
)
from gino_gate.paper_forward import PaperPosition


def position(**overrides):
    base = {
        "key": "trader|NVDA|Put|2026-05-15|150|put",
        "trader": "trader",
        "ticker": "NVDA",
        "direction": "Put",
        "status": "EXPIRED_NO_CLOSE",
        "opened_row": "1",
        "closed_row": None,
        "expiry_date": "2026-05-15",
        "intent_verdict": "PAPER_READY",
        "intent_reason": "parseable entry with stop/risk",
        "last_event_type": "Update",
        "last_pnl_pct": "56.01%",
        "last_pnl_dollars": "$2,168",
        "event_count": 2,
        "events": [],
    }
    base.update(overrides)
    return PaperPosition(**base)


def close(symbol="NVDA", close_value=225.32):
    return UnderlyingClose(
        symbol=symbol,
        close_date="2026-05-15",
        close=close_value,
        source="fixture",
        fetched_at="2026-06-26T00:00:00Z",
    )


def test_otm_expired_no_close_settles_worthless():
    row = settle_expired_option(position(), close=close(close_value=225.32))

    assert row.moneyness == "OTM"
    assert row.settlement_status == "SETTLED_WORTHLESS"
    assert row.settled_return_pct == "-100.00"
    assert "out-of-the-money" in row.reason


def test_itm_expired_no_close_requires_option_price_settlement():
    row = settle_expired_option(position(), close=close(close_value=100.00))

    assert row.moneyness == "ITM"
    assert row.settlement_status == "NEEDS_OPTION_PRICE_SETTLEMENT"
    assert row.settled_return_pct == ""
    assert "do not infer" in row.reason


def test_settlement_only_reviews_paper_ready_expired_no_close():
    reviewed = settle_expired_no_close_positions(
        [
            position(ticker="NVDA"),
            position(ticker="TSLA", intent_verdict="PAPER_ONLY"),
            position(ticker="QQQ", status="OPEN"),
        ],
        fetch_close=lambda symbol, expiry: close(symbol=symbol, close_value=999.00),
    )

    assert len(reviewed) == 1
    assert reviewed[0].ticker == "NVDA"
