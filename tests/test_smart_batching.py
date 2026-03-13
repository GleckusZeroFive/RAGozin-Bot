"""Тесты для батчинга эмбеддингов (LocalEmbedder._split_into_batches)."""

from app.core.embedder import LocalEmbedder


def _make_embedder(batch_max_items: int = 3) -> LocalEmbedder:
    """Создать LocalEmbedder с кастомным batch_max_items."""
    embedder = LocalEmbedder.__new__(LocalEmbedder)
    embedder._model = None
    embedder.dimension = 1024
    embedder._batch_max_items = batch_max_items
    return embedder


def test_split_by_item_count():
    """Батчи разбиваются по количеству элементов."""
    embedder = _make_embedder(batch_max_items=2)
    batches = embedder._split_into_batches(["a", "b", "c", "d", "e"])
    assert len(batches) == 3
    assert batches[0] == ["a", "b"]
    assert batches[1] == ["c", "d"]
    assert batches[2] == ["e"]


def test_single_batch():
    """Все элементы помещаются в один батч."""
    embedder = _make_embedder(batch_max_items=10)
    batches = embedder._split_into_batches(["a", "b", "c"])
    assert len(batches) == 1
    assert batches[0] == ["a", "b", "c"]


def test_exact_batch_size():
    """Количество элементов кратно batch_max_items."""
    embedder = _make_embedder(batch_max_items=2)
    batches = embedder._split_into_batches(["a", "b", "c", "d"])
    assert len(batches) == 2
    assert batches[0] == ["a", "b"]
    assert batches[1] == ["c", "d"]


def test_empty_input():
    """Пустой список → пустой результат."""
    embedder = _make_embedder(batch_max_items=100)
    batches = embedder._split_into_batches([])
    assert batches == []


def test_single_element():
    """Один элемент → один батч."""
    embedder = _make_embedder(batch_max_items=100)
    batches = embedder._split_into_batches(["hello"])
    assert len(batches) == 1
    assert batches[0] == ["hello"]
