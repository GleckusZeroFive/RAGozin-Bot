"""Единый реестр команд бота — используется в /help и в промптах LLM."""

BOT_COMMANDS: dict[str, str] = {
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

# Краткий список ключевых команд (одна строка для SYSTEM_PROMPT)
COMMANDS_SHORT = "/docs, /stats, /law, /new, /help"


def format_commands_for_prompt() -> str:
    """Компактный список для вставки в CHAT_PROMPT."""
    return "\n".join(f"• {cmd} — {desc}" for cmd, desc in BOT_COMMANDS.items())


def format_commands_for_help() -> str:
    """Форматирование для /help хендлера."""
    return "\n".join(f"{cmd} — {desc}" for cmd, desc in BOT_COMMANDS.items())
