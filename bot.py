import asyncio
import json
import logging
import os
from dataclasses import dataclass

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardRemove,
    ReplyKeyboardMarkup,
)
from dotenv import load_dotenv
from openai import AsyncOpenAI


logging.basicConfig(level=logging.INFO)
log = logging.getLogger("gpt_consultant_bot")

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
STORE_PATH = os.path.join(PROJECT_DIR, "gpt_store.json")


DEFAULT_SYSTEM_PROMPT = (
    "Ты — хамоватая, но не грубая продавщица советского магазина/общепита. "
    "Отвечай коротко, по делу, с лёгкой дерзостью и подбадриванием.\n\n"
    "ЖЁСТКОЕ ТЗ (строгий сценарий):\n"
    "1) Сначала запроси аукционные документы.\n"
    "2) После того как пользователь прислал аукционные документы — запроси приложение.\n"
    "3) После приложения — запроси руководство по эксплуатации.\n"
    "4) После получения всех трёх типов материалов выдай таблицу соответствия в двух версиях:\n"
    "   - Версия WORD: таблица в формате, пригодном для вставки в Word (например, Markdown/HTML-таблица).\n"
    "   - Версия PDF: таблица в формате, пригодном для экспорта/печати (например, тот же HTML/таблица).\n\n"
    "Правила:\n"
    "- Не используй вопросительные предложения и знак `?`.\n"
    "- Проси документы/материалы императивно: «Пришли…», «Нужен…».\n"
    "- Если данных пока недостаточно — запрашивай следующий документ по списку.\n"
    "- Для таблицы соответствия используй извлечённые из присланных материалов сущности/разделы.\n"
)


@dataclass(frozen=True)
class Settings:
    bot_token: str
    openai_api_key: str
    openai_model: str
    admin_telegram_ids: list[int]
    gpt_system_prompt: str


def _split_ints(value: str) -> list[int]:
    parts = [p.strip() for p in (value or "").split(",")]
    return [int(p) for p in parts if p]


def load_settings() -> Settings:
    load_dotenv()
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
    openai_model = os.getenv("OPENAI_MODEL", "gpt-5.4").strip()
    admin_ids_raw = os.getenv("ADMIN_TELEGRAM_IDS", "").strip()
    admin_telegram_ids = _split_ints(admin_ids_raw)
    gpt_system_prompt = os.getenv("GPT_SYSTEM_PROMPT", "").strip()

    missing: list[str] = []
    if not bot_token:
        missing.append("BOT_TOKEN")
    if not openai_api_key:
        missing.append("OPENAI_API_KEY")
    if not admin_telegram_ids:
        missing.append("ADMIN_TELEGRAM_IDS")

    if missing:
        raise RuntimeError(f"Missing env vars: {', '.join(missing)}")

    return Settings(
        bot_token=bot_token,
        openai_api_key=openai_api_key,
        openai_model=openai_model,
        admin_telegram_ids=admin_telegram_ids,
        gpt_system_prompt=gpt_system_prompt,
    )


def ensure_store() -> dict:
    if not os.path.exists(STORE_PATH):
        initial_prompt = os.getenv("GPT_SYSTEM_PROMPT", "").strip() or DEFAULT_SYSTEM_PROMPT
        initial_model = os.getenv("OPENAI_MODEL", "").strip() or "gpt-5.4"
        with open(STORE_PATH, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "version": 1,
                    "gpt_system_prompt": initial_prompt,
                    "openai_model": initial_model,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )

    with open(STORE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_store(data: dict) -> None:
    with open(STORE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_admin_kb(*, is_admin: bool) -> ReplyKeyboardMarkup | ReplyKeyboardRemove:
    if not is_admin:
        return ReplyKeyboardRemove()
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="АДМИН")]], resize_keyboard=True)


def admin_inline_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Показать ТЗ", callback_data="admin:show_prompt")],
            [InlineKeyboardButton(text="Изменить ТЗ", callback_data="admin:edit_prompt")],
            [InlineKeyboardButton(text="Изменить модель", callback_data="admin:edit_model")],
        ]
    )


def chunk_text(text: str, limit: int = 3800) -> list[str]:
    if not text:
        return [""]
    if len(text) <= limit:
        return [text]
    return [text[i : i + limit] for i in range(0, len(text), limit)]


class AdminStates(StatesGroup):
    WAIT_PROMPT = State()
    WAIT_MODEL = State()


async def gpt_reply(client: AsyncOpenAI, model: str, system_prompt: str, user_text: str, history: list[dict]) -> str:
    # Simple chat history: last few turns.
    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    messages.extend(history[-10:])
    messages.append({"role": "user", "content": user_text})

    resp = await client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.7,
    )
    return (resp.choices[0].message.content or "").strip()


