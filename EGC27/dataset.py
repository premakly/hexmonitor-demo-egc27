"""Étape 1 : extraction du jeu de données réduit et de la densité a priori.

Une trajectoire = une fenêtre de `window_points` points AIS consécutifs
(200 par défaut, trou compris, contrainte de VISTA), prise dans un segment
continu (aucun écart > max_sampling_gap_min), dans la zone et la période.
Une fenêtre est éligible si le navire y est en route (vitesse médiane
suffisante), traverse assez de cellules pour le plus grand trou plus du
contexte, et respecte le critère de sinuosité de son niveau. Un navire
fournit au plus une fenêtre, choisie au hasard (graine fixe) parmi ses
fenêtres éligibles.

Produit, dans <experiment_dir>/dataset/ :
  - trajectories.parquet : les points des fenêtres retenues (idx 0..N-1) ;
  - vessels.parquet      : une ligne par trajectoire (niveau, type, mesures) ;
  - density_prior.parquet: densité H3 par cellule, SANS les MMSI retenus ;
  - manifest.json        : critères, effectifs, empreintes.

Lancement depuis la racine : python -m EGC27.dataset
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from .config import ExperimentConfig, load_config, write_run_manifest

EARTH_KM = 6371.0088
CONTEXT_CELLS = 5      # cellules de contexte exigées de part et d'autre d'un trou
MIN_CELLS = 42         # cellules minimales par fenêtre (32 + 2 × 5), indépendant des tailles de trou
WINDOW_STRIDE = 25     # pas de glissement entre fenêtres candidates (en points)
MIN_CHORD_KM = 0.5     # en deçà, la sinuosité est considérée infinie (boucle)


# --------------------------------------------------------------- types AIS
def dominant_types(density_cache: Path, resolution: int) -> pd.DataFrame:
    """Type dominant (le plus de points) de chaque MMSI, lu dans le cache."""
    data = json.loads(Path(density_cache).read_text())
    if int(data.get("resolution", -1)) != resolution:
        raise ValueError(
            f"cache de densité en résolution {data.get('resolution')}, configuration en {resolution}"
        )
    rows = []
    for mmsi, per_type in data["by_mmsi"].items():
        totals = {t: sum(c.values()) for t, c in per_type.items()}
        rows.append((int(mmsi), _to_code(max(totals, key=totals.get))))
    return pd.DataFrame(rows, columns=["mmsi", "ship_type"])


def _to_code(value) -> int | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return int(f) if f.is_integer() and f > 0 else None


def level_of(ship_type: pd.Series, cfg: ExperimentConfig) -> pd.Series:
    level = pd.Series(pd.NA, index=ship_type.index, dtype="object")
    for name, lv in cfg.dataset.levels.items():
        level[ship_type.isin(lv.ais_types)] = name
    return level


# --------------------------------------------------------------- segments
def _bounds(cfg: ExperimentConfig) -> list:
    z = cfg.zone
    t0 = int(pd.Timestamp(cfg.period.start, tz="UTC").timestamp())
    t1 = int(pd.Timestamp(cfg.period.end, tz="UTC").timestamp())
    return [t0, t1, z.lon_min, z.lon_max, z.lat_min, z.lat_max]


def long_segments(con, cfg: ExperimentConfig, mmsi: list[int]) -> pd.DataFrame:
    """Segments continus d'au moins `window_points` points, calculés dans DuckDB."""
    con.register("cand", pd.DataFrame({"mmsi": mmsi}))
    return con.execute(
        """
        WITH p AS (
            SELECT p.mmsi, p.ts FROM points p JOIN cand USING (mmsi)
            WHERE p.ts BETWEEN ? AND ?
              AND p.lon BETWEEN ? AND ? AND p.lat BETWEEN ? AND ?
        ), g AS (
            SELECT mmsi, ts,
                   CASE WHEN ts - LAG(ts) OVER w > ? THEN 1 ELSE 0 END AS brk
            FROM p WINDOW w AS (PARTITION BY mmsi ORDER BY ts)
        ), s AS (
            SELECT mmsi, ts, SUM(brk) OVER (PARTITION BY mmsi ORDER BY ts) AS seg FROM g
        )
        SELECT mmsi, seg, MIN(ts) AS t_start, MAX(ts) AS t_end, COUNT(DISTINCT ts) AS n_points
        FROM s GROUP BY mmsi, seg
        HAVING COUNT(DISTINCT ts) >= ?
        ORDER BY mmsi, seg
        """,
        _bounds(cfg) + [cfg.dataset.quality.max_sampling_gap_min * 60, cfg.dataset.window_points],
    ).fetchdf()


