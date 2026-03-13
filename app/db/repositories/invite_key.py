import random
import string
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import InviteKey

# Символы без амбивалентных (0/O, 1/I/L)
_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def generate_key() -> str:
    """Генерация ключа формата XXXX-XXXX-XXXX."""
    chars = "".join(random.choices(_ALPHABET, k=12))
    return f"{chars[:4]}-{chars[4:8]}-{chars[8:12]}"


class InviteKeyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, tier: str, created_by_id: int | None = None) -> InviteKey:
        key = InviteKey(
            key=generate_key(),
            tier=tier,
            created_by_id=created_by_id,
        )
        self.session.add(key)
        await self.session.commit()
        await self.session.refresh(key)
        return key

    async def get_by_key(self, key: str) -> InviteKey | None:
        result = await self.session.execute(
            select(InviteKey).where(InviteKey.key == key)
        )
        return result.scalar_one_or_none()

    async def mark_used(self, invite_key: InviteKey, user_id: int) -> None:
        invite_key.used_by_id = user_id
        invite_key.used_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await self.session.commit()

    async def get_by_creator(self, user_id: int) -> list[InviteKey]:
        result = await self.session.execute(
            select(InviteKey)
            .where(InviteKey.created_by_id == user_id)
            .order_by(InviteKey.created_at.desc())
        )
        return list(result.scalars().all())
