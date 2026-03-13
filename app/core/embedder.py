"""
Локальный эмбеддер на базе sentence-transformers.

Использует intfloat/multilingual-e5-large (1024-dim) с lazy loading.
Async-обёртка через asyncio.to_thread() для синхронного sentence-transformers.
"""

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

# Тип для callback прогресса: (batch_num, total_batches) -> None
ProgressCallback = Callable[[int, int], Coroutine[Any, Any, None]]


class EmbeddingServiceError(Exception):
    """Ошибка при загрузке модели или генерации эмбеддингов."""


class LocalEmbedder:
    """
    Локальный эмбеддер (sentence-transformers).

    Модель загружается лениво при первом вызове.
    Для E5-моделей: "passage: " prefix для документов, "query: " для запросов.
    """

    def __init__(self) -> None:
        self._model = None
        self.dimension = settings.embedding_dimension
        self._batch_max_items = settings.embedding_batch_max_items

        logger.info(
            "LocalEmbedder: model=%s, device=%s, dim=%d, batch=%d",
            settings.embedding_model, settings.embedding_device,
            self.dimension, self._batch_max_items,
        )

    def _get_model(self):
        """Lazy-load модели при первом использовании."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer

                logger.info("Загрузка модели %s...", settings.embedding_model)
                self._model = SentenceTransformer(
                    settings.embedding_model,
                    device=settings.embedding_device,
                )
                logger.info("Модель загружена: %s", settings.embedding_model)
            except Exception as e:
                raise EmbeddingServiceError(
                    f"Не удалось загрузить модель {settings.embedding_model}: {e}"
                ) from e
        return self._model

    def _split_into_batches(self, texts: list[str]) -> list[list[str]]:
        """Разбить тексты на батчи по количеству элементов."""
        batches: list[list[str]] = []
        for i in range(0, len(texts), self._batch_max_items):
            batches.append(texts[i : i + self._batch_max_items])
        return batches

    def _embed_batch_sync(self, texts: list[str]) -> list[list[float]]:
        """Синхронный эмбеддинг батча документов (prefix 'passage: ')."""
        model = self._get_model()
        prefixed = [f"passage: {t}" for t in texts]
        embeddings = model.encode(
            prefixed,
            batch_size=self._batch_max_items,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return embeddings.tolist()

    def _embed_query_sync(self, text: str) -> list[float]:
        """Синхронный эмбеддинг одного запроса (prefix 'query: ')."""
        model = self._get_model()
        embedding = model.encode(
            f"query: {text}",
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return embedding.tolist()

    async def embed_documents(
        self,
        texts: list[str],
        on_progress: ProgressCallback | None = None,
    ) -> list[list[float]]:
        """
        Async эмбеддинг списка документов.

        Разбивает на батчи по embedding_batch_max_items,
        каждый батч выполняется в отдельном потоке.
        """
        all_embeddings: list[list[float]] = []
        batches = self._split_into_batches(texts)
        total_batches = len(batches)

        for batch_num, batch in enumerate(batches, 1):
            logger.info(
                "Эмбеддинг батч %d/%d (%d текстов)...",
                batch_num, total_batches, len(batch),
            )

            embeddings = await asyncio.to_thread(self._embed_batch_sync, batch)
            all_embeddings.extend(embeddings)

            if on_progress:
                await on_progress(batch_num, total_batches)

        logger.info("Сгенерировано %d эмбеддингов документов", len(all_embeddings))
        return all_embeddings

    async def embed_query(self, text: str) -> list[float]:
        """Async эмбеддинг одного поискового запроса."""
        return await asyncio.to_thread(self._embed_query_sync, text)

    async def check_health(self) -> dict:
        """Проверка работоспособности модели."""
        try:
            vec = await self.embed_query("health check")
            return {"status": "ok", "dimension": len(vec)}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _embed_passage_sync(self, text: str) -> list[float]:
        """Синхронный эмбеддинг одного пассажа (prefix 'passage: ' — для HyDE)."""
        model = self._get_model()
        embedding = model.encode(
            f"passage: {text}",
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return embedding.tolist()

    async def embed_passage(self, text: str) -> list[float]:
        """Async эмбеддинг гипотетического документа (passage prefix для HyDE)."""
        return await asyncio.to_thread(self._embed_passage_sync, text)
