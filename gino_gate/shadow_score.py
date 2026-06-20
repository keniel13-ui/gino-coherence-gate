"""Shadow-score owned signals on saved read-only historical data."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .baselines import random_timed_entry_expectancy, spy_buy_hold_same_window
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


def shadow_score_universe(
    series_by_symbol: dict[str, PriceSeries],
    policy: ScoringPolicy,
    *,
    spy_series: PriceSeries | None = None,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    """Shadow-score a saved symbol universe with baseline discipline."""
    signals: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    random_samples: list[float] = []

    for symbol in sorted(series_by_symbol):
        series = series_by_symbol[symbol]
        symbol_signals = generate_ts_momentum_signals(series) + generate_rsi2_signals(series)
        symbol_bars = [_bar_as_dict(bar) for bar in series.bars]
        signals.extend(symbol_signals)

        for signal in symbol_signals:
            baseline_value = _random_baseline([signal], symbol_bars, policy)
            if baseline_value is not None:
                random_samples.append(baseline_value)
            for rule in policy.rule_variants:
                rule_name = str(rule["name"])
                for sizing in policy.sizing_variants:
                    sizing_name = str(sizing["name"])
                    records.append(
                        simulate_signal(
                            signal,
                            symbol_bars,
                            policy,
                            rule_name=rule_name,
                            sizing_name=sizing_name,
                        )
                    )

    random_baseline = sum(random_samples) / len(random_samples) if random_samples else None
    spy_baseline = _spy_baseline(records, spy_series)
    started_at = _earliest_bar_ts(series_by_symbol)
    report = aggregate_records(
        records,
        policy,
        as_of=as_of or datetime.now(timezone.utc),
        started_at=started_at,
        baseline_expectancy_usd=spy_baseline,
    )
    grouped = aggregate_by_source_variant(records, policy) if records else {}
    measurement_gate = _measurement_gate(signals, policy)
    status = _universe_status(measurement_gate, spy_baseline)
    action_verdict = _universe_action_verdict(measurement_gate, spy_baseline, report)

    return {
        "status": status,
        "symbols": sorted(series_by_symbol),
        "symbol_count": len(series_by_symbol),
        "bar_count_by_symbol": {symbol: len(series_by_symbol[symbol].bars) for symbol in sorted(series_by_symbol)},
        "signal_count": len(signals),
        "record_count": len(records),
        "policy_hash": policy.policy_hash,
        "measurement_gate": measurement_gate,
        "baseline": {
            "random_timed_entry_expectancy_usd": random_baseline,
            "spy_buy_hold_same_window_expectancy_usd": spy_baseline,
            "spy_baseline_status": "present" if spy_baseline is not None else "missing_spy_series",
        },
        "signals": signals,
        "report": report,
        "by_source_variant": grouped,
        "action_verdict": action_verdict,
        "decision_ready": measurement_gate["ready"] and spy_baseline is not None,
    }


def shadow_score_historicals_payload(symbol: str, payload: Any, policy: ScoringPolicy) -> dict[str, Any]:
    return shadow_score_series(normalize_historicals_response(symbol, payload), policy)


def shadow_score_historicals_universe_payloads(
    payloads_by_symbol: dict[str, Any],
    policy: ScoringPolicy,
    *,
    spy_payload: Any | None = None,
) -> dict[str, Any]:
    series_by_symbol = {
        symbol.upper(): normalize_historicals_response(symbol, payload)
        for symbol, payload in payloads_by_symbol.items()
    }
    spy_series = normalize_historicals_response("SPY", spy_payload) if spy_payload is not None else None
    return shadow_score_universe(series_by_symbol, policy, spy_series=spy_series)


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


def _spy_baseline(records: list[dict[str, Any]], spy_series: PriceSeries | None) -> float | None:
    if spy_series is None:
        return None
    spy_bars = [_bar_as_dict(bar) for bar in spy_series.bars]
    samples = [
        value
        for record in records
        if record.get("settled") and not record.get("excluded")
        for value in [spy_buy_hold_same_window(record, spy_bars)]
        if value is not None
    ]
    if not samples:
        return None
    return sum(samples) / len(samples)


def _earliest_bar_ts(series_by_symbol: dict[str, PriceSeries]) -> datetime | None:
    starts = [series.bars[0].ts for series in series_by_symbol.values() if series.bars]
    return min(starts) if starts else None


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


def _universe_status(measurement_gate: dict[str, Any], spy_baseline: float | None) -> str:
    if not measurement_gate["ready"]:
        return "measurement_preview_insufficient_sample"
    if spy_baseline is None:
        return "measurement_preview_missing_spy_baseline"
    return "measurement_preview_ready_for_verdict"


def _universe_action_verdict(measurement_gate: dict[str, Any], spy_baseline: float | None, report: dict[str, Any]) -> str:
    if not measurement_gate["ready"]:
        return "continue_collecting"
    if spy_baseline is None:
        return "unmeasurable"
    return str(report["action_verdict"])