async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    is_admin = message.from_user.id in SETTINGS.admin_telegram_ids
    await message.answer(
        "Здравствуй, клиент.\n"
        "Пиши сообщение — отвечу через GPT.\n"
        "Если ты админ — нажми `АДМИН`.",
        reply_markup=get_admin_kb(is_admin=is_admin),
        parse_mode=ParseMode.MARKDOWN,
    )


async def on_admin_text(message: Message, state: FSMContext) -> None:
    if message.from_user.id not in SETTINGS.admin_telegram_ids:
        await message.answer("Нет доступа.")
        return
    await state.clear()
    await message.answer("Админ-панель:", reply_markup=admin_inline_kb())


async def on_admin_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.from_user.id not in SETTINGS.admin_telegram_ids:
        await callback.answer("Нет доступа.", show_alert=True)
        return

    store = ensure_store()
    data = callback.data or ""

    if data == "admin:show_prompt":
        prompt = str(store.get("gpt_system_prompt") or DEFAULT_SYSTEM_PROMPT)
        model = str(store.get("openai_model") or SETTINGS.openai_model)
        await callback.message.edit_text(
            f"Текущие значения:\nМодель: `{model}`\n\nТЗ отправлю целиком (частями, если нужно).",
            parse_mode=ParseMode.MARKDOWN,
        )
        for i, chunk in enumerate(chunk_text(prompt), start=1):
            await callback.message.answer(f"ТЗ (часть {i}):\n{chunk}")
        await callback.answer()
        return

    if data == "admin:edit_prompt":
        await state.set_state(AdminStates.WAIT_PROMPT)
        await callback.message.edit_text("Пришли новое ТЗ для GPT (одним сообщением).")
        await callback.answer()
        return

    if data == "admin:edit_model":
        await state.set_state(AdminStates.WAIT_MODEL)
        await callback.message.edit_text(
            "Пришли новое имя модели API (например, `gpt-5.4-mini`).",
            parse_mode=ParseMode.MARKDOWN,
        )
        await callback.answer()
        return

    await callback.answer()


async def on_admin_message(message: Message, state: FSMContext) -> None:
    if message.from_user.id not in SETTINGS.admin_telegram_ids:
        return

    st = await state.get_state()
    if st == AdminStates.WAIT_PROMPT.state:
        text = (message.text or "").strip()
        if not text:
            await message.answer("Пусто. Пришли ТЗ снова.")
            return
        store = ensure_store()
        store["gpt_system_prompt"] = text
        save_store(store)
        await state.clear()
        await message.answer("ТЗ обновлено.", reply_markup=admin_inline_kb())
        return

    if st == AdminStates.WAIT_MODEL.state:
        text = (message.text or "").strip()
        if not text:
            await message.answer("Пусто. Пришли модель снова.")
            return
        store = ensure_store()
        store["openai_model"] = text
        save_store(store)
        await state.clear()
        await message.answer("Модель обновлена.", reply_markup=admin_inline_kb())
        return


async def on_user_message(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return

    if message.text.strip() == "АДМИН":
        return

    # If admin is editing, don't treat messages as user chat.
    st = await state.get_state()
    if st and st.startswith("AdminStates"):
        return

    store = ensure_store()
    model = str(store.get("openai_model") or SETTINGS.openai_model)
    system_prompt = str(store.get("gpt_system_prompt") or DEFAULT_SYSTEM_PROMPT)

    data = await state.get_data()
    history: list[dict] = list(data.get("history") or [])
    user_text = message.text.strip()

    if not user_text:
        return

    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")

    try:
        reply = await gpt_reply(OPENAI, model, system_prompt, user_text, history)
    except Exception:
        log.exception("GPT user message error")
        await message.answer("Не вывезло запрос. Попробуй ещё раз или коротко переформулируй.")
        return

    if not reply:
        await message.answer("Пусто вышло. Попробуй ещё раз или перефразируй.")
        return

    await message.answer(reply)

    # Save history (for context)
    history.append({"role": "user", "content": user_text})
    history.append({"role": "assistant", "content": reply})
    await state.update_data(history=history[-20:])


SETTINGS = load_settings()
STORE = ensure_store()

OPENAI = AsyncOpenAI(api_key=SETTINGS.openai_api_key)


async def main() -> None:
    bot = Bot(token=SETTINGS.bot_token)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    dp.message.register(cmd_start, Command("start"))
    dp.message.register(on_admin_text, F.text == "АДМИН")

    dp.callback_query.register(on_admin_callback, F.data.startswith("admin:"))
    dp.message.register(on_admin_message, AdminStates.WAIT_PROMPT)
    dp.message.register(on_admin_message, AdminStates.WAIT_MODEL)

    dp.message.register(on_user_message)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

