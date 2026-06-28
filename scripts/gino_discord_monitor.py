from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gino_gate.chat_agent import DEFAULT_SOURCE_CSV, GinoChatAgent
from scripts.gino_telegram_bot import TelegramClient


class DiscordRestClient:
    def __init__(self, token: str):
        if not token:
            raise ValueError("Discord bot token is required")
        self.token = token

    def recent_messages(self, channel_id: str, *, after: str | None = None, limit: int = 25) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": str(limit)}
        if after:
            params["after"] = after
        query = urllib.parse.urlencode(params)
        request = urllib.request.Request(f"https://discord.com/api/v10/channels/{channel_id}/messages?{query}")
        request.add_header("Authorization", f"Bot {self.token}")
        request.add_header("User-Agent", "gino-coherence-gate/0.1")
        with urllib.request.urlopen(request, timeout=20) as response:
            messages = json.loads(response.read().decode("utf-8"))
        if not isinstance(messages, list):
            raise RuntimeError(f"Discord messages response was not a list: {messages}")
        return list(reversed(messages))


def _env_list(name: str) -> list[str]:
    return [part.strip() for part in os.environ.get(name, "").split(",") if part.strip()]


def _message_text(message: dict[str, Any]) -> str:
    content = str(message.get("content") or "").strip()
    embeds = message.get("embeds") or []
    embed_text: list[str] = []
    for embed in embeds:
        if not isinstance(embed, dict):
            continue
        for key in ("title", "description"):
            if embed.get(key):
                embed_text.append(str(embed[key]))
        for field in embed.get("fields") or []:
            if isinstance(field, dict):
                embed_text.append(str(field.get("name") or ""))
                embed_text.append(str(field.get("value") or ""))
    return " ".join(part for part in [content, *embed_text] if part).strip()


def run_monitor(
    *,
    discord: DiscordRestClient,
    channel_ids: list[str],
    agent: GinoChatAgent,
    telegram: TelegramClient | None = None,
    telegram_chat_id: int | None = None,
    poll_seconds: float = 5.0,
) -> None:
    if not channel_ids:
        raise ValueError("At least one Discord channel ID is required")

    last_seen: dict[str, str | None] = {channel_id: None for channel_id in channel_ids}
    print("Gino Discord monitor is running in paper/shadow mode.")
    print("It reads approved Discord channels, verdicts parseable calls, and never places trades.")
    print("Press Ctrl+C to stop.")

    while True:
        try:
            for channel_id in channel_ids:
                for message in discord.recent_messages(channel_id, after=last_seen[channel_id]):
                    message_id = str(message.get("id") or "")
                    if message_id:
                        last_seen[channel_id] = message_id
                    text = _message_text(message)
                    if not text:
                        continue
                    try:
                        response = agent.reply(text)
                    except ValueError as exc:
                        response = None
                        print(f"Skipped Discord message {message_id}: {exc}")
                    if response is None or response.verdict is None:
                        continue
                    alert = f"Discord channel {channel_id} message {message_id}\n\n{response.message}"
                    if telegram and telegram_chat_id is not None:
                        telegram.send_message(telegram_chat_id, alert)
                    else:
                        print(alert)
            time.sleep(poll_seconds)
        except KeyboardInterrupt:
            print("\nStopped.")
            return
        except Exception as exc:
            print(f"Discord monitor error: {exc}", file=sys.stderr)
            time.sleep(max(poll_seconds, 3.0))


def main() -> int:
    parser = argparse.ArgumentParser(description="Monitor Discord channels and send Gino agent verdicts to Telegram/stdout.")
    parser.add_argument("--source-csv", type=Path, default=DEFAULT_SOURCE_CSV)
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--discord-token-env", default="GINO_DISCORD_BOT_TOKEN")
    parser.add_argument("--discord-channel-ids-env", default="GINO_DISCORD_CHANNEL_IDS")
    parser.add_argument("--telegram-token-env", default="GINO_TELEGRAM_BOT_TOKEN")
    parser.add_argument("--telegram-chat-id-env", default="GINO_TELEGRAM_CHAT_ID")
    args = parser.parse_args()

    discord_token = os.environ.get(args.discord_token_env, "").strip()
    channel_ids = _env_list(args.discord_channel_ids_env)
    if not discord_token:
        print(f"Missing Discord bot token. Set: export {args.discord_token_env}='...'", file=sys.stderr)
        return 2
    if not channel_ids:
        print(f"Missing Discord channel IDs. Set: export {args.discord_channel_ids_env}='123,456'", file=sys.stderr)
        return 2

    telegram_token = os.environ.get(args.telegram_token_env, "").strip()
    telegram_chat = os.environ.get(args.telegram_chat_id_env, "").strip()
    telegram = TelegramClient(telegram_token) if telegram_token else None
    telegram_chat_id = int(telegram_chat) if telegram_chat else None

    run_monitor(
        discord=DiscordRestClient(discord_token),
        channel_ids=channel_ids,
        agent=GinoChatAgent(args.source_csv),
        telegram=telegram,
        telegram_chat_id=telegram_chat_id,
        poll_seconds=args.poll_seconds,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

