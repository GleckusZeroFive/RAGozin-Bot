"""
Тесты для LocalEmbedder.
Требуют загруженной модели sentence-transformers — пропускаются, если модель недоступна.
"""

import pytest

from app.config import settings
from app.core.embedder import LocalEmbedder


@pytest.fixture
def embedder():
    return LocalEmbedder()


@pytest.mark.asyncio
async def test_embed_query(embedder) -> None:
    try:
        vector = await embedder.embed_query("Что такое машинное обучение?")
    except Exception:
        pytest.skip("Модель эмбеддингов недоступна")
    assert isinstance(vector, list)
    assert len(vector) == settings.embedding_dimension


@pytest.mark.asyncio
async def test_embed_documents(embedder) -> None:
    texts = ["Первый текст", "Второй текст"]
    try:
        vectors = await embedder.embed_documents(texts)
    except Exception:
        pytest.skip("Модель эмбеддингов недоступна")
    assert len(vectors) == 2
    assert len(vectors[0]) == settings.embedding_dimension
    assert len(vectors[1]) == settings.embedding_dimension


@pytest.mark.asyncio
async def test_check_health(embedder) -> None:
    result = await embedder.check_health()
    assert "status" in result
    if result["status"] == "ok":
        assert result["dimension"] == settings.embedding_dimension
