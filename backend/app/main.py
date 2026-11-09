"""FastAPI app: routers, CORS, startup (DB + usage sink + job worker)."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import books, characters, compare, export, files, jobs, manual, pages, settings, themes
from .config import get_settings
from .db import init_db
from .jobs.runner import Worker
from .services import usage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    usage.install()
    worker = None
    if get_settings().run_worker:
        worker = Worker(parallel=2)
        worker.start()
    app.state.worker = worker
    try:
        yield
    finally:
        if worker:
            await worker.stop()


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title="Dodo Book Studio", version="1.0.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=s.cors_origins, allow_credentials=False,
                       allow_methods=["*"], allow_headers=["*"])

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/health")
    def api_health():
        from .services.manual import is_manual

        return {"status": "ok", "image_provider": s.image_provider, "text_provider": s.text_provider, "manual_mode": is_manual()}

    for r in (settings, jobs, books, themes, characters, pages, export, files, compare, manual):
        app.include_router(r.router)
    return app


app = create_app()


def run() -> None:  # `python -m app.main`
    import uvicorn

    s = get_settings()
    uvicorn.run("app.main:app", host=s.host, port=s.port, reload=False)


if __name__ == "__main__":
    run()
