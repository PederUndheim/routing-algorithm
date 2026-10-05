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

from skimap import config, crux

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
    "F": (None, 55.0, None),   # Fall hazard alone
    "S": (None, 35.0, None),   # Steep slope alone
    "U": (None, 15.0, 250),    # Runout area alone
    "X": (None, None, None),   # slope unknown and nothing else found: No data
    "p": (80, 10.0, None),     # PRA on gentle ground, out of runout: nothing
    "P": (80, 38.0, None),     # steep and a release area, not in runout
    "V": (80, 55.0, None),     # steep, a release area AND a fall hazard
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


def marks(area: dict) -> tuple[bool, bool]:
    """(probable release area, fall hazard) of one Crux or segment."""
    return area.get("probable_release_area", False), area.get("fall_hazard", False)


class CruxTestCase(unittest.TestCase):
    """A strip of terrain, read with the settings that ship.

    Strips are laid out so the shipped split_gap_m and steep_gap_m do what
    the test is about; `setting` overrides one for a test that is about the
    threshold itself.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self._crux = dict(config.CRUX)

    def tearDown(self) -> None:
        config.CRUX.clear()
        config.CRUX.update(self._crux)
        self._tmp.cleanup()

    def setting(self, **settings) -> None:
        """Settings for this test only; tearDown puts them all back."""
        config.CRUX.update(settings)

    def identify(self, pattern: str, *, reverse: bool = False,
                 cells: dict | None = None) -> dict:
        sources = paint(pattern, self.tmp, cells)
        return crux.identify(line_along(len(pattern), reverse=reverse), sources)


class WhatASampleIs(CruxTestCase):
    def test_steep_slope(self):
        result = self.identify("...SSS...")

        self.assertEqual(cruxes(result), [(1, "steep_slope", 30.0, 30.0)])
        self.assertEqual(segments(result), [
            ("none", 0.0, 25.0),
            ("steep_slope", 25.0, 55.0),
            ("none", 55.0, 80.0),
        ])
        self.assertEqual(result["length_m"], 80.0)
        self.assertEqual(result["no_data_m"], 0.0)

        # The Crux sits on the area's first sample, and the coloured stretch
        # runs from half a cell before it to half a cell past the last. Six
        # places: the response rounds to seven, about a centimetre.
        position = result["cruxes"][0]["position"]
        lng, lat = wgs84(cell_centre(3), ROW_Y)
        self.assertAlmostEqual(position["lng"], lng, places=6)
        self.assertAlmostEqual(position["lat"], lat, places=6)

        line = result["segments"][1]["line"]
        self.assertEqual(line["type"], "LineString")
        first, last = line["coordinates"][0], line["coordinates"][-1]
        for got, want in ((first, wgs84(cell_centre(0) + 25.0, ROW_Y)),
                          (last, wgs84(cell_centre(0) + 55.0, ROW_Y))):
            self.assertAlmostEqual(got[0], want[0], places=6)
            self.assertAlmostEqual(got[1], want[1], places=6)

    def test_runout_area(self):
        result = self.identify("..UUUUU..")

        self.assertEqual(cruxes(result), [(1, "runout_area", 20.0, 50.0)])

    def test_release_ground_itself_counts_as_runout_area(self):
        # Runout 0 is a release cell of the runout model. On gentle ground
        # that is all that applies there.
        result = self.identify("..000..", cells={"0": (30, 20.0, 0)})

        self.assertEqual(cruxes(result), [(1, "runout_area", 20.0, 30.0)])

    def test_steep_ground_is_steep_even_inside_a_runout(self):
        # Every R cell is 38 degrees AND inside the runout model. Slope
        # decides; runout is only the fallback.
        result = self.identify("..RRRR..")

        self.assertEqual(cruxes(result), [(1, "steep_slope", 20.0, 40.0)])

    def test_a_release_area_off_steep_ground_is_nothing(self):
        # 80 % PRA on 10-degree ground, outside any runout. The slope map
        # this is read against shows nothing there, so neither does this.
        result = self.identify("..ppp..")

        self.assertEqual(cruxes(result), [])
        self.assertEqual(segments(result), [("none", 0.0, 60.0)])

    def test_the_slope_threshold(self):
        # Below 30 is nothing; 30 and up is a Steep slope, with no upper
        # cap. Four cells between each, so no pair is merged as one area.
        result = self.identify(
            "..a....b....c..",
            cells={"a": (None, 29.9, None), "b": (None, 30.0, None),
                   "c": (None, 75.0, None)},
        )

        self.assertEqual(cruxes(result), [
            (1, "steep_slope", 70.0, 10.0),
            (2, "steep_slope", 120.0, 10.0),
        ])


class WhatASteepAreaTurnsOutToBe(CruxTestCase):
    def test_plain_steep_ground_carries_neither_mark(self):
        result = self.identify("..SSS..")
        entry = result["cruxes"][0]

        self.assertEqual(marks(entry), (False, False))
        self.assertEqual(entry["max_slope_deg"], 35.0)
        self.assertNotIn("max_pra_percent", entry)

    def test_a_release_area_anywhere_in_it_marks_the_whole_area(self):
        # One release cell in the middle of otherwise plain steep ground.
        result = self.identify("..SSPSS..")
        entry = result["cruxes"][0]

        self.assertEqual(marks(entry), (True, False))
        self.assertEqual(entry["length_m"], 50.0)
        self.assertEqual(entry["max_pra_percent"], 80.0)

    def test_the_pra_threshold(self):
        # Above 50, not at it.
        at = self.identify("..SSS..", cells={"S": (50, 35.0, None)})
        above = self.identify("..SSS..", cells={"S": (51, 35.0, None)})

        self.assertEqual(marks(at["cruxes"][0]), (False, False))
        self.assertEqual(marks(above["cruxes"][0]), (True, False))

    def test_a_fall_hazard_anywhere_in_it_marks_the_whole_area(self):
        result = self.identify("..SSFSS..")
        entry = result["cruxes"][0]

        self.assertEqual(marks(entry), (False, True))
        self.assertEqual(entry["max_slope_deg"], 55.0)

    def test_an_area_can_be_both(self):
        result = self.identify("..SSVSS..")

        self.assertEqual(marks(result["cruxes"][0]), (True, True))

    def test_a_release_area_outside_the_steep_ground_does_not_count(self):
        # The PRA cells are gentle and out of runout, so they are none, and
        # the steep area beside them is plain.
        result = self.identify("..ppSSSpp..")
        entry = result["cruxes"][0]

        self.assertEqual(marks(entry), (False, False))
        self.assertEqual(entry["length_m"], 30.0)

    def test_a_runout_area_carries_none_of_it(self):
        entry = self.identify("..UUUUU..")["cruxes"][0]

        for key in ("probable_release_area", "fall_hazard", "max_slope_deg",
                    "max_pra_percent"):
            self.assertNotIn(key, entry)

    def test_the_segment_says_the_same_as_its_crux(self):
        result = self.identify("..SSPSS..")
        steep = [s for s in result["segments"] if s["class"] == "steep_slope"][0]

        self.assertEqual(marks(steep), marks(result["cruxes"][0]))
        self.assertEqual(steep["max_pra_percent"],
                         result["cruxes"][0]["max_pra_percent"])


class MergingRunsIntoAreas(CruxTestCase):
    def test_safe_ground_under_the_gap_is_no_break(self):
        # 30 m of none inside steep ground, and split_gap_m is 40.
        result = self.identify("..SSS...SSS..")

        self.assertEqual(cruxes(result), [(1, "steep_slope", 20.0, 90.0)])
        self.assertEqual(segments(result), [
            ("none", 0.0, 15.0),
            ("steep_slope", 15.0, 105.0),
            ("none", 105.0, 120.0),
        ])

    def test_safe_ground_at_the_gap_is_a_break(self):
        # 40 m, so not under 40.
        result = self.identify("..SSS....SSS..")

        self.assertEqual([c[1] for c in cruxes(result)],
                         ["steep_slope", "steep_slope"])

    def test_closing_a_gap_never_promotes_it(self):
        # None between runout and steep becomes runout, the lower of the
        # two - never steep, which would invent steep ground.
        result = self.identify("..UUU...SSS..")

        self.assertEqual(segments(result), [
            ("none", 0.0, 15.0),
            ("runout_area", 15.0, 75.0),
            ("steep_slope", 75.0, 105.0),
            ("none", 105.0, 120.0),
        ])

    def test_safe_ground_at_either_end_is_never_closed(self):
        result = self.identify("..SSS")

        self.assertEqual(segments(result)[0], ("none", 0.0, 15.0))

    def test_runout_under_the_steep_gap_joins_two_steep_areas(self):
        # 30 m of runout between, and steep_gap_m is 100: one area, one
        # Crux, and the runout between takes the worst of it.
        result = self.identify("..SSSUUUSSS..")

        self.assertEqual(cruxes(result), [(1, "steep_slope", 20.0, 90.0)])
        self.assertEqual(segments(result), [
            ("none", 0.0, 15.0),
            ("steep_slope", 15.0, 105.0),
            ("none", 105.0, 120.0),
        ])

    def test_runout_at_the_steep_gap_does_not(self):
        result = self.identify("..SSS" + "U" * 10 + "SSS..")

        self.assertEqual([c[1] for c in cruxes(result)],
                         ["steep_slope", "steep_slope"])

    def test_runout_over_the_steep_gap_does_not(self):
        result = self.identify("..SSS" + "U" * 15 + "SSS..")

        self.assertEqual([c[1] for c in cruxes(result)],
                         ["steep_slope", "steep_slope"])

    def test_the_marks_of_a_merged_area_are_the_worst_of_it(self):
        # Plain steep, runout, then steep holding a release area: merged,
        # so the whole thing is a probable release area.
        result = self.identify("..SSSUUUPPP..")

        self.assertEqual(len(result["cruxes"]), 1)
        self.assertEqual(marks(result["cruxes"][0]), (True, False))
        self.assertEqual(result["cruxes"][0]["length_m"], 90.0)

    def test_several_hops_merge_into_one_area(self):
        result = self.identify("..SSUUSSUUSS..")

        self.assertEqual(cruxes(result), [(1, "steep_slope", 20.0, 100.0)])

    def test_no_data_between_two_steep_areas_does_not_merge_them(self):
        # 60 m of No data - past split_gap_m, and not runout either.
        result = self.identify("..SSSXXXXXXSSS..")

        self.assertEqual([c[1] for c in cruxes(result)],
                         ["steep_slope", "steep_slope"])


class WhereCruxesGo(CruxTestCase):
    """A marker where an area outranks the one before it, and nowhere else."""

    def test_the_first_runout_gets_a_crux(self):
        result = self.identify("..UUUUU..")

        self.assertEqual(cruxes(result), [(1, "runout_area", 20.0, 50.0)])

    def test_a_line_starting_in_runout_gets_a_crux(self):
        result = self.identify("UUUUU..")

        self.assertEqual(cruxes(result), [(1, "runout_area", 0.0, 45.0)])

    def test_steep_ground_after_runout_gets_a_crux(self):
        result = self.identify("..UUUSSSUUU..")

        self.assertEqual(cruxes(result), [
            (1, "runout_area", 20.0, 30.0),
            (2, "steep_slope", 50.0, 30.0),
        ])

    def test_runout_after_steep_ground_gets_no_crux(self):
        # The line still turns orange - it is the one colour with no marker
        # of its own, and it is deliberate.
        result = self.identify("..SSSUUUUU..")

        self.assertEqual(cruxes(result), [(1, "steep_slope", 20.0, 30.0)])
        self.assertEqual([s[0] for s in segments(result)],
                         ["none", "steep_slope", "runout_area", "none"])

    def test_a_long_runout_after_steep_ground_still_gets_no_crux(self):
        result = self.identify("..SSS" + "U" * 40 + "..")

        self.assertEqual(cruxes(result), [(1, "steep_slope", 20.0, 30.0)])

    def test_runout_after_safe_ground_gets_a_crux_again(self):
        # Steep, runout, 50 m of none - past split_gap_m - then runout.
        result = self.identify("..SSSUUU.....UUU..")

        self.assertEqual(cruxes(result), [
            (1, "steep_slope", 20.0, 30.0),
            (2, "runout_area", 130.0, 30.0),
        ])

    def test_every_steep_area_gets_one_crux(self):
        result = self.identify("..SSS" + "U" * 15 + "SSS" + "U" * 15 + "SSS..")

        self.assertEqual([c[1] for c in cruxes(result)],
                         ["steep_slope", "steep_slope", "steep_slope"])

    def test_a_reversed_line_gives_mirrored_cruxes(self):
        # Safe ground, steep, runout. Walked the other way the runout comes
        # first, off safe ground, so it rises and earns a Crux the forward
        # direction never gives it. Same terrain, different decisions.
        forward = self.identify("...SSSUU..")
        backward = self.identify("...SSSUU..", reverse=True)

        self.assertEqual(cruxes(forward), [(1, "steep_slope", 30.0, 30.0)])
        self.assertEqual(cruxes(backward), [
            (1, "runout_area", 20.0, 20.0),
            (2, "steep_slope", 40.0, 30.0),
        ])
        self.assertEqual(forward["length_m"], backward["length_m"])


class NoData(CruxTestCase):
    def test_a_nodata_hole_is_a_no_data_stretch(self):
        result = self.identify("...XXXXXX...")

        self.assertEqual([s[0] for s in segments(result)],
                         ["none", "no_data", "none"])
        self.assertEqual(result["no_data_m"], 60.0)
        self.assertEqual(cruxes(result), [])

    def test_off_the_rasters_is_no_data(self):
        # A line running past the end of the strip: the samples beyond it
        # are off every raster.
        cells = 10
        sources = paint("." * cells, self.tmp)
        ends = [wgs84(cell_centre(0), ROW_Y), wgs84(cell_centre(cells + 9), ROW_Y)]
        result = crux.identify(
            {"type": "LineString", "coordinates": [list(p) for p in ends]}, sources)

        self.assertEqual([s[0] for s in segments(result)], ["none", "no_data"])

    def test_a_known_danger_outranks_a_missing_raster(self):
        # Slope unknown, but the runout raster puts the cell in a runout:
        # that is an answer, so the sample is a Runout area, not No data.
        result = self.identify("..mmm..", cells={"m": (None, None, 250)})

        self.assertEqual([s[0] for s in segments(result)],
                         ["none", "runout_area", "none"])


class ShortRunoutAreas(CruxTestCase):
    def test_a_runout_area_under_the_minimum_is_none(self):
        result = self.identify("....U....")

        self.assertEqual(cruxes(result), [])
        self.assertEqual(segments(result), [("none", 0.0, 80.0)])

    def test_a_runout_area_of_exactly_the_minimum_counts(self):
        result = self.identify("....UU....")

        self.assertEqual(cruxes(result), [(1, "runout_area", 40.0, 20.0)])

    def test_a_short_runout_area_does_not_shorten_steep_ground(self):
        result = self.identify("..USSSU..")

        self.assertEqual(cruxes(result), [(1, "steep_slope", 30.0, 30.0)])


class LongRoutes(CruxTestCase):
    def test_a_line_longer_than_one_read_piece(self):
        # More samples than PIECE_SAMPLES, so the rasters are read in
        # several pieces and the results concatenated.
        cells = crux.PIECE_SAMPLES + 100
        pattern = list("." * cells)
        for i in range(20, 23):
            pattern[i] = "S"
        for i in range(cells - 50, cells - 47):
            pattern[i] = "S"
        result = self.identify("".join(pattern))

        self.assertEqual(cruxes(result), [
            (1, "steep_slope", 200.0, 30.0),
            (2, "steep_slope", (cells - 50) * CELL, 30.0),
        ])


if __name__ == "__main__":
    unittest.main()
