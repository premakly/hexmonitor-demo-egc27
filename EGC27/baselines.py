"""Étape 6 : références simples, sans LLM.

  - linear : interpolation linéaire entre les deux points d'ancrage, à vitesse
    constante ;
  - astar  : plus court chemin sur la grille H3, de la cellule d'ancrage avant
    à la cellule d'ancrage après. Entrer dans une cellule coûte d'autant moins
    qu'elle est fréquentée (densité a priori, calculée sans les MMSI retenus) ;
    les cellules terrestres sont interdites. Les positions sont ensuite placées
    le long du chemin comme pour Hexa (même conversion cellules → points).

Usage, depuis la racine : python -m EGC27.baselines --size 2
"""

from __future__ import annotations

import argparse
import heapq
import math
import time
from pathlib import Path

import h3
import numpy as np
import pandas as pd

from .completion import cells_to_waypoints, gap_contexts, place_along, points_frame, write_completions
from .config import ExperimentConfig, load_config
from .landmask import LandMask

# Coût d'entrée dans une cellule : 1 + DENSITY_WEIGHT × (1 − log(1+n) / log(1+n_max)).
# Une cellule très fréquentée coûte 1, une cellule jamais vue 1 + DENSITY_WEIGHT.
# Le coût minimal valant 1, la distance de grille reste une heuristique admissible.
DENSITY_WEIGHT = 4.0
# Rayon de recherche autour des ancres : RADIUS_FACTOR × distance initiale + RADIUS_MARGIN.
RADIUS_FACTOR = 3
RADIUS_MARGIN = 5


def linear(ctx) -> np.ndarray:
    waypoints = np.array([(ctx.lat_before, ctx.lon_before), (ctx.lat_after, ctx.lon_after)])
    return place_along(waypoints, ctx.ts_before, ctx.ts_after, ctx.target_ts)


class DensityCost:
    def __init__(self, prior: pd.DataFrame):
        self.counts = dict(zip(prior["cell"], prior["count"]))
        self.log_max = math.log1p(max(self.counts.values(), default=1))

    def __call__(self, cell: str) -> float:
        n = self.counts.get(cell, 0)
        return 1.0 + DENSITY_WEIGHT * (1.0 - math.log1p(n) / self.log_max)


def astar(start: str, goal: str, cost: DensityCost, land: LandMask | None) -> list[str] | None:
    """Chemin de cellules de start à goal (inclus), ou None s'il n'en existe pas."""
    if start == goal:
        return [start]
    radius = RADIUS_FACTOR * h3.grid_distance(start, goal) + RADIUS_MARGIN
    land_cache: dict[tuple[str, str], bool] = {}

    def blocked(cur: str, nxt: str) -> bool:
        """
        Pas interdit si la cellule d'arrivée est terrestre, ou si le segment
        entre les deux centres touche la terre : tester les seuls centres
        laisserait franchir une presqu'île ou une île plus étroite qu'une
        cellule. Les ancres sont exemptées, puisqu'un navire peut se trouver
        dans une cellule côtière (port, estuaire).
        """
        if land is None:
            return False
        key = (cur, nxt)
        if key not in land_cache:
            if nxt == goal or cur == start:
                land_cache[key] = nxt != goal and land.cell_on_land(nxt)
            else:
                land_cache[key] = land.cell_on_land(nxt) or land.crosses_land(
                    h3.cell_to_latlng(cur), h3.cell_to_latlng(nxt))
        return land_cache[key]

    g = {start: 0.0}
    came: dict[str, str] = {}
    heap = [(h3.grid_distance(start, goal), 0.0, start)]
    while heap:
        _, g_cur, cur = heapq.heappop(heap)
        if cur == goal:
            path = [cur]
            while cur in came:
                cur = came[cur]
                path.append(cur)
            return path[::-1]
        if g_cur > g.get(cur, math.inf):
            continue
        for nxt in sorted(h3.grid_ring(cur, 1)):  # tri : départage déterministe
            if h3.grid_distance(start, nxt) > radius or blocked(cur, nxt):
                continue
            g_new = g_cur + cost(nxt)
            if g_new < g.get(nxt, math.inf):
                g[nxt] = g_new
                came[nxt] = cur
                heapq.heappush(heap, (g_new + h3.grid_distance(nxt, goal), g_new, nxt))
    return None


def run(cfg: ExperimentConfig, size: int, limit: int | None = None, land: LandMask | None = None) -> None:
    contexts = gap_contexts(cfg, size, limit)
    prior = pd.read_parquet(Path(cfg.paths.experiment_dir) / "dataset" / "density_prior.parquet")
    cost = DensityCost(prior)

    lin_pts, lin_out, a_pts, a_out = [], [], [], []
    for ctx in contexts.itertuples():
        started = time.time()
        lin_pts.append(points_frame(ctx, "linear", linear(ctx)))
        lin_out.append({"gap_id": ctx.gap_id, "method": "linear", "status": "ok", "reason": None,
                        "latency_s": time.time() - started, "tokens": 0, "path": None})

        started = time.time()
        path = astar(ctx.cell_before, ctx.cell_after, cost, land)
        if path is None:
            a_out.append({"gap_id": ctx.gap_id, "method": "astar", "status": "failed",
                          "reason": "aucun chemin maritime dans le rayon de recherche",
                          "latency_s": time.time() - started, "tokens": 0, "path": None})
            continue
        positions = place_along(cells_to_waypoints(path, ctx), ctx.ts_before, ctx.ts_after, ctx.target_ts)
        a_pts.append(points_frame(ctx, "astar", positions))
        a_out.append({"gap_id": ctx.gap_id, "method": "astar", "status": "ok", "reason": None,
                      "latency_s": time.time() - started, "tokens": 0, "path": path})

    write_completions(cfg, "linear", size, lin_pts, lin_out, {}, limit)
    write_completions(cfg, "astar", size, a_pts, a_out, {
        "density_weight": DENSITY_WEIGHT, "radius_factor": RADIUS_FACTOR, "radius_margin": RADIUS_MARGIN,
        "land_mask": land is not None,
    }, limit)


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="python -m EGC27.baselines")
    p.add_argument("--size", type=int, required=True, help="taille de trou (cellules)")
    p.add_argument("--limit", type=int, help="ne traiter que les N premiers trous (essai)")
    a = p.parse_args(argv)
    cfg = load_config(resolve_model=False)
    run(cfg, a.size, a.limit, LandMask.from_config(cfg))


if __name__ == "__main__":
    main()
