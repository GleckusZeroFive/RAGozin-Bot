"""Управление контекстом диалога (follow-up вопросы)."""

import logging
import time
from dataclasses import dataclass, field

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class QAPair:
    """Одна пара вопрос-ответ в истории диалога."""
    question: str
    answer: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class ConversationContext:
    """Контекст диалога для одного пользователя."""
    history: list[QAPair] = field(default_factory=list)
    last_activity: float = field(default_factory=time.time)

    def is_expired(self) -> bool:
        ttl_seconds = settings.conversation_ttl_minutes * 60
        return (time.time() - self.last_activity) > ttl_seconds

    def add_pair(self, question: str, answer: str) -> None:
        """Добавить пару Q&A и обрезать историю до max_pairs."""
        self.history.append(QAPair(question=question, answer=answer))
        self.last_activity = time.time()
        max_pairs = settings.conversation_max_pairs
        if len(self.history) > max_pairs:
            self.history = self.history[-max_pairs:]

    def get_history_messages(self) -> list[dict[str, str]]:
        """Возвращает историю в формате OpenAI messages."""
        messages = []
        for pair in self.history:
            messages.append({"role": "user", "content": pair.question})
            messages.append({"role": "assistant", "content": pair.answer})
        return messages

    def clear(self) -> None:
        self.history.clear()
        self.last_activity = time.time()


# Глобальное хранилище контекстов: telegram_id → ConversationContext
_conversations: dict[int, ConversationContext] = {}


def get_context(telegram_id: int) -> ConversationContext:
    """Получить или создать контекст диалога для пользователя."""
    ctx = _conversations.get(telegram_id)
    if ctx is None or ctx.is_expired():
        ctx = ConversationContext()
        _conversations[telegram_id] = ctx
    return ctx


def clear_context(telegram_id: int) -> None:
    """Принудительно очистить контекст (команда /new)."""
    _conversations.pop(telegram_id, None)


def cleanup_expired() -> int:
    """Удаляет истёкшие контексты. Возвращает количество удалённых."""
    expired_ids = [
        tid for tid, ctx in _conversations.items() if ctx.is_expired()
    ]
    for tid in expired_ids:
        del _conversations[tid]
    if expired_ids:
        logger.info("Очищено %d истёкших контекстов диалога", len(expired_ids))
    return len(expired_ids)
