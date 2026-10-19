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



class ScriptedTelegramClient(FakeTelegramClient):
    def __init__(self, updates):
        super().__init__()
        self._updates = updates

    def get_updates(self, *, offset=None):
        self.calls += 1
        if self.calls == 1:
            return self._updates
        raise KeyboardInterrupt


def _empty_csv(tmp_path):
    csv_path = tmp_path / "calls.csv"
    csv_path.write_text(
        "#,Trader,Date,Time,Ticker,Direction,Contract / Fill,Event Type,Mark,P/L %,P/L $,Trader Commentary\n",
        encoding="utf-8",
    )
    return csv_path


def test_allowlist_ignores_unknown_chats(tmp_path):
    client = ScriptedTelegramClient([
        {"update_id": 1, "message": {"chat": {"id": 666}, "text": "what can you do?"}},
        {"update_id": 2, "message": {"chat": {"id": 100}, "text": "what can you do?"}},
    ])
    run_bot(client, GinoChatAgent(_empty_csv(tmp_path)), allowed_chat_ids={100})
    assert [chat for chat, _ in client.sent] == [100]


def test_missing_source_csv_gets_a_reply_instead_of_a_silent_backoff(tmp_path):
    # Regression: FileNotFoundError escaped the handler, hit the transport retry
    # branch (sleep + backoff), and the user never got an answer.
    client = ScriptedTelegramClient([{"update_id": 1, "message": {"chat": {"id": 100}, "text": "explain row 32 COIN"}}])
    run_bot(client, GinoChatAgent(tmp_path / "missing.csv"))
    assert len(client.sent) == 1
    assert "captured call log not found" in client.sent[0][1]


def test_unexpected_agent_error_is_answered_not_retried(tmp_path):
    class BrokenAgent:
        def reply(self, text):
            raise KeyError("boom")

    client = ScriptedTelegramClient([{"update_id": 1, "message": {"chat": {"id": 100}, "text": "hello"}}])
    run_bot(client, BrokenAgent())
    assert client.sent == [(100, "Error: I could not process that message. It was logged locally.")]


def test_parse_chat_allowlist():
    from scripts.gino_telegram_bot import parse_chat_allowlist

    assert parse_chat_allowlist("") is None
    assert parse_chat_allowlist(" 100, -200 ,") == {100, -200}


def test_request_errors_do_not_leak_the_token(monkeypatch):
    import pytest

    from scripts import gino_telegram_bot

    def explode(request, timeout):
        raise ValueError(f"bad url {request.full_url}")

    monkeypatch.setattr(gino_telegram_bot.urllib.request, "urlopen", explode)
    client = gino_telegram_bot.TelegramClient("123:SECRET")
    with pytest.raises(RuntimeError) as excinfo:
        client.get_updates()
    assert "SECRET" not in str(excinfo.value)
    assert "<redacted>" in str(excinfo.value)
