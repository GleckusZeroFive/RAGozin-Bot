from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import TIER_LIMITS
from app.db.models import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        result = await self.session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def get_or_create(
        self,
        telegram_id: int,
        username: str | None = None,
        first_name: str | None = None,
    ) -> User:
        user = await self.get_by_telegram_id(telegram_id)
        if user:
            # Обновляем данные профиля, если изменились
            changed = False
            if username is not None and user.username != username:
                user.username = username
                changed = True
            if first_name is not None and user.first_name != first_name:
                user.first_name = first_name
                changed = True
            if changed:
                await self.session.commit()
            return user

        user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
        )
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def increment_queries_today(self, user_id: int) -> None:
        result = await self.session.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one()
        user.queries_today += 1
        await self.session.commit()

    async def update_tier(
        self,
        user_id: int,
        tier: str,
        expires_at: datetime,
    ) -> None:
        result = await self.session.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one()
        limits = TIER_LIMITS[tier]
        user.tier = tier
        user.tier_expires_at = expires_at
        user.documents_limit = limits["documents_limit"]
        user.queries_limit = limits["queries_limit"]
        await self.session.commit()

    async def revert_to_free(self, user_id: int) -> None:
        result = await self.session.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one()
        limits = TIER_LIMITS["free"]
        user.tier = "free"
        user.tier_expires_at = None
        user.documents_limit = limits["documents_limit"]
        user.queries_limit = limits["queries_limit"]
        await self.session.commit()

    async def reset_daily_queries(self) -> None:
        """Сброс счётчика запросов (для ежедневного cron-а)."""
        result = await self.session.execute(select(User))
        for user in result.scalars():
            user.queries_today = 0
        await self.session.commit()
