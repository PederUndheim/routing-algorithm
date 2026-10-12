r"""A route through waypoints: its legs joined into one line, and their
corridors into one picture.

Run from the project directory - skimap/, the one holding skimap/ and tests/:

    & "C:\Program Files\QGIS 4.2.0\bin\python-qgis.bat" -m unittest discover -s tests -t . -v

Nothing here routes - that needs GRASS and the national surface. These are
the parts that put finished legs together.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
from osgeo import gdal, osr

from app.backend import corridor as corridor_png
from app.backend.service import join_legs
from skimap import config

gdal.UseExceptions()

X0, Y0 = 136_000.0, 6_964_000.0


def line(*points):
    return np.array([(X0 + x, Y0 + y) for x, y in points], dtype=np.float64)


class JoinLegs(unittest.TestCase):

    def test_a_shared_point_is_kept_once(self):
        joined, starts = join_legs([line((0, 0), (100, 0)), line((100, 0), (100, 50))])
        np.testing.assert_allclose(joined, line((0, 0), (100, 0), (100, 50)))
        self.assertEqual(starts, [0.0, 100.0])

    def test_a_gap_is_stepped_across_and_counted(self):
        # A terrain leg starts on its first cell's centre, a few metres off.
        joined, starts = join_legs([line((0, 0), (100, 0)), line((103, 4), (200, 4))])
        self.assertEqual(len(joined), 4)
        self.assertEqual(starts, [0.0, 105.0])

    def test_three_legs_each_start_where_the_line_has_got_to(self):
        _, starts = join_legs([line((0, 0), (10, 0)), line((10, 0), (30, 0)),
                               line((30, 0), (30, 40))])
        self.assertEqual(starts, [0.0, 10.0, 30.0])


def corridor_tif(directory: Path, name: str, west: float, scores: np.ndarray) -> Path:
    """A corridor GeoTIFF as route_one writes them: Float32 on 10 m cells,
    config.NODATA outside the band."""
    path = directory / name
    rows, cols = scores.shape
    out = gdal.GetDriverByName("GTiff").Create(str(path), cols, rows, 1, gdal.GDT_Float32)
    out.SetGeoTransform((X0 + west, 10.0, 0.0, Y0, 0.0, -10.0))
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(config.CRS_EPSG)
    out.SetProjection(srs.ExportToWkt())
    band = out.GetRasterBand(1)
    band.SetNoDataValue(config.NODATA)
    band.WriteArray(scores.astype(np.float32))
    out = None
    return path


class MergeCorridors(unittest.TestCase):

    def test_both_legs_are_in_the_merged_grid_and_the_higher_score_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            a = np.full((4, 4), config.NODATA)
            a[:, 2:] = 0.5
            b = np.full((4, 4), config.NODATA)
            b[:, :2] = 0.9
            # b starts 20 m east of a, so a's right half and b's left overlap.
            merged = corridor_png._merge([corridor_tif(tmp, "a.tif", 0.0, a),
                                          corridor_tif(tmp, "b.tif", 20.0, b)])
            self.assertEqual((merged.RasterXSize, merged.RasterYSize), (6, 4))
            scores = merged.GetRasterBand(1).ReadAsArray()
            np.testing.assert_allclose(scores[:, 2:4], 0.9)
            self.assertTrue(np.isnan(scores[:, :2]).all())
            self.assertTrue(np.isnan(scores[:, 4:]).all())

    def test_two_tifs_make_one_png(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            tifs = [corridor_tif(tmp, "a.tif", 0.0, np.full((4, 4), 0.5)),
                    corridor_tif(tmp, "b.tif", 2000.0, np.full((4, 4), 0.5))]
            bounds = corridor_png.to_png(tifs, tmp / "out.png")
            self.assertTrue((tmp / "out.png").exists())
            self.assertLess(bounds["west"], bounds["east"])


if __name__ == "__main__":
    unittest.main()
