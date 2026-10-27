"""Contrat commun des méthodes de complétion (étape 3).

Entrée d'une méthode, pour chaque trou (gap_contexts) : les deux points
d'ancrage (dernier point connu avant le trou, premier après), leurs cellules,
le cap et la vitesse au départ, et les instants auxquels produire des points
(ceux des points retirés, comme VISTA les reçoit).

Sortie, dans <experiment_dir>/completions/ :
  - {méthode}_c{k}.parquet          : gap_id, method, idx, ts, lat, lon
                                      (un point par point retiré) ;
  - {méthode}_c{k}_outcomes.parquet : gap_id, method, status ("ok"/"failed"),
                                      reason, latency_s, tokens, path (cellules,
                                      pour les méthodes qui en parcourent).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import h3
import numpy as np
import pandas as pd

from .config import ExperimentConfig
from .dataset import haversine_km

POINT_COLUMNS = ["gap_id", "method", "idx", "ts", "lat", "lon"]


def gap_contexts(cfg: ExperimentConfig, size: int, limit: int | None = None) -> pd.DataFrame:
    """Une ligne par trou de la taille demandée, avec ancres et instants cibles."""
    root = Path(cfg.paths.experiment_dir)
    traj = pd.read_parquet(root / "dataset" / "trajectories.parquet").set_index(["mmsi", "idx"])
    gaps = pd.read_parquet(root / "gaps" / "gaps.parquet")
    truth = pd.read_parquet(root / "gaps" / "truth.parquet")
    gaps = gaps[gaps["size_cells"] == size].sort_values("mmsi").reset_index(drop=True)
    if limit:
        gaps = gaps.head(limit)

    targets = truth.sort_values("idx").groupby("gap_id").agg(target_idx=("idx", list), target_ts=("ts", list))
    rows = []
    for g in gaps.itertuples():
        before = traj.loc[(g.mmsi, g.idx_start - 1)]
        after = traj.loc[(g.mmsi, g.idx_end + 1)]
        rows.append({
            "gap_id": g.gap_id, "mmsi": g.mmsi, "level": g.level, "size_cells": g.size_cells,
            "lat_before": before.lat, "lon_before": before.lon, "ts_before": int(before.ts),
            "sog_before": before.sog, "cog_before": before.cog, "cell_before": before.cell,
            "lat_after": after.lat, "lon_after": after.lon, "ts_after": int(after.ts), "cell_after": after.cell,
        })
    return pd.DataFrame(rows).merge(targets, left_on="gap_id", right_index=True)


def cells_to_waypoints(path: list[str], ctx) -> np.ndarray:
    """
    Points de passage d'un chemin de cellules : le vrai point d'ancrage à
    chaque bout, et le centre de chaque cellule intermédiaire.
    """
    inner = [h3.cell_to_latlng(c) for c in path[1:-1]]
    return np.array([(ctx.lat_before, ctx.lon_before), *inner, (ctx.lat_after, ctx.lon_after)], dtype=float)


def smooth(waypoints: np.ndarray, iterations: int = 2) -> np.ndarray:
    """
    Lissage de Chaikin : chaque angle est coupé au quart de ses côtés, les deux
    extrémités (les vraies ancres) restant fixes. Atténue le zigzag imposé par
    le passage aux centres des cellules.
    """
    pts = np.asarray(waypoints, dtype=float)
    for _ in range(iterations):
        if len(pts) < 3:
            return pts
        a, b = pts[:-1], pts[1:]
        q, r = 0.75 * a + 0.25 * b, 0.25 * a + 0.75 * b
        inner = np.column_stack([q, r]).reshape(-1, 2)[1:-1]
        pts = np.vstack([pts[:1], inner, pts[-1:]])
    return pts


def place_along(waypoints: np.ndarray, ts_before: int, ts_after: int, targets: list[int]) -> np.ndarray:
    """
    Positions aux instants cibles, à vitesse constante le long de la ligne
    brisée : la fraction de temps écoulée donne la fraction de distance.
    """
    lat, lon = waypoints[:, 0], waypoints[:, 1]
    step = haversine_km(lat[:-1], lon[:-1], lat[1:], lon[1:]) if len(waypoints) > 1 else np.array([])
    cum = np.concatenate([[0.0], np.cumsum(step)])
    total = cum[-1]
    frac = (np.asarray(targets, dtype=float) - ts_before) / max(ts_after - ts_before, 1)
    if total == 0:
        return np.repeat(waypoints[:1], len(targets), axis=0)
    dist = np.clip(frac, 0, 1) * total
    return np.column_stack([np.interp(dist, cum, lat), np.interp(dist, cum, lon)])


def points_frame(ctx, method: str, positions: np.ndarray) -> pd.DataFrame:
    return pd.DataFrame({
        "gap_id": ctx.gap_id, "method": method,
        "idx": ctx.target_idx, "ts": ctx.target_ts,
        "lat": positions[:, 0], "lon": positions[:, 1],
    })


def write_completions(cfg: ExperimentConfig, method: str, size: int, points: list[pd.DataFrame],
                      outcomes: list[dict], params: dict, limit: int | None = None) -> None:
    dest = Path(cfg.paths.experiment_dir) / "completions"
    dest.mkdir(parents=True, exist_ok=True)
    name = f"{method}_c{size}" + (f"_essai{limit}" if limit else "")
    pts = pd.concat(points, ignore_index=True) if points else pd.DataFrame(columns=POINT_COLUMNS)
    out = pd.DataFrame(outcomes)
    pts.to_parquet(dest / f"{name}.parquet", index=False)
    out.to_parquet(dest / f"{name}_outcomes.parquet", index=False)
    (dest / f"{name}_manifest.json").write_text(json.dumps({
        "method": method, "size_cells": size, "config_hash": cfg.hash, "params": params,
        "gaps": len(out), "ok": int((out["status"] == "ok").sum()) if len(out) else 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }, indent=2, ensure_ascii=False))
    print(f"{method} c{size} : {int((out['status'] == 'ok').sum())}/{len(out)} trous complétés → {dest / name}.parquet")
