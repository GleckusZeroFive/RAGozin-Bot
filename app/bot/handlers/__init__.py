from app.bot.handlers.docs import router as docs_router
from app.bot.handlers.keys import router as keys_router
from app.bot.handlers.law import router as law_router
from app.bot.handlers.start import router as start_router
from app.bot.handlers.update import router as update_router
from app.bot.handlers.upload import router as upload_router
from app.bot.handlers.voice import router as voice_router
from app.bot.handlers.query import router as query_router

__all__ = [
    "start_router", "docs_router", "keys_router", "law_router",
    "update_router", "upload_router", "voice_router", "query_router",
]
