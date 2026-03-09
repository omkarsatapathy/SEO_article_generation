import logging

from config.config import cfg

_log_cfg = cfg.settings.logging

logging.basicConfig(
    level=getattr(logging, _log_cfg.level, logging.INFO),
    format=_log_cfg.format,
    datefmt=_log_cfg.datefmt,
)


class EndpointFilter(logging.Filter):
    def __init__(self, path: str):
        self.path = path

    def filter(self, record: logging.LogRecord) -> bool:
        return self.path not in record.getMessage()


# Add filter to uvicorn access logger for paths defined in config
_access_logger = logging.getLogger("uvicorn.access")
for _filtered_path in cfg.settings.logging.filtered_paths:
    _access_logger.addFilter(EndpointFilter(_filtered_path))

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.api.log_stream import router as log_router
from app.config import settings
from app.db.repository import init_db

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run startup tasks before the application begins serving requests."""
    try:
        await init_db(settings.DATABASE_URL)
        logger.info("Database initialised successfully.")
    except Exception as exc:
        logger.warning("Database not available at startup (%s). DB-dependent routes will fail.", exc)
    yield


app = FastAPI(
    title=cfg.settings.app.title,
    version=cfg.settings.app.version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cfg.settings.cors.allow_origins,
    allow_credentials=cfg.settings.cors.allow_credentials,
    allow_methods=cfg.settings.cors.allow_methods,
    allow_headers=cfg.settings.cors.allow_headers,
)

app.include_router(router)
app.include_router(log_router)


@app.get("/health")
async def health_check():
    return {"status": "healthy"}

