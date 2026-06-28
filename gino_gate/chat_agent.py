from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

from .operator_verdict import OperatorVerdict, explain_call


DEFAULT_SOURCE_CSV = Path("/Users/kenielmaldonado/gino_discord_capture/raw/playbit_signal_chain_log_google_sheet_2026-06-25.csv")


@dataclass(frozen=True)
class ChatResponse:
    message: str
    verdict: OperatorVerdict | None = None


@dataclass
class ChatMemory:
    turns: list[tuple[str, str]] = field(default_factory=list)
    captured_profile: dict[str, str] = field(default_factory=dict)

    def remember(self, user: str, assistant: str) -> None:
        self.turns.append((user, assistant))
        if len(self.turns) > 20:
            self.turns = self.turns[-20:]


class GinoChatAgent:
    """Deterministic chat shell over the current Gino operator engine.

    This is intentionally not an open-ended LLM. It answers within the money-safe
    boundary we can verify today and delegates trade judgments to `explain_call`.
    """

    def __init__(self, source_csv: Path = DEFAULT_SOURCE_CSV):
        self.source_csv = source_csv
        self.memory = ChatMemory()

    def reply(self, message: str) -> ChatResponse:
        text = message.strip()
        lowered = text.lower()
        if not text:
            return self._remembered(text, "I'm here. Tell me what trade, rule, source, or concern you want to work through.")

        row_query = self._parse_row_query(text)
        if row_query is not None:
            row_id, ticker = row_query
            row = self._read_row(row_id, ticker=ticker)
            verdict = explain_call(row)
            response = _format_verdict(verdict)
            self.memory.remember(text, response)
            return ChatResponse(response, verdict=verdict)

        live_call = self._parse_pasted_discord_call(text)
        if live_call is not None:
            verdict = explain_call(live_call)
            response = (
                "I parsed this as a pasted Discord call.\n\n"
                f"{_format_verdict(verdict)}\n\n"
                "Boundary: this is a paper/shadow verdict from pasted text, not a live Robinhood order."
            )
            self.memory.remember(text, response)
            return ChatResponse(response, verdict=verdict)

        if captured := self._capture_profile(text):
            return self._remembered(text, captured)

        if any(word in lowered for word in ("what can you do", "capabilities", "help", "commands")):
            return self._remembered(
                text,
                "I can do six things today:\n"
                "1. Explain the current safety boundary.\n"
                "2. Walk through Gino's strategy/risk rules that must be captured.\n"
                "3. Judge a captured trade row as REFUSE, PAPER_ONLY, or REVIEW_ELIGIBLE.\n"
                "4. Talk through whether a source deserves trust.\n"
                "5. Help slow down impulse trades and bad-day decisions.\n"
                "6. Keep the conversation pointed at paper evidence until live authority is earned.\n\n"
                "Try: explain row 32 COIN, or tell me what kind of trades you want me to judge."
            )

        if any(word in lowered for word in ("bad day", "revenge", "impulse", "tilt", "loss", "losing", "down bad", "frustrated")):
            return self._remembered(
                text,
                "Then the first job is capital protection. No revenge trades, no size increase to get even, and no live trade without a written stop. "
                "If today already broke the daily loss rule, the correct verdict is stop trading and log what happened."
            )

        if any(word in lowered for word in ("boundary", "live", "trade", "robinhood", "autonomous", "auto")):
            return self._remembered(
                text,
                "Current boundary: I do not place live Robinhood trades. I do not auto-trade. "
                "I can review captured calls, refuse weak ones, mark paper-only calls, and identify review-eligible calls. "
                "Live trading comes later only after Gino's risk caps, approval flow, paper results, and kill switch are explicit."
            )

        if any(word in lowered for word in ("risk", "rules", "setup", "strategy", "policy")):
            return self._remembered(
                text,
                "Before money moves, I need Gino's rules:\n"
                "- allowed instruments: stocks, options, crypto, or specific tickers\n"
                "- max dollars or percent risk per trade\n"
                "- max trades per day/week\n"
                "- daily and weekly loss stop\n"
                "- required stop and target format\n"
                "- no-trade conditions\n"
                "- which sources are allowed and whether they include losers\n\n"
                "No machine-checkable stop and target means no live trade."
            )

        if any(word in lowered for word in ("score", "record", "playbit", "source", "edge", "profitable")):
            return self._remembered(
                text,
                "The captured PlayBit-style source did not prove a live edge. "
                "Blind-following the visible record failed, and the strict live-eligible subset did not show enough edge to trade live. "
                "That does not mean every future setup is dead. It means we track Gino's real calls in paper and let settled outcomes decide."
            )

        if any(word in lowered for word in ("should i take", "take this", "buy", "enter", "call", "put", "position")):
            return self._remembered(
                text,
                "I will not tell you to take a live trade from a loose description. "
                "Give me the source, ticker, contract or shares, entry, stop, target, and why the setup exists before entry. "
                "If stop or target is missing, my answer is paper-only or refuse-live."
            )

        if any(word in lowered for word in ("why", "purpose", "goal", "make money", "save me", "trust you")):
            return self._remembered(
                text,
                "My job is not to save you or replace your judgment. My job is to keep the rules visible when emotion, screenshots, or a hot source make the story feel convincing. "
                "If a setup survives evidence, paper results, and your risk limits, we can review it. If it does not, I protect you by saying no."
            )

        return self._remembered(
            text,
            "I can talk this through, but I need something concrete to judge: a trade idea, a source, a risk rule, or a concern. "
            "If you want a trade verdict, give me ticker, instrument, entry, stop, target, source, and timing."
        )

    def _remembered(self, user: str, assistant: str) -> ChatResponse:
        self.memory.remember(user, assistant)
        return ChatResponse(assistant)

    def _capture_profile(self, text: str) -> str | None:
        lowered = text.lower()
        patterns = {
            "max_loss": r"(?:max loss|max risk|risk)\s+(?:is\s+)?\$?(?P<value>\d+(?:\.\d+)?%?)",
            "instrument": r"(?:i trade|trade|focus on)\s+(?P<value>options|stocks|equities|crypto|forex)",
            "source": r"(?:i follow|source is|sources are)\s+(?P<value>[^.]+)",
        }
        for key, pattern in patterns.items():
            found = re.search(pattern, lowered, flags=re.IGNORECASE)
            if not found:
                continue
            value = found.group("value").strip()
            self.memory.captured_profile[key] = value
            return f"Got it. I recorded {key.replace('_', ' ')} as: {value}. I still need the full rule set before any live-trade authority."
        return None

    def _parse_row_query(self, text: str) -> tuple[str, str] | None:
        found = re.search(r"\b(?:row|#)\s*(?P<row>\d+)\b(?:.*?\b(?P<ticker>[A-Z]{1,6})\b)?", text, flags=re.IGNORECASE)
        if not found:
            return None
        ticker = (found.group("ticker") or "").upper()
        return found.group("row"), ticker

    def _parse_pasted_discord_call(self, text: str) -> dict[str, str] | None:
        normalized = re.sub(r"\s+", " ", text.strip())
        if not normalized:
            return None

        contract = _extract_option_contract(normalized)
        ticker = _extract_ticker(normalized, contract)
        if not ticker or not contract:
            return None

        direction = "Call" if re.search(r"\d\s*[cC]\b", contract) else "Put"
        source = self.memory.captured_profile.get("source", "pasted_discord_call")
        return {
            "#": "live-paste",
            "Trader": source,
            "Date": "",
            "Time": "",
            "Ticker": ticker,
            "Direction": direction,
            "Contract / Fill": contract,
            "Event Type": "ENTRY",
            "Mark": "",
            "P/L %": "",
            "P/L $": "",
            "Trader Commentary": normalized,
        }

    def _read_row(self, row_id: str, *, ticker: str = "") -> dict[str, str]:
        matches: list[dict[str, str]] = []
        with self.source_csv.open("r", newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                if str(row.get("#", "")).strip() != row_id:
                    continue
                if ticker and str(row.get("Ticker", "")).strip().upper() != ticker:
                    continue
                matches.append(row)
        if not matches:
            raise ValueError(f"row {row_id} was not found" + (f" for {ticker}" if ticker else ""))
        if len(matches) > 1:
            tickers = ", ".join(f"{row.get('Ticker')} by {row.get('Trader')}" for row in matches[:8])
            raise ValueError(f"row {row_id} is ambiguous; include a ticker. Matches: {tickers}")
        return matches[0]


def _format_verdict(verdict: OperatorVerdict) -> str:
    reasons = "\n".join(f"- {reason}" for reason in verdict.reasons)
    return (
        f"Verdict: {verdict.verdict}\n"
        f"Action: {verdict.action}\n"
        f"Trader: {verdict.trader}\n"
        f"Ticker: {verdict.ticker}\n\n"
        f"{verdict.summary}\n\n"
        f"Reasons:\n{reasons}"
    )


def _extract_option_contract(text: str) -> str | None:
    patterns = [
        # AAPL 7/19 200c @2.50 -> 7/19 200c @2.50
        r"\b(?P<expiry>\d{1,2}/\d{1,2}(?:/\d{2,4})?)\s+\$?(?P<strike>\d+(?:\.\d+)?)\s*(?P<kind>[cCpP])(?:\s*@\s*\$?(?P<price>\d*(?:\.\d+)?))?",
        # AAPL 200c 7/19 @2.50 -> 200c 7/19 @2.50
        r"\b(?P<strike>\d+(?:\.\d+)?)\s*(?P<kind>[cCpP])\s+(?P<expiry>\d{1,2}/\d{1,2}(?:/\d{2,4})?)(?:\s*@\s*\$?(?P<price>\d*(?:\.\d+)?))?",
        # 20 MAR 26 70C
        r"\b(?P<expiry>\d{1,2}\s+[A-Za-z]{3}\s+\d{2,4})\s+(?P<strike>\d+(?:\.\d+)?)\s*(?P<kind>[cCpP])\b",
    ]
    for pattern in patterns:
        found = re.search(pattern, text)
        if not found:
            continue
        parts = found.groupdict()
        if pattern.startswith("\\b(?P<expiry>"):
            contract = f"{parts['expiry']} {parts['strike']}{parts['kind'].lower()}"
        else:
            contract = f"{parts['strike']}{parts['kind'].lower()} {parts['expiry']}"
        price = parts.get("price")
        if price:
            contract += f" @{price}"
        return contract
    return None


def _extract_ticker(text: str, contract: str | None) -> str:
    if not contract:
        return ""
    contract_index = text.lower().find(contract.lower())
    prefix = text if contract_index < 0 else text[:contract_index]
    candidates = re.findall(r"\$?\b([A-Z]{1,6})\b", prefix)
    ignored = {"SL", "TP", "CALL", "PUT", "BUY", "SELL", "ENTRY", "STOP", "TARGET"}
    for candidate in reversed(candidates):
        if candidate.upper() not in ignored:
            return candidate.upper()
    all_candidates = re.findall(r"\$?\b([A-Z]{1,6})\b", text)
    for candidate in all_candidates:
        if candidate.upper() not in ignored:
            return candidate.upper()
    return ""
