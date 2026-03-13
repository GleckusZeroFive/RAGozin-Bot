"""
HTTP-клиент для поиска по российскому законодательству.

Поддерживает два режима:
  1. Modules Gateway (рекомендуется): modules_gateway_url + modules_api_key
  2. Legacy: прямой вызов law-api по law_api_url
"""

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class LawClient:
    """Клиент для модуля rus_law через Modules Gateway или напрямую."""

    def __init__(self) -> None:
        self._use_gateway = bool(settings.modules_gateway_url and settings.modules_api_key)
        if self._use_gateway:
            self._gateway_url = settings.modules_gateway_url.rstrip("/")
            self._api_key = settings.modules_api_key
            logger.info("LawClient: режим Gateway (%s)", self._gateway_url)
        else:
            self._base_url = settings.law_api_url.rstrip("/")
            logger.info("LawClient: режим Legacy (%s)", self._base_url)

        self._client = httpx.AsyncClient(timeout=15)

    async def close(self) -> None:
        """Закрыть HTTP-клиент."""
        await self._client.aclose()

    async def search(
        self,
        query_text: str,
        query_vector: list[float],
        top_k: int | None = None,
    ) -> list[dict]:
        """Поиск по базе законодательства (POST с готовым вектором)."""
        payload = {
            "query_vector": query_vector,
            "query_text": query_text,
            "top_k": top_k or settings.law_corpus_top_k,
        }

        if self._use_gateway:
            return await self._gateway_search(payload)
        return await self._legacy_search(payload)

    async def _gateway_search(self, payload: dict) -> list[dict]:
        url = f"{self._gateway_url}/modules/rus_law/search"
        headers = {"X-API-Key": self._api_key}
        resp = await self._client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results")
        if results is None:
            logger.warning("Law API Gateway: ответ без 'results': %s", list(data.keys()))
            return []
        return results

    async def _legacy_search(self, payload: dict) -> list[dict]:
        resp = await self._client.post(f"{self._base_url}/search", json=payload)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results")
        if results is None:
            logger.warning("Law API Legacy: ответ без 'results': %s", list(data.keys()))
            return []
        return results

    async def stats(self) -> dict:
        """Статистика корпуса."""
        if self._use_gateway:
            url = f"{self._gateway_url}/modules/rus_law/stats"
            headers = {"X-API-Key": self._api_key}
            resp = await self._client.post(url, json={}, headers=headers)
            resp.raise_for_status()
            return resp.json()
        else:
            resp = await self._client.get(f"{self._base_url}/stats")
            resp.raise_for_status()
            return resp.json()

    async def health(self) -> bool:
        """Проверка доступности сервиса."""
        try:
            if self._use_gateway:
                url = f"{self._gateway_url}/health/rus_law"
                resp = await self._client.get(url)
                data = resp.json()
                return data.get("status") == "healthy"
            else:
                resp = await self._client.get(f"{self._base_url}/health")
                return resp.status_code == 200
        except Exception:
            return False
