from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from typing import Any

from .scorer import parse_ts
from .scoring_policy import ScoringPolicy


def aggregate_records(
    records: list[dict[str, Any]],
    policy: ScoringPolicy,
    *,
    as_of: datetime | None = None,
    started_at: datetime | None = None,
    baseline_expectancy_usd: float | None = None,
) -> dict[str, Any]:
    captured_n = len(records)
    excluded = [record for record in records if record.get("excluded")]
    settled = [record for record in records if record.get("settled") and not record.get("excluded")]
    wins = [record for record in settled if record["outcome"]["net_pnl_usd"] > 0]
    losses = [record for record in settled if record["outcome"]["net_pnl_usd"] <= 0]
    pnl_values = [float(record["outcome"]["net_pnl_usd"]) for record in settled]
    net_returns = [float(record["outcome"]["net_return_pct"]) for record in settled]
    late_calls = [record for record in settled if record.get("detectors", {}).get("late_call")]

    equity_curve = _equity_curve(pnl_values)
    max_drawdown = _max_drawdown(equity_curve)
    max_loss_streak = _max_consecutive_losses(pnl_values)
    avg_loss_usd = abs(sum(v for v in pnl_values if v <= 0) / len(losses)) if losses else 0.0
    account_equity = policy.account_equity_usd
    survival = {
        "max_consecutive_losses": max_loss_streak,
        "avg_loss_usd": round(avg_loss_usd, 6),
        "losses_to_20pct_drawdown_est": None if avg_loss_usd == 0 else int((account_equity * 0.20) // avg_loss_usd),
        "survives_10_avg_losses": True if avg_loss_usd == 0 else (avg_loss_usd * 10) <= (account_equity * 0.20),
    }

    expectancy = sum(pnl_values) / len(settled) if settled else 0.0
    haircut_pct = float(policy.raw.get("live_haircut", {}).get("stress_pct", 0) or 0)
    haircut_expectancy = expectancy * (1 - haircut_pct / 100.0)
    ready = _decision_ready(records, policy, as_of=as_of, started_at=started_at)

    report = {
        "captured_n": captured_n,
        "settled_n": len(settled),
        "excluded_n": len(excluded),
        "exclusion_reasons": dict(Counter(str(record.get("exclusion_reason")) for record in excluded)),
        "late_call_n": len(late_calls),
        "hit_rate": round(len(wins) / len(settled), 6) if settled else 0.0,
        "avg_win_pct": round(sum(float(r["outcome"]["net_return_pct"]) for r in wins) / len(wins), 6) if wins else 0.0,
        "avg_loss_pct": round(sum(float(r["outcome"]["net_return_pct"]) for r in losses) / len(losses), 6) if losses else 0.0,
        "net_expectancy_per_signal_usd": round(expectancy, 6),
        "live_haircut_expectancy_usd": round(haircut_expectancy, 6),
        "worst_single_usd": round(min(pnl_values), 6) if pnl_values else 0.0,
        "max_drawdown_usd": round(max_drawdown, 6),
        "equity_curve_usd": [round(value, 6) for value in equity_curve],
        "consecutive_loss_survival": survival,
        "baseline_expectancy_usd": None if baseline_expectancy_usd is None else round(baseline_expectancy_usd, 6),
        "beats_baseline": None if baseline_expectancy_usd is None else expectancy > baseline_expectancy_usd,
        "decision_ready": ready["ready"],
        "decision_reason": ready["reason"],
    }
    report["action_verdict"] = action_verdict(report, policy)
    return report


def action_verdict(report: dict[str, Any], policy: ScoringPolicy) -> str:
    if not report["decision_ready"]:
        return "continue_collecting"
    if report["captured_n"] == 0 or report["settled_n"] == 0:
        return "unmeasurable"
    if report["excluded_n"] / max(report["captured_n"], 1) > 0.5:
        return "unmeasurable"

    min_after_haircut = float(policy.raw.get("live_haircut", {}).get("min_expectancy_usd_after_haircut", 0) or 0)
    if report["live_haircut_expectancy_usd"] <= min_after_haircut:
        return "kill_source"
    if policy.raw.get("require_baseline_for_advance", True):
        if report.get("beats_baseline") is None:
            return "unmeasurable"
        if report.get("beats_baseline") is False:
            return "kill_source"

    if report["worst_single_usd"] < -(policy.account_equity_usd * 0.10) or not report["consecutive_loss_survival"]["survives_10_avg_losses"]:
        return "rerun_one_correction"

    return "advance"


def _decision_ready(
    records: list[dict[str, Any]],
    policy: ScoringPolicy,
    *,
    as_of: datetime | None,
    started_at: datetime | None,
) -> dict[str, Any]:
    settled_n = len([record for record in records if record.get("settled") and not record.get("excluded")])
    if settled_n >= policy.min_settled_n:
        return {"ready": True, "reason": "min_settled_n"}
    if started_at and as_of and as_of >= started_at + timedelta(days=policy.decision_timebox_days):
        return {"ready": True, "reason": "decision_timebox_days"}
    return {"ready": False, "reason": "waiting_for_n_or_timebox"}


def _equity_curve(values: list[float]) -> list[float]:
    total = 0.0
    curve = []
    for value in values:
        total += value
        curve.append(total)
    return curve


def _max_drawdown(curve: list[float]) -> float:
    peak = 0.0
    max_dd = 0.0
    for value in curve:
        peak = max(peak, value)
        max_dd = max(max_dd, peak - value)
    return max_dd


def _max_consecutive_losses(values: list[float]) -> int:
    current = 0
    best = 0
    for value in values:
        if value <= 0:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best


def group_key(record: dict[str, Any]) -> tuple[str, str, str]:
    return (str(record.get("source")), str(record.get("rule_variant")), str(record.get("sizing_variant")))


def aggregate_by_source_variant(records: list[dict[str, Any]], policy: ScoringPolicy) -> dict[str, dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for record in records:
        grouped.setdefault(group_key(record), []).append(record)
    return {
        "|".join(key): aggregate_records(group, policy, started_at=parse_ts(group[0]["posted_at"]) if group else None)
        for key, group in grouped.items()
    }
