import logging
from datetime import datetime, timedelta, timezone

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import TIER_LIMITS, settings
from app.db.models import User
from app.db.repositories.invite_key import InviteKeyRepository
from app.db.repositories.user import UserRepository

logger = logging.getLogger(__name__)
router = Router()

_TIER_NAMES = {
    "free": "Free",
    "pro": "Pro",
    "admin": "Admin",
}

_VALID_KEY_TIERS = {"pro", "admin"}


@router.message(Command("genkey"))
async def cmd_genkey(
    message: Message, command: CommandObject, user: User, session: AsyncSession
) -> None:
    # Только admin-пользователи могут генерировать ключи
    if user.tier != "admin":
        await message.answer("Генерация ключей доступна только для тарифа <b>Admin</b>.")
        return

    # Парсим аргумент — тариф
    tier = (command.args or "").strip().lower()
    if tier not in _VALID_KEY_TIERS:
        await message.answer(
            "Укажите тариф для ключа:\n"
            "<code>/genkey pro</code> — ключ на тариф Pro\n"
            "<code>/genkey admin</code> — ключ на тариф Admin"
        )
        return

    key_repo = InviteKeyRepository(session)
    invite_key = await key_repo.create(tier=tier, created_by_id=user.id)

    tier_name = _TIER_NAMES[tier]
    limits = TIER_LIMITS[tier]
    await message.answer(
        f"Ключ для тарифа <b>{tier_name}</b> создан:\n\n"
        f"<code>{invite_key.key}</code>\n\n"
        f"Лимиты: {limits['documents_limit']} документов, "
        f"{limits['queries_limit']} запросов/день\n"
        f"Срок действия: {settings.tier_duration_days} дней с момента активации\n"
        "Ключ одноразовый."
    )
    logger.info(
        "Ключ %s (%s) создан пользователем %s",
        invite_key.key, tier, user.telegram_id,
    )


@router.message(Command("activate"))
async def cmd_activate(
    message: Message, command: CommandObject, user: User, session: AsyncSession
) -> None:
    key_str = (command.args or "").strip().upper()
    if not key_str:
        await message.answer("Укажите ключ: <code>/activate XXXX-XXXX-XXXX</code>")
        return

    key_repo = InviteKeyRepository(session)
    invite_key = await key_repo.get_by_key(key_str)

    if not invite_key:
        await message.answer("Ключ не найден.")
        return

    if invite_key.used_by_id is not None:
        await message.answer("Этот ключ уже использован.")
        return

    # Активируем ключ
    new_tier = invite_key.tier
    expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=settings.tier_duration_days)

    user_repo = UserRepository(session)
    await user_repo.update_tier(user.id, new_tier, expires_at)
    await key_repo.mark_used(invite_key, user.id)

    tier_name = _TIER_NAMES.get(new_tier, new_tier)
    expires_str = expires_at.strftime("%d.%m.%Y")
    limits = TIER_LIMITS[new_tier]

    await message.answer(
        f"Тариф <b>{tier_name}</b> активирован!\n\n"
        f"Документов: до {limits['documents_limit']}\n"
        f"Запросов/день: до {limits['queries_limit']}\n"
        f"Действует до: {expires_str}"
    )
    logger.info(
        "Ключ %s активирован пользователем %s → тариф %s до %s",
        invite_key.key, user.telegram_id, new_tier, expires_str,
    )
