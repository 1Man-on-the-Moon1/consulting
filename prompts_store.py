import json
import os
from dataclasses import dataclass
from typing import Any


DEFAULT_PROMPTS = {
    "gpt_chat_system_prompt": (
        "Ты — хамоватая, но не грубая продавщица советского магазина/общепита. "
        "Отвечай по делу, с короткими фразами, лёгкой дерзостью и подбадриванием. "
        "Твоя задача — помочь клиенту понять, как лучше обучаться нейросетям и подготовить информацию "
        "для записи в курс. "
        "Не проси лишние персональные данные. "
        "Не задавай пользователю вопросов с вопросительным знаком. Если нужно уточнение — перечисли "
        "варианты того, что пользователь может написать дальше (в формате инструкций), без вопросов. "
        "Отвечай по текущему сообщению и давай короткие практичные рекомендации."
    ),
    "gpt_resume_system_prompt": (
        "Ты — редактор резюме для обучения нейросетям. "
        "Собери 'резюме клиента' на русском на основе входных данных пользователя и переписки. "
        "Структура ответа: "
        "1) Краткое резюме (2-3 предложения) "
        "2) Анкета: Имя, Возраст, Опыт, Цель обучения "
        "3) Контакты: телефон, Telegram-аккаунт "
        "4) Сильные стороны/что уже умеет (если видно из чата) "
        "5) Рекомендация по курсу (1-2 конкретных пункта, без обещаний 'гарантированно') "
        "6) Доп. заметки из чата "
        "Пиши чётко, без воды. Не добавляй выдуманных фактов."
    ),
    "openai_model": "gpt-5.4-mini",
}

NO_ASK_QUESTIONS_SUFFIX = (
    "\n\n"
    "ЖЕСТКОЕ ПРАВИЛО: не задавай пользователю вопросы и не используй вопросительные предложения. "
    "Если не хватает данных — предложи варианты для продолжения (списком команд/фраз), "
    "но не спрашивай. Действуй как продавщица/консультант: коротко, по делу."
)


@dataclass
class PromptsStore:
    path: str
    data: dict[str, Any]


def load_store(path: str) -> PromptsStore:
    if not os.path.exists(path):
        store = {"version": 1, **DEFAULT_PROMPTS}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(store, f, ensure_ascii=False, indent=2)
        return PromptsStore(path=path, data=store)

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Backward-compatible defaults
    changed = False
    for k, v in DEFAULT_PROMPTS.items():
        if k not in data:
            data[k] = v
            changed = True

    if changed:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    return PromptsStore(path=path, data=data)


def get_chat_system_prompt(store: PromptsStore) -> str:
    base = str(store.data.get("gpt_chat_system_prompt") or "")
    # Backward-safe: don't override custom prompt, just ensure the anti-question directive exists.
    if "ЖЕСТКОЕ ПРАВИЛО" not in base and "не задавай" not in base.lower():
        return base + NO_ASK_QUESTIONS_SUFFIX
    return base


def get_resume_system_prompt(store: PromptsStore) -> str:
    return str(store.data.get("gpt_resume_system_prompt") or "")


def get_openai_model(store: PromptsStore) -> str:
    model = store.data.get("openai_model") or DEFAULT_PROMPTS["openai_model"]
    return str(model)


def update_field(store: PromptsStore, field: str, value: str) -> None:
    store.data[field] = value
    with open(store.path, "w", encoding="utf-8") as f:
        json.dump(store.data, f, ensure_ascii=False, indent=2)

