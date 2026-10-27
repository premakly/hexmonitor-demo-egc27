"""Diagnostic : plancher d'erreur des méthodes par cellules.

L'« oracle » connaît le vrai chemin de cellules de chaque trou (les passages
retirés, entre les deux cellules d'ancrage) et le convertit en points
exactement comme Hexa et l'A*. Son erreur ne vient donc que de la
représentation : passer par le centre des cellules au lieu du vrai tracé.
Aucune méthode par cellules ne peut, en moyenne, faire mieux avec la même
conversion. La variante « oracle_lisse » mesure ce qu'un lissage de Chaikin
de ce tracé permettrait de regagner.

Sortie au format commun (completions/oracle_c{k}.parquet, oracle_lisse_c{k}…),
reprise automatiquement par metrics.py.

Usage, depuis la racine : python -m EGC27.oracle
"""

from __future__ import annotations

import pandas as pd

from .completion import cells_to_waypoints, gap_contexts, place_along, points_frame, smooth, write_completions
from .config import load_config

SMOOTHING_ITERATIONS = 2


def run(cfg) -> None:
    gaps = pd.read_parquet(f"{cfg.paths.experiment_dir}/gaps/gaps.parquet").set_index("gap_id")
    for size in sorted(cfg.gaps.sizes_cells):
        results = {"oracle": ([], []), "oracle_lisse": ([], [])}
        for ctx in gap_contexts(cfg, size).itertuples():
            path = [ctx.cell_before, *gaps.at[ctx.gap_id, "cells"], ctx.cell_after]
            waypoints = cells_to_waypoints(path, ctx)
            for method, wp in (("oracle", waypoints), ("oracle_lisse", smooth(waypoints, SMOOTHING_ITERATIONS))):
                pts, out = results[method]
                pts.append(points_frame(ctx, method, place_along(wp, ctx.ts_before, ctx.ts_after, ctx.target_ts)))
                out.append({"gap_id": ctx.gap_id, "method": method, "status": "ok", "reason": None,
                            "latency_s": 0.0, "tokens": 0, "path": list(path)})
        for method, (pts, out) in results.items():
            write_completions(cfg, method, size, pts, out,
                              {"smoothing_iterations": SMOOTHING_ITERATIONS if method == "oracle_lisse" else 0})


if __name__ == "__main__":
    run(load_config(resolve_model=False))
