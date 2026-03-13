"""Управление OAuth-токеном Claude из ~/.claude/.credentials.json."""

import asyncio
import json
import logging
import os
import time

logger = logging.getLogger(__name__)

_CREDENTIALS_PATH = os.path.expanduser("~/.claude/.credentials.json")
_REFRESH_MARGIN_SEC = 300  # обновлять за 5 мин до истечения


class TokenManager:
    """Кешированный доступ к Claude OAuth access token с авто-обновлением."""

    def __init__(self) -> None:
        self._access_token: str = ""
        self._expires_at: float = 0.0  # unix seconds

    def _read_credentials(self) -> None:
        """Прочитать токен из файла учётных данных Claude CLI."""
        try:
            with open(_CREDENTIALS_PATH) as f:
                data = json.load(f)
            oauth = data["claudeAiOauth"]
            self._access_token = oauth["accessToken"]
            self._expires_at = oauth["expiresAt"] / 1000.0  # ms → sec
            logger.debug(
                "Токен загружен, истекает через %.0f мин",
                (self._expires_at - time.time()) / 60,
            )
        except (FileNotFoundError, KeyError, json.JSONDecodeError) as e:
            logger.error("Не удалось прочитать %s: %s", _CREDENTIALS_PATH, e)
            raise RuntimeError(
                f"Claude credentials не найдены: {_CREDENTIALS_PATH}"
            ) from e

    async def _trigger_cli_refresh(self) -> None:
        """Запустить `claude auth status` чтобы CLI обновил токен."""
        logger.info("Запускаю claude auth status для обновления токена...")
        env = os.environ.copy()
        env.pop("CLAUDECODE", None)  # убрать чтобы не блокировал вложенный запуск
        try:
            proc = await asyncio.create_subprocess_exec(
                "claude", "auth", "status",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            await asyncio.wait_for(proc.wait(), timeout=15.0)
            logger.info("claude auth status завершён (code=%d)", proc.returncode)
        except (asyncio.TimeoutError, FileNotFoundError) as e:
            logger.warning("Не удалось обновить токен через CLI: %s", e)

    async def get_token(self) -> str:
        """Вернуть актуальный access token, обновив при необходимости."""
        now = time.time()

        # Первая загрузка или токен скоро истечёт
        if not self._access_token or now >= self._expires_at - _REFRESH_MARGIN_SEC:
            self._read_credentials()

            # Если после перечитки токен всё ещё истекает — дёрнуть CLI
            if time.time() >= self._expires_at - _REFRESH_MARGIN_SEC:
                await self._trigger_cli_refresh()
                self._read_credentials()

        return self._access_token

    def invalidate(self) -> None:
        """Сбросить кеш (вызывать после 401 от API)."""
        self._access_token = ""
        self._expires_at = 0.0
