from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.commands import format_commands_for_help
from app.core.conversation import clear_context
from app.db.models import User
from app.db.repositories.document import DocumentRepository

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, user: User) -> None:
    name = user.first_name or user.username or "\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044c"
    await message.answer(
        f"\u041f\u0440\u0438\u0432\u0435\u0442, <b>{name}</b>! \u042f \u2014 <b>RAGozin</b>, AI-\u0430\u0441\u0441\u0438\u0441\u0442\u0435\u043d\u0442 \u043f\u043e \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u0430\u043c.\n\n"
        "\u041e\u0442\u043f\u0440\u0430\u0432\u044c \u043c\u043d\u0435 \u0444\u0430\u0439\u043b (PDF, DOCX, TXT, MD) \u2014 \u044f \u043f\u0440\u043e\u0438\u043d\u0434\u0435\u043a\u0441\u0438\u0440\u0443\u044e \u0435\u0433\u043e "
        "\u0438 \u0441\u043c\u043e\u0433\u0443 \u043e\u0442\u0432\u0435\u0447\u0430\u0442\u044c \u043d\u0430 \u0432\u043e\u043f\u0440\u043e\u0441\u044b \u043f\u043e \u0441\u043e\u0434\u0435\u0440\u0436\u0438\u043c\u043e\u043c\u0443.\n\n"
        "/help \u2014 \u0432\u0441\u0435 \u043a\u043e\u043c\u0430\u043d\u0434\u044b\n"
        "/about \u2014 \u043e \u0431\u043e\u0442\u0435"
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        f"<b>\u041a\u043e\u043c\u0430\u043d\u0434\u044b:</b>\n"
        f"{format_commands_for_help()}\n\n"
        "<b>\u0417\u0430\u0433\u0440\u0443\u0437\u043a\u0430 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u043e\u0432:</b>\n"
        "\u041e\u0442\u043f\u0440\u0430\u0432\u044c \u0444\u0430\u0439\u043b (PDF, DOCX, TXT, MD) \u2014 \u044f \u0435\u0433\u043e \u043f\u0440\u043e\u0438\u043d\u0434\u0435\u043a\u0441\u0438\u0440\u0443\u044e.\n\n"
        "<b>\u0412\u043e\u043f\u0440\u043e\u0441\u044b:</b>\n"
        "\u041e\u0442\u043f\u0440\u0430\u0432\u044c \u0442\u0435\u043a\u0441\u0442\u043e\u0432\u043e\u0435 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435 \u2014 \u044f \u043f\u043e\u0438\u0449\u0443 \u043e\u0442\u0432\u0435\u0442 \u0432 \u0437\u0430\u0433\u0440\u0443\u0436\u0435\u043d\u043d\u044b\u0445 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u0430\u0445.\n"
        "\u0423\u0442\u043e\u0447\u043d\u044f\u044e\u0449\u0438\u0435 \u0432\u043e\u043f\u0440\u043e\u0441\u044b (\"А что ещё?\", \"Подробнее\") \u0443\u0447\u0438\u0442\u044b\u0432\u0430\u044e\u0442 \u043a\u043e\u043d\u0442\u0435\u043a\u0441\u0442 \u0434\u0438\u0430\u043b\u043e\u0433\u0430.\n\n"
        "<b>\u0413\u043e\u043b\u043e\u0441\u043e\u0432\u044b\u0435 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u044f:</b>\n"
        "\u041e\u0442\u043f\u0440\u0430\u0432\u044c \u0433\u043e\u043b\u043e\u0441\u043e\u0432\u043e\u0435 \u2014 \u044f \u0440\u0430\u0441\u043f\u043e\u0437\u043d\u0430\u044e \u0440\u0435\u0447\u044c \u0438 \u043f\u043e\u0438\u0449\u0443 \u043e\u0442\u0432\u0435\u0442 \u0432 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u0430\u0445."
    )


@router.message(Command("about"))
async def cmd_about(message: Message) -> None:
    await message.answer(
        "<b>RAGozin \u2014 AI-\u0430\u0441\u0441\u0438\u0441\u0442\u0435\u043d\u0442 \u043f\u043e \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u0430\u043c</b>\n\n"
        "\u0417\u0430\u0433\u0440\u0443\u0436\u0430\u0439\u0442\u0435 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u044b (PDF, DOCX, TXT, MD) \u0438 \u0437\u0430\u0434\u0430\u0432\u0430\u0439\u0442\u0435 \u0432\u043e\u043f\u0440\u043e\u0441\u044b \u2014 "
        "\u0431\u043e\u0442 \u043d\u0430\u0439\u0434\u0451\u0442 \u043e\u0442\u0432\u0435\u0442\u044b \u0432 \u0432\u0430\u0448\u0438\u0445 \u0444\u0430\u0439\u043b\u0430\u0445 \u0441 \u043f\u043e\u043c\u043e\u0449\u044c\u044e \u0442\u0435\u0445\u043d\u043e\u043b\u043e\u0433\u0438\u0438 RAG "
        "(Retrieval-Augmented Generation).\n\n"
        "<b>\u0412\u043e\u0437\u043c\u043e\u0436\u043d\u043e\u0441\u0442\u0438:</b>\n"
        "\u2022 \u0423\u043c\u043d\u044b\u0439 \u043f\u043e\u0438\u0441\u043a \u043f\u043e \u0437\u0430\u0433\u0440\u0443\u0436\u0435\u043d\u043d\u044b\u043c \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u0430\u043c\n"
        "\u2022 \u041f\u043e\u0438\u0441\u043a \u043f\u043e \u0437\u0430\u043a\u043e\u043d\u043e\u0434\u0430\u0442\u0435\u043b\u044c\u0441\u0442\u0432\u0443 \u0420\u0424\n"
        "\u2022 \u0413\u043e\u043b\u043e\u0441\u043e\u0432\u044b\u0435 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u044f\n"
        "\u2022 \u041a\u043e\u043d\u0442\u0435\u043a\u0441\u0442\u043d\u044b\u0439 \u0434\u0438\u0430\u043b\u043e\u0433 \u0441 \u043f\u0430\u043c\u044f\u0442\u044c\u044e\n\n"
        "\u0412\u0435\u0440\u0441\u0438\u044f: 1.0"
    )


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
