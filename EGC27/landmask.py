"""Masque terre, à partir des shapefiles Natural Earth de la configuration.

Lecture légère (pyshp + shapely, sans geopandas). Seules les terres proches
de la zone d'étude sont conservées, découpées à son emprise élargie : le
polygone de l'Eurasie entier rendrait chaque test inutilement coûteux.
"""

from __future__ import annotations

from pathlib import Path

import h3
import numpy as np
import shapefile
import shapely
from shapely.geometry import box, shape

from .config import ExperimentConfig

MARGIN_DEG = 2.0


class LandMask:
    def __init__(self, paths, bbox: tuple[float, float, float, float] | None = None):
        clip = box(*bbox) if bbox else None
        geoms = []
        for path in paths:
            reader = shapefile.Reader(str(path))
            for shp in reader.iterShapes():
                if clip is not None:
                    xmin, ymin, xmax, ymax = shp.bbox
                    if xmax < bbox[0] or xmin > bbox[2] or ymax < bbox[1] or ymin > bbox[3]:
                        continue
                geom = shape(shp.__geo_interface__)
                if not geom.is_valid:
                    geom = geom.buffer(0)
                if clip is not None:
                    geom = geom.intersection(clip)
                if not geom.is_empty:
                    geoms.append(geom)
        self.tree = shapely.STRtree(geoms)
        self.size = len(geoms)

    @classmethod
    def from_config(cls, cfg: ExperimentConfig) -> "LandMask":
        z = cfg.zone
        bbox = (z.lon_min - MARGIN_DEG, z.lat_min - MARGIN_DEG, z.lon_max + MARGIN_DEG, z.lat_max + MARGIN_DEG)
        return cls([Path(p) for p in cfg.paths.land_masks], bbox)

    def on_land(self, lat, lon) -> np.ndarray:
        """Vrai pour chaque position située sur terre."""
        lat, lon = np.atleast_1d(lat).astype(float), np.atleast_1d(lon).astype(float)
        hits = self.tree.query(shapely.points(lon, lat), predicate="intersects")
        land = np.zeros(len(lat), dtype=bool)
        land[np.unique(hits[0])] = True
        return land

    def crosses_land(self, a: tuple[float, float], b: tuple[float, float]) -> bool:
        """Vrai si le segment entre deux positions (lat, lon) touche la terre."""
        line = shapely.linestrings([[a[1], a[0]], [b[1], b[0]]])
        return len(self.tree.query(line, predicate="intersects")) > 0

    def cell_on_land(self, cell: str) -> bool:
        """Une cellule est terrestre si son centre l'est."""
        lat, lon = h3.cell_to_latlng(cell)
        return bool(self.on_land(lat, lon)[0])
