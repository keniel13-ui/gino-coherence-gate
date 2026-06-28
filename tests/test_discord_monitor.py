from pathlib import Path

from gino_gate.chat_agent import GinoChatAgent
from scripts.gino_discord_monitor import run_monitor


class FakeDiscord:
    def __init__(self):
        self.calls = 0

    def recent_messages(self, channel_id, *, after=None, limit=25):
        self.calls += 1
        if self.calls == 1:
            return [
                {"id": "1", "content": "gm everyone"},
                {"id": "2", "content": "AAPL 7/19 200c @2.50 TP 210 SL 190"},
            ]
        raise KeyboardInterrupt


class FakeTelegram:
    def __init__(self):
        self.sent = []

    def send_message(self, chat_id, text):
        self.sent.append((chat_id, text))


def _sample_csv(tmp_path: Path) -> Path:
    path = tmp_path / "calls.csv"
    path.write_text(
        "#,Trader,Date,Time,Ticker,Direction,Contract / Fill,Event Type,Mark,P/L %,P/L $,Trader Commentary\n",
        encoding="utf-8",
    )
    return path


def test_discord_monitor_alerts_on_parseable_trade(tmp_path):
    telegram = FakeTelegram()

    run_monitor(
        discord=FakeDiscord(),
        channel_ids=["channel-1"],
        agent=GinoChatAgent(_sample_csv(tmp_path)),
        telegram=telegram,
        telegram_chat_id=100,
        poll_seconds=0,
    )

    assert len(telegram.sent) == 1
    assert telegram.sent[0][0] == 100
    assert "Verdict: REVIEW_ELIGIBLE" in telegram.sent[0][1]
    assert "Ticker: AAPL" in telegram.sent[0][1]

