r"""Road routing, on small hand-made networks.

Run from the project directory - skimap/, the one holding skimap/ and tests/:

    & "C:\Program Files\QGIS 4.2.0\bin\python-qgis.bat" -m unittest discover -s tests -t . -v

Each network is a few roads given as point lists in grid metres, joined
where their ends meet, exactly as build() joins NVDB's. Nothing is read
from disk.
"""

from __future__ import annotations

import unittest

import numpy as np

from skimap import road_network as rn

# Somewhere in Romsdalen, so the numbers look like grid coordinates.
X0, Y0 = 136_000.0, 6_964_000.0


def road(*points, category="K", flags=0, oneway=0):
    return {"points": [(X0 + x, Y0 + y) for x, y in points],
            "category": category, "flags": flags, "oneway": oneway}


def network(*roads) -> rn.RoadNetwork:
    """The arrays build() would write for these roads, loaded."""
    ends: dict[tuple, int] = {}

    def node(p):
        return ends.setdefault((round(p[0], 3), round(p[1], 3)), len(ends))

    coords = np.vstack([np.array(r["points"]) for r in roads])
    origin = np.floor(coords.min(axis=0))
    counts = [len(r["points"]) for r in roads]
    arrays = {
        "origin": origin,
        "edge_u": np.array([node(r["points"][0]) for r in roads], dtype=np.int32),
        "edge_v": np.array([node(r["points"][-1]) for r in roads], dtype=np.int32),
        "edge_length": np.array([float(np.hypot(*np.diff(np.array(r["points"]), axis=0).T).sum())
                                 for r in roads]),
        "edge_category": np.array([rn.CATEGORIES.index(r["category"]) + 1 for r in roads],
                                  dtype=np.uint8),
        "edge_flags": np.array([r["flags"] for r in roads], dtype=np.uint8),
        "edge_oneway": np.array([r["oneway"] for r in roads], dtype=np.int8),
        "edge_offsets": np.concatenate([[0], np.cumsum(counts)]).astype(np.int64),
        "coords": (coords - origin).astype(np.float32),
    }
    return rn.RoadNetwork(arrays)


def at(x, y):
    return (X0 + x, Y0 + y)


class WhichWay(unittest.TestCase):

    def test_a_fast_road_beats_a_shorter_slow_one(self):
        # 1 km of forest road straight across, or 1.4 km of E-road round.
        net = network(
            road((0, 0), (1000, 0), category="S"),
            road((0, 0), (500, 500), category="E"),
            road((500, 500), (1000, 0), category="E"),
        )
        drive = net.route(at(0, 0), at(1000, 0))
        self.assertGreater(drive.xy[:, 1].max() - Y0, 400)
        self.assertAlmostEqual(drive.length_m, 2 * np.hypot(500, 500), delta=1)

    def test_a_one_way_road_is_not_driven_against_its_direction(self):
        # The short way is one-way the other way, so it goes round.
        net = network(
            road((1000, 0), (0, 0), oneway=1),
            road((0, 0), (500, 800)),
            road((500, 800), (1000, 0)),
        )
        drive = net.route(at(0, 0), at(1000, 0))
        self.assertGreater(drive.length_m, 1500)
        # And with it, the short way is fine.
        back = net.route(at(1000, 0), at(0, 0))
        self.assertAlmostEqual(back.length_m, 1000, delta=1)

    def test_minus_one_is_one_way_against_the_line(self):
        net = network(road((0, 0), (1000, 0), oneway=-1),
                      road((0, 0), (500, 800)), road((500, 800), (1000, 0)))
        self.assertAlmostEqual(net.route(at(1000, 0), at(0, 0)).length_m, 1000, delta=1)
        self.assertGreater(net.route(at(0, 0), at(1000, 0)).length_m, 1500)

    def test_the_line_runs_from_start_to_end(self):
        net = network(road((0, 0), (1000, 0)), road((1000, 0), (1000, 1000)))
        drive = net.route(at(1000, 1000), at(0, 0))
        np.testing.assert_allclose(drive.xy[0], at(1000, 1000), atol=0.2)
        np.testing.assert_allclose(drive.xy[-1], at(0, 0), atol=0.2)


