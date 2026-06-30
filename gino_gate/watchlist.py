from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any

# Local-first interpreter. Anthropic slots in as a higher rung when Gino's key lands;
# Ollama is the local brain (same one Aza-Rion falls back to); deterministic regex is
# the floor so the parser never hard-fails. The LLM is interpreter only -- it structures
# Gino's messy text. It NEVER decides whether a setup is good. The gate is the judge.
OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "llama3.2"

# A watchlist is a hypothesis, not a trade. These are the fields a real trade needs that a
# watchlist almost never carries. We surface what's missing instead of pretending it's ready.
ALWAYS_MISSING = ("stop", "sizing")


@dataclass
class WatchlistItem:
    ticker: str
    thesis: str = ""
    trigger: str | None = None          # e.g. "break above 705"
    target: str | None = None           # e.g. "740"
    timeframe: str | None = None        # e.g. "this week"
    instrument_note: str | None = None  # e.g. "use next week's contracts"
    missing_fields: list[str] = field(default_factory=list)
    raw: str = ""
    engine: str = "deterministic"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _compute_missing(item: WatchlistItem) -> list[str]:
    missing = list(ALWAYS_MISSING)
    if not item.trigger:
        missing.append("entry_confirmation")
    # "exact contract" means a specific strike + expiry. A generic note like
    # "use next week's contracts" is guidance, not a contract.
    note = (item.instrument_note or "").lower()
    has_exact = bool(re.search(r"\d+\s*[cp]\b", note)) or bool(re.search(r"\$?\d+(?:\.\d+)?\s*(call|put)", note))
    if not has_exact:
        missing.append("exact_contract")
    return missing


_TICKER_RE = re.compile(r"\$([A-Z]{1,5})\b|\b([A-Z]{2,5})\s*\(")
_TRIGGER_RE = re.compile(r"(?:break(?:s)?\s+above|above|over|clear(?:s)?|needs|reclaim(?:s)?)\s+\$?(\d+(?:\.\d+)?)", re.IGNORECASE)
_TARGET_RE = re.compile(r"(?:toward|target|to|->|→)\s+\$?(\d+(?:\.\d+)?)|\$?(\d+(?:\.\d+)?)\s+(?:is\s+)?possible", re.IGNORECASE)
_TIMEFRAME_RE = re.compile(r"\b(today|this week|next week|tomorrow|intraday)\b", re.IGNORECASE)
_CONTRACT_NOTE_RE = re.compile(r"[^.]*\bcontracts?\b[^.]*", re.IGNORECASE)


def _parse_deterministic(text: str) -> list[WatchlistItem]:
    items: list[WatchlistItem] = []
    contract_note = None
    note_match = _CONTRACT_NOTE_RE.search(text)
    if note_match:
        contract_note = re.sub(r"\s+", " ", note_match.group(0)).strip()

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        tm = _TICKER_RE.search(line)
        if not tm:
            continue
        ticker = (tm.group(1) or tm.group(2) or "").upper()
        if not ticker:
            continue
        trig = _TRIGGER_RE.search(line)
        targ = _TARGET_RE.search(line)
        tf = _TIMEFRAME_RE.search(line)
        item = WatchlistItem(
            ticker=ticker,
            thesis=re.sub(r"\s+", " ", line).strip(),
            trigger=(f"above {trig.group(1)}" if trig else None),
            target=((targ.group(1) or targ.group(2)) if targ else None),
            timeframe=(tf.group(1).lower() if tf else None),
            instrument_note=contract_note,
            raw=line,
            engine="deterministic",
        )
        item.missing_fields = _compute_missing(item)
        items.append(item)
    return items


def _parse_with_ollama(text: str, *, model: str, timeout: int) -> list[WatchlistItem] | None:
    prompt = (
        "You extract a stock/options watch list into JSON. Return ONLY a JSON array, no prose. "
        "Each element: {\"ticker\": str, \"thesis\": str, \"trigger\": str|null, "
        "\"target\": str|null, \"timeframe\": str|null, \"instrument_note\": str|null}. "
        "trigger is the price level that confirms entry. target is the upside level. "
        "Do not judge whether the trade is good. Just structure it.\n\nWATCH LIST:\n" + text
    )
    payload = json.dumps({"model": model, "prompt": prompt, "stream": False, "format": "json"}).encode("utf-8")
    req = urllib.request.Request(OLLAMA_URL, data=payload, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        raw = (body.get("response") or "").strip()
        # format=json may return an object wrapping the array, or the array itself.
        data = json.loads(raw)
        if isinstance(data, dict):
            # llama with format=json often returns a single item object, or wraps the
            # array under a key. Handle both.
            if data.get("ticker"):
                data = [data]
            else:
                for v in data.values():
                    if isinstance(v, list):
                        data = v
                        break
        if not isinstance(data, list):
            return None
        items: list[WatchlistItem] = []
        for obj in data:
            if not isinstance(obj, dict) or not obj.get("ticker"):
                continue
            item = WatchlistItem(
                ticker=str(obj["ticker"]).upper().lstrip("$"),
                thesis=str(obj.get("thesis") or "").strip(),
                trigger=(str(obj["trigger"]).strip() if obj.get("trigger") else None),
                target=(str(obj["target"]).strip() if obj.get("target") else None),
                timeframe=(str(obj["timeframe"]).strip() if obj.get("timeframe") else None),
                instrument_note=(str(obj["instrument_note"]).strip() if obj.get("instrument_note") else None),
                raw=text,
                engine=f"ollama:{model}",
            )
            item.missing_fields = _compute_missing(item)
            items.append(item)
        return items or None
    except Exception:
        return None


def parse_watchlist(text: str, *, use_llm: bool = True, model: str = DEFAULT_MODEL, timeout: int = 60) -> list[WatchlistItem]:
    """Free-form watch list text -> structured WatchlistItems.

    Tries the local LLM interpreter first (good at messy language), falls back to the
    deterministic regex parser so it never hard-fails. The LLM only structures; it does
    not judge the trade.
    """
    deterministic = _parse_deterministic(text)
    if not use_llm:
        return deterministic
    llm = _parse_with_ollama(text, model=model, timeout=timeout)
    if not llm:
        return deterministic
    # Prefer the richer extraction. Count items that carry a trigger as a completeness
    # proxy; tie-break to deterministic, which has higher field quality on structured lists.
    # (A local model like llama is modest; this keeps it from degrading a clean parse.)
    def score(items: list[WatchlistItem]) -> tuple[int, int]:
        return (sum(1 for it in items if it.trigger), len(items))
    return llm if score(llm) > score(deterministic) else deterministic


def summarize_watchlist(items: list[WatchlistItem]) -> str:
    """Honest, paper-mode summary. Never says a setup is good; always names what's missing
    and that a small captured slice is not a verdict."""
    if not items:
        return "No watch list items parsed. Send tickers with trigger levels and I'll track them in paper mode."
    lines = [
        f"Parsed {len(items)} watch list items. These are hypotheses, not trade-ready signals.",
        "",
    ]
    for it in items:
        bits = [f"  {it.ticker}"]
        if it.trigger:
            bits.append(f"trigger: {it.trigger}")
        if it.target:
            bits.append(f"target: {it.target}")
        if it.timeframe:
            bits.append(f"timeframe: {it.timeframe}")
        lines.append(" | ".join(bits))
        lines.append(f"      missing: {', '.join(it.missing_fields)}")
    lines += [
        "",
        "Tracking these in paper mode only. No live execution, no claim of edge.",
        "A small captured slice over a few days is evidence, not a verdict.",
    ]
    return "\n".join(lines)
