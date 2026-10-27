"""
The Experiment view's API: reads the EGC27 scripts' files, never runs a model.
"""
import json

import numpy as np
import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from egc27demo import api as experiment
from egc27demo.experiment_store import ExperimentStore

CELLS = ["871841443ffffff", "871841441ffffff"]


def write_experiment(root):
    """A miniature run: two vessels, gaps of 2 cells, three methods."""
    data = root / "data"
    for sub in ("dataset", "gaps", "completions", "results"):
        (data / sub).mkdir(parents=True)

    traj = pd.concat([
        pd.DataFrame({"mmsi": m, "idx": range(20), "ts": [1000 + 600 * i for i in range(20)],
                      "lat": [46 + 0.01 * i for i in range(20)], "lon": -3.0, "sog": 10.0, "cog": 0.0,
                      "cell": "x", "level": lv})
        for m, lv in ((111, "facile"), (222, "difficile"))
    ])
    traj.to_parquet(data / "dataset" / "trajectories.parquet", index=False)

    gaps = pd.DataFrame({
        "gap_id": ["111_c2", "222_c2"], "mmsi": [111, 222], "level": ["facile", "difficile"],
        "size_cells": [2, 2], "idx_start": [8, 8], "idx_end": [9, 9], "n_removed": [2, 2],
        "duration_h": [0.5, 0.5], "length_km": [2.2, 2.2], "cells": [CELLS, CELLS],
    })
    gaps.to_parquet(data / "gaps" / "gaps.parquet", index=False)
    truth = traj[traj["idx"].isin([8, 9])].assign(gap_id=lambda d: d["mmsi"].astype(str) + "_c2")
    truth.to_parquet(data / "gaps" / "truth.parquet", index=False)

    def completion(method, ok_gaps, path=None):
        pts = truth[truth["gap_id"].isin(ok_gaps)][["gap_id", "idx", "ts", "lat", "lon"]].assign(method=method)
        pts.to_parquet(data / "completions" / f"{method}_c2.parquet", index=False)
        pd.DataFrame({
            "gap_id": ["111_c2", "222_c2"], "method": method,
            "status": ["ok" if g in ok_gaps else "failed" for g in ("111_c2", "222_c2")],
            "reason": [None if g in ok_gaps else "no usable choice" for g in ("111_c2", "222_c2")],
            "latency_s": 1.5, "tokens": [np.nan, np.nan] if method == "vista" else [120.0, 80.0],
            "path": [path, path],
        }).to_parquet(data / "completions" / f"{method}_c2_outcomes.parquet", index=False)

    completion("linear", ["111_c2", "222_c2"])
    completion("hexa", ["111_c2"], path=CELLS)
    completion("vista", ["111_c2", "222_c2"])
    # A trial run must not appear as a method of its own.
    completion("hexa", ["111_c2"])
    (data / "completions" / "hexa_c2.parquet").rename(data / "completions" / "hexa_c2_essai2.parquet")
    (data / "completions" / "hexa_c2_outcomes.parquet").rename(data / "completions" / "hexa_c2_essai2_outcomes.parquet")
    completion("hexa", ["111_c2"], path=CELLS)

    (data / "completions" / "vista_c2_explanations.json").write_text(json.dumps({
        "111_c2": {"status": "ok", "behaviour": {"id": "vb_1", "attributes": {"intent": "navigating"}},
                   "function": {"id": "vf_1", "code": "def spatial_function(...)"}, "explanation": {"operational": "Typical."}},
        "222_c2": {"status": "failed", "behaviour": None, "function": None, "explanation": None},
    }))

    pd.DataFrame({
        "gap_id": ["111_c2", "111_c2", "222_c2"], "size_cells": 2, "level": ["facile", "facile", "difficile"],
        "method": ["hexa", "linear", "hexa"], "status": ["ok", "ok", "failed"],
        "mean_km": [1.2, 0.3, np.nan], "frechet_km": [1.5, 0.4, np.nan],
    }).to_parquet(data / "results" / "per_gap.parquet", index=False)
    pd.DataFrame({"method": ["hexa"], "size_cells": [2], "level": ["tous"], "mean_km": [1.2],
                  "ci_low": [np.nan]}).to_csv(data / "results" / "summary.csv", index=False)
    pd.DataFrame({"size_cells": [2], "a": ["vista"], "b": ["hexa"], "p": [0.01]}).to_csv(
        data / "results" / "tests.csv", index=False)
    (data / "results" / "manifest.json").write_text(json.dumps({"created_at": "2026-10-16T08:00:00"}))

    cache = root / "cache" / "hexa" / "c2"
    cache.mkdir(parents=True)
    (cache / "111_c2.json").write_text(json.dumps({"payload": {"scenarios": [
        {"path": CELLS[::-1], "probability": 0.2, "finished": True},
        {"path": CELLS[:1], "probability": 0.5, "finished": False},
        {"path": CELLS, "probability": 0.6, "finished": True},
    ]}}))
    return data


