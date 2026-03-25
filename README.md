# Telegram GPT bot (admin edits prompt + model)

## What it does
- Users write messages to the bot.
- Users can also send files:
  - `PDF`
  - `DOCX` (и иногда `DOC`, если Telegram и формат совпадают)
- The bot answers using **GPT API** with a stored **system prompt**.
- Admin has access to an **admin panel**:
  - Show the current system prompt
  - Change the system prompt (ТЗ for GPT)
  - Change the OpenAI model name

All settings are stored in `gpt_store.json` on the server filesystem.

## Setup
1. Create `.env` in the project root (copy from `.env.example`)
2. Install dependencies:
   - `pip install -r requirements.txt`
3. Run:
   - `python bot.py`

## Required environment variables
- `BOT_TOKEN`
- `OPENAI_API_KEY`
- `OPENAI_MODEL` (default `gpt-5.4`)
- `ADMIN_TELEGRAM_IDS` (comma-separated user ids)
- `GPT_SYSTEM_PROMPT` (optional; if set, it overrides stored prompt)


