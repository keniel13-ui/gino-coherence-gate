from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gino_gate.chat_agent import DEFAULT_SOURCE_CSV, GinoChatAgent
from gino_gate.interaction_log import InteractionLog


class TelegramClient:
    def __init__(self, token: str, *, timeout: int = 30):
        if not token:
            raise ValueError("Telegram bot token is required")
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.timeout = timeout

    def get_updates(self, *, offset: int | None = None) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"timeout": self.timeout}
        if offset is not None:
            params["offset"] = offset
        data = self._request("getUpdates", params)
        if not data.get("ok"):
            raise RuntimeError(f"Telegram getUpdates failed: {data}")
        return list(data.get("result", []))

    def send_message(self, chat_id: int, text: str) -> None:
        # Telegram caps messages at 4096 chars. Keep replies comfortably below that.
        chunks = [text[i:i + 3500] for i in range(0, len(text), 3500)] or [""]
        for chunk in chunks:
            data = self._request("sendMessage", {"chat_id": chat_id, "text": chunk})
            if not data.get("ok"):
                raise RuntimeError(f"Telegram sendMessage failed: {data}")

    def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        encoded = urllib.parse.urlencode(params).encode("utf-8")
        request = urllib.request.Request(f"{self.base_url}/{method}", data=encoded, method="POST")
        with urllib.request.urlopen(request, timeout=self.timeout + 10) as response:
            return json.loads(response.read().decode("utf-8"))


BASE_BACKOFF = 3.0
MAX_BACKOFF = 60.0


def run_bot(client: TelegramClient, agent: GinoChatAgent, *, log: InteractionLog | None = None) -> None:
    print("Gino Telegram agent is running in paper/shadow mode.")
    print("Open Telegram, message the bot, and send: what can you do?")
    print("Press Ctrl+C to stop.")
    offset: int | None = None
    backoff = BASE_BACKOFF
    last_error_kind: str | None = None
    repeat = 0
    while True:
        try:
            updates = client.get_updates(offset=offset)
            # Reset resilience state on any successful poll.
            backoff = BASE_BACKOFF
            if last_error_kind is not None:
                print("Telegram connection recovered.", file=sys.stderr)
                last_error_kind = None
                repeat = 0
            for update in updates:
                offset = int(update["update_id"]) + 1
                message = update.get("message") or {}
                chat = message.get("chat") or {}
                chat_id = chat.get("id")
                text = str(message.get("text") or "").strip()
                if chat_id is None or not text:
                    continue
                if text.lower() in {"/start", "start"}:
                    reply = (
                        "Gino agent is online in paper/shadow mode. I can talk through trades, rules, "
                        "sources, discipline, and verdicts. I cannot place live Robinhood trades."
                    )
                    client.send_message(chat_id, reply)
                    if log is not None:
                        log.record(channel="telegram", chat_id=chat_id, user_text=text,
                                   reply_text=reply, engine="deterministic")
                    continue
                verdict_label: str | None = None
                action_label: str | None = None
                try:
                    response = agent.reply(text)
                    reply = response.message
                    if response.verdict is not None:
                        verdict_label = getattr(response.verdict, "verdict", None)
                        action_label = getattr(response.verdict, "action", None)
                except ValueError as exc:
                    reply = f"Error: {exc}"
                client.send_message(chat_id, reply)
                if log is not None:
                    log.record(channel="telegram", chat_id=chat_id, user_text=text,
                               reply_text=reply, engine="deterministic",
                               verdict=verdict_label, action=action_label)
        except KeyboardInterrupt:
            print("\nStopped.")
            return
        except Exception as exc:
            # Exponential backoff with jitter, and quiet the error flood: announce the
            # first failure of a kind, then only every 10th, so a network outage does
            # not machine-gun the log the way it did on 2026-06-29.
            kind = type(exc).__name__
            if kind == last_error_kind:
                repeat += 1
                if repeat % 10 == 0:
                    print(f"Telegram still unreachable ({kind}), retrying every ~{backoff:.0f}s (x{repeat})",
                          file=sys.stderr)
            else:
                print(f"Telegram loop error: {exc} — backing off, will retry quietly", file=sys.stderr)
                last_error_kind = kind
                repeat = 0
            time.sleep(backoff + random.uniform(0, backoff * 0.25))
            backoff = min(MAX_BACKOFF, backoff * 2)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Gino's local paper/shadow agent as a Telegram bot.")
    parser.add_argument("--source-csv", type=Path, default=DEFAULT_SOURCE_CSV)
    parser.add_argument("--token-env", default="GINO_TELEGRAM_BOT_TOKEN")
    args = parser.parse_args()

    token = os.environ.get(args.token_env, "").strip()
    if not token:
        print(f"Missing Telegram token. Set it first: export {args.token_env}='123:abc'", file=sys.stderr)
        return 2

    run_bot(TelegramClient(token), GinoChatAgent(args.source_csv), log=InteractionLog())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

