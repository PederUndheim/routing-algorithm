r"""Steep ground spread onto its neighbours - combine.spread_steep and the
halo read it depends on.

Run from the project directory - skimap/, the one holding skimap/ and tests/:

    & "C:\Program Files\QGIS 4.2.0\bin\python-qgis.bat" -m unittest tests.test_steep_spread -v

The leak tests are the point of the change. r.cost moves 8-connected and
charges a diagonal step on its two end cells only, so a band of steep cells
that touch only at their corners is no wall: the router steps through the
corner and pays for neither. Whether cheap ground on the two sides of a band
is still 8-connected is exactly whether that step exists.
"""

from __future__ import annotations

import tempfile
import unittest
from collections import deque
from pathlib import Path
from unittest import mock

import numpy as np
from osgeo import gdal, osr

from skimap import config, raster
from skimap.cost_surface import combine
from skimap.grid import Tile

gdal.UseExceptions()

FLAT, STEEP = 10.0, 35.0
CHEAP, DEAR = 4.0, 40.0


def spread(cost, slope, *, radius_px=1, footprint="square", share=1.0, threshold_deg=30.0):
    return combine.spread_steep(cost, slope, threshold_deg=threshold_deg,
                                radius_px=radius_px, footprint=footprint, share=share)


def diagonal_band(n: int = 9) -> tuple[np.ndarray, np.ndarray]:
    """A one-cell steep line from the top-left corner to the bottom-right,
    every cell touching the next only at a corner. (cost, slope)."""
    slope = np.full((n, n), FLAT, dtype=np.float32)
    idx = np.arange(n)
    slope[idx, idx] = STEEP
    return np.where(slope >= 30.0, DEAR, CHEAP).astype(np.float32), slope


def cheap_side_to_side(cost: np.ndarray, below: float = DEAR) -> bool:
    """Can an 8-connected walk on cells cheaper than `below` get from the
    bottom-left corner to the top-right one - across the band?"""
    n_rows, n_cols = cost.shape
    start, goal = (n_rows - 1, 0), (0, n_cols - 1)
    if cost[start] >= below or cost[goal] >= below:
        return False
    seen, todo = {start}, deque([start])
    while todo:
        y, x = todo.popleft()
        if (y, x) == goal:
            return True
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                q = (y + dy, x + dx)
                if (0 <= q[0] < n_rows and 0 <= q[1] < n_cols
                        and q not in seen and cost[q] < below):
                    seen.add(q)
                    todo.append(q)
    return False


class CornerLeak(unittest.TestCase):

    def test_diagonal_band_leaks_without_spread(self):
        cost, _ = diagonal_band()
        self.assertTrue(cheap_side_to_side(cost),
                        "the premise: corner-touching steep cells are crossable")

    def test_disk_radius_1_closes_the_leak(self):
        cost, slope = diagonal_band()
        self.assertFalse(cheap_side_to_side(spread(cost, slope, footprint="disk")))

    def test_square_radius_1_closes_the_leak(self):
        cost, slope = diagonal_band()
        self.assertFalse(cheap_side_to_side(spread(cost, slope, footprint="square")))

    def test_half_share_still_closes_it_at_half_price(self):
        cost, slope = diagonal_band()
        out = spread(cost, slope, share=0.5)
        self.assertFalse(cheap_side_to_side(out, below=DEAR / 2))
        self.assertTrue(cheap_side_to_side(out, below=DEAR),
                        "at half share the ring is a toll, not a wall")


