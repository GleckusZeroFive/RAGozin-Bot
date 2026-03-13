from app.core.chunker import TextChunker


def test_chunk_returns_list(sample_text: str) -> None:
    chunker = TextChunker()
    chunks = chunker.chunk(sample_text)
    assert isinstance(chunks, list)
    assert len(chunks) > 0


def test_chunk_structure(sample_text: str) -> None:
    chunker = TextChunker()
    chunks = chunker.chunk(sample_text)
    for chunk in chunks:
        assert "text" in chunk
        assert "chunk_index" in chunk
        assert "metadata" in chunk
        assert isinstance(chunk["text"], str)
        assert isinstance(chunk["chunk_index"], int)


def test_chunk_with_metadata(sample_text: str) -> None:
    chunker = TextChunker()
    meta = {"filename": "test.pdf", "file_type": "pdf"}
    chunks = chunker.chunk(sample_text, metadata=meta)
    for chunk in chunks:
        assert chunk["metadata"]["filename"] == "test.pdf"
        assert chunk["metadata"]["file_type"] == "pdf"


def test_chunk_indexes_sequential(sample_text: str) -> None:
    chunker = TextChunker()
    chunks = chunker.chunk(sample_text)
    for i, chunk in enumerate(chunks):
        assert chunk["chunk_index"] == i


def test_short_text_single_chunk(sample_short_text: str) -> None:
    chunker = TextChunker()
    chunks = chunker.chunk(sample_short_text)
    assert len(chunks) == 1
    assert chunks[0]["text"] == sample_short_text


def test_empty_text() -> None:
    chunker = TextChunker()
    chunks = chunker.chunk("")
    assert chunks == []
