"""Étape 5 : Hexa, le moteur hexagonal de Hex Monitor, branché sans modification.

Pour chaque trou, le walker (hexmonitor.engine.walker.walk_gap) avance de
cellule en cellule, de la cellule d'ancrage avant à la cellule d'ancrage
après, avec le même contexte que dans l'application (runner.build_context :
type de navire, dernière vitesse et dernier cap, durée du silence). On retient
le scénario abouti le plus probable ; sa suite de cellules est convertie en
points aux instants des points retirés, comme pour l'A* (completion.py).

Chaque trou est mis en cache (EGC27/cache/hexa/c{k}/<gap_id>.json) avec sa
réponse complète : une exécution interrompue (Ollama qui s'arrête) reprend là
où elle en était, et la démonstration pourra rejouer les marches sans LLM.
Le cache est invalidé si le modèle ou les paramètres du walker changent.

Usage, depuis la racine : python -m EGC27.hexa_adapter --size 2 [--limit 2]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import duckdb
import pandas as pd

from .completion import cells_to_waypoints, gap_contexts, place_along, points_frame, write_completions
from .config import ExperimentConfig, load_config


def _engine():
    """Le moteur de Hex Monitor, importé depuis backend/ si besoin."""
    try:
        import hexmonitor  # noqa: F401
    except ImportError:
        sys.path.insert(0, str(Path("backend").resolve()))
    from hexmonitor.engine import llm, runner, walker
    try:
        from hexmonitor.engine.ship_types import ship_type_label
    except ImportError:
        ship_type_label = None
    return walker, llm, runner, ship_type_label


def walker_params(cfg: ExperimentConfig) -> dict:
    """Paramètres transmis à walk_gap : ceux absents de la config gardent leur défaut."""
    return {k: v for k, v in {
        "max_candidates": cfg.hexa.max_candidates,
        "max_scenarios": cfg.hexa.max_scenarios,
    }.items() if v is not None}


def cache_key(cfg: ExperimentConfig) -> str:
    relevant = {"model": cfg.llm.model, "options": cfg.llm.options, "walker": walker_params(cfg)}
    return hashlib.sha256(json.dumps(relevant, sort_keys=True).encode()).hexdigest()[:12]


def vessel_labels(cfg: ExperimentConfig, mmsi: list[int], label) -> dict[int, str]:
    con = duckdb.connect(str(cfg.paths.duckdb), read_only=True)
    try:
        rows = con.execute("SELECT mmsi, ship_type FROM vessels WHERE mmsi IN (SELECT UNNEST(?))", [mmsi]).fetchall()
    finally:
        con.close()
    out = {}
    for m, code in rows:
        try:
            code = int(float(code))
        except (TypeError, ValueError):
            code = None
        out[int(m)] = (label(code) if label and code is not None else str(code)) if code is not None else "unknown"
    return out


def walk_one(ctx, vessel_type: str, cfg: ExperimentConfig, walker, llm, runner) -> dict:
    """Une marche complète sur un trou, résumée en un enregistrement de cache."""
    gap = {
        "start_cell": ctx.cell_before, "end_cell": ctx.cell_after,
        "start_time": pd.Timestamp(ctx.ts_before, unit="s").isoformat(),
        "end_time": pd.Timestamp(ctx.ts_after, unit="s").isoformat(),
        "duration_seconds": ctx.ts_after - ctx.ts_before,
        "last_sog": None if pd.isna(ctx.sog_before) else float(ctx.sog_before),
        "last_cog": None if pd.isna(ctx.cog_before) else float(ctx.cog_before),
    }
    client = llm.LLMClient(llm.LLMConfig(
        base_url=cfg.llm.host.rstrip("/") + "/v1",
        model=cfg.llm.model,
        temperature=cfg.llm.options.get("temperature", 0),
    ))
    started = time.time()
    scenarios = walker.walk_gap(
        ctx.cell_before, ctx.cell_after, client,
        context=runner.build_context(gap, vessel_type), **walker_params(cfg),
    )
    latency = time.time() - started
    finished = [s for s in scenarios if s.finished]
    best = max(finished, key=lambda s: s.probability) if finished else None
    top = scenarios[0] if scenarios else None
    return {
        "gap_id": ctx.gap_id,
        "status": "ok" if best else "failed",
        "reason": None if best else (top.abandoned_reason if top else "aucun scénario"),
        "path": best.path if best else None,
        "probability": best.probability if best else None,
        "finished_scenarios": len(finished),
        "llm_calls": client.calls,
        "prompt_tokens": client.prompt_tokens,
        "completion_tokens": client.completion_tokens,
        "failed_calls": getattr(client, "failed_calls", None),
        "latency_s": latency,
        "payload": walker.to_dict(scenarios, ctx.cell_before, ctx.cell_after),
    }


def run(cfg: ExperimentConfig, size: int, limit: int | None = None) -> None:
    walker, llm, runner, label = _engine()
    contexts = gap_contexts(cfg, size, limit)
    labels = vessel_labels(cfg, [int(m) for m in contexts["mmsi"]], label)
    key = cache_key(cfg)
    cache = Path(cfg.paths.cache_dir) / "hexa" / f"c{size}"
    cache.mkdir(parents=True, exist_ok=True)

    points, outcomes = [], []
    for i, ctx in enumerate(contexts.itertuples(), 1):
        file = cache / f"{ctx.gap_id}.json"
        record = json.loads(file.read_text()) if file.exists() else None
        if record is None or record.get("cache_key") != key:
            print(f"[{i}/{len(contexts)}] {ctx.gap_id} …", flush=True)
            record = walk_one(ctx, labels.get(int(ctx.mmsi), "unknown"), cfg, walker, llm, runner)
            record["cache_key"] = key
            file.write_text(json.dumps(record, ensure_ascii=False))

        outcomes.append({
            "gap_id": ctx.gap_id, "method": "hexa", "status": record["status"], "reason": record["reason"],
            "latency_s": record["latency_s"],
            "tokens": record["prompt_tokens"] + record["completion_tokens"],
            "llm_calls": record["llm_calls"], "probability": record["probability"], "path": record["path"],
        })
        if record["status"] == "ok":
            positions = place_along(cells_to_waypoints(record["path"], ctx), ctx.ts_before, ctx.ts_after, ctx.target_ts)
            points.append(points_frame(ctx, "hexa", positions))

    write_completions(cfg, "hexa", size, points, outcomes,
                      {"model": cfg.llm.model, "walker": walker_params(cfg), "cache_key": key}, limit)


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="python -m EGC27.hexa_adapter")
    p.add_argument("--size", type=int, required=True, help="taille de trou (cellules)")
    p.add_argument("--limit", type=int, help="ne traiter que les N premiers trous (essai)")
    a = p.parse_args(argv)
    run(load_config(resolve_model=False), a.size, a.limit)


if __name__ == "__main__":
    main()
