"""Upload test documents programmatically into RAGozin bot.
Run from WSL: cd /home/gleckus/projects/RAG-DEMO-PET && python upload_test_docs.py
"""
import asyncio
import uuid
import sys

sys.path.insert(0, '/home/gleckus/projects/RAG-DEMO-PET')

from app.config import settings
from app.db.database import db
from app.db.models import Document
from app.core.chunker import AdvancedChunker
from app.core.embedder import LocalEmbedder
from app.core.indexer import QdrantIndexer
from sqlalchemy import select


DB_USER_ID = 1
COLLECTION_NAME = "user_1190430916"

DOCS = [
    {
        "path": "/home/gleckus/projects/RAG-DEMO-PET/uploads/hr_policy_technosoft.txt",
        "filename": "hr_policy_technosoft.txt",
    },
    {
        "path": "/home/gleckus/projects/RAG-DEMO-PET/uploads/it_security_technosoft.txt",
        "filename": "it_security_technosoft.txt",
    },
]


async def main():
    await db.connect()

    embedder = LocalEmbedder()
    indexer = QdrantIndexer()
    chunker = AdvancedChunker()

    async with db.get_session() as session:
        for doc_info in DOCS:
            filepath = doc_info["path"]
            filename = doc_info["filename"]

            existing = (await session.execute(
                select(Document).where(
                    Document.user_id == DB_USER_ID,
                    Document.filename == filename,
                )
            )).scalar_one_or_none()

            if existing:
                print(f"SKIP: {filename} already exists (id={existing.id})")
                continue

            with open(filepath, "r", encoding="utf-8") as f:
                text = f.read()

            print(f"\nProcessing: {filename} ({len(text)} chars)")

            metadata = {"filename": filename}
            chunks = chunker.chunk(text, metadata)
            print(f"  Chunks: {len(chunks)}")

            texts_to_embed = [f"passage: {c['text']}" for c in chunks]
            embeddings = []
            batch_size = 32
            for i in range(0, len(texts_to_embed), batch_size):
                batch = texts_to_embed[i:i + batch_size]
                batch_emb = embedder._model.encode(batch, normalize_embeddings=True).tolist()
                embeddings.extend(batch_emb)
            print(f"  Embeddings: {len(embeddings)}")

            doc_id = str(uuid.uuid4())

            indexed = indexer.index_chunks(
                collection_name=COLLECTION_NAME,
                chunks=chunks,
                embeddings=embeddings,
                document_id=doc_id,
                filename=filename,
            )
            print(f"  Indexed: {indexed} points in Qdrant")

            doc = Document(
                id=doc_id,
                user_id=DB_USER_ID,
                filename=filename,
                file_type="txt",
                file_size=len(text.encode("utf-8")),
                chunk_count=len(chunks),
                status="ready",
                qdrant_collection=COLLECTION_NAME,
                full_text=text,
                version=1,
                is_backup=False,
            )
            session.add(doc)
            await session.commit()
            print(f"  Saved to DB: id={doc_id}")

    await db.disconnect()
    print("\nDone!")


asyncio.run(main())
