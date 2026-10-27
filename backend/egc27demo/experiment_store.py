"""
Read side of the EGC 2027 experiment: the files the EGC27/ scripts wrote,
replayed by the demo.

Everything here reads files the experiment scripts wrote; nothing calls the
language model. That is what makes the view a safe demonstration: it replays
finished walks and imputations instead of running them live.

Methods, gap sizes and difficulty levels are discovered from the files, never
listed here, so a new gap size or a new method variant shows up without a
code change.
"""
import json
import math
import os
import re
from pathlib import Path
from typing import Dict, List, Optional

import h3
import pandas as pd

# backend/egc27demo/experiment_store.py -> the repository root
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = REPO_ROOT / "data" / "experiment"

# completions/<method>_c<size>_outcomes.parquet; trial runs (_essaiN) are left out.
OUTCOMES_FILE = re.compile(r"^(?P<method>[a-z_]+?)_c(?P<size>\d+)_outcomes\.parquet$")

# The order the methods are listed in when present; any other is appended.
METHOD_ORDER = ["vista", "hexa", "linear", "astar", "oracle", "oracle_lisse"]

EXPORTS = {"summary": "summary.csv", "tests": "tests.csv"}

ALTERNATIVE_SCENARIOS = 3

COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]

NOT_RUN = (
    "No experiment results found in {path}. The demo reads data/experiment/ "
    "(see the README), or the folder named by EGC27_DEMO_DATA."
)


class ExperimentMissing(Exception):
    """The experiment's dataset and gaps have not been produced yet."""


def default_data_dir() -> Path:
    return Path(os.environ.get("EGC27_DEMO_DATA") or DEFAULT_DATA_DIR)


def clean(value):
    """JSON-safe: NaN and infinities become null, numpy scalars plain numbers."""
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if hasattr(value, "tolist") and not isinstance(value, (str, bytes)):
        return clean(value.tolist())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _records(frame: pd.DataFrame) -> List[Dict]:
    return clean(frame.astype(object).where(frame.notna(), None).to_dict(orient="records"))


def _method_key(method: str):
    return (METHOD_ORDER.index(method) if method in METHOD_ORDER else len(METHOD_ORDER), method)


