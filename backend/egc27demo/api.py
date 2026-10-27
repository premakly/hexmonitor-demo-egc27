"""The EGC 2027 experiment, read-only: results, gaps, and replayed completions."""
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from .experiment_store import ExperimentMissing, ExperimentStore

router = APIRouter(tags=["experiment"])


def _store(request: Request) -> ExperimentStore:
    return request.app.state.experiment


@router.get("/experiment")
def experiment_overview(request: Request):
    """Gap sizes, levels and methods found, with the aggregated results once computed."""
    try:
        return _store(request).overview()
    except ExperimentMissing as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/experiment/gaps")
def experiment_gaps(request: Request, size: Optional[int] = None, level: Optional[str] = None):
    try:
        return {"gaps": _store(request).gaps(size=size, level=level)}
    except ExperimentMissing as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/experiment/gaps/{gap_id}")
def experiment_gap(gap_id: str, request: Request):
    """One gap: its 200-point window, the ground truth, and every method's completion."""
    try:
        detail = _store(request).gap(gap_id)
    except ExperimentMissing as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    if detail is None:
        raise HTTPException(status_code=404, detail=f"no such gap: {gap_id}")
    return detail


@router.get("/experiment/export/{name}.csv")
def experiment_export(name: str, request: Request):
    path = _store(request).export_path(name)
    if path is None:
        raise HTTPException(
            status_code=404,
            detail=f"no {name} table: run `python -m EGC27.metrics` to produce it",
        )
    return FileResponse(path, media_type="text/csv", filename=f"experiment_{name}.csv")
