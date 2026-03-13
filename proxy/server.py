"""
OpenAI-совместимый прокси для Claude через CLI.

Принимает запросы в формате OpenAI /v1/chat/completions,
вызывает `claude -p` через subprocess и возвращает
ответ в формате OpenAI.

Поддержка:
- Текстовые сообщения (system / user / assistant)
- Multipart content с изображениями (image_url с data URI → temp file + --file)
- Стриминг (stream: true → SSE в формате OpenAI)

Использует авторизацию Claude CLI (подписка Max x5).
"""

import asyncio
import base64
import json
import logging
import os
import tempfile
import time
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("claude-proxy")

# Таймаут на один запрос к Claude CLI
REQUEST_TIMEOUT = 120.0

# Окружение для subprocess: убираем CLAUDECODE чтобы claude не блокировал вложенный запуск
_subprocess_env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

# MIME → расширение для временных файлов
_MIME_TO_EXT = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}

app = FastAPI(title="Claude Proxy")


# --- Форматирование ---

def _extract_content(content: Any) -> tuple[str, list[Path]]:
    """
    Извлечь текст и изображения из OpenAI content.

    Args:
        content: str или list[{type: "text"/"image_url", ...}]

    Returns:
        (text, temp_files) — текстовая часть и список временных файлов с изображениями.
    """
    if isinstance(content, str):
        return content, []

    if not isinstance(content, list):
        return str(content), []

    text_parts: list[str] = []
    temp_files: list[Path] = []

    for part in content:
        if not isinstance(part, dict):
            text_parts.append(str(part))
            continue

        if part.get("type") == "text":
            text_parts.append(part.get("text", ""))
        elif part.get("type") == "image_url":
            image_url = part.get("image_url", {})
            url = image_url.get("url", "") if isinstance(image_url, dict) else str(image_url)

            # Поддержка data URI: data:image/jpeg;base64,...
            if url.startswith("data:"):
                temp_path = _decode_data_uri(url)
                if temp_path:
                    temp_files.append(temp_path)
                else:
                    text_parts.append("[Ошибка декодирования изображения]")
            else:
                text_parts.append(f"[Изображение: {url}]")

    return "\n".join(text_parts), temp_files


def _decode_data_uri(data_uri: str) -> Path | None:
    """Декодировать data URI в временный файл. Возвращает путь или None."""
    try:
        # data:image/jpeg;base64,/9j/4AAQ...
        header, b64_data = data_uri.split(",", 1)
        mime_type = header.split(":")[1].split(";")[0] if ":" in header else "image/jpeg"
        ext = _MIME_TO_EXT.get(mime_type, ".jpg")

        image_bytes = base64.b64decode(b64_data)
        fd, path = tempfile.mkstemp(suffix=ext, prefix="claude_vision_")
        with open(fd, "wb") as f:
            f.write(image_bytes)

        logger.info("Декодировано изображение: %s (%d байт)", path, len(image_bytes))
        return Path(path)
    except Exception as e:
        logger.error("Ошибка декодирования data URI: %s", e)
        return None


def _build_prompt(messages: list[dict[str, Any]]) -> tuple[str, str, list[Path]]:
    """
    Из OpenAI messages array собрать (system_prompt, user_prompt, temp_files).

    system-сообщения → system_prompt.
    Остальные (history + текущий user) → форматируются в единый user_prompt.
    Изображения из multipart content → декодируются во временные файлы.
    """
    system_parts: list[str] = []
    conversation: list[dict[str, Any]] = []
    all_temp_files: list[Path] = []

    for msg in messages:
        if msg["role"] == "system":
            text, files = _extract_content(msg["content"])
            system_parts.append(text)
            all_temp_files.extend(files)
        else:
            conversation.append(msg)

    system_prompt = "\n\n".join(system_parts)

    # Если только один user-message — отправляем как есть
    if len(conversation) == 1 and conversation[0]["role"] == "user":
        text, files = _extract_content(conversation[0]["content"])
        all_temp_files.extend(files)
        return system_prompt, text, all_temp_files

    # Несколько сообщений (history) — форматируем
    parts: list[str] = []
    for msg in conversation:
        role = msg["role"]
        text, files = _extract_content(msg["content"])
        all_temp_files.extend(files)
        if role == "user":
            parts.append(f"Пользователь: {text}")
        elif role == "assistant":
            parts.append(f"Ассистент: {text}")

    return system_prompt, "\n\n".join(parts), all_temp_files


def _make_openai_response(result_text: str, model: str, usage: dict) -> dict[str, Any]:
    """Сформировать ответ в формате OpenAI chat completion."""
    return {
        "id": "",
        "object": "chat.completion",
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": result_text},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": usage.get("input_tokens", 0),
            "completion_tokens": usage.get("output_tokens", 0),
            "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
        },
    }


def _make_stream_chunk(content: str, model: str, finish_reason: str | None = None) -> str:
    """Сформировать один SSE chunk в формате OpenAI."""
    data = {
        "id": "",
        "object": "chat.completion.chunk",
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {"content": content} if content else {},
                "finish_reason": finish_reason,
            }
        ],
    }
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


# --- Вызов Claude CLI ---

