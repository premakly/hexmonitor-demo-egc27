"""Étape 4 : VISTA comme référence, branché sans modification de son code.

VISTA ne masque que des segments entiers (10 par trajectoire de 200 points)
et reconstruit un segment masqué à partir du dernier point du segment
précédent et du premier point du segment suivant. L'adaptateur :

  1. prepare : écrit, pour une taille de trou k, le fichier d'entrée de VISTA
     (format « …_SegementId_PointInfo_200_N.csv ») à partir de nos fenêtres,
     en découpant chacune en 10 segments dont NOTRE trou forme exactement un ;
     écrit la matrice de masquage correspondante (1 = segment masqué) ;
  2. run     : lance VISTA dans un processus séparé, en remplaçant son tirage
     aléatoire des segments masqués (get_missing_mark) par notre matrice, et
     en lui imposant le modèle et l'adresse du LLM de experiment.yaml ;
  3. collect : relit le CSV COMPARISON de VISTA et produit nos complétions au
     format commun : <experiment_dir>/completions/vista_c{k}.parquet (points)
     et vista_c{k}_outcomes.parquet (une ligne par trou, réussite ou échec).

Une exécution par taille de trou (les trous de tailles différentes d'une même
trajectoire peuvent se chevaucher), chacune sous son propre exp_name : VISTA
reprend alors de lui-même après une interruption, grâce à ses points de reprise.

Usage, depuis la racine du projet :
  python -m EGC27.vista_adapter all --size 2 --limit 2   # essai sur 2 trajectoires
  python -m EGC27.vista_adapter all --size 2             # les 40 trajectoires
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from .config import ExperimentConfig, load_config
from .vista_explain import write_explanations

N_SEGMENTS = 10
SEGMENT_LEN = 20          # mini_segment_len de VISTA : 200 // 20 = 10 segments
HEADING_UNAVAILABLE = 511  # convention AIS « non disponible »
VISTA_COLUMNS = [
    "sequence_id", "mmsi", "timestamp", "latitude", "longitude", "sog", "cog", "heading",
    "ship_type", "navigational_status", "draught", "length", "width", "destination", "rot",
    "segment_id", "dynamic_info",
]
STANDARDIZED_SUFFIX = "_standardized_with_SequenceId_SegementId_PointInfo_"


# ------------------------------------------------------------------ chemins
def work_dir(cfg: ExperimentConfig, k: int) -> Path:
    return Path(cfg.paths.experiment_dir) / "vista" / f"c{k}"


def exp_name(k: int, limit: int | None) -> str:
    return f"EGC27_c{k}" + (f"_essai{limit}" if limit else "")


def raw_name(k: int) -> str:
    return f"egc27_c{k}.csv"


# ------------------------------------------------------------------ segments
def segment_ids(n: int, i0: int, i1: int) -> np.ndarray:
    """
    Numéro de segment (0..9) de chacun des n points, le trou [i0, i1] formant
    exactement un segment. Les 9 autres se répartissent avant et après le trou
    au prorata des points disponibles, au moins un de chaque côté.
    """
    before, after = i0, n - 1 - i1
    others = N_SEGMENTS - 1
    if before < 1 or after < 1 or before + after < others:
        raise ValueError(f"trou [{i0}, {i1}] : contexte insuffisant pour {N_SEGMENTS} segments")
    nb = int(round(others * before / (before + after)))
    nb = min(max(nb, 1), others - 1, before)
    na = others - nb
    if na > after:
        na, nb = after, others - after

    ids = np.empty(n, dtype=int)
    for s, part in enumerate(np.array_split(np.arange(before), nb)):
        ids[part] = s
    ids[i0:i1 + 1] = nb
    for s, part in enumerate(np.array_split(np.arange(i1 + 1, n), na)):
        ids[part] = nb + 1 + s
    return ids


# ------------------------------------------------------------------ préparation
def _ship_type_mapping(vista_root: Path) -> dict:
    """La table code → libellé de VISTA elle-même (Id2SHIP_TYPE_Mapping)."""
    sys.path.insert(0, str(vista_root))
    try:
        from src.data.utils.AISDataMappingDicts import Id2SHIP_TYPE_Mapping
    finally:
        sys.path.remove(str(vista_root))
    return Id2SHIP_TYPE_Mapping


def _code(value):
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return int(f) if f.is_integer() else None


def _attributes(cfg: ExperimentConfig, traj: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Attributs AIS des points (par mmsi, ts) et des navires, lus dans DuckDB."""
    con = duckdb.connect(str(cfg.paths.duckdb), read_only=True)
    try:
        con.register("keys", traj[["mmsi", "ts"]])
        points = con.execute(
            """SELECT p.mmsi, p.ts, p.heading, p.rot, p.navigational_status, p.draught, p.destination
               FROM points p JOIN keys k ON p.mmsi = k.mmsi AND p.ts = k.ts"""
        ).df().drop_duplicates(["mmsi", "ts"])
        vessels = con.execute(
            "SELECT mmsi, ship_type, length, width FROM vessels WHERE mmsi IN (SELECT DISTINCT mmsi FROM keys)"
        ).df()
    finally:
        con.close()
    return points, vessels


