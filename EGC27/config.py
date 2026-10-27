"""Chargement, validation et empreinte de la configuration d'expérience."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import httpx
import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

class Paths(BaseModel):
    duckdb: Path
    density_cache: Path
    experiment_dir: Path
    cache_dir: Path
    land_masks: list[Path]


class Zone(BaseModel):
    lon_min: float
    lat_min: float
    lon_max: float
    lat_max: float

    @model_validator(mode="after")
    def _check(self) -> "Zone":
        if not (self.lon_min < self.lon_max and self.lat_min < self.lat_max):
            raise ValueError("zone invalide : min doit être inférieur à max")
        return self


class Period(BaseModel):
    start: str
    end: str


class H3Conf(BaseModel):
    resolution: int = Field(ge=0, le=15)


class LandMask(BaseModel):
    source: str
    scale: str


class Quality(BaseModel):
    max_sampling_gap_min: float
    min_median_sog_kn: float


class Level(BaseModel):
    ais_types: list[int]
    max_sinuosity: float | None = None
    min_sinuosity: float | None = None

    @field_validator("ais_types", mode="before")
    @classmethod
    def _expand_ranges(cls, v: list) -> list[int]:
        """Accepte des entiers ou des plages « 70-79 »."""
        out: list[int] = []
        for item in v:
            if isinstance(item, str) and "-" in item:
                a, b = (int(x) for x in item.split("-"))
                out.extend(range(a, b + 1))
            else:
                out.append(int(item))
        return sorted(set(out))


class Dataset(BaseModel):
    n_per_level: int
    window_points: int = 200
    quality: Quality
    levels: dict[str, Level]


class Gaps(BaseModel):
    sizes_cells: list[int]
    min_context_points: int


class Density(BaseModel):
    exclude_selected_mmsi: bool = True


class LLM(BaseModel):
    provider: Literal["ollama"]
    host: str
    model: str
    model_digest: str | None = None
    options: dict


class Hexa(BaseModel):
    k_ring: int = 1
    max_candidates: int = 3
    max_scenarios: int = 5


class Metrics(BaseModel):
    resample_step_s: int
    bootstrap_samples: int
    invalid_outputs: Literal["exclude"]

class Vista(BaseModel):
    root: Path


class ExperimentConfig(BaseModel):
    seed: int
    paths: Paths
    zone: Zone
    period: Period
    h3: H3Conf
    land_mask: LandMask
    dataset: Dataset
    gaps: Gaps
    density: Density
    llm: LLM
    methods: list[Literal["vista", "hexa", "linear", "astar"]]
    hexa: Hexa
    metrics: Metrics
    vista: Vista

    def canonical_json(self) -> str:
        """Sérialisation stable (clés triées) servant au calcul de l'empreinte."""
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)

    @property
    def hash(self) -> str:
        return hashlib.sha256(self.canonical_json().encode()).hexdigest()[:12]


def load_config(path: str | Path = "./EGC27/experiment.yaml", resolve_model: bool = True) -> ExperimentConfig:
    """Charge et valide la configuration ; renseigne l'empreinte du modèle Ollama."""
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    cfg = ExperimentConfig.model_validate(raw)
    if resolve_model and cfg.llm.model_digest is None:
        cfg.llm.model_digest = _ollama_digest(cfg.llm.host, cfg.llm.model)
    return cfg


def _ollama_digest(host: str, model: str) -> str:
    """Empreinte exacte du modèle installé, pour figer sa version."""
    tags = httpx.get(f"{host}/api/tags", timeout=10).json()
    for m in tags.get("models", []):
        if m["name"] == model or m["model"] == model:
            return m["digest"]
    raise RuntimeError(f"modèle {model} absent d'Ollama")


def _git_commit() -> str | None:
    try:
        sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        dirty = subprocess.run(["git", "diff", "--quiet"]).returncode != 0
        return f"{sha}-dirty" if dirty else sha
    except Exception:
        return None


def write_run_manifest(cfg: ExperimentConfig, run_name: str) -> Path:
    """Enregistre la configuration, son empreinte et le commit git d'une exécution."""
    run_dir = cfg.paths.experiment_dir / "runs" / f"{run_name}_{cfg.hash}"
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "run": run_name,
        "config_hash": cfg.hash,
        "git_commit": _git_commit(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "config": json.loads(cfg.canonical_json()),
    }
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return run_dir


if __name__ == "__main__":
    c = load_config()
    print(f"configuration valide — empreinte {c.hash} — modèle {c.llm.model_digest[:12]}")