def load_points(con, cfg: ExperimentConfig, segs: pd.DataFrame) -> pd.DataFrame:
    con.register("segs", segs[["mmsi", "seg", "t_start", "t_end"]])
    z = cfg.zone
    return con.execute(
        """
        SELECT s.seg, p.mmsi, p.ts, p.lat, p.lon, p.sog, p.cog, p.cell
        FROM points p JOIN segs s ON p.mmsi = s.mmsi AND p.ts BETWEEN s.t_start AND s.t_end
        WHERE p.lon BETWEEN ? AND ? AND p.lat BETWEEN ? AND ?
        ORDER BY p.mmsi, p.ts
        """,
        [z.lon_min, z.lon_max, z.lat_min, z.lat_max],
    ).fetchdf().drop_duplicates(["mmsi", "ts"])


# --------------------------------------------------------------- mesures
def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_KM * np.arcsin(np.sqrt(a))

def _nanstat(f, x):
    """Statistique sur les valeurs renseignées ; NaN (sans avertissement) s'il n'y en a aucune."""
    x = x[~np.isnan(x)]
    return f(x) if len(x) else np.nan

def window_measures(seg: pd.DataFrame, n: int, stride: int) -> pd.DataFrame:
    """Mesures de toutes les fenêtres de n points d'un segment (pas = stride)."""
    lat, lon = seg["lat"].to_numpy(), seg["lon"].to_numpy()
    ts, sog, cells = seg["ts"].to_numpy(), seg["sog"].to_numpy(dtype=float), seg["cell"].to_numpy()
    cog = seg["cog"].to_numpy(dtype=float)
    step_km = np.concatenate([[0.0], np.cumsum(haversine_km(lat[:-1], lon[:-1], lat[1:], lon[1:]))])
    changes = np.concatenate([[0], np.cumsum(cells[1:] != cells[:-1])])

    rows = []
    for s in range(0, len(seg) - n + 1, stride):
        e = s + n - 1
        path = step_km[e] - step_km[s]
        chord = haversine_km(lat[s], lon[s], lat[e], lon[e])
        c = cog[s:e + 1]
        c = np.radians(c[(c >= 0) & (c < 360)])
        rows.append({
            "start": s,
            "t_start": int(ts[s]), "t_end": int(ts[e]),
            "duration_h": (ts[e] - ts[s]) / 3600,
            "length_km": path,
            "sinuosity": path / chord if chord >= MIN_CHORD_KM else np.inf,
            "cog_circ_var": 1 - np.hypot(np.cos(c).mean(), np.sin(c).mean()) if len(c) else np.nan,
            "sog_median": _nanstat(np.median, sog[s:e + 1]),
            "sog_std": _nanstat(np.std, sog[s:e + 1]),
            "n_cells": int(1 + changes[e] - changes[s]),
        })
    return pd.DataFrame(rows)


def eligible_mask(w: pd.DataFrame, level: str, cfg: ExperimentConfig) -> pd.Series:
    lv = cfg.dataset.levels[level]
    ok = (w["sog_median"] >= cfg.dataset.quality.min_median_sog_kn) & (
        w["n_cells"] >= MIN_CELLS
    )
    if lv.max_sinuosity is not None:
        ok &= w["sinuosity"] <= lv.max_sinuosity
    if lv.min_sinuosity is not None:
        ok &= w["sinuosity"] >= lv.min_sinuosity
    return ok


def pick_window(pts: pd.DataFrame, level: str, cfg: ExperimentConfig, seed: int):
    """Une fenêtre éligible du navire, tirée avec une graine propre au MMSI."""
    n = cfg.dataset.window_points
    candidates = []
    for seg_id, seg in pts.groupby("seg", sort=True):
        w = window_measures(seg.reset_index(drop=True), n, WINDOW_STRIDE)
        if w.empty:
            continue
        w = w[eligible_mask(w, level, cfg)]
        if not w.empty:
            candidates.append(w.assign(seg=seg_id))
    if not candidates:
        return None
    pool = pd.concat(candidates, ignore_index=True)
    mmsi = int(pts["mmsi"].iat[0])
    choice = pool.iloc[np.random.default_rng([seed, mmsi]).integers(len(pool))]
    seg = pts[pts["seg"] == choice["seg"]].reset_index(drop=True)
    window = seg.iloc[int(choice["start"]): int(choice["start"]) + n].reset_index(drop=True)
    return choice.drop(["start", "seg"]), window