def build_vista_frame(traj: pd.DataFrame, gaps: pd.DataFrame, points: pd.DataFrame,
                      vessels: pd.DataFrame, type_mapping: dict) -> tuple[pd.DataFrame, np.ndarray, pd.DataFrame]:
    """
    Le fichier d'entrée de VISTA, la matrice de masquage alignée sur l'ordre
    des séquences du fichier, et la table séquence → trou.
    """
    gaps = gaps.sort_values("mmsi").reset_index(drop=True)
    frames, mask, index = [], np.zeros((len(gaps), N_SEGMENTS), dtype=int), []
    for seq, g in gaps.iterrows():
        t = traj[traj["mmsi"] == g["mmsi"]].sort_values("idx").reset_index(drop=True)
        ids = segment_ids(len(t), int(g["idx_start"]), int(g["idx_end"]))
        gap_segment = int(ids[int(g["idx_start"])])
        mask[seq, gap_segment] = 1
        frames.append(t.assign(sequence_id=seq, segment_id=ids))
        index.append({"sequence_id": seq, "mmsi": int(g["mmsi"]), "gap_id": g["gap_id"],
                      "segment_id": gap_segment, "idx_start": int(g["idx_start"])})

    df = pd.concat(frames, ignore_index=True)
    df = df.merge(points, on=["mmsi", "ts"], how="left").merge(vessels, on="mmsi", how="left")

    out = pd.DataFrame({
        "sequence_id": df["sequence_id"],
        "mmsi": df["mmsi"],
        "timestamp": pd.to_datetime(df["ts"], unit="s").dt.strftime("%Y-%m-%d %H:%M:%S"),
        "latitude": df["lat"],
        "longitude": df["lon"],
        "sog": df["sog"],
        "cog": df["cog"],
        "heading": df["heading"].fillna(HEADING_UNAVAILABLE).round().astype(int),
        "ship_type": [type_mapping.get(_code(v), "Undefined") for v in df["ship_type"]],
        "navigational_status": df["navigational_status"].fillna("Not defined"),
        "draught": df["draught"],
        "length": df["length"],
        "width": df["width"],
        "destination": df["destination"].map(lambda v: v if pd.isna(v) else str(v).strip().upper()),
        "rot": df["rot"],
        "segment_id": df["segment_id"],
    })
    out["dynamic_info"] = [
        f"timestamp: {r.timestamp},latitude: {r.latitude}, longitude: {r.longitude}, "
        f"sog: {r.sog}, cog: {r.cog}, heading: {r.heading}"
        for r in out.itertuples()
    ]
    return out[VISTA_COLUMNS], mask, pd.DataFrame(index)


def prepare(cfg: ExperimentConfig, k: int) -> Path:
    root = Path(cfg.paths.experiment_dir)
    traj = pd.read_parquet(root / "dataset" / "trajectories.parquet")
    gaps = pd.read_parquet(root / "gaps" / "gaps.parquet")
    gaps = gaps[gaps["size_cells"] == k]
    if gaps.empty:
        raise SystemExit(f"aucun trou de {k} cellules dans gaps.parquet")

    points, vessels = _attributes(cfg, traj)
    frame, mask, index = build_vista_frame(traj, gaps, points, vessels, _ship_type_mapping(cfg.vista.root))

    out = work_dir(cfg, k)
    out.mkdir(parents=True, exist_ok=True)
    n = len(index)
    csv = out / raw_name(k).replace(".csv", f"{STANDARDIZED_SUFFIX}200_{n}.csv")
    frame.to_csv(csv, index=False)
    np.save(out / "mask.npy", mask)
    index.to_parquet(out / "sequences.parquet", index=False)
    print(f"préparé : {n} séquences, {len(frame)} points → {csv}")
    return csv


