from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.v1.auth import auth, profile
from app.api.v1.extras import admin, notifications, pages, public
from app.api.v1.monitors import dashboard, incidents, monitors
from app.core.config import settings
from app.core.security import redis_client
from app.db.session import session_factory


@asynccontextmanager
async def lifespan(_app):
    yield
    await redis_client().aclose()
    await session_factory().kw["bind"].dispose()


def create_app() -> FastAPI:
    config = settings()
    app = FastAPI(
        title="PulseMonitor API", version="1.0.0", docs_url="/api/docs", redoc_url="/api/redoc",
        openapi_url="/api/openapi.json", debug=config.app_debug, lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware, allow_origins=config.origins, allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"], allow_headers=["Authorization", "Content-Type"],
    )

    @app.middleware("http")
    async def prevent_caching(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, error: RequestValidationError):
        # Request validation errors can otherwise echo passwords, tokens and private monitor URLs.
        fields = [".".join(map(str, item["loc"][1:])) for item in error.errors()]
        return JSONResponse(status_code=422, content={"detail": "Проверьте поля запроса", "fields": fields})

    api = APIRouter(prefix="/api/v1")
    for router in (auth, profile, monitors, dashboard, incidents, pages, public, notifications, admin):
        api.include_router(router)

    @api.get("/health", tags=["system"])
    async def health():
        return {"status": "ok"}

    @api.get("/ready", tags=["system"])
    async def ready():
        try:
            async with session_factory()() as db:
                await db.execute(text("SELECT 1 FROM alembic_version"))
            await redis_client().ping()
        except (SQLAlchemyError, RedisError, OSError) as exc:
            raise HTTPException(503, "Сервисы ещё запускаются") from exc
        return {"status": "ready"}

    app.include_router(api)
    return app
