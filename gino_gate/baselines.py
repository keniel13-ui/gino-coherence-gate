from __future__ import annotations

import random
from typing import Any

from .scorer import simulate_signal
from .scoring_policy import ScoringPolicy


def spy_buy_hold_same_window(signal_record: dict[str, Any], spy_bars: list[dict[str, Any]]) -> float | None:
    entry = signal_record.get("entry")
    exit_ = signal_record.get("exit")
    if not entry or not exit_ or not spy_bars:
        return None
    entry_ts = entry["ts"]
    exit_ts = exit_["ts"]
    entry_bar = next((bar for bar in spy_bars if bar["ts"] >= entry_ts), None)
    exit_bar = next((bar for bar in reversed(spy_bars) if bar["ts"] <= exit_ts), None)
    if not entry_bar or not exit_bar:
        return None
    notional = float(entry["notional_usd"])
    ret = (float(exit_bar["close"]) - float(entry_bar["open"])) / float(entry_bar["open"])
    return notional * ret


def random_timed_entry_expectancy(
    signal: dict[str, Any],
    bars: list[dict[str, Any]],
    policy: ScoringPolicy,
    *,
    rule_name: str,
    sizing_name: str,
    trials: int = 25,
    seed: int = 13,
) -> float | None:
    if len(bars) < 2:
        return None
    rng = random.Random(seed)
    pnls: list[float] = []
    candidates = bars[:-1]
    for trial in range(trials):
        picked = rng.choice(candidates)
        shifted = dict(signal)
        shifted["signal_id"] = f"{signal['signal_id']}-random-{trial}"
        shifted["posted_at"] = picked["ts"]
        shifted["captured_at"] = picked["ts"]
        shifted["posted_price"] = picked["close"]
        record = simulate_signal(shifted, bars, policy, rule_name=rule_name, sizing_name=sizing_name)
        if record.get("settled") and not record.get("excluded"):
            pnls.append(float(record["outcome"]["net_pnl_usd"]))
    if not pnls:
        return None
    return sum(pnls) / len(pnls)
