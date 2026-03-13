from app.config import settings
from app.llm.provider import FallbackProvider, OpenAICompatibleProvider

_provider: OpenAICompatibleProvider | FallbackProvider | None = None


def get_llm_provider() -> OpenAICompatibleProvider | FallbackProvider:
    """Фабрика LLM-провайдера (singleton).

    Если задан cerebras_api_key — Cerebras как primary, Claude как fallback.
    Иначе — только Claude через прокси.
    """
    global _provider
    if _provider is not None:
        return _provider

    if settings.cerebras_api_key:
        primary = OpenAICompatibleProvider(
            base_url=settings.cerebras_api_url,
            model=settings.cerebras_model,
            api_key=settings.cerebras_api_key,
        )
        if settings.llm_fallback_enabled:
            fallback = OpenAICompatibleProvider(
                base_url=settings.claude_proxy_url,
                model=settings.claude_model,
            )
            _provider = FallbackProvider(primary, fallback)
        else:
            _provider = primary
    else:
        _provider = OpenAICompatibleProvider(
            base_url=settings.claude_proxy_url,
            model=settings.claude_model,
        )

    return _provider
