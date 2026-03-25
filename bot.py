import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any

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
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv
from openai import AsyncOpenAI

from config import get_settings
from prompts_store import (
    PromptsStore,
    get_chat_system_prompt,
    get_openai_model,
    get_resume_system_prompt,
    load_store,
    update_field,
)


logging.basicConfig(level=logging.INFO)
log = logging.getLogger("consultant_bot")


PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
STORE_PATH = os.path.join(PROJECT_DIR, "prompts_store.json")


class UserFlow(StatesGroup):
    GET_NAME = State()
    GET_AGE = State()
    GET_EXPERIENCE = State()
    GET_GOAL = State()
    GET_PHONE = State()
    GET_TG = State()
    CHAT = State()
    SUPPORT = State()


class AdminFlow(StatesGroup):
    WAIT_CHAT_PROMPT = State()
    WAIT_RESUME_PROMPT = State()
    WAIT_MODEL = State()


def is_admin(user_id: int) -> bool:
    return user_id in SETTINGS.admin_telegram_ids


def main_reply_keyboard(*, is_admin_user: bool) -> ReplyKeyboardMarkup:
    buttons: list[KeyboardButton] = [KeyboardButton(text="HELLS BELLS")]
    if is_admin_user:
        buttons.append(KeyboardButton(text="АДМИН"))
    return ReplyKeyboardMarkup(keyboard=[buttons], resize_keyboard=True)


def admin_inline_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Изменить ТЗ GPT-чата", callback_data="admin:set_chat_prompt")
    kb.button(text="Изменить ТЗ GPT-резюме", callback_data="admin:set_resume_prompt")
    kb.button(text="Изменить модель API", callback_data="admin:set_model")
    kb.button(text="Показать текущие значения", callback_data="admin:show_current")
    kb.adjust(1)
    return kb.as_markup()


def poehaly_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="ПОЕХАЛИ", callback_data="go:poehaly")]]
    )


async def ask_next(message: Message, state: FSMContext, user_flow: State, text: str) -> None:
    await state.set_state(user_flow)
    await message.answer(text)


async def gpt_chat_reply(client: AsyncOpenAI, model: str, system_prompt: str, history: list[dict[str, str]]) -> str:
    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    # Keep last N turns to limit tokens
    for item in history[-16:]:
        messages.append({"role": item["role"], "content": item["content"]})

    resp = await client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.7,
    )
    return (resp.choices[0].message.content or "").strip()


async def gpt_resume(client: AsyncOpenAI, model: str, system_prompt: str, payload: str) -> str:
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": payload},
    ]
    resp = await client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.2,
    )
    return (resp.choices[0].message.content or "").strip()


SETTINGS = get_settings()
STORE = load_store(STORE_PATH)


async def on_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    user_admin = is_admin(message.from_user.id)
    await message.answer(
        "Ну что, клиент. Нажмешь кнопку — начнем разговор.\n"
        "Я там не для красоты, а для пользы.",
        reply_markup=main_reply_keyboard(is_admin_user=user_admin),
    )


async def handle_hells_bells(message: Message, state: FSMContext) -> None:
    # Reset state
    await state.clear()
    await ask_next(
        message,
        state,
        UserFlow.GET_NAME,
        "ХЕЛЛС БЕЛЛС.\nКак тебя зовут, клиент? Не тяни резину.",
    )


