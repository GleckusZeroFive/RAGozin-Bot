from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings


class Database:
    def __init__(self) -> None:
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    async def connect(self, database_url: str | None = None) -> None:
        url = database_url or settings.database_url
        self._engine = create_async_engine(url, echo=False, pool_size=10, max_overflow=20)
        self._session_factory = async_sessionmaker(
            bind=self._engine,
            expire_on_commit=False,
        )

    async def disconnect(self) -> None:
        if self._engine:
            await self._engine.dispose()

    def get_session(self) -> AsyncSession:
        if not self._session_factory:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._session_factory()


db = Database()