class ExperimentStore:
    def __init__(self, data_dir: Optional[Path] = None, cache_dir: Optional[Path] = None):
        self.data_dir = Path(data_dir) if data_dir else default_data_dir()
        self.cache_dir = Path(cache_dir) if cache_dir else self.data_dir.parent / "cache"

    # ------------------------------------------------------------- files
    def _path(self, *parts) -> Path:
        return self.data_dir.joinpath(*parts)

    def available(self) -> bool:
        return self._path("dataset", "trajectories.parquet").exists() and self._path("gaps", "gaps.parquet").exists()

    def _require(self) -> None:
        if not self.available():
            raise ExperimentMissing(NOT_RUN.format(path=self.data_dir))

    def _gaps(self) -> pd.DataFrame:
        return pd.read_parquet(self._path("gaps", "gaps.parquet"))

    def runs(self) -> Dict[str, List[int]]:
        """Method -> gap sizes it has completions for."""
        found: Dict[str, List[int]] = {}
        folder = self._path("completions")
        if folder.exists():
            for file in folder.iterdir():
                match = OUTCOMES_FILE.match(file.name)
                if match and file.with_name(file.name.replace("_outcomes", "")).exists():
                    found.setdefault(match["method"], []).append(int(match["size"]))
        return {m: sorted(found[m]) for m in sorted(found, key=_method_key)}

    def _outcomes(self, method: str, size: int) -> pd.DataFrame:
        return pd.read_parquet(self._path("completions", f"{method}_c{size}_outcomes.parquet"))

    def _points(self, method: str, size: int) -> pd.DataFrame:
        return pd.read_parquet(self._path("completions", f"{method}_c{size}.parquet"))

    def _per_gap(self) -> Optional[pd.DataFrame]:
        path = self._path("results", "per_gap.parquet")
        return pd.read_parquet(path) if path.exists() else None

    def export_path(self, name: str) -> Optional[Path]:
        if name not in EXPORTS:
            return None
        path = self._path("results", EXPORTS[name])
        return path if path.exists() else None

    # ------------------------------------------------------------- views
    def overview(self) -> Dict:
        self._require()
        gaps = self._gaps()
        counts = gaps.groupby(["size_cells", "level"]).size().reset_index(name="gaps")

        summary = tests = None
        if self._path("results", "summary.csv").exists():
            summary = _records(pd.read_csv(self._path("results", "summary.csv")))
        if self._path("results", "tests.csv").exists():
            tests = _records(pd.read_csv(self._path("results", "tests.csv")))
        manifest_path = self._path("results", "manifest.json")
        manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else None

        return clean({
            "sizes": sorted(int(s) for s in gaps["size_cells"].unique()),
            "levels": sorted(gaps["level"].unique(), key=lambda lv: (lv != "facile", lv)),
            "methods": list(self.runs()),
            "runs": self.runs(),
            "counts": _records(counts),
            "summary": summary,
            "tests": tests,
            "results_built_at": manifest.get("created_at") if manifest else None,
            "exports": [name for name in EXPORTS if self.export_path(name)],
        })

    def gaps(self, size: Optional[int] = None, level: Optional[str] = None) -> List[Dict]:
        """Every gap, with each method's status and, once computed, its errors."""
        self._require()
        gaps = self._gaps()
        if size is not None:
            gaps = gaps[gaps["size_cells"] == size]
        if level is not None:
            gaps = gaps[gaps["level"] == level]
        gaps = gaps.sort_values(["size_cells", "level", "mmsi"])

        results: Dict[str, Dict[str, Dict]] = {g: {} for g in gaps["gap_id"]}
        for method, sizes in self.runs().items():
            for s in sizes:
                if size is not None and s != size:
                    continue
                for o in self._outcomes(method, s).itertuples():
                    if o.gap_id in results:
                        results[o.gap_id][method] = {"status": o.status, "mean_km": None, "frechet_km": None}

        per_gap = self._per_gap()
        if per_gap is not None:
            for r in per_gap[per_gap["gap_id"].isin(results)].itertuples():
                entry = results[r.gap_id].setdefault(r.method, {"status": r.status})
                entry["mean_km"] = r.mean_km
                entry["frechet_km"] = r.frechet_km

        columns = ["gap_id", "mmsi", "level", "size_cells", "n_removed", "duration_h", "length_km"]
        rows = _records(gaps[columns])
        for row in rows:
            row["methods"] = clean(results[row["gap_id"]])
        return rows

    def gap(self, gap_id: str) -> Optional[Dict]:
        """One gap in full: the window, the truth, every method's completion."""
        self._require()
        gaps = self._gaps()
        found = gaps[gaps["gap_id"] == gap_id]
        if found.empty:
            return None
        g = found.iloc[0]
        size = int(g["size_cells"])

        traj = pd.read_parquet(self._path("dataset", "trajectories.parquet"))
        track = traj[traj["mmsi"] == g["mmsi"]].sort_values("idx")[["idx", "ts", "lat", "lon", "sog", "cog"]]
        truth = pd.read_parquet(self._path("gaps", "truth.parquet"))
        truth = truth[truth["gap_id"] == gap_id].sort_values("idx")[["idx", "ts", "lat", "lon"]]

        metrics = {}
        per_gap = self._per_gap()
        if per_gap is not None:
            for r in _records(per_gap[per_gap["gap_id"] == gap_id]):
                metrics[r["method"]] = r

        methods = []
        for method, sizes in self.runs().items():
            if size not in sizes:
                continue
            outcomes = self._outcomes(method, size)
            o = outcomes[outcomes["gap_id"] == gap_id]
            if o.empty:
                continue
            o = _records(o)[0]
            points = self._points(method, size)
            points = points[points["gap_id"] == gap_id].sort_values("idx")[["idx", "ts", "lat", "lon"]]
            methods.append({
                "method": method,
                "status": o.get("status"),
                "reason": o.get("reason"),
                "path": o.get("path"),
                "latency_s": o.get("latency_s"),
                "tokens": o.get("tokens"),
                "points": _records(points),
                "metrics": metrics.get(method),
                "alternatives": self._alternatives(method, size, gap_id),
                "walk": self._walk(method, size, gap_id),
                "explanation": self._explanation(method, size, gap_id),
            })

        detail = _records(found.drop(columns=["cells"], errors="ignore"))[0]
        detail["cells"] = clean(list(g["cells"])) if "cells" in g else []
        return clean({
            "gap": detail,
            "track": _records(track),
            "truth": _records(truth),
            "methods": methods,
        })

    def _walk_record(self, method: str, size: int, gap_id: str) -> Optional[Dict]:
        """A walk's cached record (EGC27/cache/hexa/c<size>/<gap_id>.json), or None."""
        if method != "hexa":
            return None
        path = self.cache_dir / "hexa" / f"c{size}" / f"{gap_id}.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text())
        except (OSError, ValueError):
            return None

    def _explanation(self, method: str, size: int, gap_id: str) -> Optional[Dict]:
        """
        What a method recorded of its own reasoning for this gap, when the
        experiment extracted it (completions/<method>_c<size>_explanations.json,
        written for VISTA by `vista_adapter collect`).
        """
        path = self._path("completions", f"{method}_c{size}_explanations.json")
        if not path.exists():
            return None
        try:
            return clean(json.loads(path.read_text()).get(gap_id))
        except (OSError, ValueError):
            return None

    def _walk(self, method: str, size: int, gap_id: str) -> Optional[Dict]:
        record = self._walk_record(method, size, gap_id)
        return explain_walk(record) if record else None

    def _alternatives(self, method: str, size: int, gap_id: str) -> List[Dict]:
        """The other scenarios a walk considered, from the walk's own cache."""
        record = self._walk_record(method, size, gap_id)
        if record is None:
            return []
        payload = record.get("payload") or {}
        # Only walks that reached the gap's far end, most probable first: an
        # abandoned branch stops partway and, drawn beside the finished ones,
        # reads as a route that does not connect.
        finished = [s for s in payload.get("scenarios") or [] if s.get("finished", True) and s.get("path")]
        finished.sort(key=lambda s: s.get("probability") or 0, reverse=True)
        return clean([
            {"path": s["path"], "probability": s.get("probability")}
            for s in finished[:ALTERNATIVE_SCENARIOS]
        ])


