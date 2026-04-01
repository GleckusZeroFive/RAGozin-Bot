# Contributing to RAGozin Bot

## Development Setup

1. Clone and install:

```bash
git clone https://github.com/GleckusZeroFive/RAGozin-Bot.git
cd RAGozin-Bot
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

2. Start infrastructure:

```bash
docker compose -f docker-compose.dev.yml up -d
```

3. Configure environment:

```bash
cp .env.example .env
# Edit .env with your settings
```

## Project Structure

- `app/` — main application code (bot, handlers, RAG pipeline)
- `alembic/` — database migrations
- `proxy/` — reverse proxy configuration
- `tests/` — test suite
- `demo_*.txt` — sample documents for testing

## How to Contribute

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Make your changes
4. Run tests: `pytest tests/`
5. Commit with a clear message
6. Push and open a Pull Request

## Code Style

- Python 3.10+
- Async-first (aiogram, asyncpg)
- Type hints where practical
- Follow existing code patterns

## Key Areas for Contribution

- **Search quality** — improving BM25/semantic fusion, tuning RRF parameters
- **Document parsing** — adding new format support
- **Chunking strategies** — experimenting with different chunk sizes and overlap
- **Tests** — expanding test coverage

## Reporting Issues

Open an issue with:
- Steps to reproduce
- Expected vs actual behavior
- Sample document (if relevant)
- Python version and OS
