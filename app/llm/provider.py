import asyncio
import logging
import time
from collections.abc import AsyncGenerator
from typing import Any

import httpx
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
)

from app.config import settings

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_BACKOFF = (1.0, 3.0, 7.0)  # задержки между попытками
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503}


import hashlib


class RoundRobinKeyManager:
    """Manages multiple API keys with round-robin rotation."""

    def __init__(self, keys: list[str]):
        self._keys = keys
        self._index = 0

    def next_key(self) -> str:
        key = self._keys[self._index % len(self._keys)]
        self._index += 1
        return key

    @property
    def count(self) -> int:
        return len(self._keys)


class ResponseCache:
    """Simple in-memory cache for LLM responses (classifier, rewrite, HyDE)."""

    def __init__(self, max_size: int = 500):
        self._cache: dict[str, str] = {}
        self._max_size = max_size

    def _key(self, messages: list[dict], model: str, temperature: float) -> str:
        content = "|".join(m.get("content", "")[:200] for m in messages)
        raw = f"{model}:{temperature}:{content}"
        return hashlib.md5(raw.encode()).hexdigest()

    def get(self, messages: list[dict], model: str, temperature: float) -> str | None:
        k = self._key(messages, model, temperature)
        return self._cache.get(k)

    def put(self, messages: list[dict], model: str, temperature: float, response: str) -> None:
        if len(self._cache) >= self._max_size:
            # Remove oldest 20%
            keys_to_remove = list(self._cache.keys())[:self._max_size // 5]
            for k in keys_to_remove:
                del self._cache[k]
        k = self._key(messages, model, temperature)
        self._cache[k] = response


# Global cache instance
_response_cache = ResponseCache()


class LLMError(Exception):
    """Понятная ошибка уровня LLM для показа пользователю."""


class OpenAICompatibleProvider:
    """
    LLM-провайдер для OpenAI-совместимого API (Cerebras, Claude proxy и др.).
    Retry и таймауты.
    """

    def __init__(self, base_url: str, model: str, api_key: str = "unused",
                 key_manager: RoundRobinKeyManager | None = None) -> None:
        self.model = model
        self.base_url = base_url
        self._key_manager = key_manager
        self._api_key = api_key
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=httpx.Timeout(60.0, connect=10.0),
        )
        if key_manager:
            logger.info("LLM provider: %s, model=%s, keys=%d (round-robin)",
                        base_url, model, key_manager.count)
        else:
            logger.info("LLM provider: %s, model=%s", base_url, model)

    def _rotate_key(self) -> None:
        """Rotate to next API key if round-robin is enabled."""
        if self._key_manager:
            next_key = self._key_manager.next_key()
            if next_key != self._api_key:
                self._api_key = next_key
                self._client = AsyncOpenAI(
                    api_key=next_key,
                    base_url=self.base_url,
                    timeout=httpx.Timeout(60.0, connect=10.0),
                )

    async def generate(
        self,
        messages: list[dict[str, Any]],
        temperature: float | None = None,
        max_tokens: int | None = None,
        model: str | None = None,
    ) -> str:
        """Генерация ответа через LLM с retry, кешированием и round-robin ключами."""
        use_model = model or self.model
        use_temp = temperature if temperature is not None else settings.llm_temperature

        # Cache check (only for non-streaming, deterministic calls like classifier)
        if use_temp <= 0.1:
            cached = _response_cache.get(messages, use_model, use_temp)
            if cached is not None:
                logger.info("Cache hit for model=%s", use_model)
                return cached

        last_error: Exception | None = None

        for attempt in range(1, _MAX_RETRIES + 1):
            # Round-robin key rotation
            self._rotate_key()
            try:
                response = await self._client.chat.completions.create(
                    model=use_model,
                    messages=messages,
                    temperature=temperature if temperature is not None else settings.llm_temperature,
                    max_tokens=max_tokens if max_tokens is not None else settings.llm_max_tokens,
                )

                if not response.choices:
                    raise LLMError("LLM вернул пустой ответ (нет choices)")

                result = response.choices[0].message.content or ""
                if not result.strip():
                    logger.warning("LLM returned empty content, model=%s, finish_reason=%s", use_model, response.choices[0].finish_reason)
                # Cache the response for low-temperature calls
                if use_temp <= 0.1:
                    _response_cache.put(messages, use_model, use_temp, result)
                return result

            except APIStatusError as e:
                last_error = e
                status = e.status_code

                if status == 404:
                    logger.error(
                        "Модель '%s' не найдена: %s",
                        use_model, e.message,
                    )
                    raise LLMError(
                        "Сервис временно недоступен. Попробуйте позже."
                    ) from e

                if status in (401, 403):
                    logger.error("Ошибка авторизации: %s", e.message)
                    raise LLMError(
                        "Сервис временно недоступен. Попробуйте позже."
                    ) from e

                # 429, 5xx — transient, ретраим
                if status in _RETRYABLE_STATUS_CODES and attempt < _MAX_RETRIES:
                    delay = _RETRY_BACKOFF[attempt - 1]
                    logger.warning(
                        "LLM API %d (попытка %d/%d), жду %.0fс...",
                        status, attempt, _MAX_RETRIES, delay,
                    )
                    await asyncio.sleep(delay)
                    continue

                logger.error("LLM API ошибка %d: %s", status, e.message)
                raise LLMError("Сервис генерации ответов временно недоступен.") from e

            except APITimeoutError as e:
                last_error = e
                if attempt < _MAX_RETRIES:
                    delay = _RETRY_BACKOFF[attempt - 1]
                    logger.warning(
                        "LLM API таймаут (попытка %d/%d), жду %.0fс...",
                        attempt, _MAX_RETRIES, delay,
                    )
                    await asyncio.sleep(delay)
                    continue

                logger.error("LLM API таймаут после %d попыток", _MAX_RETRIES)
                raise LLMError("Сервис генерации ответов не отвечает. Попробуйте позже.") from e

            except APIConnectionError as e:
                last_error = e
                if attempt < _MAX_RETRIES:
                    delay = _RETRY_BACKOFF[attempt - 1]
                    logger.warning(
                        "LLM API connection error (попытка %d/%d), жду %.0fс...",
                        attempt, _MAX_RETRIES, delay,
                    )
                    await asyncio.sleep(delay)
                    continue

                logger.error("LLM API недоступен после %d попыток: %s", _MAX_RETRIES, e)
                raise LLMError("Сервис генерации ответов недоступен. Попробуйте позже.") from e

        raise LLMError("Сервис генерации ответов временно недоступен.") from last_error

    def _handle_status_error(self, e: APIStatusError, model: str) -> LLMError:
        """Преобразовать APIStatusError в LLMError с дифференциацией по коду."""
        status = e.status_code
        if status == 404:
            logger.error("Модель '%s' не найдена: %s", model, e.message)
            return LLMError(
                "Сервис временно недоступен. Попробуйте позже."
            )
        if status in (401, 403):
            logger.error("Ошибка авторизации: %s", e.message)
            return LLMError("Сервис временно недоступен. Попробуйте позже.")
        logger.error("LLM API ошибка %d: %s", status, e.message)
        return LLMError("Сервис генерации ответов временно недоступен.")

    async def generate_stream(
        self,
        messages: list[dict[str, Any]],
        temperature: float | None = None,
        max_tokens: int | None = None,
        model: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """
        Стриминг ответа через LLM с retry и метриками.

        Retry (3 попытки с backoff) только на этапе подключения (create).
        После первого yield дельты — ошибки пробрасываются без retry.
        """
        use_model = model or self.model
        last_error: Exception | None = None
        response = None

        # Retry на этапе подключения
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                response = await self._client.chat.completions.create(
                    model=use_model,
                    messages=messages,
                    temperature=temperature if temperature is not None else settings.llm_temperature,
                    max_tokens=max_tokens if max_tokens is not None else settings.llm_max_tokens,
                    stream=True,
                )
                break  # Подключение успешно

            except APIStatusError as e:
                last_error = e
                if e.status_code not in _RETRYABLE_STATUS_CODES:
                    raise self._handle_status_error(e, use_model) from e
                if attempt < _MAX_RETRIES:
                    delay = _RETRY_BACKOFF[attempt - 1]
                    logger.warning(
                        "LLM stream API %d (попытка %d/%d), жду %.0fс...",
                        e.status_code, attempt, _MAX_RETRIES, delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                raise self._handle_status_error(e, use_model) from e

            except APITimeoutError as e:
                last_error = e
                if attempt < _MAX_RETRIES:
                    delay = _RETRY_BACKOFF[attempt - 1]
                    logger.warning(
                        "LLM stream таймаут (попытка %d/%d), жду %.0fс...",
                        attempt, _MAX_RETRIES, delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                logger.error("LLM stream таймаут после %d попыток", _MAX_RETRIES)
                raise LLMError(
                    "Сервис генерации ответов не отвечает. Попробуйте позже."
                ) from e

            except APIConnectionError as e:
                last_error = e
                if attempt < _MAX_RETRIES:
                    delay = _RETRY_BACKOFF[attempt - 1]
                    logger.warning(
                        "LLM stream connection error (попытка %d/%d), жду %.0fс...",
                        attempt, _MAX_RETRIES, delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                logger.error("LLM stream недоступен после %d попыток: %s", _MAX_RETRIES, e)
                raise LLMError(
                    "Сервис генерации ответов недоступен. Попробуйте позже."
                ) from e

        if response is None:
            raise LLMError("Сервис генерации ответов временно недоступен.") from last_error

        # Итерация по дельтам (без retry — текст уже может быть показан пользователю)
        start = time.monotonic()
        delta_count = 0
        total_chars = 0
        try:
            async for chunk in response:
                if chunk.choices:
                    delta = chunk.choices[0].delta
                    if delta and delta.content:
                        delta_count += 1
                        total_chars += len(delta.content)
                        yield delta.content
        except APIStatusError as e:
            raise self._handle_status_error(e, use_model) from e
        except (APITimeoutError, APIConnectionError) as e:
            logger.error("LLM stream прерван mid-stream: %s", e)
            raise LLMError("Генерация ответа прервана. Попробуйте позже.") from e
        finally:
            elapsed = time.monotonic() - start
            logger.info(
                "LLM stream %s model=%s chars=%d deltas=%d %.1fс",
                "OK" if delta_count > 0 else "EMPTY",
                use_model, total_chars, delta_count, elapsed,
            )


# Transient-ошибки, при которых FallbackProvider переключается на fallback
_TRANSIENT_EXCEPTIONS = (APIConnectionError, APITimeoutError)
_TRANSIENT_STATUS_CODES = {429, 500, 502, 503}


def _is_transient(exc: Exception) -> bool:
    """Определить, является ли ошибка временной (стоит попробовать fallback)."""
    if isinstance(exc, _TRANSIENT_EXCEPTIONS):
        return True
    if isinstance(exc, APIStatusError) and exc.status_code in _TRANSIENT_STATUS_CODES:
        return True
    return False


class FallbackProvider:
    """
    LLM-провайдер с авто-fallback: primary (Cerebras) → fallback (Claude proxy).

    При transient-ошибках (timeout, connection error, 429, 5xx) на primary
    автоматически переключается на fallback с логированием.
    Перманентные ошибки (401, 403, 404) пробрасываются сразу.
    """

    def __init__(
        self,
        primary: OpenAICompatibleProvider,
        fallback: OpenAICompatibleProvider,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.model = primary.model  # активная модель
        logger.info(
            "FallbackProvider: primary=%s (%s), fallback=%s (%s)",
            primary.base_url, primary.model, fallback.base_url, fallback.model,
        )

    async def generate(
        self,
        messages: list[dict[str, Any]],
        temperature: float | None = None,
        max_tokens: int | None = None,
        model: str | None = None,
    ) -> str:
        """Генерация с авто-fallback."""
        try:
            result = await self.primary.generate(
                messages, temperature, max_tokens, model,
            )
            self.model = self.primary.model
            return result
        except LLMError as e:
            if not _is_transient(e.__cause__) if e.__cause__ else False:
                raise
            logger.warning(
                "Primary LLM (%s) недоступен: %s — переключаюсь на fallback (%s)",
                self.primary.model, e, self.fallback.model,
            )

        result = await self.fallback.generate(
            messages, temperature, max_tokens, model,
        )
        self.model = self.fallback.model
        return result

    async def generate_stream(
        self,
        messages: list[dict[str, Any]],
        temperature: float | None = None,
        max_tokens: int | None = None,
        model: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """Стриминг с авто-fallback (fallback только на этапе подключения)."""
        try:
            stream = self.primary.generate_stream(
                messages, temperature, max_tokens, model,
            )
            # Пробуем получить первый чанк чтобы убедиться что подключение ОК
            first_chunk = await stream.__anext__()
            self.model = self.primary.model
            yield first_chunk
            async for chunk in stream:
                yield chunk
            return
        except LLMError as e:
            if not _is_transient(e.__cause__) if e.__cause__ else False:
                raise
            logger.warning(
                "Primary LLM stream (%s) недоступен: %s — переключаюсь на fallback (%s)",
                self.primary.model, e, self.fallback.model,
            )
        except StopAsyncIteration:
            # Primary вернул пустой стрим — тоже fallback
            logger.warning(
                "Primary LLM stream (%s) пуст — переключаюсь на fallback (%s)",
                self.primary.model, self.fallback.model,
            )

        self.model = self.fallback.model
        async for chunk in self.fallback.generate_stream(
            messages, temperature, max_tokens, model,
        ):
            yield chunk