class WhatSpreads(unittest.TestCase):

    def test_off_is_identity(self):
        cost, slope = diagonal_band()
        self.assertIs(spread(cost, slope, radius_px=0), cost)

    def test_only_steep_cells_spread(self):
        # A dear cell on gentle ground - deep in a runout zone, say - stays
        # where it is. Only slope decides what is a source.
        slope = np.full((5, 5), FLAT, dtype=np.float32)
        cost = np.full((5, 5), CHEAP, dtype=np.float32)
        cost[2, 2] = DEAR
        np.testing.assert_array_equal(spread(cost, slope), cost)

    def test_threshold_is_inclusive(self):
        slope = np.full((3, 3), 29.9, dtype=np.float32)
        cost = np.full((3, 3), CHEAP, dtype=np.float32)
        slope[1, 1], cost[1, 1] = 30.0, DEAR
        self.assertTrue((spread(cost, slope) == DEAR).all())

    def test_footprints(self):
        slope = np.full((5, 5), FLAT, dtype=np.float32)
        cost = np.full((5, 5), CHEAP, dtype=np.float32)
        slope[2, 2], cost[2, 2] = STEEP, DEAR

        square = spread(cost, slope, footprint="square") == DEAR
        disk = spread(cost, slope, footprint="disk") == DEAR
        self.assertEqual(int(square.sum()), 9)
        self.assertEqual(int(disk.sum()), 5)
        self.assertFalse(disk[1, 1], "a radius 1 disk is the 4 neighbours")

        self.assertEqual(int((spread(cost, slope, radius_px=2, footprint="square") == DEAR).sum()), 25)
        self.assertEqual(int((spread(cost, slope, radius_px=2, footprint="disk") == DEAR).sum()), 13)

    def test_dearest_neighbour_wins_and_nothing_gets_cheaper(self):
        slope = np.full((1, 5), FLAT, dtype=np.float32)
        cost = np.array([[CHEAP, 30.0, CHEAP, 60.0, 80.0]], dtype=np.float32)
        slope[0, 1] = slope[0, 3] = STEEP
        out = spread(cost, slope)
        # cell 2 sits between a 30 and a 60: it takes the 60. Cell 4 is
        # dearer than anything near it and keeps its own 80.
        np.testing.assert_array_equal(out, [[30.0, 30.0, 60.0, 60.0, 80.0]])

    def test_share_scales_the_spread_value(self):
        slope = np.array([[FLAT, STEEP, FLAT]], dtype=np.float32)
        cost = np.array([[CHEAP, DEAR, 25.0]], dtype=np.float32)
        out = spread(cost, slope, share=0.5)
        np.testing.assert_array_equal(out, [[DEAR / 2, DEAR, 25.0]])

    def test_bad_footprint(self):
        cost, slope = diagonal_band()
        with self.assertRaises(ValueError):
            spread(cost, slope, footprint="hexagon")


class HaloRead(unittest.TestCase):
    """read_tile(halo=) must hand back the cells just outside the tile, on
    the same lattice, or the spread has a seam on every tile edge."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        # A tile on the grid lattice, and a small raster on the raster
        # lattice straddling its north-west corner: 3 cells outside it, 3
        # inside, each way. Values are row * 100 + col, so a cell says where
        # it came from.
        ox, oy = config.GRID_ORIGIN
        self.tile = Tile("tile_test", ox + 100 * config.TILE_SIZE, oy + 300 * config.TILE_SIZE)
        x_nw, y_nw = raster.tile_origin(self.tile)
        p = config.PIXEL_SIZE
        n = 6
        self.path = Path(self.tmp.name) / "probe.tif"
        ds = gdal.GetDriverByName("GTiff").Create(str(self.path), n, n, 1, gdal.GDT_Float32)
        ds.SetGeoTransform((x_nw - 3 * p, p, 0.0, y_nw + 3 * p, 0.0, -p))
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(config.CRS_EPSG)
        ds.SetProjection(srs.ExportToWkt())
        rows, cols = np.mgrid[0:n, 0:n]
        ds.GetRasterBand(1).WriteArray((rows * 100 + cols).astype(np.float32))
        ds.GetRasterBand(1).SetNoDataValue(-9999.0)
        ds = None

    def tearDown(self):
        self.tmp.cleanup()

    def read(self, halo):
        with mock.patch.object(raster.paths, "layer", return_value=self.path):
            return raster.read_tile("probe", self.tile, fill=-1.0, halo=halo)

    def test_no_halo_starts_at_the_tile(self):
        out = self.read(0)
        self.assertEqual(out.shape, (raster.TILE_PX, raster.TILE_PX))
        self.assertEqual(out[0, 0], 303.0)

    def test_halo_reaches_outside_and_keeps_the_inside_aligned(self):
        out = self.read(2)
        self.assertEqual(out.shape, (raster.TILE_PX + 4, raster.TILE_PX + 4))
        self.assertEqual(out[0, 0], 101.0)          # two cells out, each way
        self.assertEqual(out[2, 2], 303.0)          # the tile's own first cell
        np.testing.assert_array_equal(out[2:, 2:][:3, :3], self.read(0)[:3, :3])


if __name__ == "__main__":
    unittest.main()
