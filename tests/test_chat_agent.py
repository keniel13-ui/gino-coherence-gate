from pathlib import Path

from gino_gate.chat_agent import GinoChatAgent


def _sample_csv(tmp_path: Path) -> Path:
    path = tmp_path / "calls.csv"
    path.write_text(
        "#,Trader,Date,Time,Ticker,Direction,Contract / Fill,Event Type,Mark,P/L %,P/L $,Trader Commentary\n"
        "32,glacierboy300,2/9/26,9:30 AM,COIN,Call,200c 3/20 @4.90,ENTRY,,,,TP 208; SL 143\n"
        "16,Robby4C,2/9/26,9:31 AM,ORCL,Call,180c 3/20 @3.10,ENTRY,,,,small position\n",
        encoding="utf-8",
    )
    return path


def test_chat_agent_explains_current_boundary(tmp_path):
    agent = GinoChatAgent(_sample_csv(tmp_path))

    response = agent.reply("Can you auto trade Robinhood live?")

    assert "do not place live Robinhood trades" in response.message
    assert "approval flow" in response.message
    assert response.verdict is None


def test_chat_agent_routes_row_question_to_operator_verdict(tmp_path):
    agent = GinoChatAgent(_sample_csv(tmp_path))

    response = agent.reply("explain row 32 COIN")

    assert response.verdict is not None
    assert response.verdict.verdict == "REVIEW_ELIGIBLE"
    assert "stop: SL 143" in response.message
    assert "target: TP 208" in response.message


def test_chat_agent_keeps_missing_stop_target_paper_only(tmp_path):
    agent = GinoChatAgent(_sample_csv(tmp_path))

    response = agent.reply("what about row 16 ORCL?")

    assert response.verdict is not None
    assert response.verdict.verdict == "PAPER_ONLY"
    assert "should not become a live Robinhood order yet" in response.message


def test_chat_agent_discusses_purpose_without_promising_rescue(tmp_path):
    agent = GinoChatAgent(_sample_csv(tmp_path))

    response = agent.reply("why should I trust you to make money and save me?")

    assert "not to save you" in response.message
    assert "replace your judgment" in response.message
    assert "protect you by saying no" in response.message


def test_chat_agent_slows_down_impulse_trades(tmp_path):
    agent = GinoChatAgent(_sample_csv(tmp_path))

    response = agent.reply("I'm frustrated and want a revenge trade after a loss")

    assert "capital protection" in response.message
    assert "No revenge trades" in response.message
    assert "daily loss rule" in response.message


def test_chat_agent_captures_profile_rule_in_memory(tmp_path):
    agent = GinoChatAgent(_sample_csv(tmp_path))

    response = agent.reply("my max risk is $50")

    assert "recorded max loss as: 50" in response.message
    assert agent.memory.captured_profile["max_loss"] == "50"
