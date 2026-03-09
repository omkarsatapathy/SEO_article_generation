import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(name)s │ %(message)s",
    datefmt="%H:%M:%S",
)


class EndpointFilter(logging.Filter):
    def __init__(self, path: str):
        self.path = path

    def filter(self, record: logging.LogRecord) -> bool:
        return self.path not in record.getMessage()


# Add filter to uvicorn access logger
logging.getLogger("uvicorn.access").addFilter(EndpointFilter("/jobs/"))
logging.getLogger("uvicorn.access").addFilter(EndpointFilter("/health"))

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
    title="SEO Article Generation API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(log_router)


@app.get("/health")
async def health_check():
    return {"status": "healthy"}

