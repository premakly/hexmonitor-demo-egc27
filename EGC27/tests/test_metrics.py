"""Tests des métriques (étape 7)."""
import numpy as np
import pandas as pd
import pytest

from EGC27.dataset import haversine_km
from EGC27.metrics import (
    bootstrap_ci,
    discrete_frechet_km,
    holm,
    interior_grid,
    paired_test,
    rank_biserial,
    resample,
    summarise,
)


# --- rééchantillonnage ------------------------------------------------------------


def test_grid_stays_strictly_inside_the_gap():
    """Les ancres sont communes à toutes les méthodes : les inclure gonflerait l'accord."""
    g = interior_grid(0, 1000, 300)
    assert g.tolist() == [300, 600, 900]


def test_a_gap_shorter_than_the_step_still_gets_its_midpoint():
    assert interior_grid(0, 200, 300).tolist() == [100]


def test_resample_interpolates_in_time():
    t = np.array([0, 100, 200])
    lat = np.array([46.0, 46.1, 46.3])
    lon = np.array([-3.0, -3.0, -3.0])
    out = resample(t, lat, lon, np.array([50, 150]))
    assert out[:, 0] == pytest.approx([46.05, 46.2])


# --- Fréchet ----------------------------------------------------------------------


def test_frechet_of_identical_tracks_is_zero():
    a = np.array([(46.0, -3.0), (46.1, -3.0), (46.2, -3.0)])
    assert discrete_frechet_km(a, a) == pytest.approx(0.0)


def test_frechet_of_a_parallel_track_is_the_offset():
    a = np.array([(46.0, -3.0), (46.1, -3.0), (46.2, -3.0)])
    b = a + [0.0, 0.1]
    assert discrete_frechet_km(a, b) == pytest.approx(haversine_km(46.0, -3.0, 46.0, -2.9), rel=0.01)


def test_frechet_sees_an_excursion_a_mean_would_dilute():
    a = np.array([(46.0, -3.0 + 0.01 * i) for i in range(21)])
    b = a.copy()
    b[10, 0] += 0.2  # une excursion de 22 km sur un seul point
    assert discrete_frechet_km(a, b) > 20


def test_frechet_respects_order():
    """Parcourir les mêmes lieux à l'envers n'est pas suivre la même route."""
    a = np.array([(46.0, -3.0), (46.1, -3.0), (46.2, -3.0)])
    assert discrete_frechet_km(a, a[::-1]) > 10


# --- statistiques -----------------------------------------------------------------


def test_bootstrap_ci_brackets_the_mean_and_is_reproducible():
    x = np.random.default_rng(1).normal(5, 1, 50)
    lo, hi = bootstrap_ci(x, 2000, seed=42)
    assert lo < x.mean() < hi
    assert (lo, hi) == bootstrap_ci(x, 2000, seed=42)


def test_bootstrap_of_a_single_value_has_no_interval():
    assert np.isnan(bootstrap_ci(np.array([3.0]), 100, seed=0)[0])


def test_rank_biserial_sign_and_bounds():
    """Négatif quand la première méthode a l'erreur la plus faible."""
    assert rank_biserial(np.array([-1.0, -2.0, -3.0])) == pytest.approx(-1.0)
    assert rank_biserial(np.array([1.0, 2.0, 3.0])) == pytest.approx(1.0)
    assert -1 < rank_biserial(np.array([-3.0, 1.0, 2.0])) < 1


def test_paired_test_uses_only_gaps_both_methods_completed():
    per_gap = pd.DataFrame({
        "gap_id": ["g1", "g2", "g3", "g1", "g2", "g3"],
        "method": ["a", "a", "a", "b", "b", "b"],
        "status": ["ok", "ok", "failed", "ok", "ok", "ok"],
        "mean_km": [1.0, 2.0, np.nan, 2.0, 4.0, 9.0],
    })
    r = paired_test(per_gap, "a", "b")
    assert r["n"] == 2
    assert r["wins_a_pct"] == pytest.approx(100.0)


def test_holm_is_monotone_and_never_below_raw():
    p = np.array([0.01, 0.04, 0.03, 0.2])
    adj = holm(p)
    assert np.all(adj >= p)
    assert adj[np.argsort(p)].tolist() == sorted(adj.tolist())
    assert adj[0] == pytest.approx(0.04)


# --- agrégation -------------------------------------------------------------------


def per_gap_frame():
    rows = []
    for level in ("facile", "difficile"):
        for i in range(4):
            rows.append({"gap_id": f"{level}{i}", "size_cells": 2, "level": level, "method": "m",
                         "status": "failed" if i == 3 else "ok", "mean_km": np.nan if i == 3 else float(i + 1),
                         "max_km": 1.0, "frechet_km": 1.0, "point_mae_km": 1.0, "land_pct": 0.0,
                         "tokens": 10.0, "latency_s": 1.0})
    return pd.DataFrame(rows)


def test_failures_count_in_the_rate_not_in_the_errors():
    s = summarise(per_gap_frame(), bootstrap=200, seed=0)
    row = s[(s.level == "facile")].iloc[0]
    assert row["n_gaps"] == 4 and row["n_ok"] == 3
    assert row["failure_pct"] == pytest.approx(25.0)
    assert row["mean_km"] == pytest.approx(2.0)


def test_summary_has_an_all_levels_row():
    s = summarise(per_gap_frame(), bootstrap=200, seed=0)
    assert set(s.level) == {"facile", "difficile", "tous"}
    assert s[s.level == "tous"].iloc[0]["n_gaps"] == 8