class Snapping(unittest.TestCase):

    def test_ends_beside_a_road_join_it_part_way_along(self):
        # A 10 km road, driven between two points 50 m off it - only the
        # 2 km between them, not out to either junction.
        net = network(road((0, 0), (10_000, 0)))
        drive = net.route(at(4000, 50), at(6000, -50))
        self.assertAlmostEqual(drive.length_m, 2000, delta=1)
        self.assertAlmostEqual(drive.start_snap_m, 50, delta=0.5)
        np.testing.assert_allclose(drive.xy[0], at(4000, 0), atol=0.2)

    def test_both_ends_on_one_edge_follow_it_directly(self):
        net = network(road((0, 0), (1000, 0), (1000, 1000)))
        drive = net.route(at(1000, 900), at(500, 0))
        self.assertAlmostEqual(drive.length_m, 900 + 500, delta=1)

    def test_a_point_far_from_any_road_is_refused(self):
        net = network(road((0, 0), (1000, 0)))
        with self.assertRaisesRegex(ValueError, "No road within"):
            net.route(at(0, 5000), at(1000, 0))

    def test_snapped_is_where_the_drive_starts(self):
        # So a terrain leg routed to it meets the drive exactly.
        net = network(road((0, 0), (1000, 0), (1000, 1000)))
        point = net.snapped(at(1080, 500))
        np.testing.assert_allclose(point, at(1000, 500), atol=0.01)
        np.testing.assert_allclose(net.route(point, at(0, 0)).xy[0], point, atol=0.01)

    def test_two_unconnected_roads_are_refused(self):
        net = network(road((0, 0), (1000, 0)), road((0, 1000), (1000, 1000)))
        with self.assertRaisesRegex(ValueError, "No road connects"):
            net.route(at(0, 0), at(1000, 1000))


class Stretches(unittest.TestCase):

    def test_tunnels_and_ferries_are_placed_along_the_line(self):
        net = network(
            road((0, 0), (1000, 0)),
            road((1000, 0), (1500, 0), flags=rn.TUNNEL),
            road((1500, 0), (2000, 0), flags=rn.TUNNEL),
            road((2000, 0), (3000, 0)),
            road((3000, 0), (4000, 0), category="F", flags=rn.FERRY),
        )
        drive = net.route(at(0, 0), at(4000, 0))
        # Two tunnel edges end to end are one tunnel.
        self.assertEqual(drive.tunnels, [(1000.0, 2000.0)])
        self.assertEqual(drive.ferries, [(3000.0, 4000.0)])

    def test_a_ferry_has_a_wait_so_the_road_round_can_win(self):
        # 2 km of ferry against 3 km of road: the wait decides it.
        net = network(
            road((0, 0), (2000, 0), flags=rn.FERRY),
            road((0, 0), (1000, 1000), category="E"),
            road((1000, 1000), (2000, 0), category="E"),
        )
        self.assertEqual(net.route(at(0, 0), at(2000, 0)).ferries, [])


class LaneDirections(unittest.TestCase):

    def test_odd_lanes_run_with_the_road_and_even_against(self):
        self.assertEqual(rn._oneway("1#2"), 0)
        self.assertEqual(rn._oneway("1"), 1)
        self.assertEqual(rn._oneway("1#3"), 1)
        self.assertEqual(rn._oneway("2"), -1)
        self.assertEqual(rn._oneway("1K#2K"), 0)
        self.assertEqual(rn._oneway(None), 0)

    def test_a_turning_lane_counts_by_its_own_number_only(self):
        # '2H1' is lane 2 with a turning lane on its right, not lanes 2 and 1.
        self.assertEqual(rn._oneway("1#1H1"), 1)


if __name__ == "__main__":
    unittest.main()