# --------------------------------------------------------------- densité
def density_prior(density_cache: Path, excluded: set[int]) -> pd.DataFrame:
    """Points par cellule, tous types confondus, sans les MMSI retenus."""
    data = json.loads(Path(density_cache).read_text())
    counts: dict[str, int] = {}
    for mmsi, per_type in data["by_mmsi"].items():
        if int(mmsi) in excluded:
            continue
        for cells in per_type.values():
            for cell, k in cells.items():
                counts[cell] = counts.get(cell, 0) + k
    return pd.DataFrame(sorted(counts.items()), columns=["cell", "count"])


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


# --------------------------------------------------------------- principal
def build(cfg: ExperimentConfig) -> dict:
    out = Path(cfg.paths.experiment_dir) / "dataset"
    out.mkdir(parents=True, exist_ok=True)

    types = dominant_types(cfg.paths.density_cache, cfg.h3.resolution)
    types["level"] = level_of(types["ship_type"], cfg)
    types = types.dropna(subset=["level"])
    level_by_mmsi = dict(zip(types["mmsi"], types["level"]))

    con = duckdb.connect(str(cfg.paths.duckdb), read_only=True)
    segs = long_segments(con, cfg, types["mmsi"].tolist())
    pts = load_points(con, cfg, segs)
    con.close()

    # Une fenêtre éligible par navire, au plus.
    measures, windows = [], {}
    for mmsi, vp in pts.groupby("mmsi", sort=True):
        level = level_by_mmsi[int(mmsi)]
        picked = pick_window(vp, level, cfg, cfg.seed)
        if picked is None:
            continue
        m, w = picked
        measures.append({"mmsi": int(mmsi), "level": level, **m.to_dict()})
        windows[int(mmsi)] = w
    eligible = pd.DataFrame(measures).merge(types[["mmsi", "ship_type"]], on="mmsi") if measures else \
        pd.DataFrame(columns=["mmsi", "level", "ship_type"])

    # Tirage stratifié, déterministe.
    rng = np.random.default_rng(cfg.seed)
    picked = []
    for name in cfg.dataset.levels:
        pool = eligible[eligible["level"] == name].sort_values("mmsi")
        k = min(cfg.dataset.n_per_level, len(pool))
        if k:
            picked.append(pool.iloc[np.sort(rng.choice(len(pool), k, replace=False))])
    selected = pd.concat(picked, ignore_index=True)

    traj = pd.concat(
        [windows[m].assign(idx=np.arange(len(windows[m])), level=lv)
         for m, lv in zip(selected["mmsi"], selected["level"])],
        ignore_index=True,
    ).drop(columns="seg")
    prior = density_prior(cfg.paths.density_cache, set(selected["mmsi"]))

    files = {
        "trajectories": out / "trajectories.parquet",
        "vessels": out / "vessels.parquet",
        "density_prior": out / "density_prior.parquet",
    }
    traj.to_parquet(files["trajectories"], index=False)
    selected.to_parquet(files["vessels"], index=False)
    prior.to_parquet(files["density_prior"], index=False)

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "config_hash": cfg.hash,
        "criteria": {
            "zone": cfg.zone.model_dump(), "period": cfg.period.model_dump(),
            "window_points": cfg.dataset.window_points,
            "quality": cfg.dataset.quality.model_dump(),
            "levels": {k: v.model_dump() for k, v in cfg.dataset.levels.items()},
            "min_cells": MIN_CELLS,
            "window_stride": WINDOW_STRIDE,
        },
        "counts": {
            "typed_by_level": types["level"].value_counts().to_dict(),
            "with_long_segment": int(segs["mmsi"].nunique()),
            "eligible_by_level": eligible["level"].value_counts().to_dict(),
            "selected_by_level": selected["level"].value_counts().to_dict(),
            "points": int(len(traj)),
            "prior_cells": int(len(prior)),
        },
        "mmsi": {lv: sorted(int(m) for m in g["mmsi"]) for lv, g in selected.groupby("level")},
        "files": {k: file_hash(p) for k, p in files.items()},
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    return manifest


if __name__ == "__main__":
    cfg = load_config(resolve_model=False)
    write_run_manifest(cfg, "dataset")
    m = build(cfg)
    print(json.dumps(m["counts"], indent=2, ensure_ascii=False))
