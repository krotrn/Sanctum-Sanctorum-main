"""Application factory for the Sanctum Sanctorum Bookstore API."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

import app.models  # noqa: F401  (registers tables on Base.metadata)
from app.clock import get_now
from app.db import Base, SessionLocal, engine
from app.routers import books, loans, members, orders, reports
from app.schemas import HealthOut
from app.seed import seed_if_empty

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Create tables on the default engine and load demo data into an empty database."""
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed_if_empty(db, get_now())
    yield


async def not_implemented_handler(_: Request, exc: NotImplementedError) -> JSONResponse:
    return JSONResponse(status_code=501, content={"detail": f"Not implemented: {exc}"})


def create_app(init_db: bool = True) -> FastAPI:
    application = FastAPI(
        title="Sanctum Sanctorum Bookstore",
        lifespan=lifespan if init_db else None,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.add_exception_handler(NotImplementedError, not_implemented_handler)

    @application.get("/health", response_model=HealthOut, tags=["health"])
    def health():
        return {"status": "ok"}

    application.include_router(books.router)
    application.include_router(members.router)
    application.include_router(orders.router)
    application.include_router(loans.router)
    application.include_router(reports.router)

    # Mounted last so API routes take precedence over static files.
    if FRONTEND_DIR.is_dir():
        application.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

    return application


app = create_app()
