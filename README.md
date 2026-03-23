# RAGozin Bot

RAG-powered Telegram bot for document Q&A with hybrid search, streaming LLM responses, and multi-user support.

## Features

- **Hybrid Search** — BM25 (keyword) + semantic (vector) with Reciprocal Rank Fusion
- **Multiple Document Formats** — PDF, TXT, DOCX ingestion with automatic chunking
- **Streaming Responses** — Real-time LLM answer generation via Telegram
- **Multi-user Support** — Isolated document collections per user
- **Russian Language Optimized** — pymorphy3 lemmatization for accurate keyword matching
- **Advanced RAG Techniques** — HyDE (Hypothetical Document Embeddings), query rewriting

## Architecture

User sends a question via Telegram. The bot runs it through a hybrid search pipeline:
BM25 keyword search (with pymorphy3 lemmatization) + semantic vector search (Qdrant),
fused via Reciprocal Rank Fusion. Top results are passed to the LLM for streaming response.

Document upload: files are chunked and dual-indexed into Qdrant (vectors) and BM25 (keywords).

## Tech Stack

- **Bot Framework**: aiogram 3 (async)
- **Vector DB**: Qdrant
- **Relational DB**: PostgreSQL + pgvector
- **Search**: BM25 + Semantic + Reciprocal Rank Fusion
- **NLP**: pymorphy3 (Russian morphology)
- **LLM**: OpenAI API (configurable)
- **Migrations**: Alembic
- **Deployment**: Docker, Docker Compose

## Quick Start

1. Clone the repo
2. Copy .env.example to .env and fill in your API keys
3. Run: docker compose up -d

## Project Structure

- app/bot/ — Telegram bot handlers and middleware
- app/core/ — RAG pipeline, search, chunking, embeddings
- app/db/ — Database models and migrations
- app/llm/ — LLM integration and streaming
- app/presets/ — YAML product presets (loader, default, corporate_faq)
- app/config.py — Configuration management
- app/main.py — Application entry point

## Presets (Product Variants)

The bot supports multiple product profiles via YAML presets. Same codebase deploys as different products.

Set `BOT_PRESET=<name>` in `.env` to switch. Available presets:

| Preset | Bot Name | Use Case |
|--------|----------|----------|
| `default` | RAGozin | General document Q&A + Russian law search |
| `corporate_faq` | DocHelper | Corporate internal documentation assistant |

Create custom presets by copying `app/presets/default.yml` and modifying prompts, messages, and features.

## License

Source Available License — see LICENSE for details.
Personal and educational use is permitted. Commercial use requires explicit permission.

## Author

**Vladislav Pestov** — GitHub: GleckusZeroFive