# ------------------------------------------------------------- walk explanation
def _move(a: str, b: str) -> str:
    """The compass direction of one step between two cells, or "stay"."""
    if a == b:
        return "stay"
    (lat1, lon1), (lat2, lon2) = h3.cell_to_latlng(a), h3.cell_to_latlng(b)
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    bearing = math.degrees(math.atan2(
        math.sin(dlon) * math.cos(phi2),
        math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlon),
    )) % 360
    return COMPASS[int((bearing + 22.5) // 45) % 8]


def _outcome(scenario: Dict, kept: Optional[List[str]]) -> str:
    if scenario.get("finished"):
        return "kept" if kept is not None and scenario.get("path") == kept else "finished"
    reason = scenario.get("abandoned_reason") or ""
    if reason.startswith("did not reach"):
        return "step_limit"
    if reason.startswith("pruned"):
        return "pruned"
    return "abandoned"


def explain_walk(record: Dict) -> Optional[Dict]:
    """
    How a Hexa walk reached its answer, from its cached record:

      - steps: the kept path, one step per move, with the model's reason for
        it and the move's compass direction ("stay" for staying put);
      - tree:  every branch the walk explored, as a prefix tree of cells. A
        node is a partial path; a leaf carries how its branch ended (kept,
        finished, pruned for a more probable one, out of steps, abandoned)
        and its probability.

    Each scenario's reasons[i] justifies the move path[i] -> path[i+1].
    """
    payload = record.get("payload") or {}
    scenarios = [s for s in payload.get("scenarios") or [] if s.get("path")]
    if not scenarios:
        return None
    kept = record.get("path")

    steps = []
    kept_scenario = next((s for s in scenarios if s["path"] == kept), None) if kept else None
    if kept_scenario:
        reasons = kept_scenario.get("reasons") or []
        for i in range(len(kept) - 1):
            steps.append({
                "step": i + 1,
                "from": kept[i],
                "to": kept[i + 1],
                "move": _move(kept[i], kept[i + 1]),
                "reason": reasons[i] if i < len(reasons) else None,
            })

    nodes: List[Dict] = []
    index: Dict[tuple, int] = {}
    for scenario in scenarios:
        path, reasons = scenario["path"], scenario.get("reasons") or []
        for depth in range(len(path)):
            key = tuple(path[: depth + 1])
            if key in index:
                continue
            index[key] = len(nodes)
            nodes.append({
                "id": len(nodes),
                "parent": index[key[:-1]] if depth else None,
                "cell": path[depth],
                "depth": depth,
                "reason": reasons[depth - 1] if 0 < depth <= len(reasons) else None,
                "outcome": None,
                "probability": None,
                "abandoned_reason": None,
            })
        leaf = nodes[index[tuple(path)]]
        leaf["outcome"] = _outcome(scenario, kept)
        leaf["probability"] = scenario.get("probability")
        leaf["abandoned_reason"] = scenario.get("abandoned_reason")

    outcomes = [_outcome(s, kept) for s in scenarios]
    return clean({
        "probability": record.get("probability"),
        "llm_calls": record.get("llm_calls"),
        "steps": steps,
        "tree": {
            "nodes": nodes,
            "counts": {
                "branches": len(scenarios),
                "finished": sum(o in ("kept", "finished") for o in outcomes),
                "pruned": outcomes.count("pruned"),
                "step_limit": outcomes.count("step_limit"),
                "abandoned": outcomes.count("abandoned"),
                "max_depth": max(n["depth"] for n in nodes),
            },
        },
    })
