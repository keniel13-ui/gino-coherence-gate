from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gino_gate.chat_agent import DEFAULT_SOURCE_CSV, GinoChatAgent


def main() -> int:
    parser = argparse.ArgumentParser(description="Chat with Gino's local paper/shadow trading agent.")
    parser.add_argument("--source-csv", type=Path, default=DEFAULT_SOURCE_CSV)
    parser.add_argument("--message", default="", help="Run one message and exit.")
    args = parser.parse_args()

    agent = GinoChatAgent(args.source_csv)
    if args.message:
        try:
            print(agent.reply(args.message).message)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2
        return 0

    print("Gino agent chat is running in paper/shadow mode.")
    print("It can talk through trades, rules, sources, discipline, and verdicts.")
    print("It cannot place live Robinhood trades. Try: explain row 32 COIN")
    print("Type 'exit' or 'quit' to stop.\n")
    while True:
        try:
            message = input("Gino> ")
        except EOFError:
            print("")
            return 0
        if message.strip().lower() in {"exit", "quit"}:
            return 0
        try:
            print(agent.reply(message).message)
        except ValueError as exc:
            print(f"Error: {exc}")
        print("")


if __name__ == "__main__":
    raise SystemExit(main())
