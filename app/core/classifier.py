"""LLM-классификатор намерений пользователя (rag / chat / followup).

Chat by default: при сомнении или ошибке возвращает "chat".
"""

import logging
from typing import Literal

from app.config import settings
from app.llm.factory import get_llm_provider
from app.presets import get_preset

logger = logging.getLogger(__name__)

Intent = Literal["rag", "chat", "followup"]

_CLASSIFIER_SYSTEM = """\
Ты — классификатор сообщений бота-ассистента по документам.
Определи, нужен ли поиск по документам для ответа на последнее сообщение.

Документы пользователя:
{doc_list}

Поиск по законодательству РФ: {law_status}

Типы:
• rag — пользователь задаёт фактический вопрос, ответ на который \
может быть в его документах или в базе законодательства. \
Любой конкретный вопрос по тематике загруженных документов — это rag. \
Примеры: «найди», «что написано», «расскажи про [тема]», \
конкретные вопросы о фактах, правилах, процессах, суммах, сроках.
• chat — приветствия, вопросы о боте и его возможностях, \
светская беседа, вопросы об аккаунте/тарифе/лимитах, \
мета-вопросы об управлении документами («стоит ли загрузить», «как обновить документ»).
• followup — уточнение к предыдущему ответу бота \
(просьба объяснить, развить мысль, рассказать подробнее, пояснить почему).

ВАЖНО: если у пользователя есть документы и вопрос МОЖЕТ быть связан \
с их тематикой — выбирай rag. ПРИ СОМНЕНИИ И НАЛИЧИИ ДОКУМЕНТОВ — ВЫБИРАЙ rag.
Упоминание слова «документ» НЕ обязательно для rag. \
«Стоит ли загрузить документы?» — chat. «Какие комиссии?» — rag (если есть документы по теме).

Отвечай ОДНИМ словом: rag, chat или followup. Без пояснений."""

_VALID_INTENTS: frozenset[str] = frozenset({"rag", "chat", "followup"})


def _format_history_snippet(history: list[dict[str, str]]) -> str:
    """Форматировать последние 2 Q&A пары для промпта классификатора."""
    if not history:
        return "(первое сообщение)"
    pairs: list[str] = []
    # history — плоский список [user, assistant, user, assistant, ...]
    # Берём последние 4 сообщения = 2 пары
    recent = history[-4:]
    i = 0
    while i + 1 < len(recent):
        u = recent[i]["content"]
        a = recent[i + 1]["content"]
        # Обрезаем длинные ответы бота
        a_short = a[:300] + "..." if len(a) > 300 else a
        pairs.append(f"Пользователь: {u}\nБот: {a_short}")
        i += 2
    return "\n\n".join(pairs) if pairs else "(первое сообщение)"


async def classify_intent(
    question: str,
    history: list[dict[str, str]],
    doc_names: list[str] | None = None,
    law_search_enabled: bool = False,
) -> Intent:
    """Классифицировать намерение пользователя через LLM.

    Returns:
        "rag"      — нужен поиск по документам
        "chat"     — разговорный режим, без поиска
        "followup" — уточнение к предыдущему ответу бота

    При ошибке LLM возвращает "chat" (безопасное умолчание).
    """
    try:
        provider = get_llm_provider()
        history_text = _format_history_snippet(history)

        doc_list = (
            "\n".join(f"• {name}" for name in doc_names)
            if doc_names
            else "(нет документов)"
        )
        law_status = "включён" if law_search_enabled else "выключен"
        preset = get_preset()
        classifier_template = preset.prompts.classifier
        # Corporate presets may not have {law_status} placeholder
        try:
            system = classifier_template.format(
                doc_list=doc_list, law_status=law_status,
            )
        except KeyError:
            system = classifier_template.format(doc_list=doc_list)

        user_content = (
            f"История диалога:\n{history_text}\n\n"
            f"Текущее сообщение пользователя: {question}"
        )

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ]

        raw = await provider.generate(
            messages,
            temperature=settings.classifier_temperature,
            max_tokens=settings.classifier_max_tokens,
            model=settings.classifier_model,
        )

        logger.info("Классификатор raw: %r для вопроса: %.80s", raw, question)
        intent = raw.strip().lower().rstrip(".,!?;:")
        if intent in _VALID_INTENTS:
            logger.info("Классификатор: '%s' → %s", question[:80], intent)
            return intent  # type: ignore[return-value]

        logger.warning(
            "Классификатор вернул неизвестный интент '%s', дефолт: chat", raw,
        )
        return "chat"

    except Exception:
        logger.warning("Ошибка классификатора интентов, дефолт: chat", exc_info=True)
        return "chat"