async def handle_admin_text(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        await message.answer("Админкой тут не пахнет. Давай по курсу: `HELLS BELLS`.")
        return
    await state.clear()
    await message.answer("Админ-панель. Чего поменяем?", reply_markup=admin_inline_keyboard())


async def handle_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if not name:
        await message.answer("Давай нормально: имя в студию.")
        return
    await state.update_data(name=name)
    await ask_next(message, state, UserFlow.GET_AGE, "Сколько тебе лет? Только без сюрпризов.")


def parse_age(text: str) -> int | None:
    try:
        age = int(text.strip())
    except Exception:
        return None
    if 10 <= age <= 100:
        return age
    return None


async def handle_age(message: Message, state: FSMContext) -> None:
    age = parse_age(message.text or "")
    if age is None:
        await message.answer("Возраст между 10 и 100. Повтори, а то я уже старый бухгалтер.")
        return
    await state.update_data(age=age)
    await ask_next(
        message,
        state,
        UserFlow.GET_EXPERIENCE,
        "Есть опыт с нейросетями? Сколько и что делал/а. По-честному.",
    )


async def handle_experience(message: Message, state: FSMContext) -> None:
    experience = (message.text or "").strip()
    if not experience:
        await message.answer("Пиши, не стесняйся. Хоть пару слов — и поехали.")
        return
    await state.update_data(experience=experience)
    await ask_next(message, state, UserFlow.GET_GOAL, "Чему хочешь научиться в первую очередь? Внятно.")


async def handle_goal(message: Message, state: FSMContext) -> None:
    goal = (message.text or "").strip()
    if not goal:
        await message.answer("Цель нужна. Курс — не сонник. Что именно хочешь научиться делать?")
        return
    await state.update_data(goal=goal)
    await ask_next(message, state, UserFlow.GET_PHONE, "Оставь телефон для связи (можно WhatsApp).")


async def handle_phone(message: Message, state: FSMContext) -> None:
    phone = (message.text or "").strip()
    if not phone or len(phone) < 6:
        await message.answer("Телефон выглядит коротким. Присылай номер ещё раз.")
        return
    await state.update_data(phone=phone)
    await ask_next(message, state, UserFlow.GET_TG, "И Telegram-аккаунт: пришли `@username`. Ну давай.")


async def handle_tg(message: Message, state: FSMContext, openai: AsyncOpenAI) -> None:
    try:
        tg = (message.text or "").strip()
        log.info("GET_TG handler: user_id=%s tg=%r", message.from_user.id if message.from_user else None, tg)

        if not tg:
            await message.answer("Ну так как тебя искать? Пришли `@username`.")
            return

        await state.update_data(tg_account=tg)

        # Initialize chat history for further chat/resume generation.
        await state.update_data(chat_history=[])
        await state.update_data(hint_question_count=0)

        # Резюме показываем только после нажатия "ПОЕХАЛИ" (по вашему ТЗ).
        await state.set_state(UserFlow.CHAT)

        await message.answer(
            "Отлично. Теперь можешь общаться: расскажи, что уже пробовал/а, что не получается, какие задачи.",
            reply_markup=poehaly_inline_keyboard(),
        )
    except Exception:
        log.exception("GET_TG handler crashed")
        await message.answer("Не вывезло этот шаг. Напиши `HELLS BELLS`, начнем заново.")
        await state.clear()


async def on_admin_callback(callback: CallbackQuery, state: FSMContext) -> None:
    data = callback.data or ""
    if not callback.from_user:
        return
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    if data == "admin:set_chat_prompt":
        await state.set_state(AdminFlow.WAIT_CHAT_PROMPT)
        await callback.message.edit_text("Пришли новое ТЗ для GPT-чата (одним сообщением).")
        await callback.answer()
        return
    if data == "admin:set_resume_prompt":
        await state.set_state(AdminFlow.WAIT_RESUME_PROMPT)
        await callback.message.edit_text("Пришли новое ТЗ для GPT-резюме (одним сообщением).")
        await callback.answer()
        return
    if data == "admin:set_model":
        await state.set_state(AdminFlow.WAIT_MODEL)
        await callback.message.edit_text("Пришли точное имя модели API (например, `gpt-5.4-mini`).")
        await callback.answer()
        return
    if data == "admin:show_current":
        chat_prompt = get_chat_system_prompt(STORE)
        resume_prompt = get_resume_system_prompt(STORE)
        model = get_openai_model(STORE)
        await callback.message.edit_text(
            f"Текущие значения:\n\n"
            f"Модель: `{model}`\n\n"
            f"ТЗ GPT-чата (коротко):\n{chat_prompt[:500]}{'...' if len(chat_prompt) > 500 else ''}\n\n"
            f"ТЗ GPT-резюме (коротко):\n{resume_prompt[:500]}{'...' if len(resume_prompt) > 500 else ''}",
            parse_mode=ParseMode.MARKDOWN,
        )
        await callback.answer()
        return

    await callback.answer()


async def on_admin_message(message: Message, state: FSMContext) -> None:
    if not callback_safe_admin_id(message.from_user.id):
        return

    st = await state.get_state()
    if st == AdminFlow.WAIT_CHAT_PROMPT.state:
        text = (message.text or "").strip()
        if not text:
            await message.answer("Пусто. Пришли текст ТЗ.")
            return
        update_field(STORE, "gpt_chat_system_prompt", text)
        await state.clear()
        await message.answer("ТЗ для GPT-чата обновлено.", reply_markup=admin_inline_keyboard())
        return

    if st == AdminFlow.WAIT_RESUME_PROMPT.state:
        text = (message.text or "").strip()
        if not text:
            await message.answer("Пусто. Пришли текст ТЗ.")
            return
        update_field(STORE, "gpt_resume_system_prompt", text)
        await state.clear()
        await message.answer("ТЗ для GPT-резюме обновлено.", reply_markup=admin_inline_keyboard())
        return

    if st == AdminFlow.WAIT_MODEL.state:
        text = (message.text or "").strip()
        if not text:
            await message.answer("Пусто. Пришли имя модели.")
            return
        update_field(STORE, "openai_model", text)
        await state.clear()
        await message.answer("Модель API обновлена.", reply_markup=admin_inline_keyboard())
        return

    # No admin state -> ignore


def callback_safe_admin_id(user_id: int) -> bool:
    return is_admin(user_id)


async def on_chat_message(message: Message, state: FSMContext, openai: AsyncOpenAI) -> None:
    text = (message.text or "").strip()
    if not text:
        return

    data = await state.get_data()
    chat_history: list[dict[str, str]] = list(data.get("chat_history") or [])
    q_count = int(data.get("hint_question_count") or 0)

    # Heuristic: treat "navigation"/clarifying questions as those with a question mark
    # or common interrogative starters.
    lower = text.lower()
    is_hint_question = bool(
        "?" in text
        or re.match(r"^(как|почему|что|сколько|где|какой|какие|когда|зачем)\b", lower)
    )
    if is_hint_question:
        q_count += 1

    # After 3 hint questions, escalate to support flow.
    if is_hint_question and q_count > 3:
        await state.update_data(hint_question_count=q_count)
        await state.set_state(UserFlow.SUPPORT)
        await message.answer(
            "Слышу много уточнений, клиент. Дальше так мы оба сдохнем от вопросов.\n"
            "Пойдем на нормальный канал: к поддержке/админу, который разрулит по-человечески.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="ПЕРЕВЕСТИ К АДМИНУ", callback_data="support:to_admin")]
                ]
            ),
        )
        return

    # GPT reply
    model = get_openai_model(STORE)
    system_prompt = get_chat_system_prompt(STORE)
    # Append user message to history for the next reply
    chat_history.append({"role": "user", "content": text})

    try:
        # Keep UX snappy: show typing action, but don't send extra bot messages.
        await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
        reply = await gpt_chat_reply(openai, model=model, system_prompt=system_prompt, history=chat_history)
    except Exception as e:
        log.exception("GPT chat error")
        await message.answer("Не пошло. Попробуй чуть позже или коротко переформулируй.")
        return

    await message.answer(reply or "Ок, понял.")

    chat_history.append({"role": "assistant", "content": reply})
    await state.update_data(chat_history=chat_history, hint_question_count=q_count)


