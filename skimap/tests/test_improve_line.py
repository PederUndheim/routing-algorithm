r"""Finding the stretches of a drawn line with a clearly cheaper way beside them.

Run from the project directory - skimap/, the one holding skimap/ and tests/:

    & "C:\Program Files\QGIS 4.2.0\bin\python-qgis.bat" -m unittest discover -s tests -t . -v

The band itself needs GRASS and the national surface; these run the search on
made-up grids, where the right answer is known.
"""

from __future__ import annotations

import unittest

import numpy as np

from skimap import config
from skimap.routing import _detours, _line_cells, _needed_saving

RES = 10.0
SIZE = 120          # cells a side: 1.2 km
NORTH = SIZE * RES


def search(points, cost=None, **overrides):
    """_detours on a line through `points` (metres, y up) over `cost`,
    uniform 10 per cell unless given, with the whole grid as the band."""
    cost = np.full((SIZE, SIZE), 10.0) if cost is None else cost
    xy = np.array(points, dtype=np.float64)
    cells, along = _line_cells(xy, 0.0, NORTH, RES)
    on_line = cost[cells[:, 0], cells[:, 1]]
    params = {**config.IMPROVE, **overrides}
    return _detours(cost, np.ones_like(cost, dtype=bool), cells, along, on_line, RES, params)


