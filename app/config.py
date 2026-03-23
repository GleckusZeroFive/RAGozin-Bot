from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # === Bot Preset ===
    bot_preset: str = "default"  # "corporate_faq", "client_faq", "legal_ocr", "tutor", "voice_assistant"

    # === Telegram ===
    telegram_bot_token: str = ""

    # === PostgreSQL ===
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "ragbot"
    postgres_user: str = "ragbot"
    postgres_password: str = "ragbot_secret"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_sync(self) -> str:
        """Для Alembic-миграций (синхронный драйвер)."""
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # === Qdrant ===
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333

    # === LLM Primary (Cerebras) ===
    cerebras_api_url: str = "https://api.cerebras.ai/v1"
    cerebras_api_key: str = ""  # csk-...
    cerebras_model: str = "gpt-oss-120b"

    # === LLM Fallback (Claude через прокси на хосте) ===
    claude_proxy_url: str = "http://host.docker.internal:8200/v1"
    claude_model: str = "claude-haiku-4-5-20251001"

    # === LLM общие ===
    llm_fallback_enabled: bool = True  # авто-переключение на Claude при ошибке Cerebras
    llm_temperature: float = 0.3
    llm_max_tokens: int = 1024

    # === Embeddings (локальная модель sentence-transformers) ===
    embedding_model: str = "intfloat/multilingual-e5-large"
    embedding_device: str = "cpu"
    embedding_dimension: int = 1024

    # === RAG ===
    chunk_size: int = 1000
    chunk_overlap: int = 200
    chunker_mode: str = "advanced"  # "basic" | "advanced"
    min_chunk_size: int = 50  # чанки короче — пропускаются (мусор, колонтитулы)
    retriever_top_k: int = 5
    retriever_score_threshold: float = 0.5

    # === Hybrid search (BM25 + semantic + RRF) ===
    hybrid_search_enabled: bool = True
    hybrid_semantic_top_k: int = 20   # кандидатов из semantic search для RRF
    hybrid_bm25_top_k: int = 20       # кандидатов из BM25 search для RRF
    hybrid_final_top_k: int = 5       # финальных результатов после fusion

    # === Embedding batching ===
    embedding_batch_max_items: int = 256

    # === OCR ===
    ocr_enabled: bool = True
    ocr_languages: str = "rus+spa+eng"
    ocr_text_threshold: int = 50  # символов на странице — ниже этого включается OCR

    # === Контекст диалога (follow-up вопросы) ===
    conversation_max_pairs: int = 3          # макс. Q&A пар в истории
    conversation_ttl_minutes: int = 15       # контекст истекает через N минут неактивности
    conversation_max_context_chars: int = 24_000  # ~6000 токенов — бюджет на историю

    # === Intent Classifier ===
    classifier_enabled: bool = True          # LLM-классификатор интентов (rag/chat/followup)
    classifier_max_tokens: int = 20          # Макс токенов для ответа классификатора
    classifier_model: str | None = None       # Модель для классификатора (None = основная)
    classifier_temperature: float = 0.0      # Детерминированная классификация

    # === STT (Speech-to-Text, faster-whisper) ===
    stt_enabled: bool = True
    whisper_model_size: str = "small"       # tiny / base / small / medium / large-v3
    whisper_language: str = "ru"
    whisper_max_duration: int = 60          # макс. длительность голосового (секунды)

    # === Law Corpus (через Modules Gateway) ===
    law_corpus_enabled: bool = False
    law_api_url: str = "http://localhost:8100"  # legacy, не используется при modules_gateway_url
    law_corpus_top_k: int = 5
    law_corpus_weight: float = 0.7

    # === Retrieval enhancement ===
    hyde_enabled: bool = True           # HyDE: гипотетический документ для dense search
    query_rewrite_enabled: bool = True  # Переформулировка запроса перед поиском

    # === Modules Gateway ===
    modules_gateway_url: str = ""  # http://gateway:8300
    modules_api_key: str = ""  # tbm_...

    # === Стриминг (буферизированный вывод) ===
    stream_tick_interval: float = 0.5      # секунд между обновлениями Telegram-сообщения
    stream_chars_per_tick: int = 40        # символов за одно обновление (визуальная скорость)
    stream_show_cursor: bool = True        # показывать курсор ▍ во время стриминга

    # === Загрузки ===
    upload_dir: str = "./uploads"
    max_file_size_mb: int = 20

    # === Тарифы ===
    tier_duration_days: int = 30
    daily_reset_hour: int = 0  # Час сброса лимитов (UTC+7, Красноярск)

settings = Settings()

TIER_LIMITS: dict[str, dict[str, int]] = {
    "free": {"documents_limit": 10, "queries_limit": 50},
    "pro": {"documents_limit": 50, "queries_limit": 200},
    "admin": {"documents_limit": 999999, "queries_limit": 999999},
}
