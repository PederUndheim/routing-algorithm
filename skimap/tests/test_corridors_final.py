r"""skimap.corridors_final: which tours merge, and what a merged corridor is.

Run from the project directory - skimap/, the one holding skimap/ and tests/:

    & "C:\Program Files\QGIS 4.2.0\bin\python-qgis.bat" -m unittest tests.test_corridors_final -v

Tours are bare (start, end) pairs in metres; corridors are tiny synthetic
rasters on the 10 m lattice, so every expectation can be checked by eye.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from osgeo import gdal, osr

from skimap import config
from skimap.corridors_final import build, chains

gdal.UseExceptions()

ND = config.NODATA


def _ends(**tours):
    """fid -> ((sx, sy), (ex, ey)) from keyword pairs like t1=((0, 0), (0, 1000))."""
    return {int(name[1:]): pair for name, pair in tours.items()}


# A -> B -> C up one valley, a Y (two approaches into one top), and a fork
# (one approach out to two summits). D stands alone but shares A's trailhead.
CHAIN = _ends(t1=((0, 0), (0, 1000)), t2=((0, 1000), (0, 2000)),
              t3=((0, 2003), (0, 3000)), t4=((0, 0), (500, 900)))
Y = _ends(t10=((10_000, 0), (10_000, 1000)), t11=((10_500, 0), (10_000, 1000.5)),
          t12=((10_000, 1000), (10_000, 2000)))
FORK = _ends(t20=((20_000, 0), (20_000, 1000)), t21=((20_000, 1000), (20_000, 2000)),
             t22=((20_000, 1001), (21_000, 1500)))


def _groups(plan):
    return {g.fids: g.how for g in plan.groups}


class Links(unittest.TestCase):

    def test_a_plain_chain_merges_in_route_order(self):
        plan = chains.plan(CHAIN)
        self.assertEqual(_groups(plan), {(1, 2, 3): "auto", (4,): "single"})

    def test_a_shared_trailhead_is_not_a_link(self):
        links = chains.find_links(CHAIN, chains.GAP_M)
        self.assertNotIn(4, {l.head for l in links} | {l.tail for l in links})

    def test_a_branching_group_is_left_unmerged_and_reported(self):
        for case, fids in ((Y, (10, 11, 12)), (FORK, (20, 21, 22))):
            plan = chains.plan(case)
            self.assertEqual(plan.unresolved, [fids])
            self.assertTrue(all(g.how == "single" for g in plan.groups))

    def test_keep_apart_settles_a_branching_group(self):
        plan = chains.plan(Y, chains.Decisions(keep_apart=frozenset({10, 11, 12})))
        self.assertEqual(plan.unresolved, [])
        self.assertEqual(len(plan.groups), 3)

    def test_one_piece_can_be_in_two_merged_corridors(self):
        decisions = chains.Decisions(merge=((20, 21), (22, 20)))
        plan = chains.plan(FORK, decisions)
        self.assertEqual(plan.unresolved, [])
        # Written 22, 20 - ordered by the link, start piece first.
        self.assertEqual(_groups(plan), {(20, 21): "merge", (20, 22): "merge"})

    def test_a_half_decided_group_is_reported_not_guessed(self):
        plan = chains.plan(FORK, chains.Decisions(merge=((20, 21),)))
        self.assertEqual(plan.unresolved, [(20, 21, 22)])
        self.assertIn((22,), _groups(plan))

    def test_a_gap_beyond_gap_m_is_a_near_miss_until_named(self):
        ends = _ends(t1=((0, 0), (0, 1000)), t2=((0, 1057), (0, 2000)))
        plan = chains.plan(ends)
        self.assertEqual([(l.head, l.tail) for l in plan.near_misses], [(1, 2)])
        plan = chains.plan(ends, chains.Decisions(merge=((2, 1),)))
        self.assertEqual(_groups(plan), {(1, 2): "merge"})
        self.assertEqual(plan.near_misses, [])

    def test_a_near_miss_named_not_a_split_is_not_reported(self):
        ends = _ends(t1=((0, 0), (0, 1000)), t2=((0, 1057), (0, 2000)))
        plan = chains.plan(ends, chains.Decisions(not_splits=frozenset({frozenset({1, 2})})))
        self.assertEqual(plan.near_misses, [])
        self.assertEqual(_groups(plan), {(1,): "single", (2,): "single"})

    def test_merges_json_round_trip_and_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "merges.json"
            path.write_text(json.dumps({"gap_m": 5, "merge": [[1, 2]],
                                        "keep_apart": [[3, 4], 5]}), encoding="utf-8")
            decisions = chains.load_decisions(path)
            self.assertEqual(decisions.keep_apart, {3, 4, 5})
            self.assertEqual(decisions.gap_m, 5)
            path.write_text(json.dumps({"merge": [[1, 2]], "keep_apart": [2]}),
                            encoding="utf-8")
            with self.assertRaises(SystemExit):
                chains.load_decisions(path)
        self.assertEqual(chains.load_decisions(Path(tmp) / "absent.json"),
                         chains.Decisions())


class Rasters(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _tif(self, name, left, top, values):
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(config.CRS_EPSG)
        path = self.dir / name
        build.write_tif(path, np.asarray(values, np.float32),
                        (left, 10.0, 0.0, top, 0.0, -10.0), srs.ExportToWkt(), {}, "t")
        return path

    def test_pieces_merge_by_max_on_one_grid_cropped_to_data(self):
        # A 3x3 window with data in its middle column; B to its north-east,
        # overlapping A's top-right cell.
        a = self._tif("a.tif", 5.0, 35.0, [[ND, 0.2, ND], [ND, 0.5, ND], [ND, 1.0, ND]])
        b = self._tif("b.tif", 15.0, 45.0, [[0.9, 0.3], [ND, 0.7]])
        values, transform, _ = build.merge_rasters([a, b])
        self.assertEqual(transform[0], 15.0)    # A's empty first column cropped
        self.assertEqual(transform[3], 45.0)
        np.testing.assert_array_equal(values, np.array(
            [[0.9, 0.3], [0.2, 0.7], [0.5, ND], [1.0, ND]], np.float32))

    def test_footprint_is_exactly_the_cells_with_data(self):
        a = self._tif("a.tif", 5.0, 35.0, [[0.1, ND, ND], [0.1, 0.1, ND], [ND, ND, 0.1]])
        values, transform, projection = build.merge_rasters([a])
        shape = build.footprint(values, transform, projection)
        self.assertAlmostEqual(shape.GetArea(), 4 * 100.0)


if __name__ == "__main__":
    unittest.main()
