"""Shadow-score owned signals on saved read-only historical data."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .baselines import random_timed_entry_expectancy
from .market_data_adapter import normalize_historicals_response
from .own_signals import generate_rsi2_signals, generate_ts_momentum_signals
from .price_data import PriceSeries
from .scorer import Bar, simulate_signal
from .scoring_metrics import aggregate_records, aggregate_by_source_variant
from .scoring_policy import ScoringPolicy


def shadow_score_series(
    series: PriceSeries,
    policy: ScoringPolicy,
    *,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    """Generate owned signals and simulate them under every frozen variant."""
    signals = generate_ts_momentum_signals(series) + generate_rsi2_signals(series)
    bar_dicts = [_bar_as_dict(bar) for bar in series.bars]
    records: list[dict[str, Any]] = []

    for signal in signals:
        for rule in policy.rule_variants:
            rule_name = str(rule["name"])
            for sizing in policy.sizing_variants:
                sizing_name = str(sizing["name"])
                records.append(
                    simulate_signal(
                        signal,
                        bar_dicts,
                        policy,
                        rule_name=rule_name,
                        sizing_name=sizing_name,
                    )
                )

    baseline = _random_baseline(signals, bar_dicts, policy)
    report = aggregate_records(
        records,
        policy,
        as_of=as_of or datetime.now(timezone.utc),
        started_at=series.bars[0].ts if series.bars else None,
        baseline_expectancy_usd=baseline,
    )
    grouped = aggregate_by_source_variant(records, policy) if records else {}
    measurement_gate = _measurement_gate(signals, policy)
    status = _preview_status(measurement_gate)
    return {
        "status": status,
        "symbol": series.symbol,
        "bar_count": len(series.bars),
        "signal_count": len(signals),
        "record_count": len(records),
        "policy_hash": policy.policy_hash,
        "measurement_gate": measurement_gate,
        "baseline": {
            "random_timed_entry_expectancy_usd": baseline,
            "spy_buy_hold_same_window": "missing_spy_series",
        },
        "signals": signals,
        "report": report,
        "by_source_variant": grouped,
    }


def shadow_score_historicals_payload(symbol: str, payload: Any, policy: ScoringPolicy) -> dict[str, Any]:
    return shadow_score_series(normalize_historicals_response(symbol, payload), policy)


def _bar_as_dict(bar: Bar) -> dict[str, Any]:
    return {
        "ts": bar.ts.isoformat().replace("+00:00", "Z"),
        "open": bar.open,
        "high": bar.high,
        "low": bar.low,
        "close": bar.close,
    }


def _random_baseline(signals: list[dict[str, Any]], bars: list[dict[str, Any]], policy: ScoringPolicy) -> float | None:
    if not signals or not policy.rule_variants or not policy.sizing_variants:
        return None
    samples: list[float] = []
    for signal in signals:
        value = random_timed_entry_expectancy(
            signal,
            bars,
            policy,
            rule_name=str(policy.rule_variants[0]["name"]),
            sizing_name=str(policy.sizing_variants[0]["name"]),
        )
        if value is not None:
            samples.append(value)
    if not samples:
        return None
    return sum(samples) / len(samples)


def _measurement_gate(signals: list[dict[str, Any]], policy: ScoringPolicy) -> dict[str, Any]:
    signal_count = len({str(signal["signal_id"]) for signal in signals})
    ready = signal_count >= policy.min_settled_n
    return {
        "ready": ready,
        "reason": "min_unique_signals" if ready else "waiting_for_min_unique_signals",
        "unique_signal_count": signal_count,
        "min_unique_signals": policy.min_settled_n,
        "note": "Variant records are not independent signals.",
    }


def _preview_status(measurement_gate: dict[str, Any]) -> str:
    if not measurement_gate["ready"]:
        return "measurement_preview_insufficient_sample"
    return "measurement_preview"