@pytest.fixture
def client(tmp_path):
    app = FastAPI()
    app.include_router(experiment.router, prefix="/api")
    app.state.experiment = ExperimentStore(write_experiment(tmp_path))
    return TestClient(app)


# --- overview ---------------------------------------------------------------------


def test_overview_discovers_sizes_levels_and_methods(client):
    body = client.get("/api/experiment").json()

    assert body["sizes"] == [2]
    assert body["levels"] == ["facile", "difficile"]
    assert body["methods"] == ["vista", "hexa", "linear"]


def test_trial_runs_are_not_methods(client):
    assert "hexa_c2_essai2" not in json.dumps(client.get("/api/experiment").json()["runs"])


def test_overview_carries_the_results_once_computed(client):
    body = client.get("/api/experiment").json()

    assert body["summary"][0]["mean_km"] == 1.2
    assert body["summary"][0]["ci_low"] is None  # NaN is not valid JSON
    assert body["tests"][0]["a"] == "vista"
    assert body["results_built_at"] == "2026-10-16T08:00:00"
    assert set(body["exports"]) == {"summary", "tests"}


def test_a_missing_experiment_is_a_404_that_says_what_to_run(tmp_path):
    app = FastAPI()
    app.include_router(experiment.router, prefix="/api")
    app.state.experiment = ExperimentStore(tmp_path / "nothing")
    response = TestClient(app).get("/api/experiment")

    assert response.status_code == 404
    assert "data/experiment" in response.json()["detail"]


# --- gap list ---------------------------------------------------------------------


def test_gap_list_carries_each_methods_status(client):
    gaps = {g["gap_id"]: g for g in client.get("/api/experiment/gaps").json()["gaps"]}

    assert gaps["111_c2"]["methods"]["hexa"]["status"] == "ok"
    assert gaps["222_c2"]["methods"]["hexa"]["status"] == "failed"
    assert gaps["111_c2"]["methods"]["hexa"]["mean_km"] == 1.2
    assert gaps["222_c2"]["methods"]["hexa"]["mean_km"] is None


def test_gap_list_filters_by_level_and_size(client):
    assert [g["gap_id"] for g in client.get("/api/experiment/gaps", params={"level": "difficile"}).json()["gaps"]] == ["222_c2"]
    assert client.get("/api/experiment/gaps", params={"size": 8}).json()["gaps"] == []


# --- one gap ----------------------------------------------------------------------


def test_gap_detail_has_window_truth_and_every_method(client):
    body = client.get("/api/experiment/gaps/111_c2").json()

    assert len(body["track"]) == 20
    assert [p["idx"] for p in body["truth"]] == [8, 9]
    assert body["gap"]["cells"] == CELLS
    assert [m["method"] for m in body["methods"]] == ["vista", "hexa", "linear"]


def test_gap_detail_gives_a_methods_points_path_and_metrics(client):
    hexa = {m["method"]: m for m in client.get("/api/experiment/gaps/111_c2").json()["methods"]}["hexa"]

    assert [p["idx"] for p in hexa["points"]] == [8, 9]
    assert hexa["path"] == CELLS
    assert hexa["metrics"]["mean_km"] == 1.2
    assert hexa["tokens"] == 120.0


def test_a_failed_method_says_why_and_has_no_points(client):
    hexa = {m["method"]: m for m in client.get("/api/experiment/gaps/222_c2").json()["methods"]}["hexa"]

    assert hexa["status"] == "failed"
    assert hexa["reason"] == "no usable choice"
    assert hexa["points"] == []


def test_hexa_alternatives_are_finished_walks_most_probable_first(client):
    """An abandoned branch stops partway: shown, it would look like a broken route."""
    hexa = {m["method"]: m for m in client.get("/api/experiment/gaps/111_c2").json()["methods"]}["hexa"]

    assert [a["probability"] for a in hexa["alternatives"]] == [0.6, 0.2]
    assert all(a["path"] != CELLS[:1] for a in hexa["alternatives"])


def test_methods_without_a_walk_have_no_alternatives(client):
    vista = {m["method"]: m for m in client.get("/api/experiment/gaps/111_c2").json()["methods"]}["vista"]

    assert vista["alternatives"] == []
    assert vista["tokens"] is None


def test_unknown_gap_is_a_404(client):
    assert client.get("/api/experiment/gaps/nope").status_code == 404


# --- exports ----------------------------------------------------------------------


def test_summary_export_is_a_csv_download(client):
    response = client.get("/api/experiment/export/summary.csv")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "mean_km" in response.text


def test_only_known_tables_can_be_exported(client):
    """The name must not reach the filesystem as a path."""
    assert client.get("/api/experiment/export/per_gap.csv").status_code == 404
    assert client.get("/api/experiment/export/..%2Fmanifest.csv").status_code == 404


# --- explaining a walk ------------------------------------------------------------

from egc27demo.experiment_store import explain_walk  # noqa: E402

A = "871841443ffffff"


def ring(cell):
    import h3
    return sorted(h3.grid_ring(cell, 1))