async def _call_claude(
    system_prompt: str,
    user_prompt: str,
    model: str,
    files: list[Path] | None = None,
) -> dict[str, Any]:
    """Вызвать claude -p через subprocess (non-streaming)."""
    cmd = [
        "claude", "-p",
        "--model", model,
        "--output-format", "json",
        "--no-session-persistence",  # не сохранять сессию на диск
    ]

    if system_prompt:
        cmd.extend(["--system-prompt", system_prompt])

    # Прикрепить файлы изображений
    if files:
        for f in files:
            cmd.extend(["--file", str(f)])

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=_subprocess_env,
    )

    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=user_prompt.encode("utf-8")),
            timeout=REQUEST_TIMEOUT,
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise HTTPException(status_code=504, detail="Claude CLI таймаут")

    if proc.returncode != 0:
        err_text = stderr.decode("utf-8", errors="replace")[:500]
        logger.error("Claude CLI exit=%d: %s", proc.returncode, err_text)
        raise HTTPException(status_code=502, detail=f"Claude CLI error: {err_text}")

    try:
        data = json.loads(stdout.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.error("Не удалось разобрать ответ Claude CLI: %s", e)
        raise HTTPException(status_code=502, detail="Неверный формат ответа Claude CLI")

    if data.get("is_error"):
        logger.error("Claude CLI вернул ошибку: %s", data.get("result", ""))
        raise HTTPException(status_code=502, detail=data.get("result", "Unknown error"))

    return data


async def _call_claude_stream(
    system_prompt: str,
    user_prompt: str,
    model: str,
    files: list[Path] | None = None,
) -> AsyncGenerator[str, None]:
    """
    Вызвать claude -p через subprocess со стримингом.

    Yields:
        SSE chunks в формате OpenAI (data: {...}\n\n)
    """
    cmd = [
        "claude", "-p",
        "--model", model,
        "--output-format", "stream-json",
        "--verbose",
        "--no-session-persistence",
    ]

    if system_prompt:
        cmd.extend(["--system-prompt", system_prompt])

    if files:
        for f in files:
            cmd.extend(["--file", str(f)])

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=_subprocess_env,
    )

    # Отправить промпт и закрыть stdin
    proc.stdin.write(user_prompt.encode("utf-8"))
    await proc.stdin.drain()
    proc.stdin.close()
    await proc.stdin.wait_closed()

    try:
        async for raw_line in proc.stdout:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line:
                continue

            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            event_type = event.get("type", "")

            # Текстовая дельта (Anthropic API format)
            if event_type == "content_block_delta":
                delta = event.get("delta", {})
                text = delta.get("text", "")
                if text:
                    yield _make_stream_chunk(text, model)

            # Частичное сообщение (Claude CLI format)
            elif event_type == "assistant":
                msg = event.get("message", {})
                if isinstance(msg, dict):
                    content = msg.get("content", "")
                    # content может быть list[{type: "text", text: "..."}] или str
                    if isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                text = block.get("text", "")
                                if text:
                                    yield _make_stream_chunk(text, model)
                    elif isinstance(content, str) and content:
                        yield _make_stream_chunk(content, model)
                elif isinstance(msg, str) and msg:
                    yield _make_stream_chunk(msg, model)

            # Финальный результат
            elif event_type == "result":
                usage = event.get("usage", {})
                logger.info(
                    "STREAM OK model=%s in=%-4d out=%-4d",
                    model,
                    usage.get("input_tokens", 0),
                    usage.get("output_tokens", 0),
                )

            else:
                logger.debug("Stream event: %s", event_type)

        # Финальный chunk: finish_reason=stop
        yield _make_stream_chunk("", model, finish_reason="stop")
        yield "data: [DONE]\n\n"

    finally:
        # Гарантированная очистка процесса
        if proc.returncode is None:
            proc.kill()
        await proc.wait()

        if proc.returncode and proc.returncode != 0:
            stderr_data = await proc.stderr.read()
            err_text = stderr_data.decode("utf-8", errors="replace")[:500]
            logger.error("Claude CLI stream exit=%d: %s", proc.returncode, err_text)


def _cleanup_temp_files(files: list[Path]) -> None:
    """Удалить временные файлы."""
    for f in files:
        try:
            f.unlink(missing_ok=True)
        except OSError:
            pass


# --- Основной эндпоинт ---

@app.post("/v1/chat/completions")
async def chat_completions(request: dict[str, Any]):
    start = time.monotonic()

    messages = request.get("messages", [])
    model = request.get("model", "haiku")
    stream = request.get("stream", False)

    if not messages:
        raise HTTPException(status_code=400, detail="messages обязателен")

    system_prompt, user_prompt, temp_files = _build_prompt(messages)

    # --- Стриминг ---
    if stream:
        async def stream_and_cleanup():
            try:
                async for chunk in _call_claude_stream(
                    system_prompt, user_prompt, model, temp_files
                ):
                    yield chunk
            finally:
                _cleanup_temp_files(temp_files)
                elapsed = time.monotonic() - start
                logger.info("Stream completed in %.1fс", elapsed)

        return StreamingResponse(
            stream_and_cleanup(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    # --- Non-streaming (как раньше) ---
    try:
        data = await _call_claude(system_prompt, user_prompt, model, temp_files)
    finally:
        _cleanup_temp_files(temp_files)

    elapsed = time.monotonic() - start

    result_text = data.get("result", "")
    usage = data.get("usage", {})

    logger.info(
        "OK model=%s in=%-4d out=%-4d %.1fс%s",
        model,
        usage.get("input_tokens", 0),
        usage.get("output_tokens", 0),
        elapsed,
        f" files={len(temp_files)}" if temp_files else "",
    )

    return _make_openai_response(result_text, model, usage)


@app.get("/health")
async def health():
    return {"status": "ok"}
