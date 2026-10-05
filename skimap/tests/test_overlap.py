r"""skimap.overlap, against synthetic lines and corridors.

Run from the project directory - skimap/, the one holding skimap/ and tests/:

    & "C:\Program Files\QGIS 4.2.0\bin\python-qgis.bat" -m unittest tests.test_overlap -v

The lines are in metres on a bare plane. Corridors are made from them
directly - membership falling from 1 on the line to 0 at HALF_WIDTH - so
every expectation below can be worked out by hand from a distance.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
from osgeo import gdal, osr
from scipy.spatial import cKDTree

from skimap import config, overlap

gdal.UseExceptions()

NEAR, FAR, MIN_SHARED = 30.0, 100.0, 200.0
HALF_WIDTH = 200.0
CELL = 10.0

# Green climbs straight north. Red shares its first kilometre, then turns east.
GREEN = [(0.0, 0.0), (0.0, 2000.0)]
RED = [(0.0, 0.0), (0.0, 1000.0), (1500.0, 1000.0)]


def _weights(lines, fade_in_m=0.0):
    return overlap.weights(lines, near_m=NEAR, far_m=FAR, min_shared_m=MIN_SHARED,
                           fade_in_m=fade_in_m)


def _at(line: overlap.Line, station: float) -> int:
    return int(np.argmin(np.abs(line.station - station)))


class Weights(unittest.TestCase):

    def test_a_tour_with_nothing_easier_is_drawn_in_full(self):
        red = overlap.make_line(1, "red", RED, step_m=5.0)
        self.assertTrue(np.all(_weights({1: red})[1] == 1.0))

    def test_the_easiest_tour_is_never_faded(self):
        lines = {1: overlap.make_line(1, "green", GREEN, step_m=5.0),
                 2: overlap.make_line(2, "red", RED, step_m=5.0)}
        self.assertTrue(np.all(_weights(lines)[1] == 1.0))

    def test_a_shared_start_fades_and_the_own_leg_returns(self):
        red = overlap.make_line(2, "red", RED, step_m=5.0)
        lines = {1: overlap.make_line(1, "green", GREEN, step_m=5.0), 2: red}
        w = _weights(lines)[2]
        self.assertEqual(w[_at(red, 500.0)], 0.0)      # on the green line
        self.assertEqual(w[_at(red, 1500.0)], 1.0)     # 500 m east of it
        # The handover is gradual, not a step.
        mid = w[_at(red, 1065.0)]                      # 65 m off the green line
        self.assertGreater(mid, 0.0)
        self.assertLess(mid, 1.0)

    def test_fade_in_brings_the_own_leg_in_over_route(self):
        # The lines are 100 m apart - the end of the fade - 1100 m along red.
        red = overlap.make_line(2, "red", RED, step_m=5.0)
        lines = {1: overlap.make_line(1, "green", GREEN, step_m=5.0), 2: red}
        plain, faded = _weights(lines)[2], _weights(lines, fade_in_m=400.0)[2]
        self.assertEqual(plain[_at(red, 1200.0)], 1.0)
        self.assertLess(faded[_at(red, 1200.0)], 0.5)      # 100 m into the fade-in
        self.assertEqual(faded[_at(red, 1600.0)], 1.0)     # past it
        self.assertTrue(np.all(np.diff(faded[_at(red, 1100.0):_at(red, 1500.0)]) >= 0.0))

    def test_fade_in_leaves_an_unshared_tour_alone(self):
        red = overlap.make_line(1, "red", RED, step_m=5.0)
        self.assertTrue(np.all(_weights({1: red}, fade_in_m=400.0)[1] == 1.0))

    def test_a_crossing_is_not_a_shared_trail(self):
        lines = {1: overlap.make_line(1, "green", [(-1000.0, 0.0), (1000.0, 0.0)], step_m=5.0),
                 2: overlap.make_line(2, "red", [(0.0, -1000.0), (0.0, 1000.0)], step_m=5.0)}
        self.assertTrue(np.all(_weights(lines)[2] == 1.0))

    def test_same_class_tours_do_not_fade_each_other(self):
        lines = {1: overlap.make_line(1, "red", GREEN, step_m=5.0),
                 2: overlap.make_line(2, "red", RED, step_m=5.0)}
        w = _weights(lines)
        self.assertTrue(np.all(w[1] == 1.0) and np.all(w[2] == 1.0))


class Blend(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.lines = {1: overlap.make_line(1, "green", GREEN, step_m=5.0),
                     2: overlap.make_line(2, "red", RED, step_m=5.0)}
        xs = np.arange(-400.0, 1700.0, CELL) + CELL / 2
        ys = np.arange(2400.0, -400.0, -CELL) - CELL / 2
        cls.cx, cls.cy = np.meshgrid(xs, ys)
        cells = np.column_stack([cls.cx.ravel(), cls.cy.ravel()])
        cls.corridors = {}
        for fid, line in cls.lines.items():
            d, _ = cKDTree(line.points).query(cells)
            cls.corridors[fid] = (np.clip(1.0 - d / HALF_WIDTH, 0.0, 1.0) ** 2).reshape(cls.cx.shape)
        cls.weights = _weights(cls.lines)
        cls.severity, cls.value = overlap.blend(
            cls.corridors, cls.lines, cls.weights, (cls.cx, cls.cy), easier_priority=1.0)

    def _cell(self, x, y):
        return np.unravel_index(np.argmin(np.abs(self.cx - x) + np.abs(self.cy - y)), self.cx.shape)

    def test_the_shared_start_is_green_across_its_width(self):
        green = overlap.SEVERITY["green"]
        self.assertEqual(self.severity[self._cell(0, 500)], green)
        self.assertEqual(self.severity[self._cell(150, 500)], green)

    def test_no_red_shows_under_the_shared_start(self):
        red = overlap.SEVERITY["red"]
        self.assertFalse(np.any((self.severity == red) & (self.cy < 700)))

    def test_the_red_leg_is_red(self):
        self.assertEqual(self.severity[self._cell(1000, 1000)], overlap.SEVERITY["red"])

    def test_no_gap_where_the_lines_split(self):
        for x in np.arange(0.0, 1400.0, CELL):
            value = self.value[self._cell(x, 1000)]
            self.assertGreaterEqual(value, 0.35, f"membership {value:.2f} at x={x:.0f} on the red leg")

    def test_priority_keeps_contested_cells_for_the_easier_band(self):
        # About 70 m off the green line on the red leg, red's weighted
        # membership beats green's by less than 2x: a plain argmax gives the
        # cell to red, a priority of 2 keeps it green.
        cell = self._cell(70, 1000)
        severity, _ = overlap.blend(self.corridors, self.lines, self.weights,
                                    (self.cx, self.cy), easier_priority=2.0, priority_floor=0.25)
        self.assertEqual(self.severity[cell], overlap.SEVERITY["red"])
        self.assertEqual(severity[cell], overlap.SEVERITY["green"])

    def test_the_easier_fringe_gets_no_priority(self):
        # 105 m off the green line and 95 m off the red leg: green's
        # membership is about 0.23, red's 0.28. Boosted, the faint green
        # fringe would win; under the floor it does not.
        cell = self._cell(105, 1095)
        boosted, _ = overlap.blend(self.corridors, self.lines, self.weights,
                                   (self.cx, self.cy), easier_priority=2.0, priority_floor=0.0)
        floored, _ = overlap.blend(self.corridors, self.lines, self.weights,
                                   (self.cx, self.cy), easier_priority=2.0, priority_floor=0.25)
        self.assertEqual(boosted[cell], overlap.SEVERITY["green"])
        self.assertEqual(floored[cell], overlap.SEVERITY["red"])

    def test_the_classes_are_disjoint_and_cover_only_corridor(self):
        inside = (self.corridors[1] > 0) | (self.corridors[2] > 0)
        self.assertFalse(np.any((self.severity >= 0) & ~inside))
        self.assertTrue(np.all((self.severity >= 0) == (self.value > 0)))


class Seam(unittest.TestCase):
    """Green on the left half of a strip, red on the right, full membership."""

    def setUp(self):
        self.severity = np.full((5, 40), overlap.SEVERITY["green"], dtype=np.int8)
        self.severity[:, 20:] = overlap.SEVERITY["red"]
        self.value = np.ones((5, 40), dtype=np.float32)

    def test_no_seam_is_the_disjoint_split(self):
        out = overlap.soft_classes(self.severity, self.value, pixel_m=CELL, seam_m=0.0)
        self.assertTrue(np.all(out["green"][:, :20] == 1.0) and np.all(out["green"][:, 20:] == 0.0))
        self.assertTrue(np.all(out["red"][:, 20:] == 1.0) and np.all(out["red"][:, :20] == 0.0))

    def test_a_seam_cross_fades_and_keeps_the_total(self):
        out = overlap.soft_classes(self.severity, self.value, pixel_m=CELL, seam_m=40.0)
        green, red = out["green"][2], out["red"][2]
        self.assertAlmostEqual(float(green[1]), 1.0, places=3)     # far from the seam
        self.assertAlmostEqual(float(red[38]), 1.0, places=3)
        self.assertGreater(float(red[19]), 0.3)                    # beside the old line
        self.assertGreater(float(green[20]), 0.3)
        self.assertTrue(np.allclose(green + red, 1.0, atol=1e-5))
        self.assertTrue(np.all(np.diff(red) >= -1e-6))             # red only grows left to right

    def test_empty_cells_stay_empty(self):
        self.severity[:, :5] = -1
        self.value[:, :5] = 0.0
        out = overlap.soft_classes(self.severity, self.value, pixel_m=CELL, seam_m=40.0)
        self.assertTrue(np.all(out["green"][:, :5] == 0.0) and np.all(out["red"][:, :5] == 0.0))
        self.assertAlmostEqual(float(out["green"][2, 6]), 1.0, places=3)  # no fade at the outer edge


CORRIDOR_NODATA = -9999.0


def _write_tif(path: Path, array: np.ndarray, *, x0: float, y1: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ds = gdal.GetDriverByName("GTiff").Create(str(path), array.shape[1], array.shape[0], 1,
                                              gdal.GDT_Float32)
    ds.SetGeoTransform((x0, CELL, 0.0, y1, 0.0, -CELL))
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(25833)
    ds.SetProjection(srs.ExportToWkt())
    band = ds.GetRasterBand(1)
    band.SetNoDataValue(CORRIDOR_NODATA)
    band.WriteArray(array.astype(np.float32))
    ds = None


@unittest.skipUnless(float(config.PIXEL_SIZE) == CELL, "corridors here are built at 10 m")
class WriteClasses(unittest.TestCase):
    """The tiled writer exposure uses, against one window blended whole.

    Each corridor is written as its own GeoTIFF cropped to where it has
    cells, with nodata outside, the way route_one writes them. Tiles of 16
    cells against a seam that reaches 9 put almost every seam across a tile
    edge - which is where a tiled version would go wrong.
    """

    SETTINGS = dict(near_m=NEAR, far_m=FAR, min_shared_m=MIN_SHARED, fade_in_m=0.0,
                    easier_priority=2.0, priority_floor=0.25)
    SEAM = 40.0

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.lines = {1: overlap.make_line(1, "green", GREEN, step_m=5.0),
                      2: overlap.make_line(2, "red", RED, step_m=5.0)}

        xs = np.arange(-400.0, 1700.0, CELL) + CELL / 2
        ys = np.arange(2400.0, -400.0, -CELL) - CELL / 2
        cx, cy = np.meshgrid(xs, ys)
        cells = np.column_stack([cx.ravel(), cy.ravel()])
        self.files = {}
        for fid, line in self.lines.items():
            d, _ = cKDTree(line.points).query(cells)
            v = (np.clip(1.0 - d / HALF_WIDTH, 0.0, 1.0) ** 2).reshape(cx.shape)
            rows, cols = np.nonzero(v > 0)
            r0, r1, c0, c1 = rows.min(), rows.max() + 1, cols.min(), cols.max() + 1
            crop = v[r0:r1, c0:c1]
            path = self.root / "corridors" / f"{fid:03d}_synthetic.tif"
            _write_tif(path, np.where(crop > 0, crop, CORRIDOR_NODATA),
                       x0=-400.0 + c0 * CELL, y1=2400.0 - r0 * CELL)
            self.files[fid] = path

    def test_tiles_give_what_one_window_gives(self):
        out = self.root / "colored"
        stale = out / "corridors_black.tif"
        _write_tif(stale, np.ones((2, 2)), x0=0.0, y1=0.0)

        written = overlap.write_classes(self.lines, self.files, out, seam_m=self.SEAM,
                                        tile_cells=16, report=False, **self.SETTINGS)
        self.assertEqual(set(written), {"green", "red"})
        self.assertFalse(stale.exists(), "a class with no cells must not leave a stale raster")

        boxes = [overlap.extent(p) for p in self.files.values()]
        x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
        x1, y1 = max(b[2] for b in boxes), max(b[3] for b in boxes)
        window = overlap.Window(x0, y1, int(round((x1 - x0) / CELL)),
                                int(round((y1 - y0) / CELL)), CELL)
        settings = dict(self.SETTINGS)
        priority, floor = settings.pop("easier_priority"), settings.pop("priority_floor")
        whole = {fid: overlap.read(window, p) for fid, p in self.files.items()}
        severity, value = overlap.blend(whole, self.lines, overlap.weights(self.lines, **settings),
                                        window.centres(), easier_priority=priority,
                                        priority_floor=floor)
        expected = overlap.soft_classes(severity, value, pixel_m=CELL, seam_m=self.SEAM)

        for colour in ("green", "red"):
            np.testing.assert_allclose(overlap.read(window, written[colour]), expected[colour],
                                       atol=1e-6, err_msg=colour)
        self.assertGreater(float((expected["red"] > 0).sum()), 0.0)
        self.assertGreater(float(((expected["green"] > 0) & (expected["red"] > 0)).sum()), 0.0,
                           "the seam should make the two overlap somewhere")


if __name__ == "__main__":
    unittest.main()
