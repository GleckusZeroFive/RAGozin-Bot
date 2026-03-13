import logging
from collections.abc import AsyncGenerator
from typing import Any

from app.bot.commands import COMMANDS_SHORT, format_commands_for_prompt
from app.config import settings
from app.llm.factory import get_llm_provider

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Ты — ассистент по документам и российскому законодательству. \
Отвечай на вопросы пользователя СТРОГО на основе предоставленного контекста.

Контекст может включать:
• Загруженные пользователем документы
• Нормативно-правовые акты РФ из базы законодательства

Правила:
1. Если ответ есть в контексте — отвечай на его основе.
2. Если ответа нет — честно скажи: "Информации по этому вопросу не найдено."
3. Не придумывай информацию.
4. Отвечай на том языке, на котором задан вопрос.
5. Будь лаконичен, но информативен.
6. Форматирование — используй HTML-теги для Telegram:
   - Жирный: <b>текст</b>
   - Курсив: <i>текст</i>
   - Списки: символ • вместо дефиса
   - НЕ используй Markdown (**, *, #, ```)
   - НЕ используй <br> — для переноса строки используй обычный перенос
7. НЕ дублируй источники в ответе — список источников добавляется автоматически.
8. Если пользователь задаёт уточняющий вопрос (например, "А что ещё?", "Расскажи подробнее"), \
учитывай предыдущие вопросы и ответы из диалога.
9. При ссылке на правовые акты указывай их тип, номер и дату.
10. Если предлагаешь команду бота — используй только: """ + COMMANDS_SHORT + """.

Контекст из документов:
{context}
"""

FOLLOWUP_PROMPT = """Ты — дружелюбный ассистент по документам и российскому законодательству.

Пользователь задаёт уточняющий вопрос к твоему предыдущему ответу.

Правила:
1. Отвечай на основе истории диалога — предыдущие ответы содержат нужную информацию.
2. Рассуждай на основе данных из истории. Не добавляй конкретные числа, факты или условия, \
которых нет в предыдущих ответах ассистента.
3. Если для ответа не хватает информации из истории — скажи об этом кратко \
и предложи задать вопрос напрямую (не полагайся на общие знания).
4. Отвечай на том языке, на котором задан вопрос.
5. Будь лаконичен.
6. Форматирование — используй HTML-теги для Telegram:
   - Жирный: <b>текст</b>
   - Курсив: <i>текст</i>
   - Списки: символ • вместо дефиса
   - НЕ используй Markdown (**, *, #, ```)
   - НЕ используй <br> — для переноса строки используй обычный перенос
"""

CHAT_PROMPT = """Ты — RAGozin, дружелюбный ассистент. Ты помогаешь пользователям работать с документами: \
загружать, индексировать и отвечать на вопросы по их содержимому. \
Также умеешь искать по базе российского законодательства.

Текущее состояние пользователя:
{user_state}

Доступные команды бота:
""" + format_commands_for_prompt() + """

Правила:
1. Общайся естественно и дружелюбно. Ты — собеседник, не просто поисковик.
2. Если пользователь спрашивает что ты умеешь или как работаешь — расскажи о своих возможностях: \
поиск по загруженным документам (PDF, DOCX, TXT, MD), поиск по законодательству РФ (/law), \
голосовые сообщения, уточняющие вопросы с учётом контекста диалога.
3. Если пользователь спрашивает о документах, тарифе, лимитах — \
отвечай на основе «Текущее состояние пользователя» выше. Используй реальные данные.
4. Если пользователь хочет управлять документами (загрузить, удалить, обновить) — \
подскажи соответствующую команду из списка выше.
5. Если пользователь задаёт вопрос по теме, ответ на который может быть в его документах — \
предложи задать этот вопрос, и ты поищешь в документах.
6. НЕ упоминай команды, которых нет в списке выше.
7. Отвечай на том языке, на котором задан вопрос.
8. Будь лаконичен.
9. Форматирование — HTML-теги для Telegram:
   - Жирный: <b>текст</b>
   - Курсив: <i>текст</i>
   - Списки: символ • вместо дефиса
   - НЕ используй Markdown (**, *, #, ```)
   - НЕ используй <br> — для переноса строки используй обычный перенос
"""


class ResponseGenerator:
    def __init__(self) -> None:
        self.provider = get_llm_provider()

    def _trim_history(
        self,
        conversation_history: list[dict[str, str]],
        system_chars: int,
        question_chars: int,
    ) -> list[dict[str, str]] | None:
        """Обрезать историю, если суммарный размер превышает бюджет."""
        max_chars = settings.conversation_max_context_chars
        budget = max_chars - system_chars - question_chars
        if budget <= 0:
            return None

        history_chars = sum(len(m["content"]) for m in conversation_history)
        if history_chars <= budget:
            return conversation_history

        # Убираем старые пары (по 2 сообщения: user + assistant), оставляя свежие
        trimmed: list[dict[str, str]] = []
        used = 0
        for msg in reversed(conversation_history):
            msg_len = len(msg["content"])
            if used + msg_len > budget:
                break
            trimmed.insert(0, msg)
            used += msg_len

        # История должна начинаться с user, не с assistant
        if trimmed and trimmed[0]["role"] == "assistant":
            trimmed = trimmed[1:]

        return trimmed if trimmed else None

    def _build_messages(
        self,
        question: str,
        context_chunks: list[dict],
        conversation_history: list[dict[str, str]] | None = None,
        user_state: str | None = None,
        mode: str = "rag",
    ) -> list[dict[str, Any]]:
        """Собрать messages для LLM: system + history + question."""
        if mode == "followup":
            system_content = FOLLOWUP_PROMPT
        elif mode == "chat":
            # Chat mode: если есть история диалога — скорее всего уточнение (follow-up)
            # → используем FOLLOWUP_PROMPT чтобы избежать галлюцинаций
            if conversation_history:
                system_content = FOLLOWUP_PROMPT
            else:
                state = user_state or "Нет данных"
                system_content = CHAT_PROMPT.format(user_state=state)
        elif not context_chunks:
            # RAG без результатов → дружелюбный ассистент
            state = user_state or "Нет данных"
            system_content = CHAT_PROMPT.format(user_state=state)
        else:
            context_parts = []
            for chunk in context_chunks:
                if chunk.get("source_type") == "law":
                    parts = []
                    if chunk.get("doc_type"):
                        parts.append(chunk["doc_type"])
                    if chunk.get("heading"):
                        parts.append(chunk["heading"])
                    if chunk.get("doc_date"):
                        parts.append(f"от {chunk['doc_date']}")
                    if chunk.get("doc_number"):
                        parts.append(f"N{chunk['doc_number']}")
                    if chunk.get("status"):
                        parts.append(f"Статус: {chunk['status']}")
                    label = f"[law: {', '.join(parts)}]"
                else:
                    parts = [chunk["filename"]]
                    if chunk.get("page_number"):
                        parts.append(f"стр. {chunk['page_number']}")
                    if chunk.get("section_header"):
                        parts.append(chunk["section_header"])
                    parts.append(f"чанк {chunk['chunk_index']}")
                    label = f"[{', '.join(parts)}]"
                context_parts.append(f"{label}\n{chunk['text']}")

            context = "\n\n---\n\n".join(context_parts)
            system_content = SYSTEM_PROMPT.format(context=context)

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_content},
        ]

        if conversation_history:
            trimmed = self._trim_history(
                conversation_history,
                system_chars=len(system_content),
                question_chars=len(question),
            )
            if trimmed:
                messages.extend(trimmed)

        messages.append({"role": "user", "content": question})
        return messages

    @staticmethod
    def extract_sources(context_chunks: list[dict]) -> list[dict]:
        """Дедупликация и извлечение источников из чанков."""
        sources = []
        seen: set[tuple] = set()
        for chunk in context_chunks:
            if chunk.get("source_type") == "law":
                key = ("law", chunk.get("pravo_nd", ""), chunk.get("chunk_index", 0))
                if key not in seen:
                    seen.add(key)
                    sources.append({
                        "source_type": "law",
                        "heading": chunk.get("heading"),
                        "doc_type": chunk.get("doc_type"),
                        "doc_date": chunk.get("doc_date"),
                        "doc_number": chunk.get("doc_number"),
                        "status": chunk.get("status"),
                        "pravo_nd": chunk.get("pravo_nd"),
                        "score": chunk.get("score", 0),
                    })
            else:
                key = ("user", chunk["filename"], chunk["chunk_index"])
                if key not in seen:
                    seen.add(key)
                    source = {
                        "source_type": "user",
                        "filename": chunk["filename"],
                        "chunk_index": chunk["chunk_index"],
                        "score": chunk["score"],
                    }
                    if chunk.get("page_number"):
                        source["page_number"] = chunk["page_number"]
                    if chunk.get("section_header"):
                        source["section_header"] = chunk["section_header"]
                    sources.append(source)
        return sources

    async def generate(
        self,
        question: str,
        context_chunks: list[dict],
        conversation_history: list[dict[str, str]] | None = None,
        user_state: str | None = None,
        mode: str = "rag",
    ) -> dict:
        """
        Генерация ответа на основе контекста из чанков.

        Returns:
            {"answer": str, "sources": list[dict], "model": str}
        """
        messages = self._build_messages(
            question, context_chunks, conversation_history,
            user_state=user_state, mode=mode,
        )
        answer = await self.provider.generate(messages)
        sources = self.extract_sources(context_chunks)

        logger.info("Ответ сгенерирован: model=%s, sources=%d", self.provider.model, len(sources))
        return {
            "answer": answer,
            "sources": sources,
            "model": self.provider.model,
        }


    async def generate_hypothetical(self, question: str) -> str:
        messages = [
            {
                "role": "system",
                "content": (
                    "Ты — ассистент. Напиши КОРОТКИЙ фрагмент документа (2-4 предложения), "
                    "который непосредственно отвечает на вопрос пользователя. "
                    "Пиши от третьего лица, как справочный текст. "
                    "Если не знаешь точного ответа — напиши правдоподобный фрагмент."
                ),
            },
            {"role": "user", "content": question},
        ]
        return await self.provider.generate(messages, max_tokens=200)

    async def rewrite_query(
        self,
        question: str,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> str:
        """Перефразировать запрос для улучшения поиска.

        Если есть история диалога — раскрывает эллиптические ссылки.
        Возвращает самодостаточный поисковый запрос на русском языке.
        """
        history_text = ""
        if conversation_history:
            recent = conversation_history[-4:]
            pairs = []
            for msg in recent:
                role = "Пользователь" if msg["role"] == "user" else "Ассистент"
                pairs.append(f"{role}: {msg['content'][:300]}")
            history_text = "\n".join(pairs)

        if history_text:
            prompt = (
                f"\u0418\u0441\u0442\u043e\u0440\u0438\u044f \u0434\u0438\u0430\u043b\u043e\u0433\u0430:\n{history_text}\n\n"
                f"\u041d\u043e\u0432\u044b\u0439 \u0432\u043e\u043f\u0440\u043e\u0441 \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044f: {question}\n\n"
                "Перепиши вопрос как самодостаточный поисковый запрос (без местоимений, "
                "с полным контекстом). Верни ТОЛЬКО переформулированный запрос, без пояснений."
            )
        else:
            prompt = (
                f"\u0412\u043e\u043f\u0440\u043e\u0441: {question}\n\n"
                "Перепиши как поисковый запрос для семантического поиска по документам. "
                "Верни ТОЛЬКО запрос, без пояснений."
            )

        messages = [
            {"role": "system", "content": "Ты — система переформулировки запросов."},
            {"role": "user", "content": prompt},
        ]
        rewritten = await self.provider.generate(messages, max_tokens=100)
        return rewritten.strip() or question

    async def generate_stream(
        self,
        question: str,
        context_chunks: list[dict],
        conversation_history: list[dict[str, str]] | None = None,
        user_state: str | None = None,
        mode: str = "rag",
    ) -> AsyncGenerator[str, None]:
        """
        Стриминг ответа. Yields текстовые дельты.

        Sources не зависят от LLM — вычисляются отдельно через extract_sources().
        """
        messages = self._build_messages(
            question, context_chunks, conversation_history,
            user_state=user_state, mode=mode,
        )
        async for delta in self.provider.generate_stream(messages):
            yield delta
