from __future__ import annotations

from dataclasses import dataclass

from .live_eligibility import parse_target_rule
from .stop_enforcement import parse_stop_rule
from .trade_intent import propose_trade_intent


@dataclass(frozen=True)
class OperatorVerdict:
    verdict: str
    trader: str
    ticker: str
    action: str
    summary: str
    reasons: list[str]


def explain_call(row: dict[str, str]) -> OperatorVerdict:
    intent = propose_trade_intent(row, mode="paper")
    trader = (row.get("Trader") or "").strip()
    ticker = (row.get("Ticker") or "").strip().upper()
    reasons: list[str] = []

    if intent.verdict == "BLOCK":
        return OperatorVerdict(
            verdict="REFUSE",
            trader=trader,
            ticker=ticker,
            action="do_not_trade",
            summary=f"Refusing {ticker}: {intent.reason}.",
            reasons=[intent.reason],
        )

    if intent.verdict == "NEEDS_REVIEW":
        return OperatorVerdict(
            verdict="PAPER_ONLY",
            trader=trader,
            ticker=ticker,
            action="manual_review_before_any_trade",
            summary=f"{ticker} needs manual review before it can be trusted.",
            reasons=[intent.reason],
        )

    stop = parse_stop_rule_from_row(row)
    target = parse_target_rule_from_row(row)

    if stop.status != "ENFORCEABLE":
        reasons.append(f"stop not live-enforceable: {stop.reason}")
    if target.status != "ENFORCEABLE":
        reasons.append(f"target not live-enforceable: {target.reason}")
    if intent.verdict != "PAPER_READY":
        reasons.append(intent.reason)

    if reasons:
        return OperatorVerdict(
            verdict="PAPER_ONLY",
            trader=trader,
            ticker=ticker,
            action="track_in_paper",
            summary=f"{ticker} can be tracked, but it should not become a live Robinhood order yet.",
            reasons=reasons,
        )

    return OperatorVerdict(
        verdict="REVIEW_ELIGIBLE",
        trader=trader,
        ticker=ticker,
        action="prepare_review_order_only",
        summary=f"{ticker} has a parseable entry, machine-checkable stop, and machine-checkable target.",
        reasons=[
            "entry is parseable",
            f"stop: {stop.raw}",
            f"target: {target.raw}",
            "live order still requires Gino approval and policy/risk caps",
        ],
    )


def _paper_position_from_row(row: dict[str, str]):
    from .paper_forward import replay_rows

    positions = replay_rows([row])
    return positions[0] if positions else None


def parse_stop_rule_from_row(row: dict[str, str]):
    position = _paper_position_from_row(row)
    if position is None:
        class Missing:
            status = "NO_STOP_FOUND"
            raw = ""
            reason = "row did not create a paper position"
        return Missing()
    return parse_stop_rule(position)


def parse_target_rule_from_row(row: dict[str, str]):
    position = _paper_position_from_row(row)
    if position is None:
        class Missing:
            status = "NO_TARGET_FOUND"
            raw = ""
            reason = "row did not create a paper position"
        return Missing()
    return parse_target_rule(position)
