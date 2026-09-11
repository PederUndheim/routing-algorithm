r"""The Crux Identifier, against small synthetic rasters.

Run from the project directory - skimap/, the one holding skimap/ and tests/:

    & "C:\Program Files\QGIS 4.2.0\bin\python-qgis.bat" -m unittest discover -s tests -t . -v

unittest rather than pytest: the QGIS-bundled Python has no pytest, and
skimap runs with nothing to install.

Each test paints a strip of terrain, one character per 10 m cell, and
writes it as the three rasters the identifier reads - Int8 PRA, Float32
slope, Int16 runout, each with the national raster's own nodata value, so
the sentinels are read here exactly as they are in the real data. The strip
sits on the national lattice in EPSG:25833, and the line walked along it is
handed over in WGS84, as the app sends it. It runs along the middle row from
the first cell's centre to the last's, so each 10 m sample lands on exactly
one cell and sample i is i * 10 m from the start.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
from osgeo import gdal, osr

from skimap import crux

gdal.UseExceptions()

# Somewhere in Romsdalen, on the national lattice: cell edges at 5 + 10k.
WEST = 136_005.0
NORTH = 6_964_505.0
CELL = 10.0
ROWS = 3
ROW_Y = NORTH - 1.5 * CELL  # the middle row's centre

# The national rasters' nodata. For PRA it means "not a release area" and
# for runout "beyond runout reach" - both answers. Only slope's is a hole.
PRA_NODATA = -128
SLOPE_NODATA = -9999.0
RUNOUT_NODATA = 10_000

# One character per cell: (PRA %, slope in degrees, runout in metres). None
# is that raster's nodata value.
CELLS = {
    ".": (None, 10.0, None),   # nothing: no release area, gentle, out of reach
    "R": (80, 38.0, 0),        # Probable release area - and steep, and in runout
    "F": (None, 35.0, None),   # Fall hazard alone
    "U": (None, 15.0, 250),    # Runout area alone
    "X": (None, None, None),   # slope unknown and nothing else found: No data
}


def _grid_to_wgs84() -> osr.CoordinateTransformation:
    source, target = osr.SpatialReference(), osr.SpatialReference()
    source.ImportFromEPSG(25833)
    target.ImportFromEPSG(4326)
    source.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    target.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    return osr.CoordinateTransformation(source, target)


TO_WGS84 = _grid_to_wgs84()


def wgs84(x: float, y: float) -> tuple[float, float]:
    """(lng, lat) of a grid point."""
    lng, lat, _ = TO_WGS84.TransformPoint(x, y)
    return lng, lat


def cell_centre(col: int) -> float:
    return WEST + (col + 0.5) * CELL


def _write(path: Path, values: np.ndarray, gdal_type: int, nodata: float) -> Path:
    ds = gdal.GetDriverByName("GTiff").Create(
        str(path), values.shape[1], values.shape[0], 1, gdal_type)
    ds.SetGeoTransform((WEST, CELL, 0.0, NORTH, 0.0, -CELL))
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(25833)
    ds.SetProjection(srs.ExportToWkt())
    band = ds.GetRasterBand(1)
    band.SetNoDataValue(nodata)
    band.WriteArray(values)
    ds = None
    return path


def paint(pattern: str, directory: Path, cells: dict | None = None) -> crux.Sources:
    """The three rasters for a strip drawn as `pattern`, every row alike."""
    legend = {**CELLS, **(cells or {})}
    pra, slope, runout = zip(*(legend[c] for c in pattern))

    def column(values, nodata, dtype):
        row = np.array([nodata if v is None else v for v in values], dtype=dtype)
        return np.tile(row, (ROWS, 1))

    return crux.Sources(
        pra=_write(directory / "pra.tif", column(pra, PRA_NODATA, np.int8),
                   gdal.GDT_Int8, PRA_NODATA),
        slope=_write(directory / "slope.tif", column(slope, SLOPE_NODATA, np.float32),
                     gdal.GDT_Float32, SLOPE_NODATA),
        runout=_write(directory / "runout.tif", column(runout, RUNOUT_NODATA, np.int16),
                      gdal.GDT_Int16, RUNOUT_NODATA),
    )


def line_along(cells: int, *, reverse: bool = False) -> dict:
    """A WGS84 LineString from the first cell's centre to the last's."""
    ends = [wgs84(cell_centre(0), ROW_Y), wgs84(cell_centre(cells - 1), ROW_Y)]
    if reverse:
        ends.reverse()
    return {"type": "LineString", "coordinates": [list(p) for p in ends]}


def cruxes(result: dict) -> list[tuple]:
    """(number, class, distance from start, zone length) per Crux."""
    return [(c["number"], c["class"], c["distance_m"], c["length_m"])
            for c in result["cruxes"]]


def segments(result: dict) -> list[tuple]:
    """(class, start, end) per segment."""
    return [(s["class"], s["start_m"], s["end_m"]) for s in result["segments"]]


class CruxTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def identify(self, pattern: str, *, reverse: bool = False,
                 cells: dict | None = None) -> dict:
        sources = paint(pattern, self.tmp, cells)
        return crux.identify(line_along(len(pattern), reverse=reverse), sources)


class EachDangerClassAlone(CruxTestCase):
    def test_probable_release_area(self):
        result = self.identify("....RRRR....")

        self.assertEqual(cruxes(result), [(1, "probable_release_area", 40.0, 40.0)])
        self.assertEqual(segments(result), [
            ("none", 0.0, 35.0),
            ("probable_release_area", 35.0, 75.0),
            ("none", 75.0, 110.0),
        ])
        self.assertEqual(result["length_m"], 110.0)
        self.assertEqual(result["no_data_m"], 0.0)

        # The Crux sits on the zone's first sample, and the red stretch is
        # drawn from half a cell before it to half a cell past the last.
        # Six places: the response rounds to seven, about a centimetre.
        position = result["cruxes"][0]["position"]
        lng, lat = wgs84(cell_centre(4), ROW_Y)
        self.assertAlmostEqual(position["lng"], lng, places=6)
        self.assertAlmostEqual(position["lat"], lat, places=6)

        line = result["segments"][1]["line"]
        self.assertEqual(line["type"], "LineString")
        first, last = line["coordinates"][0], line["coordinates"][-1]
        expected_first = wgs84(cell_centre(0) + 35.0, ROW_Y)
        expected_last = wgs84(cell_centre(0) + 75.0, ROW_Y)
        for got, want in ((first, expected_first), (last, expected_last)):
            self.assertAlmostEqual(got[0], want[0], places=6)
            self.assertAlmostEqual(got[1], want[1], places=6)

    def test_fall_hazard(self):
        result = self.identify("...FFF...")

        self.assertEqual(cruxes(result), [(1, "fall_hazard", 30.0, 30.0)])
        self.assertEqual(segments(result), [
            ("none", 0.0, 25.0),
            ("fall_hazard", 25.0, 55.0),
            ("none", 55.0, 80.0),
        ])

    def test_runout_area(self):
        result = self.identify("..UUUUU..")

        self.assertEqual(cruxes(result), [(1, "runout_area", 20.0, 50.0)])

    def test_release_ground_itself_counts_as_runout_area(self):
        # Runout 0 is a release cell of the runout model. Below the PRA
        # threshold and on gentle ground, that is all that applies there.
        result = self.identify("..000..", cells={"0": (30, 20.0, 0)})

        self.assertEqual(cruxes(result), [(1, "runout_area", 20.0, 30.0)])

    def test_thresholds(self):
        # PRA must be above 50; slope 30 or more, with no upper cap.
        result = self.identify(
            "..a..b..c..d..",
            cells={"a": (50, 10.0, None), "b": (51, 10.0, None),
                   "c": (None, 29.9, None), "d": (None, 75.0, None)},
        )

        self.assertEqual(cruxes(result), [
            (1, "probable_release_area", 50.0, 10.0),
            (2, "fall_hazard", 110.0, 10.0),
        ])


class OverlappingClasses(CruxTestCase):
    def test_probable_release_area_outranks_the_other_two(self):
        # Every R cell is also 38 degrees and inside the runout model.
        result = self.identify("..RRRR..")

        self.assertEqual(cruxes(result), [(1, "probable_release_area", 20.0, 40.0)])

    def test_fall_hazard_outranks_runout_area(self):
        result = self.identify("..ffff..", cells={"f": (None, 35.0, 200)})

        self.assertEqual(cruxes(result), [(1, "fall_hazard", 20.0, 40.0)])


class DangerZonesAndCruxes(CruxTestCase):
    def test_re_entering_a_class_gives_a_second_crux(self):
        result = self.identify("..FFF.....FFF..")

        self.assertEqual(cruxes(result), [
            (1, "fall_hazard", 20.0, 30.0),
            (2, "fall_hazard", 100.0, 30.0),
        ])

    def test_a_step_down_gives_a_new_crux(self):
        # Leaving the release area while still on steep ground.
        result = self.identify("..RRRFFF..")

        self.assertEqual(cruxes(result), [
            (1, "probable_release_area", 20.0, 30.0),
            (2, "fall_hazard", 50.0, 30.0),
        ])

    def test_a_reversed_line_gives_mirrored_cruxes(self):
        pattern = "..RRR.....FF.."

        forward = self.identify(pattern)
        backward = self.identify(pattern, reverse=True)

        self.assertEqual(cruxes(forward), [
            (1, "probable_release_area", 20.0, 30.0),
            (2, "fall_hazard", 100.0, 20.0),
        ])
        self.assertEqual(cruxes(backward), [
            (1, "fall_hazard", 20.0, 20.0),
            (2, "probable_release_area", 90.0, 30.0),
        ])


class NoData(CruxTestCase):
    def test_a_nodata_hole_is_a_no_data_stretch(self):
        result = self.identify("...XXXX...")

        self.assertEqual(segments(result), [
            ("none", 0.0, 25.0),
            ("no_data", 25.0, 65.0),
            ("none", 65.0, 90.0),
        ])
        self.assertEqual(result["no_data_m"], 40.0)
        self.assertEqual(cruxes(result), [])

    def test_off_the_rasters_is_no_data(self):
        # Four cells of terrain, a line three cells longer than that. The
        # "." cells are PRA and runout nodata - known ground, not missing.
        sources = paint("....", self.tmp)

        result = crux.identify(line_along(7), sources)

        self.assertEqual(segments(result), [("none", 0.0, 35.0), ("no_data", 35.0, 60.0)])
        self.assertEqual(result["no_data_m"], 25.0)

    def test_a_known_danger_outranks_a_missing_raster(self):
        # Slope unknown throughout, but PRA establishes a release area and
        # the runout model reaches the second stretch.
        result = self.identify("..PPP..uuu..", cells={"P": (80, None, None),
                                                      "u": (None, None, 250),
                                                      ".": (None, None, None)})

        self.assertEqual(cruxes(result), [
            (1, "probable_release_area", 20.0, 30.0),
            (2, "runout_area", 70.0, 30.0),
        ])
        self.assertEqual([s[0] for s in segments(result)], [
            "no_data", "probable_release_area", "no_data", "runout_area", "no_data",
        ])


class BridgingShortDips(CruxTestCase):
    def test_a_short_dip_to_a_lower_class_stays_in_one_zone(self):
        # Probable release area, 20 m of Fall hazard, Probable release area.
        result = self.identify("..RRRFFRRR..")

        self.assertEqual(cruxes(result), [(1, "probable_release_area", 20.0, 80.0)])
        self.assertEqual(segments(result), [
            ("none", 0.0, 15.0),
            ("probable_release_area", 15.0, 95.0),
            ("none", 95.0, 110.0),
        ])

    def test_a_short_spike_of_a_higher_class_keeps_its_own_crux(self):
        # Fall hazard, a 10 m crossing of a release area, Fall hazard.
        result = self.identify("..FFFRFFF..")

        self.assertEqual(cruxes(result), [
            (1, "fall_hazard", 20.0, 30.0),
            (2, "probable_release_area", 50.0, 10.0),
            (3, "fall_hazard", 60.0, 30.0),
        ])

    def test_a_short_gap_of_no_danger_is_bridged(self):
        result = self.identify("..FFF..FFF..")

        self.assertEqual(cruxes(result), [(1, "fall_hazard", 20.0, 80.0)])

    def test_a_short_no_data_hole_is_bridged(self):
        result = self.identify("..FFFXXFFF..")

        self.assertEqual(cruxes(result), [(1, "fall_hazard", 20.0, 80.0)])
        self.assertEqual(result["no_data_m"], 0.0)

    def test_a_dip_of_several_lower_runs_is_bridged_as_one(self):
        # 10 m of Fall hazard then 10 m of nothing: 20 m below release, together.
        result = self.identify("..RRRF.RRR..")

        self.assertEqual(cruxes(result), [(1, "probable_release_area", 20.0, 80.0)])

    def test_a_long_gap_is_not_bridged(self):
        result = self.identify("..FFF....FFF..")

        self.assertEqual(cruxes(result), [
            (1, "fall_hazard", 20.0, 30.0),
            (2, "fall_hazard", 90.0, 30.0),
        ])

    def test_a_gap_of_exactly_the_dip_length_is_not_bridged(self):
        result = self.identify("..FFF...FFF..")

        self.assertEqual(cruxes(result), [
            (1, "fall_hazard", 20.0, 30.0),
            (2, "fall_hazard", 80.0, 30.0),
        ])

    def test_runs_at_either_end_are_never_bridged(self):
        # Short no-data runs at both ends have a zone on one side only.
        result = self.identify("XFFF..FFFX")

        self.assertEqual(segments(result), [
            ("no_data", 0.0, 5.0),
            ("fall_hazard", 5.0, 85.0),
            ("no_data", 85.0, 90.0),
        ])
        self.assertEqual(result["no_data_m"], 10.0)


class CruxDetails(CruxTestCase):
    def test_a_probable_release_area_reports_its_highest_pra(self):
        result = self.identify("..abc..", cells={"a": (60, 35.0, 0),
                                                 "b": (85, 40.0, 0),
                                                 "c": (70, 33.0, 0)})

        crux_ = result["cruxes"][0]
        self.assertEqual(crux_["max_pra_percent"], 85)
        self.assertNotIn("max_slope_deg", crux_)

    def test_a_fall_hazard_reports_its_steepest_slope(self):
        # The no-data hole inside the zone is bridged, and does not count.
        result = self.identify("..aXXb..", cells={"a": (None, 31.0, None),
                                                  "b": (None, 42.5, None)})

        crux_ = result["cruxes"][0]
        self.assertEqual(crux_["max_slope_deg"], 42.5)
        self.assertNotIn("max_pra_percent", crux_)

    def test_a_runout_area_has_no_extra_value(self):
        result = self.identify("..UU..")

        crux_ = result["cruxes"][0]
        self.assertNotIn("max_pra_percent", crux_)
        self.assertNotIn("max_slope_deg", crux_)


class LongRoutes(CruxTestCase):
    def test_a_line_longer_than_one_read_piece(self):
        piece = crux.PIECE_SAMPLES
        cells = ["."] * (2 * piece + 100)
        # One zone straddling the first piece boundary, one in the last piece.
        cells[piece - 5:piece + 5] = "R" * 10
        cells[-50:-40] = "F" * 10

        result = self.identify("".join(cells))

        self.assertEqual(cruxes(result), [
            (1, "probable_release_area", (piece - 5) * CELL, 100.0),
            (2, "fall_hazard", (len(cells) - 50) * CELL, 100.0),
        ])


if __name__ == "__main__":
    unittest.main()
