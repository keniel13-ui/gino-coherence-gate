from gino_gate.chat_agent import GinoChatAgent
from scripts.gino_telegram_bot import run_bot


class FakeTelegramClient:
    def __init__(self):
        self.calls = 0
        self.sent: list[tuple[int, str]] = []

    def get_updates(self, *, offset=None):
        self.calls += 1
        if self.calls == 1:
            return [
                {"update_id": 1, "message": {"chat": {"id": 100}, "text": "/start"}},
                {"update_id": 2, "message": {"chat": {"id": 100}, "text": "what can you do?"}},
            ]
        raise KeyboardInterrupt

    def send_message(self, chat_id: int, text: str) -> None:
        self.sent.append((chat_id, text))


def test_telegram_bot_routes_messages(tmp_path):
    csv_path = tmp_path / "calls.csv"
    csv_path.write_text(
        "#,Trader,Date,Time,Ticker,Direction,Contract / Fill,Event Type,Mark,P/L %,P/L $,Trader Commentary\n",
        encoding="utf-8",
    )
    client = FakeTelegramClient()

    run_bot(client, GinoChatAgent(csv_path))

    assert len(client.sent) == 2
    assert "paper/shadow mode" in client.sent[0][1]
    assert "I can do six things today" in client.sent[1][1]

