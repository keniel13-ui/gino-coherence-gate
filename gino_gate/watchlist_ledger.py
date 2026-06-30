from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .watchlist import WatchlistItem

# Lives under var/ (gitignored): Gino's data stays local, never committed.
DEFAULT_LEDGER_PATH = Path(__file__).resolve().parents[1] / "var" / "gino_watchlist_ledger.jsonl"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class WatchlistRecord:
    ts: str
    ticker: str
    thesis: str
    trigger: str | None
    target: str | None
    timeframe: str | None
    instrument_note: str | None
    missing_fields: list[str]
    engine: str
    # Price anchor: the receipt that makes chronological scoring possible. Source is an
    # OPEN decision (free quote API / Robinhood read / manual), so we record it honestly
    # as pending rather than fake a number.
    price_at_receipt: float | None = None
    price_source: str = "pending"
    # Outcome is filled in later at settlement. Until then it stays null on purpose.
    outcome: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class WatchlistLedger:
    """Append-only ledger that turns Gino's daily watch lists into receipts.

    Not prediction. Chronological capture: what was called, when, what it was missing, and
    (once a price source is wired) the price at the moment of the call, settled later. The
    point is evidence over time, with the honest caveat that a small slice is not a verdict.
    """

    def __init__(self, path: Path | str = DEFAULT_LEDGER_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record_item(
        self,
        item: WatchlistItem,
        *,
        price_at_receipt: float | None = None,
        price_source: str = "pending",
    ) -> WatchlistRecord:
        rec = WatchlistRecord(
            ts=_now_iso(),
            ticker=item.ticker,
            thesis=item.thesis,
            trigger=item.trigger,
            target=item.target,
            timeframe=item.timeframe,
            instrument_note=item.instrument_note,
            missing_fields=item.missing_fields,
            engine=item.engine,
            price_at_receipt=price_at_receipt,
            price_source=price_source,
        )
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec.to_dict(), ensure_ascii=False) + "\n")
        return rec

    def record_watchlist(
        self,
        items: list[WatchlistItem],
        *,
        price_lookup=None,
    ) -> list[WatchlistRecord]:
        """Record a whole watch list. If a price_lookup callable is provided
        (ticker -> (price, source)), it is used to anchor each item; otherwise price stays
        pending. Keeps the price source pluggable so the open decision doesn't block capture."""
        out: list[WatchlistRecord] = []
        for item in items:
            price, source = (None, "pending")
            if price_lookup is not None:
                try:
                    price, source = price_lookup(item.ticker)
                except Exception:
                    price, source = (None, "lookup_failed")
            out.append(self.record_item(item, price_at_receipt=price, price_source=source))
        return out

    def tail(self, n: int = 50) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines[-n:] if line.strip()]

    def count(self) -> int:
        if not self.path.exists():
            return 0
        return sum(1 for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip())