def walk_record():
    """A walk from A: kept A>n0>n0n, another finished, one pruned, one out of steps."""
    n0, n1 = ring(A)[:2]
    n0n = [c for c in ring(n0) if c != A][0]
    return {
        "path": [A, n0, n0n], "probability": 0.4, "llm_calls": 7,
        "payload": {"scenarios": [
            {"path": [A, n1], "probability": 0.05, "finished": False,
             "abandoned_reason": "pruned, less probable than surviving branches", "reasons": ["turn away"]},
            {"path": [A, n0, n0n], "probability": 0.4, "finished": True, "abandoned_reason": None,
             "reasons": ["holds course", "direct to destination"]},
            {"path": [A, n0, n0], "probability": 0.2, "finished": True, "abandoned_reason": None,
             "reasons": ["holds course", "waits"]},
            {"path": [A, n1, A], "probability": 0.01, "finished": False,
             "abandoned_reason": "did not reach target within 12 steps", "reasons": ["turn away", "back"]},
        ]},
    }, (n0, n1, n0n)


def test_steps_follow_the_kept_path_with_the_models_reasons():
    record, (n0, _, n0n) = walk_record()
    steps = explain_walk(record)["steps"]

    assert [(s["from"], s["to"]) for s in steps] == [(A, n0), (n0, n0n)]
    assert [s["reason"] for s in steps] == ["holds course", "direct to destination"]
    assert all(s["move"] in {"N", "NE", "E", "SE", "S", "SW", "W", "NW"} for s in steps)


def test_staying_put_is_named_as_such():
    record, (n0, _, _) = walk_record()
    record["path"] = [A, n0, n0]
    assert explain_walk(record)["steps"][-1]["move"] == "stay"


def test_branches_sharing_a_beginning_share_its_nodes():
    record, _ = walk_record()
    nodes = explain_walk(record)["tree"]["nodes"]

    # A, A>n1, A>n0, A>n0>n0n, A>n0>n0, A>n1>A : six distinct partial paths
    assert len(nodes) == 6
    assert sum(1 for n in nodes if n["parent"] is None) == 1
    assert all(nodes[n["parent"]]["depth"] == n["depth"] - 1 for n in nodes if n["parent"] is not None)


def test_a_node_carries_the_reason_for_the_step_into_it():
    record, (n0, _, n0n) = walk_record()
    nodes = explain_walk(record)["tree"]["nodes"]
    by_cell_depth = {(n["cell"], n["depth"]): n for n in nodes}

    assert by_cell_depth[(A, 0)]["reason"] is None
    assert by_cell_depth[(n0n, 2)]["reason"] == "direct to destination"


def test_each_leaf_says_how_its_branch_ended():
    record, _ = walk_record()
    leaves = [n for n in explain_walk(record)["tree"]["nodes"] if n["outcome"]]

    assert sorted(n["outcome"] for n in leaves) == ["finished", "kept", "pruned", "step_limit"]
    kept = next(n for n in leaves if n["outcome"] == "kept")
    assert kept["probability"] == 0.4


def test_counts_summarise_the_exploration():
    record, _ = walk_record()
    counts = explain_walk(record)["tree"]["counts"]

    assert counts == {"branches": 4, "finished": 2, "pruned": 1, "step_limit": 1, "abandoned": 0, "max_depth": 2}


def test_a_failed_walk_still_shows_what_it_explored():
    record, _ = walk_record()
    record["path"] = None
    walk = explain_walk(record)

    assert walk["steps"] == []
    assert "kept" not in {n["outcome"] for n in walk["tree"]["nodes"]}


def test_a_walk_without_scenarios_has_no_explanation():
    assert explain_walk({"payload": {"scenarios": []}}) is None


def test_the_gap_detail_carries_hexas_walk_and_only_hexas(client):
    methods = {m["method"]: m for m in client.get("/api/experiment/gaps/111_c2").json()["methods"]}

    assert methods["hexa"]["walk"]["tree"]["counts"]["branches"] == 3
    assert methods["vista"]["walk"] is None


def test_a_walk_with_no_cache_file_has_no_explanation(client):
    methods = {m["method"]: m for m in client.get("/api/experiment/gaps/222_c2").json()["methods"]}
    assert methods["hexa"]["walk"] is None


# --- VISTA's reasoning ------------------------------------------------------------


def test_the_gap_detail_carries_vistas_reasoning(client):
    vista = {m["method"]: m for m in client.get("/api/experiment/gaps/111_c2").json()["methods"]}["vista"]

    assert vista["explanation"]["behaviour"]["attributes"]["intent"] == "navigating"
    assert vista["explanation"]["function"]["code"].startswith("def spatial_function")


def test_a_failed_vista_gap_says_so(client):
    vista = {m["method"]: m for m in client.get("/api/experiment/gaps/222_c2").json()["methods"]}["vista"]
    assert vista["explanation"]["status"] == "failed"


def test_methods_without_an_extracted_reasoning_have_none(client):
    linear = {m["method"]: m for m in client.get("/api/experiment/gaps/111_c2").json()["methods"]}["linear"]
    assert linear["explanation"] is None
