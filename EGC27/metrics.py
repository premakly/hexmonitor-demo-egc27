"""Étape 7 : métriques et statistiques.

Pour chaque trou et chaque méthode, la vérité terrain et la complétion sont
rééchantillonnées au même pas de temps (metrics.resample_step_s), aux seuls
instants intérieurs au trou : les deux ancres sont communes à toutes les
méthodes et gonfleraient l'accord. On en tire :

  - mean_km / max_km : écart moyen et maximal (haversine) ;
  - frechet_km       : distance de Fréchet discrète, ancres comprises (sensible
                       à la forme et à l'ordre, là où une moyenne dilue une
                       excursion) ;
  - point_mae_km     : écart moyen aux points retirés eux-mêmes, comme le
                       calcule VISTA (pour recouper ses journaux) ;
  - land_pct         : part des positions rééchantillonnées situées sur terre.

Une sortie invalide est exclue des métriques de distance et comptée dans le
taux d'échec. Les tests appariés (Wilcoxon, avec corrélation bisériale de
rang et correction de Holm) portent sur les trous complétés par les deux
méthodes comparées.

Sorties dans <experiment_dir>/results/ : per_gap.parquet, summary.csv/.tex,
tests.csv/.tex, manifest.json.

Usage, depuis la racine : python -m EGC27.metrics
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import wilcoxon

from .completion import gap_contexts
from .config import ExperimentConfig, load_config
from .dataset import haversine_km

METHODS = ["vista", "hexa", "linear", "astar", "oracle", "oracle_lisse"]
PAIRS = [("vista", "hexa"), ("vista", "linear"), ("hexa", "linear"), ("hexa", "astar"), ("oracle", "linear")]
LABELS = {"vista": "VISTA", "hexa": "Hexa", "linear": "Linéaire", "astar": "A*",
          "oracle": "Oracle cellules", "oracle_lisse": "Oracle lissé"}


# ------------------------------------------------------------------ géométrie
def interior_grid(ts_before: int, ts_after: int, step: int) -> np.ndarray:
    grid = np.arange(ts_before + step, ts_after, step)
    return grid if len(grid) else np.array([(ts_before + ts_after) / 2])


def resample(t, lat, lon, grid) -> np.ndarray:
    return np.column_stack([np.interp(grid, t, lat), np.interp(grid, t, lon)])


def discrete_frechet_km(a: np.ndarray, b: np.ndarray) -> float:
    """Distance de Fréchet discrète entre deux suites (lat, lon), en km."""
    d = haversine_km(a[:, None, 0], a[:, None, 1], b[None, :, 0], b[None, :, 1])
    n, m = d.shape
    ca = np.full((n, m), np.inf)
    ca[0, 0] = d[0, 0]
    for i in range(1, n):
        ca[i, 0] = max(ca[i - 1, 0], d[i, 0])
    for j in range(1, m):
        ca[0, j] = max(ca[0, j - 1], d[0, j])
    for i in range(1, n):
        for j in range(1, m):
            ca[i, j] = max(min(ca[i - 1, j], ca[i - 1, j - 1], ca[i, j - 1]), d[i, j])
    return float(ca[-1, -1])


def gap_metrics(ctx, truth: pd.DataFrame, comp: pd.DataFrame, step: int, land) -> dict:
    """Métriques d'une complétion d'un trou (truth et comp : points du trou, triés)."""
    def track(points):
        t = np.concatenate([[ctx.ts_before], points["ts"], [ctx.ts_after]])
        lat = np.concatenate([[ctx.lat_before], points["lat"], [ctx.lat_after]])
        lon = np.concatenate([[ctx.lon_before], points["lon"], [ctx.lon_after]])
        return t, lat, lon

    grid = interior_grid(ctx.ts_before, ctx.ts_after, step)
    full = np.concatenate([[ctx.ts_before], grid, [ctx.ts_after]])
    T, C = track(truth), track(comp)
    tr, co = resample(*T, grid), resample(*C, grid)
    d = haversine_km(tr[:, 0], tr[:, 1], co[:, 0], co[:, 1])

    at_points = truth.merge(comp, on="idx", suffixes=("_t", ""))
    return {
        "mean_km": float(d.mean()),
        "max_km": float(d.max()),
        "frechet_km": discrete_frechet_km(resample(*T, full), resample(*C, full)),
        "point_mae_km": float(haversine_km(at_points.lat_t, at_points.lon_t, at_points.lat, at_points.lon).mean()),
        "land_pct": float(land.on_land(co[:, 0], co[:, 1]).mean() * 100) if land is not None else np.nan,
    }


# ------------------------------------------------------------------ statistiques
def bootstrap_ci(x: np.ndarray, n: int, seed: int, alpha: float = 0.05) -> tuple[float, float]:
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    if len(x) < 2:
        return (np.nan, np.nan)
    rng = np.random.default_rng(seed)
    means = x[rng.integers(0, len(x), (n, len(x)))].mean(axis=1)
    return (float(np.quantile(means, alpha / 2)), float(np.quantile(means, 1 - alpha / 2)))


def rank_biserial(diff: np.ndarray) -> float:
    """Corrélation bisériale de rang des différences (a − b) : négative si a est meilleur."""
    diff = diff[diff != 0]
    if not len(diff):
        return 0.0
    ranks = pd.Series(np.abs(diff)).rank().to_numpy()
    pos, neg = ranks[diff > 0].sum(), ranks[diff < 0].sum()
    return float((pos - neg) / (pos + neg))


def paired_test(per_gap: pd.DataFrame, a: str, b: str, metric: str = "mean_km") -> dict:
    ok = per_gap[per_gap["status"] == "ok"].pivot_table(index="gap_id", columns="method", values=metric)
    if a not in ok or b not in ok:
        return {"a": a, "b": b, "n": 0}
    pair = ok[[a, b]].dropna()
    diff = (pair[a] - pair[b]).to_numpy()
    out = {
        "a": a, "b": b, "n": len(pair),
        "median_a": float(pair[a].median()) if len(pair) else np.nan,
        "median_b": float(pair[b].median()) if len(pair) else np.nan,
        "median_diff": float(np.median(diff)) if len(pair) else np.nan,
        "wins_a_pct": float((diff < 0).mean() * 100) if len(pair) else np.nan,
        "rank_biserial": rank_biserial(diff) if len(pair) else np.nan,
        "p": np.nan,
    }
    if len(pair) >= 6 and np.any(diff != 0):
        out["p"] = float(wilcoxon(pair[a], pair[b]).pvalue)
    return out


def holm(p: np.ndarray) -> np.ndarray:
    p = np.asarray(p, dtype=float)
    adj = np.full_like(p, np.nan)
    valid = ~np.isnan(p)
    order = np.argsort(p[valid])
    pv = p[valid][order]
    m = len(pv)
    stepped = np.maximum.accumulate((m - np.arange(m)) * pv)
    out = np.empty(m)
    out[order] = np.minimum(stepped, 1.0)
    adj[valid] = out
    return adj


def summarise(per_gap: pd.DataFrame, bootstrap: int, seed: int) -> pd.DataFrame:
    rows = []
    all_levels = per_gap.assign(level="tous")
    for (method, size, level), g in pd.concat([per_gap, all_levels]).groupby(["method", "size_cells", "level"]):
        ok = g[g["status"] == "ok"]
        lo, hi = bootstrap_ci(ok["mean_km"].to_numpy(), bootstrap, seed)
        rows.append({
            "method": method, "size_cells": size, "level": level,
            "n_gaps": len(g), "n_ok": len(ok), "failure_pct": 100 * (1 - len(ok) / len(g)),
            "mean_km": ok["mean_km"].mean(), "ci_low": lo, "ci_high": hi,
            "median_km": ok["mean_km"].median(), "max_km": ok["max_km"].mean(),
            "frechet_km": ok["frechet_km"].mean(), "point_mae_km": ok["point_mae_km"].mean(),
            "land_pct": ok["land_pct"].mean(), "tokens": g["tokens"].mean(), "latency_s": g["latency_s"].mean(),
        })
    s = pd.DataFrame(rows)
    s["level"] = pd.Categorical(s["level"], ["facile", "difficile", "tous"], ordered=True)
    s["method"] = pd.Categorical(s["method"], [m for m in METHODS if m in set(s["method"])] or None, ordered=True)
    return s.sort_values(["size_cells", "level", "method"]).reset_index(drop=True)


# ------------------------------------------------------------------ LaTeX
def _fmt(v, digits=2):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "--"
    if isinstance(v, (int, np.integer)):
        return str(v)
    if isinstance(v, (float, np.floating)):
        return f"{v:.{digits}f}"
    return str(v)


def _fmt_p(v):
    if v is None or np.isnan(v):
        return "--"
    return "$<0{,}001$" if v < 0.001 else f"{v:.3f}"


def latex_table(df: pd.DataFrame, columns: dict, caption: str, label: str) -> str:
    def cell(r, c):
        return _fmt_p(r[c]) if c.startswith("p") else _fmt(r[c])

    head = " & ".join(columns.values()) + r" \\"
    body = "\n".join(" & ".join(cell(r, c) for c in columns) + r" \\" for _, r in df.iterrows())
    return "\n".join([
        r"\begin{table}[t]", r"\centering\small",
        r"\begin{tabular}{" + "l" * 3 + "r" * (len(columns) - 3) + "}", r"\toprule",
        head, r"\midrule", body, r"\bottomrule", r"\end{tabular}",
        rf"\caption{{{caption}}}", rf"\label{{{label}}}", r"\end{table}", "",
    ])


# ------------------------------------------------------------------ principal
def build(cfg: ExperimentConfig, land=None) -> dict:
    root = Path(cfg.paths.experiment_dir)
    comp_dir = root / "completions"
    out = root / "results"
    out.mkdir(parents=True, exist_ok=True)
    truth_all = pd.read_parquet(root / "gaps" / "truth.parquet")
    gaps = pd.read_parquet(root / "gaps" / "gaps.parquet").set_index("gap_id")

    rows, missing = [], []
    for size in sorted(cfg.gaps.sizes_cells):
        contexts = gap_contexts(cfg, size).set_index("gap_id")
        for method in METHODS:
            pts_file = comp_dir / f"{method}_c{size}.parquet"
            if not pts_file.exists():
                missing.append(f"{method}_c{size}")
                continue
            pts = pd.read_parquet(pts_file)
            outcomes = pd.read_parquet(comp_dir / f"{method}_c{size}_outcomes.parquet").set_index("gap_id")
            by_gap = dict(tuple(pts.groupby("gap_id")))
            for gap_id, ctx in contexts.iterrows():
                o = outcomes.loc[gap_id] if gap_id in outcomes.index else None
                status = o["status"] if o is not None else "failed"
                row = {"gap_id": gap_id, "size_cells": size, "level": ctx["level"], "method": method,
                       "status": status, "tokens": o["tokens"] if o is not None else np.nan,
                       "latency_s": o["latency_s"] if o is not None else np.nan,
                       "duration_h": gaps.at[gap_id, "duration_h"], "length_km": gaps.at[gap_id, "length_km"]}
                if status == "ok" and gap_id in by_gap:
                    truth = truth_all[truth_all["gap_id"] == gap_id].sort_values("idx")
                    comp = by_gap[gap_id].sort_values("idx")
                    ctx_ns = pd.Series({**ctx.to_dict(), "gap_id": gap_id})
                    row.update(gap_metrics(ctx_ns, truth, comp, cfg.metrics.resample_step_s, land))
                else:
                    row["status"] = "failed"
                rows.append(row)

    per_gap = pd.DataFrame(rows)
    per_gap.to_parquet(out / "per_gap.parquet", index=False)
    summary = summarise(per_gap, cfg.metrics.bootstrap_samples, cfg.seed)
    summary.to_csv(out / "summary.csv", index=False)

    tests = []
    for size in [*sorted(cfg.gaps.sizes_cells), "toutes"]:
        sub = per_gap if size == "toutes" else per_gap[per_gap["size_cells"] == size]
        for a, b in PAIRS:
            r = paired_test(sub, a, b)
            if r["n"]:
                tests.append({"size_cells": size, **r})
    tests = pd.DataFrame(tests)
    if len(tests):
        tests["p_holm"] = holm(tests["p"].to_numpy())
    tests.to_csv(out / "tests.csv", index=False)

    s_tex = summary.assign(method=summary["method"].map(LABELS), ci=lambda d: [
        f"[{_fmt(a)} ; {_fmt(b)}]" for a, b in zip(d["ci_low"], d["ci_high"])])
    (out / "summary.tex").write_text(latex_table(s_tex, {
        "size_cells": "Trou", "level": "Niveau", "method": "Méthode", "n_ok": "$n$",
        "failure_pct": r"Échecs (\%)", "mean_km": "Erreur (km)", "ci": "IC 95 \\%",
        "frechet_km": "Fréchet (km)", "land_pct": r"Terre (\%)",
    }, "Erreur de complétion par taille de trou (cellules H3), niveau et méthode.", "tab:resultats"))
    if len(tests):
        t_tex = tests.assign(a=tests["a"].map(LABELS), b=tests["b"].map(LABELS))
        (out / "tests.tex").write_text(latex_table(t_tex, {
            "size_cells": "Trou", "a": "A", "b": "B", "n": "$n$", "median_diff": r"$\Delta$ médian (km)",
            "wins_a_pct": r"A meilleur (\%)", "rank_biserial": "$r$", "p_holm": "$p$ (Holm)",
        }, "Tests appariés de Wilcoxon sur l'erreur moyenne ($r$ < 0 : A meilleur).", "tab:tests"))

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(), "config_hash": cfg.hash,
        "resample_step_s": cfg.metrics.resample_step_s, "bootstrap_samples": cfg.metrics.bootstrap_samples,
        "land_mask": land is not None, "missing_completions": missing,
        "gaps": int(per_gap["gap_id"].nunique()), "rows": len(per_gap),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    return {"summary": summary, "tests": tests, "missing": missing}


if __name__ == "__main__":
    from .landmask import LandMask

    cfg = load_config(resolve_model=False)
    res = build(cfg, LandMask.from_config(cfg))
    pd.set_option("display.width", 200)
    cols = ["size_cells", "level", "method", "n_ok", "failure_pct", "mean_km", "ci_low", "ci_high", "frechet_km", "land_pct"]
    print(res["summary"][cols].round(2).to_string(index=False))
    if len(res["tests"]):
        print()
        print(res["tests"][["size_cells", "a", "b", "n", "median_diff", "wins_a_pct", "rank_biserial", "p_holm"]]
              .round(3).to_string(index=False))
    if res["missing"]:
        print("\ncomplétions absentes :", ", ".join(res["missing"]))
