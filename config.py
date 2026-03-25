import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


def _split_ints(value: str) -> list[int]:
    parts = [p.strip() for p in (value or "").split(",")]
    return [int(p) for p in parts if p]


@dataclass(frozen=True)
class Settings:
    bot_token: str
    openai_api_key: str
    openai_model: str
    channel_id: str
    admin_telegram_ids: list[int]


def get_settings() -> Settings:
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
    openai_model = os.getenv("OPENAI_MODEL", "gpt-5.4-mini").strip()
    channel_id = os.getenv("CHANNEL_ID", "").strip()

    admin_ids_raw = os.getenv("ADMIN_TELEGRAM_IDS", "").strip()
    admin_telegram_ids = _split_ints(admin_ids_raw)

    missing = []
    if not bot_token:
        missing.append("BOT_TOKEN")
    if not openai_api_key:
        missing.append("OPENAI_API_KEY")
    if not channel_id:
        missing.append("CHANNEL_ID")
    if not admin_telegram_ids:
        missing.append("ADMIN_TELEGRAM_IDS")

    if missing:
        raise RuntimeError(f"Missing env vars: {', '.join(missing)}")

    return Settings(
        bot_token=bot_token,
        openai_api_key=openai_api_key,
        openai_model=openai_model,
        channel_id=channel_id,
        admin_telegram_ids=admin_telegram_ids,
    )

