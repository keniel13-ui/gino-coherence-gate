# Gino Agent Mac Mini Setup

This setup runs the agent in paper/shadow mode only.

The agent can:

- chat with Gino through Telegram
- read approved Discord channels if a Discord bot can be added
- parse calls
- return `REFUSE`, `PAPER_ONLY`, or `REVIEW_ELIGIBLE`
- alert Gino in Telegram

The agent cannot:

- place Robinhood trades
- cancel Robinhood orders
- autonomously execute money

## 1. Clone

```bash
git clone https://github.com/keniel13-ui/gino-coherence-gate.git
cd gino-coherence-gate
```

## 2. Verify

```bash
python3 -m pytest tests -q
```

Expected: all tests pass.

## 3. Telegram Only

```bash
export GINO_TELEGRAM_BOT_TOKEN='PASTE_TELEGRAM_TOKEN'
python3 scripts/gino_telegram_bot.py
```

Gino should message the bot:

```text
/start
what can you do?
```

## 4. Get Telegram Chat ID

After Gino sends `/start`:

```bash
curl -sS "https://api.telegram.org/bot$GINO_TELEGRAM_BOT_TOKEN/getUpdates"
```

Find:

```json
"chat":{"id":123456789
```

Then set:

```bash
export GINO_TELEGRAM_CHAT_ID='123456789'
```

## 5. Discord Monitor

Required:

- Discord bot token
- Discord channel ID
- bot added to the server/channel with read permissions

```bash
export GINO_DISCORD_BOT_TOKEN='PASTE_DISCORD_BOT_TOKEN'
export GINO_DISCORD_CHANNEL_IDS='PASTE_CHANNEL_ID'
export GINO_TELEGRAM_BOT_TOKEN='PASTE_TELEGRAM_TOKEN'
export GINO_TELEGRAM_CHAT_ID='123456789'
python3 scripts/gino_discord_monitor.py
```

Flow:

```text
Discord call -> parser/verdict engine -> Telegram alert
```

## 6. One-Command Stack

After all env vars are set:

```bash
python3 scripts/run_gino_agent_stack.py
```

Telegram-only mode:

```bash
python3 scripts/run_gino_agent_stack.py --no-discord
```

## Boundary

Do not wire live Robinhood execution until all of these exist:

- Gino-specific risk caps
- paper-forward results
- approval flow
- kill switch
- proven source/setup edge

