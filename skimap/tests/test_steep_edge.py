r"""The edge of steep ground - combine.fill_corners, combine.buffer_steep,
and the halo read they depend on.

Run from the project directory - skimap/, the one holding skimap/ and tests/:

    & "C:\Program Files\QGIS 4.2.0\bin\python-qgis.bat" -m unittest tests.test_steep_edge -v

The leak tests are the point of the corner fill. r.cost moves 8-connected and
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


def buffer(cost, slope, add, threshold_deg=30.0):
    return combine.buffer_steep(cost, slope >= threshold_deg, add=add)


def corners(cost, slope, threshold_deg=30.0):
    return combine.fill_corners(cost, slope >= threshold_deg, slope)


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

    def test_diagonal_band_leaks_as_it_is(self):
        cost, _ = diagonal_band()
        self.assertTrue(cheap_side_to_side(cost),
                        "the premise: corner-touching steep cells are crossable")


class CornerFill(unittest.TestCase):
    """Only the diagonal gaps, one cell each - nothing else moves."""

    def test_closes_the_diagonal_band(self):
        cost, slope = diagonal_band()
        out, steep = corners(cost, slope)
        self.assertFalse(cheap_side_to_side(out))
        # 9 steep cells, 8 corners between them, one cell each.
        self.assertEqual(int((out != cost).sum()), 8)
        self.assertEqual(int(steep.sum()), 9 + 8)

    def test_both_diagonals(self):
        cost, slope = diagonal_band()
        out, _ = corners(np.fliplr(cost).copy(), np.fliplr(slope).copy())
        self.assertFalse(cheap_side_to_side(np.fliplr(out)))
        self.assertEqual(int((out != np.fliplr(cost)).sum()), 8)

    def test_fills_the_steeper_gentle_cell_at_the_cheaper_steep_cost(self):
        slope = np.array([[35.0, 12.0],
                          [25.0, 40.0]], dtype=np.float32)
        cost = np.array([[50.0, 4.0],
                         [6.0, 70.0]], dtype=np.float32)
        out, _ = corners(cost, slope)
        np.testing.assert_array_equal(out, [[50.0, 4.0], [50.0, 70.0]])

    def test_a_whole_gentle_cell_is_not_a_corner(self):
        # Steep, gentle, steep in a row: a real 10 m gap, walked through
        # its own cell and paid for. Left open.
        slope = np.full((3, 3), FLAT, dtype=np.float32)
        slope[1, 0] = slope[1, 2] = STEEP
        cost = np.where(slope >= 30.0, DEAR, CHEAP).astype(np.float32)
        out, _ = corners(cost, slope)
        np.testing.assert_array_equal(out, cost)

    def test_solid_and_isolated_steep_ground_is_untouched(self):
        slope = np.full((7, 7), FLAT, dtype=np.float32)
        slope[1:4, 1:4] = STEEP     # a solid block
        slope[5, 5] = STEEP         # a lone cell
        cost = np.where(slope >= 30.0, DEAR, CHEAP).astype(np.float32)
        out, _ = corners(cost, slope)
        np.testing.assert_array_equal(out, cost)

    def test_corner_closed_by_a_steep_cell_already_is_left_alone(self):
        slope = np.array([[STEEP, STEEP],
                          [FLAT, STEEP]], dtype=np.float32)
        cost = np.where(slope >= 30.0, DEAR, CHEAP).astype(np.float32)
        out, _ = corners(cost, slope)
        np.testing.assert_array_equal(out, cost)


class Buffer(unittest.TestCase):

    def test_off_is_identity(self):
        cost, slope = diagonal_band()
        self.assertIs(buffer(cost, slope, 0.0), cost)

    def test_a_toll_on_the_8_neighbours_not_a_wall(self):
        slope = np.full((5, 5), FLAT, dtype=np.float32)
        slope[2, 2] = STEEP
        cost = np.where(slope >= 30.0, DEAR, CHEAP).astype(np.float32)
        out = buffer(cost, slope, 5.0)
        ring = np.zeros((5, 5), bool)
        ring[1:4, 1:4] = True
        ring[2, 2] = False
        np.testing.assert_array_equal(out[ring], CHEAP + 5.0)
        np.testing.assert_array_equal(out[~ring], cost[~ring])

    def test_never_lands_on_steep_cells(self):
        slope = np.array([[STEEP, STEEP, FLAT]], dtype=np.float32)
        cost = np.array([[DEAR, DEAR, CHEAP]], dtype=np.float32)
        np.testing.assert_array_equal(buffer(cost, slope, 5.0),
                                      [[DEAR, DEAR, CHEAP + 5.0]])

    def test_leaves_the_gaps_open(self):
        # Two steep patches with a gentle cell between: the toll makes it
        # dearer, not as dear as the steep ground - the detour stays worth it.
        slope = np.array([[STEEP, FLAT, STEEP]], dtype=np.float32)
        cost = np.where(slope >= 30.0, DEAR, CHEAP).astype(np.float32)
        out = buffer(cost, slope, 5.0)
        self.assertEqual(out[0, 1], CHEAP + 5.0)
        self.assertLess(out[0, 1], DEAR)

    def test_counts_filled_corners_as_steep(self):
        cost, slope = diagonal_band()
        filled, steep = combine.fill_corners(cost, slope >= 30.0, slope)
        out = combine.buffer_steep(filled, steep, add=5.0)
        np.testing.assert_array_equal(out[steep], filled[steep])
        self.assertFalse(cheap_side_to_side(out))


class HaloRead(unittest.TestCase):
    """read_tile(halo=) must hand back the cells just outside the tile, on
    the same lattice, or the corner fill and buffer have a seam on every tile edge."""

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
