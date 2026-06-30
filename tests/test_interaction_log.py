from __future__ import annotations

import json

from gino_gate.interaction_log import InteractionLog


def test_record_appends_and_tail_reads_back(tmp_path):
    log = InteractionLog(tmp_path / "log.jsonl")
    log.record(
        channel="telegram",
        chat_id=849508317,
        user_text="explain row 32 COIN",
        reply_text="REFUSE: do not trade",
        engine="deterministic",
        verdict="REFUSE",
        action="do_not_trade",
    )
    log.record(
        channel="telegram",
        chat_id=849508317,
        user_text="what can you do?",
        reply_text="paper/shadow only",
        engine="deterministic",
    )

    assert log.count() == 2
    rows = log.tail()
    assert len(rows) == 2
    first = rows[0]
    assert first["channel"] == "telegram"
    assert first["chat_id"] == 849508317
    assert first["engine"] == "deterministic"
    assert first["verdict"] == "REFUSE"
    assert first["action"] == "do_not_trade"
    assert "ts" in first
    # second turn carries no verdict (general chat), recorded honestly as null
    assert rows[1]["verdict"] is None


def test_log_is_valid_jsonl(tmp_path):
    path = tmp_path / "log.jsonl"
    log = InteractionLog(path)
    log.record(channel="cli", chat_id=None, user_text="hi", reply_text="hello", engine="deterministic")
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    json.loads(lines[0])  # must parse


def test_tail_respects_n(tmp_path):
    log = InteractionLog(tmp_path / "log.jsonl")
    for i in range(5):
        log.record(channel="cli", chat_id=None, user_text=f"q{i}", reply_text=f"a{i}", engine="deterministic")
    assert len(log.tail(2)) == 2
    assert log.tail(2)[-1]["user_text"] == "q4"
