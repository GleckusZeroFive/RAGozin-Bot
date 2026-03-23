"""Калибровка LLM-модели при старте бота.

Запускает 2 быстрых теста для определения профиля модели:
1. Следование негативным инструкциям ("НЕ делай X")
2. Следование формату (HTML vs Markdown)

По результатам выбирается вариант промпта: обычный или strict.
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ModelProfile:
    """Профиль LLM-модели, определённый при калибровке."""
    follows_negative_instructions: bool = False
    follows_format_instructions: bool = False
    needs_examples: bool = True
    model_name: str = "unknown"


_profile: ModelProfile | None = None


def get_model_profile() -> ModelProfile:
    """Получить профиль модели (синглтон). Если калибровка не прошла — strict defaults."""
    if _profile is None:
        return ModelProfile()  # strict defaults: needs_examples=True, follows_negative=False
    return _profile


async def run_calibration() -> ModelProfile:
    """Запустить калибровку модели (2 быстрых LLM-запроса)."""
    global _profile
    from app.llm.factory import get_llm_provider
    provider = get_llm_provider()

    model_name = provider.model
    follows_negative = await _test_negative_instructions(provider)
    follows_format = await _test_format_compliance(provider)

    _profile = ModelProfile(
        follows_negative_instructions=follows_negative,
        follows_format_instructions=follows_format,
        needs_examples=not (follows_negative and follows_format),
        model_name=model_name,
    )

    logger.info(
        "Калибровка завершена: model=%s, negative=%s, format=%s, needs_examples=%s",
        model_name, follows_negative, follows_format, _profile.needs_examples,
    )
    return _profile


async def _test_negative_instructions(provider) -> bool:
    """Тест: следует ли модель негативным инструкциям."""
    try:
        messages = [
            {
                "role": "system",
                "content": (
                    "Ответь на вопрос по контексту. "
                    "КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО упоминать источники, файлы, номера разделов. "
                    "Просто ответь на вопрос."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Контекст: Источник: hr_policy.txt, Раздел 2.1. "
                    "Ежегодный отпуск — 28 дней.\n\n"
                    "Вопрос: Какой срок отпуска?"
                ),
            },
        ]
        response = await provider.generate(messages, max_tokens=100)
        text = response.lower()
        has_source = any(
            w in text
            for w in ["источник", "раздел", "hr_policy", ".txt", ".pdf"]
        )
        return not has_source
    except Exception:
        logger.warning("Calibration test 1 failed", exc_info=True)
        return False


async def _test_format_compliance(provider) -> bool:
    """Тест: следует ли модель инструкции по формату."""
    try:
        messages = [
            {
                "role": "system",
                "content": (
                    "Отвечай ТОЛЬКО в HTML-формате для Telegram. "
                    "Жирный: <b>текст</b>. "
                    "НЕ используй Markdown (**, *, #). Никакого Markdown!"
                ),
            },
            {
                "role": "user",
                "content": "Перечисли 3 фрукта.",
            },
        ]
        response = await provider.generate(messages, max_tokens=100)
        has_markdown = "**" in response or response.strip().startswith("#")
        has_html = "<b>" in response
        return has_html and not has_markdown
    except Exception:
        logger.warning("Calibration test 2 failed", exc_info=True)
        return False
