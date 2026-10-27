"""
The demo application: `uvicorn egc27demo.main:create_app --factory`.

Only reads the experiment's files: no database, no language model. If the
frontend has been built (frontend/dist), it is served from the same address,
so the whole demo runs as one process.
"""
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import __version__, api
from .experiment_store import REPO_ROOT, ExperimentStore

FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"


def create_app(
    data_dir: Optional[Path] = None,
    cache_dir: Optional[Path] = None,
    frontend_dist: Optional[Path] = FRONTEND_DIST,
) -> FastAPI:
    app = FastAPI(
        title="Hex Monitor — Demo EGC27",
        version=__version__,
        description="Replay of the EGC 2027 experiment: LLM completion of AIS gaps, VISTA against Hexa.",
    )
    app.state.experiment = ExperimentStore(data_dir, cache_dir)
    app.include_router(api.router, prefix="/api")

    @app.get("/health", include_in_schema=False)
    def health():
        return {"status": "ok", "data": app.state.experiment.available()}

    # Mounted last, so /api and /health keep precedence over the static files.
    if frontend_dist is not None and Path(frontend_dist, "index.html").exists():
        app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")

    return app
