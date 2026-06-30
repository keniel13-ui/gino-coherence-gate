from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Witness ledger lives under var/ (gitignored): Gino's data stays local, never committed.
DEFAULT_LOG_PATH = Path(__file__).resolve().parents[1] / "var" / "gino_interaction_log.jsonl"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class InteractionRecord:
    ts: str
    channel: str
    chat_id: Any
    user_text: str
    reply_text: str
    engine: str          # which brain answered: "deterministic" | "ollama:<model>" | "anthropic:<model>"
    verdict: str | None  # the deterministic gate's verdict label -- the authority, not the brain's opinion
    action: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ts": self.ts,
            "channel": self.channel,
            "chat_id": self.chat_id,
            "user_text": self.user_text,
            "reply_text": self.reply_text,
            "engine": self.engine,
            "verdict": self.verdict,
            "action": self.action,
        }


class InteractionLog:
    """Append-only Witness ledger of agent turns.

    Records what came in, what the agent replied, which engine produced it, and the
    deterministic gate verdict (the authority). This is the receipt that makes
    "is the agent reasoning or pretending" a checkable question instead of a vibe:
    later we line up what a brain claimed against what the gate decided and what the
    market actually did. Without this layer the agent is a black box, and bolting an
    LLM onto a black box is the exact trap the research warns against.
    """

    def __init__(self, path: Path | str = DEFAULT_LOG_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        *,
        channel: str,
        chat_id: Any,
        user_text: str,
        reply_text: str,
        engine: str,
        verdict: str | None = None,
        action: str | None = None,
    ) -> InteractionRecord:
        rec = InteractionRecord(
            ts=_now_iso(),
            channel=channel,
            chat_id=chat_id,
            user_text=user_text,
            reply_text=reply_text,
            engine=engine,
            verdict=verdict,
            action=action,
        )
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec.to_dict(), ensure_ascii=False) + "\n")
        return rec

    def tail(self, n: int = 20) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        out: list[dict[str, Any]] = []
        for line in lines[-n:]:
            line = line.strip()
            if line:
                out.append(json.loads(line))
        return out

    def count(self) -> int:
        if not self.path.exists():
            return 0
        return sum(1 for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip())