# ------------------------------------------------------------------ exécution
def run(cfg: ExperimentConfig, k: int, limit: int | None) -> None:
    out = work_dir(cfg, k)
    n = len(pd.read_parquet(out / "sequences.parquet"))
    end = min(limit or n, n)
    if end % 2:  # VISTA sauvegarde ses points de reprise par paires (process_length = 2)
        end = min(end + 1, n)
    # Chemin absolu : le processus VISTA s'exécute depuis le dépôt VISTA, où un
    # chemin relatif à la racine du projet (backend/vista) ne mènerait nulle part.
    vista_root = Path(cfg.vista.root).resolve()
    started = time.time()
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(Path.cwd()), os.environ.get("PYTHONPATH", "")]))
    child = [
        sys.executable, "-m", "EGC27.vista_adapter", "_child",
        "--vista-root", str(vista_root),
        "--raw", str((out / raw_name(k)).resolve()),
        "--processed-dir", str(out.resolve()),
        "--mask", str((out / "mask.npy").resolve()),
        "--exp-name", exp_name(k, limit),
        "--n", str(n), "--end", str(end), "--seed", str(cfg.seed),
        "--model", cfg.llm.model, "--base-url", cfg.llm.host.rstrip("/") + "/v1",
    ]
    code = subprocess.call(child, cwd=str(vista_root), env=env)
    record = {
        "exp_name": exp_name(k, limit), "size_cells": k, "sequences": end, "returncode": code,
        "wall_time_s": round(time.time() - started, 1), "model": cfg.llm.model,
        "config_hash": cfg.hash, "finished_at": datetime.now(timezone.utc).isoformat(),
    }
    (out / f"run_{exp_name(k, limit)}.json").write_text(json.dumps(record, indent=2))
    print(f"VISTA terminé (code {code}) en {record['wall_time_s'] / 60:.1f} min pour {end} séquences")
    if code:
        raise SystemExit(code)


def _pin_vista_packages(root: Path) -> None:
    """
    Rend les paquets de VISTA prioritaires. VISTA importe des paquets aux noms
    génériques (data, utils, modules, pipeline, src) ; un paquet homonyme
    ailleurs dans les chemins (un dossier data/ du projet, une bibliothèque du
    venv) les masquerait. On les déclare donc d'emblée, pointant vers VISTA.
    """
    import types

    src = root / "src"
    sys.path[:0] = [str(src), str(root)]
    pinned = {"src": src, **{d.name: d for d in src.iterdir() if d.is_dir() and not d.name.startswith("__")}}
    for name, path in pinned.items():
        for loaded in [m for m in sys.modules if m == name or m.startswith(name + ".")]:
            del sys.modules[loaded]
        package = types.ModuleType(name)
        package.__path__ = [str(path)]
        sys.modules[name] = package


def _child(a: argparse.Namespace) -> None:
    """Processus VISTA : chemins d'import de VISTA, masque imposé, paramètres forcés."""
    root = Path(a.vista_root)
    _pin_vista_packages(root)
    mask = np.load(a.mask)

    def our_mask(args, mobility=None):
        return mask.copy()

    # configure_parser de VISTA lit sys.argv (parse_known_args) : nos propres
    # options (--end, --n…) y seraient prises pour les siennes, ou jugées
    # ambiguës. On lui présente une ligne de commande vide.
    sys.argv = [sys.argv[0]]

    from utils.HyperParameters import configure_parser
    import main as vista_main

    # get_training_test_data cherche get_missing_mark dans les variables
    # globales de son propre module : on remplace la fonction exactement là,
    # quel que soit le nom sous lequel ce module a été importé.
    vista_main.get_training_test_data.__globals__["get_missing_mark"] = our_mask

    args = configure_parser().parse_args([])
    for key, value in {
        "exp_name": a.exp_name, "seed": a.seed,
        "raw_data_file": a.raw, "processed_data_dir": a.processed_dir,
        "trajectory_num": a.n, "trajectory_len": 200, "mini_segment_len": SEGMENT_LEN,
        "training_test": 0.0, "check_point": 0, "end_point": a.end, "end_point_sdkg": a.end,
        "mining_llm": a.model, "coding_llm": a.model, "analysis_llm": a.model,
        "base_url": a.base_url, "llm_api_key": "ollama",
    }.items():
        setattr(args, key, value)
    vista_main.pipline_VISTA_Multithreading(args)