def row_of(y: float) -> int:
    return int((NORTH - y) // RES)


class LineCells(unittest.TestCase):
    def test_each_cell_is_entered_where_the_line_reaches_it(self):
        cells, along = _line_cells(np.array([[5.0, 1195.0], [205.0, 1195.0]]), 0.0, NORTH, RES)
        np.testing.assert_array_equal(cells[:, 1], np.arange(21))
        # To the metre the line is walked in.
        np.testing.assert_allclose(along, [0.0] + [5.0 + 10 * k for k in range(20)], atol=1.0)


class Detours(unittest.TestCase):
    def test_a_straight_line_on_even_ground_is_left_alone(self):
        self.assertEqual(search([(50, 600), (1150, 600)]), [])

    def test_a_needless_bump_is_cut_off(self):
        found = search([(50, 600), (400, 600), (500, 500), (600, 600), (1150, 600)])
        self.assertEqual(len(found), 1)
        detour = found[0]
        self.assertLess(detour["cost"], detour["line_cost"])
        # The new way runs along the straight, nowhere near the bump's tip.
        self.assertLessEqual(np.abs(detour["path"][:, 0] - row_of(600)).max(), 1)

    def test_the_way_round_a_steep_block_beats_crossing_it(self):
        cost = np.full((SIZE, SIZE), 10.0)
        cost[row_of(700):row_of(500), 50:70] = 100.0   # 200 m by 200 m, x 500-700
        found = search([(50, 600), (1150, 600)], cost=cost)
        self.assertEqual(len(found), 1)
        path = found[0]["path"]
        self.assertTrue((cost[path[:, 0], path[:, 1]] < 100.0).all())

    def test_a_summit_spur_is_not_cut_off(self):
        # Out to a top 400 m north and back down beside the way up: the
        # cheapest line skips it, and that is never what was meant. Cutting
        # the corners on the way there and back is fair; spanning the top is
        # not.
        points = [(50, 300), (500, 300), (500, 700), (520, 700), (520, 300), (1150, 300)]
        cells, along = _line_cells(np.array(points, float), 0.0, NORTH, RES)
        top = 450 + 400 + 10
        for detour in search(points):
            self.assertFalse(along[detour["first"]] < top < along[detour["last"]])

    def test_a_deep_narrow_bump_reads_as_a_spur(self):
        # 250 m out and back across a 200 m mouth: the same shape as a
        # summit, so it is kept, and only its sides are straightened.
        points = [(50, 600), (400, 600), (500, 350), (600, 600), (1150, 600)]
        cells, along = _line_cells(np.array(points, float), 0.0, NORTH, RES)
        tip = 350 + float(np.hypot(100, 250))
        for detour in search(points):
            self.assertFalse(along[detour["first"]] < tip < along[detour["last"]])

    def test_tight_switchbacks_are_not_straightened(self):
        # Up the slope in 20 m zigzags. Going straight up is cheaper on a
        # surface with no up or down, and stays inside the zigzag.
        points = [(600 + (20 if k % 2 else 0), 100 + 20 * k) for k in range(50)]
        self.assertEqual(search(points), [])

    def test_a_saving_below_the_minimum_is_not_suggested(self):
        bump = [(50, 600), (400, 600), (500, 500), (600, 600), (1150, 600)]
        self.assertEqual(search(bump, min_saving=1e6, min_suggestions=0), [])

    def test_a_good_line_still_gets_its_biggest_small_fixes(self):
        # Three bumps, none saving what a full suggestion must: the two
        # biggest are suggested as minor ones, in order along the line.
        line = [(50, 600)]
        for x, height in ((250, 30), (550, 60), (850, 45)):
            line += [(x - 50, 600), (x, 600 - height), (x + 50, 600)]
        line.append((1150, 600))
        cells, along = _line_cells(np.array(line, float), 0.0, NORTH, RES)
        found = search(line, min_saving=1e6, min_suggestions=2)
        self.assertEqual(len(found), 2)
        self.assertTrue(all(d["minor"] for d in found))
        # Neither is the smallest bump's, which is over by 270 m along.
        self.assertTrue(all(along[d["last"]] > 270 for d in found))
        self.assertLessEqual(found[0]["last"], found[1]["first"])

    def test_minor_suggestions_only_fill_up(self):
        # A line with a full suggestion and min_suggestions 1 gets nothing more.
        found = search([(50, 600), (400, 600), (500, 500), (600, 600), (1150, 600)],
                       min_suggestions=1)
        self.assertEqual([d["minor"] for d in found], [False])

    def test_a_way_never_doubles_back_onto_the_line(self):
        # A cheap track 40 m north of a dear line, walled off from it but for
        # one way down 40 m past the line's end. The cheapest way to the end
        # comes down there and runs back along the line - a hook, not a way
        # anyone would walk.
        def col_of(x: float) -> int:
            return int(x // RES)

        cost = np.full((SIZE, SIZE), 20.0)
        cost[row_of(640), col_of(100):col_of(850)] = 2.0
        cost[row_of(630):row_of(610) + 1, col_of(300):col_of(850)] = 200.0
        cost[row_of(630):row_of(600), col_of(840)] = 2.0
        line = [(50, 600), (800, 600)]
        self.assertEqual(len(search(line, cost=cost, max_join_deg=180.0, min_suggestions=0)), 1)
        self.assertEqual(search(line, cost=cost, min_suggestions=0), [])

    def test_a_way_never_runs_beside_another_part_of_the_line(self):
        # Out east on dear ground and back west 150 m north along a cheap
        # track: following the way back is the cheapest way out, and it is
        # the same tour's other half, not an improvement to this one.
        cost = np.full((SIZE, SIZE), 50.0)
        cost[row_of(450), :] = 5.0
        found = search([(50, 300), (1050, 300), (1050, 450), (50, 450)], cost=cost)
        for detour in found:
            # Cutting the corner onto the short end of the U is fair, and
            # margin_m lets a way round it touch the first of the track back;
            # following that track on west is not.
            path = detour["path"]
            on_the_track_back = (path[:, 0] <= row_of(450) + 1) & (path[:, 1] < 95)
            self.assertFalse(on_the_track_back.any())

    def test_a_long_way_round_is_another_route_not_an_improvement(self):
        # A dear block 400 m wide across the line and all but the whole grid
        # tall: going round it is far cheaper than crossing, and 1.6 times
        # as long as the whole line.
        cost = np.full((SIZE, SIZE), 10.0)
        cost[2:118, 40:80] = 100.0
        line = [(50, 600), (1150, 600)]
        self.assertEqual(search(line, cost=cost), [])
        # It leaves the line square on, to go round, so the join rule is off.
        self.assertEqual(len(search(line, cost=cost, max_lengthening=10.0, max_join_deg=180.0)), 1)

    def test_a_small_bump_is_worth_a_suggestion(self):
        # 60 m out over 100 m of line: 56 m of extra walking, small but real.
        found = search([(50, 600), (500, 600), (550, 540), (600, 600), (1150, 600)])
        self.assertEqual(len(found), 1)

    def test_one_way_round_two_blocks_is_two_suggestions(self):
        # Two dear blocks on the line 200 m apart. The cheapest single way
        # stays off the line between them, but two short ways round each
        # save nearly as much, and each is the user's to take or leave.
        cost = np.full((SIZE, SIZE), 10.0)
        cost[row_of(640):row_of(560), 30:40] = 100.0
        cost[row_of(640):row_of(560), 60:70] = 100.0
        found = search([(50, 600), (1150, 600)], cost=cost)
        self.assertEqual(len(found), 2)

    def test_a_long_stretch_must_save_more(self):
        short = _needed_saving(1000.0, 100.0, config.IMPROVE)
        long_ = _needed_saving(1000.0, 2000.0, config.IMPROVE)
        self.assertAlmostEqual(short, 110.0)
        self.assertAlmostEqual(long_, 300.0)
        # And never under min_saving, however cheap the stretch.
        self.assertEqual(_needed_saving(10.0, 50.0, config.IMPROVE),
                         config.IMPROVE["min_saving"])

    def test_two_bumps_are_two_suggestions_in_order(self):
        # Even where one way round both would be as cheap, they are two
        # fixes with the line between them, to be taken one at a time.
        found = search([(50, 600), (200, 600), (300, 500), (400, 600),
                        (700, 600), (800, 500), (900, 600), (1150, 600)])
        self.assertEqual(len(found), 2)
        self.assertLessEqual(found[0]["last"], found[1]["first"])


if __name__ == "__main__":
    unittest.main()
