from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.commands import format_commands_for_help
from app.core.conversation import clear_context
from app.presets import get_preset
from app.db.models import User
from app.db.repositories.document import DocumentRepository

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, user: User) -> None:
    preset = get_preset()
    name = user.first_name or user.username or "пользователь"

    if preset.messages.start:
        text = preset.messages.start.format(
            user_name=name,
            bot_name=preset.name,
        )
    else:
        text = (
            f"Привет, <b>{name}</b>! Я — <b>{preset.name}</b>, AI-ассистент по документам.\n\n"
            "Отправь мне файл (PDF, DOCX, TXT, MD) — я проиндексирую его "
            "и смогу отвечать на вопросы по содержимому.\n\n"
            "/help — все команды\n"
            "/about — о боте"
        )
    await message.answer(text)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    preset = get_preset()

    if preset.messages.help:
        text = preset.messages.help.format(
            commands_help=format_commands_for_help(),
            bot_name=preset.name,
        )
    else:
        text = (
            f"<b>Команды:</b>\n"
            f"{format_commands_for_help()}\n\n"
            "<b>Загрузка документов:</b>\n"
            "Отправь файл (PDF, DOCX, TXT, MD) — я его проиндексирую.\n\n"
            "<b>Вопросы:</b>\n"
            "Отправь текстовое сообщение — я поищу ответ.\n"
            "Уточняющие вопросы учитывают контекст диалога.\n\n"
            "<b>Голосовые сообщения:</b>\n"
            "Отправь голосовое — я распознаю речь и поищу ответ."
        )
    await message.answer(text)


@router.message(Command("about"))
async def cmd_about(message: Message) -> None:
    preset = get_preset()

    if preset.messages.about:
        text = preset.messages.about.format(bot_name=preset.name)
    else:
        text = (
            f"<b>{preset.name} — AI-ассистент по документам</b>\n\n"
            "Загружайте документы (PDF, DOCX, TXT, MD) и задавайте вопросы.\n\n"
            "<b>Возможности:</b>\n"
            "• Умный поиск по загруженным документам\n"
            "• Голосовые сообщения\n"
            "• Контекстный диалог с памятью\n\n"
            "Версия: 1.0"
        )
    await message.answer(text)


@router.message(Command("new"))
async def cmd_new(message: Message, user: User, **kwargs) -> None:
    clear_context(user.telegram_id)
    await message.answer("\u041a\u043e\u043d\u0442\u0435\u043a\u0441\u0442 \u0434\u0438\u0430\u043b\u043e\u0433\u0430 \u0441\u0431\u0440\u043e\u0448\u0435\u043d. \u041c\u043e\u0436\u0435\u0442\u0435 \u0437\u0430\u0434\u0430\u0442\u044c \u043d\u043e\u0432\u044b\u0439 \u0432\u043e\u043f\u0440\u043e\u0441.")


@router.message(Command("stats"))
async def cmd_stats(message: Message, user: User, session: AsyncSession) -> None:
    doc_repo = DocumentRepository(session)
    docs = await doc_repo.get_by_user(user.id)
    ready_count = sum(1 for d in docs if d.status == "ready")
    total_chunks = sum(d.chunk_count for d in docs)
    registered = user.created_at.strftime("%d.%m.%Y")

    tier_names = {"free": "Free", "pro": "Pro", "admin": "Admin"}
    tier_name = tier_names.get(user.tier, user.tier)

    tier_line = f"\u0422\u0430\u0440\u0438\u0444: <b>{tier_name}</b>"
    if user.tier != "free" and user.tier_expires_at:
        tier_line += f" (\u0434\u043e {user.tier_expires_at.strftime('%d.%m.%Y')})"

    is_unlimited = user.documents_limit >= 999_000
    if is_unlimited:
        docs_line = f"\u0414\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u043e\u0432: {len(docs)} (\u0433\u043e\u0442\u043e\u0432\u044b\u0445: {ready_count})"
        queries_line = f"\u0417\u0430\u043f\u0440\u043e\u0441\u043e\u0432 \u0441\u0435\u0433\u043e\u0434\u043d\u044f: {user.queries_today}"
    else:
        docs_line = f"\u0414\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u043e\u0432: {len(docs)} \u0438\u0437 {user.documents_limit} (\u0433\u043e\u0442\u043e\u0432\u044b\u0445: {ready_count})"
        queries_line = f"\u0417\u0430\u043f\u0440\u043e\u0441\u043e\u0432 \u0441\u0435\u0433\u043e\u0434\u043d\u044f: {user.queries_today} \u0438\u0437 {user.queries_limit}"

    # Progress bar for queries
    if not is_unlimited and user.queries_limit > 0:
        ratio = user.queries_today / user.queries_limit
        filled = int(ratio * 10)
        bar = "\u2588" * filled + "\u2591" * (10 - filled)
        queries_line += f"  [{bar}]"

    await message.answer(
        f"\U0001f4ca <b>\u0421\u0442\u0430\u0442\u0438\u0441\u0442\u0438\u043a\u0430</b>\n\n"
        f"\U0001f464 {tier_line}\n"
        f"\U0001f4c4 {docs_line}\n"
        f"\U0001f9e9 \u0424\u0440\u0430\u0433\u043c\u0435\u043d\u0442\u043e\u0432: {total_chunks}\n"
        f"\U0001f4ac {queries_line}\n"
        f"\U0001f4c5 \u0417\u0430\u0440\u0435\u0433\u0438\u0441\u0442\u0440\u0438\u0440\u043e\u0432\u0430\u043d: {registered}"
    )
