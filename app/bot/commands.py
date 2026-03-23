"""Единый реестр команд бота — используется в /help и в промптах LLM.

Команды загружаются из пресета (app/presets/*.yml).
Если пресет не задаёт команды — используются дефолтные.
"""

from __future__ import annotations

_DEFAULT_COMMANDS: dict[str, str] = {
    "/start": "Начать работу с ботом",
    "/help": "Справка по командам",
    "/docs": "Мои документы",
    "/update": "Обновить документ (замена или дополнение)",
    "/delete": "Удалить документ",
    "/stats": "Статистика и лимиты",
    "/reset": "Удалить все документы",
    "/activate": "Активировать ключ подписки",
    "/genkey": "Сгенерировать ключ (Admin)",
    "/new": "Сбросить контекст диалога",
    "/about": "О боте",
    "/law": "Вкл/выкл поиск по законодательству РФ",
    "/lawstats": "Статистика базы законодательства",
}

_DEFAULT_SHORT = "/docs, /stats, /law, /new, /help"


def _get_commands() -> dict[str, str]:
    """Получить команды из пресета или дефолтные."""
    from app.presets import get_preset
    preset = get_preset()
    if preset.commands.items:
        return {f"/{k}": v for k, v in preset.commands.items.items()}
    return _DEFAULT_COMMANDS


def _get_commands_short() -> str:
    """Краткий список команд для SYSTEM_PROMPT."""
    from app.presets import get_preset
    preset = get_preset()
    return preset.commands.short or _DEFAULT_SHORT


# Ленивые свойства — вычисляются при первом вызове
BOT_COMMANDS = property(lambda self: _get_commands())
COMMANDS_SHORT = property(lambda self: _get_commands_short())


def format_commands_for_prompt() -> str:
    """Компактный список для вставки в CHAT_PROMPT."""
    commands = _get_commands()
    return "\n".join(f"\u2022 {cmd} — {desc}" for cmd, desc in commands.items())


def format_commands_for_help() -> str:
    """Форматирование для /help хендлера."""
    commands = _get_commands()
    return "\n".join(f"{cmd} — {desc}" for cmd, desc in commands.items())