# ------------------------------------------------------------------ collecte
def collect(cfg: ExperimentConfig, k: int, limit: int | None) -> pd.DataFrame:
    out = work_dir(cfg, k)
    index = pd.read_parquet(out / "sequences.parquet")
    run_info = json.loads((out / f"run_{exp_name(k, limit)}.json").read_text())
    end = run_info["sequences"]
    comp_dir = Path(cfg.vista.root) / "results" / exp_name(k, limit) / "COMPARISON"
    comp_file = comp_dir / f"comparison{len(index)}_len200_seed{cfg.seed}_{end}_{end}.csv"
    # VISTA n'écrit ce fichier que si au moins un segment a été reconstruit :
    # son absence signifie que tous les trous tentés ont échoué.
    comp = pd.read_csv(comp_file) if comp_file.exists() else pd.DataFrame(columns=[
        "sequence_id", "mmsi", "segment_id", "point_index", "timestamp",
        "imputed_latitude", "imputed_longitude", "selected_function_id",
    ])

    comp = comp.merge(index, on=["sequence_id", "mmsi"], suffixes=("", "_gap"))
    stray = comp[comp["segment_id"] != comp["segment_id_gap"]]
    if not stray.empty:
        raise RuntimeError(f"VISTA a imputé des segments hors de nos trous : {stray[['sequence_id', 'segment_id']].drop_duplicates().values.tolist()}")

    points = pd.DataFrame({
        "gap_id": comp["gap_id"],
        "method": "vista",
        "idx": comp["idx_start"] + comp["point_index"],
        "ts": (pd.to_datetime(comp["timestamp"]) - pd.Timestamp("1970-01-01")) // pd.Timedelta(seconds=1),
        "lat": comp["imputed_latitude"],
        "lon": comp["imputed_longitude"],
        "function_id": comp["selected_function_id"],
    })
    attempted = index[index["sequence_id"] < end]
    done = set(points["gap_id"])
    outcomes = pd.DataFrame({
        "gap_id": attempted["gap_id"],
        "method": "vista",
        "status": ["ok" if g in done else "failed" for g in attempted["gap_id"]],
        "latency_s": run_info["wall_time_s"] / max(len(attempted), 1),  # moyenne, construction du graphe comprise
        "tokens": np.nan,  # VISTA n'expose pas le décompte des tokens
    })

    dest = Path(cfg.paths.experiment_dir) / "completions"
    dest.mkdir(parents=True, exist_ok=True)
    suffix = f"_essai{limit}" if limit else ""
    points.to_parquet(dest / f"vista_c{k}{suffix}.parquet", index=False)
    outcomes.to_parquet(dest / f"vista_c{k}{suffix}_outcomes.parquet", index=False)
    # Son raisonnement (comportement, fonction, explication) pour la vue Expérience.
    explained = write_explanations(
        Path(cfg.vista.root) / "results" / exp_name(k, limit),
        attempted, dest / f"vista_c{k}{suffix}_explanations.json",
    )
    print(f"collecté : {outcomes['status'].eq('ok').sum()}/{len(outcomes)} trous complétés, {len(points)} points, "
          f"{sum(e['status'] == 'ok' for e in explained.values())} explications")
    return outcomes


# ------------------------------------------------------------------ CLI
def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="python -m EGC27.vista_adapter")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("prepare", "run", "collect", "all"):
        s = sub.add_parser(name)
        s.add_argument("--size", type=int, required=True, help="taille de trou (cellules)")
        s.add_argument("--limit", type=int, help="ne traiter que les N premières séquences (essai)")
    c = sub.add_parser("_child")
    for opt in ("--vista-root", "--raw", "--processed-dir", "--mask", "--exp-name", "--model", "--base-url"):
        c.add_argument(opt, required=True)
    for opt in ("--n", "--end", "--seed"):
        c.add_argument(opt, type=int, required=True)
    a = p.parse_args(argv)

    if a.cmd == "_child":
        return _child(a)
    cfg = load_config(resolve_model=False)
    if a.cmd in ("prepare", "all"):
        prepare(cfg, a.size)
    if a.cmd in ("run", "all"):
        run(cfg, a.size, a.limit)
    if a.cmd in ("collect", "all"):
        collect(cfg, a.size, a.limit)


if __name__ == "__main__":
    main()
