# Telegram consultant bot (GPT)

## What it does
- `/start` -> shows button `HELLS BELLS`
- Bot collects: name, age, work experience with neural nets, what user wants to learn, phone, Telegram account
- Then user can chat; on `ПОЕХАЛИ` the bot asks GPT to summarize and sends the result to a private channel
- `АДМИН` button is shown only to `ADMIN_TELEGRAM_IDS`; admin can edit GPT prompts and model via Telegram

## Setup
1. Create `.env` in the project root (copy from `.env.example`)
2. Install dependencies:
   - `pip install -r requirements.txt`
3. Run:
   - `python bot.py`

## Telegram channel requirement
Your bot must be an admin/member of the target channel.  
In `.env` set `CHANNEL_ID` to the channel numeric id (usually `-100...`).