async def on_poehaly(callback: CallbackQuery, state: FSMContext, openai: AsyncOpenAI) -> None:
    if not callback.from_user:
        return

    data = await state.get_data()
    required_keys = ["name", "age", "experience", "goal", "phone", "tg_account", "chat_history"]
    missing = [k for k in required_keys if k not in data]
    if missing:
        await callback.answer("Анкета неполная. Дополни данные.", show_alert=True)
        return

    name = str(data["name"])
    age = data["age"]
    experience = str(data["experience"])
    goal = str(data["goal"])
    phone = str(data["phone"])
    tg_account = str(data["tg_account"])
    chat_history: list[dict[str, str]] = list(data.get("chat_history") or [])

    # Build payload for resume model
    # Only use user's messages to reduce prompt size and avoid context-limit errors.
    user_msgs: list[str] = []
    for item in chat_history[-30:]:
        if (item.get("role") or "") != "user":
            continue
        content = (item.get("content") or "").strip()
        if not content:
            continue
        user_msgs.append(content)

    # Keep last few messages and cap total length.
    user_msgs = user_msgs[-8:]
    transcript = "\n".join(user_msgs)
    if len(transcript) > 2000:
        transcript = transcript[-2000:]
    if not transcript:
        transcript = "(пусто)"

    payload = (
        f"Имя: {name}\n"
        f"Возраст: {age}\n"
        f"Опыт: {experience}\n"
        f"Цель: {goal}\n"
        f"Телефон: {phone}\n"
        f"Telegram: {tg_account}\n\n"
        f"Переписка (для доп. заметок):\n{transcript}\n"
    )

    model = get_openai_model(STORE)
    resume_system_prompt = get_resume_system_prompt(STORE)

    await callback.answer()
    msg = await callback.message.answer("Оформляю резюме…")
    try:
        # Retry once for transient API/network issues.
        try:
            await callback.bot.send_chat_action(chat_id=callback.message.chat.id, action="typing")
            resume_text = await gpt_resume(
                openai,
                model=model,
                system_prompt=resume_system_prompt,
                payload=payload,
            )
        except Exception as first_err:
            log.exception("GPT resume error (first attempt)")
            await asyncio.sleep(1.0)
            resume_text = await gpt_resume(
                openai,
                model=model,
                system_prompt=resume_system_prompt,
                payload=payload,
            )
    except Exception as e:
        log.exception("GPT resume error (final)")
        await msg.edit_text(
            "Не смог оформить резюме. Попробуй ещё раз, а если повторится — напиши, какая модель у тебя в админке (или проверь `OPENAI_MODEL`)."
        )
        return

    # Send resume back to the user in this chat first.
    try:
        await msg.edit_text(
            f"Резюме по твоей анкете и переписке. Держи:\n\n{resume_text}",
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception:
        # If markdown fails for some reason, fall back to plain text.
        await msg.edit_text("Резюме оформлено. (Не смог отформатировать ответ.)")

    # Send to channel
    try:
        await callback.bot.send_message(
            chat_id=SETTINGS.channel_id,
            text=resume_text,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
        )
    except Exception:
        log.exception("Telegram send_message error")
        await msg.edit_text("Резюме сделал, но не смог отправить в канал. Проверь `CHANNEL_ID` и доступ бота.")
        return

    await msg.edit_text("Готово. Резюме отправлено менеджеру в канал.")
    await state.clear()


async def on_support_to_admin(callback: CallbackQuery, state: FSMContext, openai: AsyncOpenAI) -> None:
    if not callback.from_user:
        return

    data = await state.get_data()
    required_keys = ["name", "age", "experience", "goal", "phone", "tg_account"]
    missing = [k for k in required_keys if k not in data]
    if missing:
        await callback.answer("Анкета не заполнена полностью. Заполни её.", show_alert=True)
        return

    # Build payload similar to POЕХАЛИ.
    name = str(data["name"])
    age = data["age"]
    experience = str(data["experience"])
    goal = str(data["goal"])
    phone = str(data["phone"])
    tg_account = str(data["tg_account"])
    chat_history: list[dict[str, str]] = list(data.get("chat_history") or [])
    last_user_messages = []
    for item in chat_history[-10:]:
        if (item.get("role") or "") == "user":
            content = (item.get("content") or "").strip()
            if content:
                last_user_messages.append(content)
    transcript = "\n".join(last_user_messages) if last_user_messages else "(пока без диалога)"

    payload = (
        f"Заявка на поддержку/админа.\n\n"
        f"Имя: {name}\n"
        f"Возраст: {age}\n"
        f"Опыт: {experience}\n"
        f"Цель: {goal}\n"
        f"Телефон: {phone}\n"
        f"Telegram: {tg_account}\n\n"
        f"Последние вопросы пользователя:\n{transcript}\n"
    )

    await callback.answer()
    # Notify all admins (so you don't have to manage who is online).
    for admin_id in SETTINGS.admin_telegram_ids:
        try:
            await callback.bot.send_message(chat_id=admin_id, text=payload)
        except Exception:
            log.exception("Failed to notify admin")

    await state.clear()
    await callback.message.answer(
        "Отправил заявку администратору. Он там не спит — ответит по нормальному.",
        reply_markup=main_reply_keyboard(is_admin_user=False),
    )


async def main() -> None:
    load_dotenv()
    bot = Bot(token=SETTINGS.bot_token)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    openai = AsyncOpenAI(api_key=SETTINGS.openai_api_key)

    dp.message.register(on_start, Command("start"))
    dp.message.register(handle_admin_text, F.text == "АДМИН")
    dp.message.register(handle_hells_bells, F.text == "HELLS BELLS")

    # User flow
    dp.message.register(handle_name, UserFlow.GET_NAME)
    dp.message.register(handle_age, UserFlow.GET_AGE)
    dp.message.register(handle_experience, UserFlow.GET_EXPERIENCE)
    dp.message.register(handle_goal, UserFlow.GET_GOAL)
    dp.message.register(handle_phone, UserFlow.GET_PHONE)
    async def tg_handler(message: Message, state: FSMContext) -> None:
        await handle_tg(message, state, openai)

    dp.message.register(tg_handler, UserFlow.GET_TG)

    # Admin flow input
    dp.message.register(on_admin_message, AdminFlow.WAIT_CHAT_PROMPT)
    dp.message.register(on_admin_message, AdminFlow.WAIT_RESUME_PROMPT)
    dp.message.register(on_admin_message, AdminFlow.WAIT_MODEL)

    # Chat mode
    async def chat_handler(message: Message, state: FSMContext) -> None:
        await on_chat_message(message, state, openai)

    dp.message.register(chat_handler, UserFlow.CHAT)

    # Support escalation
    async def support_to_admin_handler(callback: CallbackQuery, state: FSMContext) -> None:
        await on_support_to_admin(callback, state, openai)

    dp.callback_query.register(support_to_admin_handler, F.data == "support:to_admin")

    # Poehaly button
    async def poehaly_handler(callback: CallbackQuery, state: FSMContext) -> None:
        await on_poehaly(callback, state, openai)

    dp.callback_query.register(poehaly_handler, F.data == "go:poehaly")

    # Admin callbacks
    dp.callback_query.register(on_admin_callback, F.data.startswith("admin:"))

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

