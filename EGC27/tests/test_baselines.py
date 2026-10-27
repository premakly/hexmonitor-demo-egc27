"""Tests des références simples et de la conversion chemin → points."""
from types import SimpleNamespace

import h3
import numpy as np
import pandas as pd
import pytest
import shapefile

from EGC27.baselines import DENSITY_WEIGHT, DensityCost, astar, linear
from EGC27.completion import cells_to_waypoints, place_along
from EGC27.dataset import haversine_km
from EGC27.landmask import LandMask

START = h3.latlng_to_cell(46.0, -3.0, 7)
GOAL = h3.latlng_to_cell(46.0, -2.7, 7)


def ctx(**kw):
    base = dict(lat_before=46.0, lon_before=-3.0, ts_before=0, lat_after=46.0, lon_after=-2.7, ts_after=1000,
                target_ts=[250, 500, 750])
    base.update(kw)
    return SimpleNamespace(**base)


def no_density():
    return DensityCost(pd.DataFrame({"cell": ["x"], "count": [10]}))


# --- placement le long d'un chemin -----------------------------------------------


def test_positions_follow_elapsed_time_at_constant_speed():
    wp = np.array([(46.0, -3.0), (46.0, -2.7)])
    pos = place_along(wp, 0, 1000, [0, 500, 1000])
    d = haversine_km(46.0, -3.0, pos[:, 0], pos[:, 1])
    total = haversine_km(46.0, -3.0, 46.0, -2.7)
    assert d == pytest.approx([0, total / 2, total], rel=1e-3)


def test_a_detour_is_followed_not_cut():
    """Sur un chemin en L, le point situé à la longueur du premier côté est au coin."""
    wp = np.array([(46.0, -3.0), (46.3, -3.0), (46.3, -2.7)])
    first = haversine_km(46.0, -3.0, 46.3, -3.0)
    total = first + haversine_km(46.3, -3.0, 46.3, -2.7)
    lat, lon = place_along(wp, 0, 1000, [1000 * first / total])[0]
    assert lat == pytest.approx(46.3, abs=1e-6) and lon == pytest.approx(-3.0, abs=1e-6)


def test_a_motionless_path_stays_at_the_anchor():
    pos = place_along(np.array([(46.0, -3.0), (46.0, -3.0)]), 0, 1000, [100, 900])
    assert (pos == [46.0, -3.0]).all()


def test_waypoints_use_the_real_anchors_at_both_ends():
    path = [START, *h3.grid_path_cells(START, GOAL)[1:-1], GOAL]
    wp = cells_to_waypoints(path, ctx())
    assert tuple(wp[0]) == (46.0, -3.0) and tuple(wp[-1]) == (46.0, -2.7)
    assert len(wp) == len(path)


def test_linear_reference_lies_on_the_chord():
    pos = linear(ctx())
    assert np.allclose(pos[:, 0], 46.0, atol=1e-3)
    assert np.all(np.diff(pos[:, 1]) > 0)


# --- A* ----------------------------------------------------------------------------


def test_astar_links_the_two_cells_by_neighbours():
    path = astar(START, GOAL, no_density(), None)
    assert path[0] == START and path[-1] == GOAL
    assert all(h3.grid_distance(a, b) == 1 for a, b in zip(path, path[1:]))


def test_without_density_the_path_is_as_short_as_the_grid_allows():
    assert len(astar(START, GOAL, no_density(), None)) == h3.grid_distance(START, GOAL) + 1


def test_astar_prefers_a_frequented_corridor():
    """Un couloir dense légèrement plus long est préféré à la ligne droite vide."""
    lat_corr = 46.04
    corridor = {h3.latlng_to_cell(lat_corr, lon, 7) for lon in np.linspace(-3.0, -2.7, 80)}
    cost = DensityCost(pd.DataFrame({"cell": sorted(corridor), "count": 10_000}))
    path = astar(START, GOAL, cost, None)
    inner = path[1:-1]
    assert sum(c in corridor for c in inner) > len(inner) / 2


def test_cost_bounds():
    cost = DensityCost(pd.DataFrame({"cell": ["a", "b"], "count": [0, 1000]}))
    assert cost("b") == pytest.approx(1.0)
    assert cost("inconnue") == pytest.approx(1 + DENSITY_WEIGHT)


@pytest.fixture
def wall(tmp_path):
    """Une barrière de terre entre départ et arrivée, ouverte au nord."""
    path = tmp_path / "wall"
    w = shapefile.Writer(str(path), shapeType=shapefile.POLYGON)
    w.field("n", "C")
    w.poly([[(-2.86, 45.80), (-2.86, 46.08), (-2.84, 46.08), (-2.84, 45.80), (-2.86, 45.80)]])
    w.record("wall")
    w.close()
    return LandMask([str(path) + ".shp"])


def test_astar_goes_around_land_narrower_than_a_cell(wall):
    """La barrière (1,5 km) est plus étroite qu'une cellule : aucun centre n'y tombe forcément."""
    path = astar(START, GOAL, no_density(), wall)
    assert path is not None
    centres = [h3.cell_to_latlng(c) for c in path]
    assert not any(wall.crosses_land(a, b) for a, b in zip(centres[1:-2], centres[2:-1]))
    assert len(path) > h3.grid_distance(START, GOAL) + 1


def test_no_sea_route_is_reported_not_invented(tmp_path):
    path = tmp_path / "closed"
    w = shapefile.Writer(str(path), shapeType=shapefile.POLYGON)
    w.field("n", "C")
    w.poly([[(-2.86, 44.0), (-2.86, 48.0), (-2.84, 48.0), (-2.84, 44.0), (-2.86, 44.0)]])
    w.record("x")
    w.close()
    assert astar(START, GOAL, no_density(), LandMask([str(path) + ".shp"])) is None


def test_astar_is_deterministic():
    assert astar(START, GOAL, no_density(), None) == astar(START, GOAL, no_density(), None)


def test_land_mask_tells_land_from_sea(wall):
    assert wall.on_land([46.0, 46.0], [-2.85, -3.0]).tolist() == [True, False]


# --- lissage ------------------------------------------------------------------------

from EGC27.completion import smooth  # noqa: E402


def test_smoothing_keeps_the_real_anchors():
    wp = np.array([(46.0, -3.0), (46.1, -2.9), (46.0, -2.8), (46.1, -2.7)])
    out = smooth(wp, 2)
    assert tuple(out[0]) == tuple(wp[0]) and tuple(out[-1]) == tuple(wp[-1])


def test_smoothing_cuts_corners():
    """Un zigzag lissé est plus court : il ne repasse plus par chaque sommet."""
    wp = np.array([(46.0, -3.0), (46.1, -2.9), (46.0, -2.8), (46.1, -2.7), (46.0, -2.6)])
    length = lambda p: haversine_km(p[:-1, 0], p[:-1, 1], p[1:, 0], p[1:, 1]).sum()
    assert length(smooth(wp, 2)) < length(wp)


def test_a_straight_line_is_left_straight():
    wp = np.array([(46.0, -3.0), (46.0, -2.9), (46.0, -2.8)])
    assert np.allclose(smooth(wp, 2)[:, 0], 46.0)
