"""Étape 2 : générateur de trous.

Un trou de k cellules retire k cellules successives OBSERVÉES de la
trajectoire : on regroupe les points AIS consécutifs situés dans la même
cellule H3 (un « passage »), puis on retire k passages consécutifs. Chaque
cellule retirée contient donc au moins un point AIS réel, qui sert de vérité
terrain ; VISTA et Hexa perdent exactement les mêmes points.

Le trou laisse au moins CONTEXT_CELLS passages de part et d'autre. Sa position
est tirée avec une graine propre à (graine, MMSI, k) : ajouter une taille plus
tard ne modifie pas les trous déjà créés.

Produit, dans <experiment_dir>/gaps/ :
  - gaps.parquet  : une ligne par trou (indices, ancres, durée, longueurs, cellules) ;
  - truth.parquet : les points retirés (vérité terrain), par gap_id ;
  - manifest.json : tailles, effectifs, empreintes.

Lancement depuis la racine : python -m EGC27.gaps
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .config import ExperimentConfig, load_config, write_run_manifest
from .dataset import CONTEXT_CELLS, file_hash, haversine_km


def cell_passes(track: pd.DataFrame) -> pd.DataFrame:
    """Passages successifs dans une cellule : (cellule, premier idx, dernier idx)."""
    cells = track["cell"].to_numpy()
    run = np.concatenate([[0], np.cumsum(cells[1:] != cells[:-1])])
    idx = track["idx"].to_numpy()
    g = pd.DataFrame({"run": run, "idx": idx, "cell": cells}).groupby("run", sort=True)
    return pd.DataFrame({
        "cell": g["cell"].first(),
        "first": g["idx"].min(),
        "last": g["idx"].max(),
    }).reset_index(drop=True)


def make_gap(track: pd.DataFrame, passes: pd.DataFrame, k: int, seed: int) -> tuple[dict, pd.DataFrame] | None:
    mmsi = int(track["mmsi"].iat[0])
    lo, hi = CONTEXT_CELLS, len(passes) - CONTEXT_CELLS - k  # premier passage retiré ∈ [lo, hi]
    if hi < lo:
        return None
    r = lo + int(np.random.default_rng([seed, mmsi, k]).integers(hi - lo + 1))
    i0, i1 = int(passes.at[r, "first"]), int(passes.at[r + k - 1, "last"])

    t = track.set_index("idx")
    before, after = t.loc[i0 - 1], t.loc[i1 + 1]
    removed = t.loc[i0:i1]
    lat = np.concatenate([[before.lat], removed["lat"], [after.lat]])
    lon = np.concatenate([[before.lon], removed["lon"], [after.lon]])

    gap_id = f"{mmsi}_c{k}"
    row = {
        "gap_id": gap_id,
        "mmsi": mmsi,
        "level": track["level"].iat[0],
        "size_cells": k,
        "idx_start": i0,               # premier point retiré
        "idx_end": i1,                 # dernier point retiré (inclus)
        "n_removed": i1 - i0 + 1,
        "t_before": int(before.ts),    # dernier point connu avant le trou
        "t_after": int(after.ts),      # premier point connu après le trou
        "duration_h": (after.ts - before.ts) / 3600,
        "length_km": float(haversine_km(lat[:-1], lon[:-1], lat[1:], lon[1:]).sum()),
        "chord_km": float(haversine_km(before.lat, before.lon, after.lat, after.lon)),
        "cell_before": before.cell,
        "cell_after": after.cell,
        "cells": passes.loc[r:r + k - 1, "cell"].tolist(),
    }
    truth = removed.reset_index().assign(gap_id=gap_id)
    return row, truth


def build(cfg: ExperimentConfig) -> dict:
    root = Path(cfg.paths.experiment_dir)
    traj = pd.read_parquet(root / "dataset" / "trajectories.parquet")
    out = root / "gaps"
    out.mkdir(parents=True, exist_ok=True)

    rows, truths, skipped = [], [], []
    for mmsi, track in traj.groupby("mmsi", sort=True):
        track = track.sort_values("idx").reset_index(drop=True)
        passes = cell_passes(track)
        for k in sorted(cfg.gaps.sizes_cells):
            made = make_gap(track, passes, k, cfg.seed)
            if made is None:
                skipped.append({"mmsi": int(mmsi), "size_cells": k, "n_passes": len(passes)})
                continue
            rows.append(made[0])
            truths.append(made[1])

    gaps = pd.DataFrame(rows)
    truth = pd.concat(truths, ignore_index=True)
    files = {"gaps": out / "gaps.parquet", "truth": out / "truth.parquet"}
    gaps.to_parquet(files["gaps"], index=False)
    truth.to_parquet(files["truth"], index=False)

    summary = (gaps.groupby(["level", "size_cells"])
               .agg(n=("gap_id", "size"), points=("n_removed", "median"),
                    duration_h=("duration_h", "median"), length_km=("length_km", "median"))
               .round(2).reset_index())
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "config_hash": cfg.hash,
        "dataset_hash": file_hash(root / "dataset" / "trajectories.parquet"),
        "sizes_cells": sorted(cfg.gaps.sizes_cells),
        "context_cells": CONTEXT_CELLS,
        "counts": {"gaps": int(len(gaps)), "truth_points": int(len(truth)), "skipped": skipped},
        "summary_medians": summary.to_dict(orient="records"),
        "files": {k: file_hash(p) for k, p in files.items()},
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    return manifest


if __name__ == "__main__":
    cfg = load_config(resolve_model=False)
    write_run_manifest(cfg, "gaps")
    m = build(cfg)
    print(f"{m['counts']['gaps']} trous, {m['counts']['truth_points']} points de vérité terrain")
    print(pd.DataFrame(m["summary_medians"]).to_string(index=False))
    if m["counts"]["skipped"]:
        print("trajectoires trop courtes :", m["counts"]["skipped"])
