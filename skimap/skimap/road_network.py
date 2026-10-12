"""Driving routes along the road network, for road-department users.

A graph, not a cost surface. A car stays on the road, so the question is
which roads, and the road network already answers it as a network: NVDB's
lines meet end to end at junctions, and a bridge or a tunnel only joins the
roads it actually connects to. Burnt into 10 m cells the same roads would
merge where two run side by side, join an overpass to the road under it, lose
their one-way direction, and need an r.cost window the size of the whole
drive - 150 km is a couple of hundred million cells per spread.

So nothing here touches GRASS or the cost surface, and a road route has no
corridor: there is one way to keep the car on the road between two points,
not a band of ground nearly as good.

Two halves:

    build()             once, from the roads vector: junctions, edges and
                        their geometry, written to paths.ROAD_NETWORK as
                        plain .npy arrays
    RoadNetwork.load()  at server start: reads those back and turns them
                        into a directed graph, priced from config.ROAD_NETWORK
    .route(a, b)        snaps both ends onto the nearest road, one Dijkstra,
                        and the edges stitched into one line

Pricing happens at load rather than build so that a speed in config can be
changed without rebuilding anything.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

from skimap import config, paths

# Edge flags: what the vehicle is on, where it is not the ground the terrain
# rasters describe.
TUNNEL, BRIDGE, FERRY = 1, 2, 4

# VEGKATEGOR -> code; 0 is anything else. Kept as codes so the speeds stay
# in config and out of the built arrays.
CATEGORIES = ("E", "R", "F", "K", "P", "S")

ARRAYS = (
    "origin",          # (2,) float64, what `coords` are measured from
    "edge_u",          # (E,) int32, the junction at the line's first point
    "edge_v",          # (E,) int32, and at its last
    "edge_length",     # (E,) float64, metres
    "edge_category",   # (E,) uint8, index into CATEGORIES plus one
    "edge_flags",      # (E,) uint8, TUNNEL | BRIDGE | FERRY
    "edge_oneway",     # (E,) int8, +1 along the line only, -1 against, 0 both
    "edge_offsets",    # (E + 1,) int64, edge i's points are coords[o[i]:o[i+1]]
    "coords",          # (V, 2) float32, every edge's points, u end first
)

# The points are float32 from the network's south-west corner rather than
# float64 grid coordinates: 33 million of them are half a gigabyte in
# float64, in a container whose GRASS spreads already want most of its 4 GB.
# 1.5e6 m across Norway in float32 is still an eighth of a metre.


# --- build ----------------------------------------------------------------


def _oneway(lanes: Optional[str]) -> int:
    """+1 for one-way along the line, -1 against it, 0 for both ways.

    VKJORFLT lists a road's lanes - '1#2', '1#3', '1K#2K', '1#2#2H1'. NVDB
    numbers them odd in the road's own direction and even against it, so a
    road whose lanes are all odd only runs one way, and all even the other.
    Only each lane's leading number counts: the rest of '2H1' says which
    side a turning lane is on, not which way it runs.
    """
    if not lanes:
        return 0
    numbers = [int(m.group()) for token in lanes.split("#")
               if (m := re.match(r"\d+", token.strip()))]
    if not numbers:
        return 0
    odd = {n % 2 for n in numbers}
    if odd == {1}:
        return 1
    if odd == {0}:
        return -1
    return 0


def build(source: Optional[Path] = None, out_dir: Optional[Path] = None) -> Path:
    """Read the roads vector into the arrays RoadNetwork loads.

    A junction is wherever line ends meet, to config.ROAD_NETWORK's
    node_tolerance_m. That is all the topology there is to have: NVDB lines
    are split at every junction, and grade-separated crossings - a bridge
    over a road, a tunnel under one - do not share an end, so they do not
    join here either.
    """
    import pyogrio
    import shapely

    settings = config.ROAD_NETWORK
    source = source or paths.source("roads")
    out_dir = out_dir or paths.ROAD_NETWORK
    started = time.time()

    frame = pyogrio.read_dataframe(
        source, layer="roads",
        columns=["OBJTYPE", "VEGKATEGOR", "MEDIUM", "VKJORFLT"],
        where=settings["filter"],
    )
    # One edge per part. The national file has no multipart lines, but a
    # part of one would otherwise be joined to the next by a straight jump.
    frame = frame.explode(ignore_index=True)
    lines = frame.geometry.values
    print(f"Read {len(frame):,} road lines from {source.name} "
          f"in {time.time() - started:.0f}s")

    coords, owner = shapely.get_coordinates(lines, return_index=True)
    counts = np.bincount(owner, minlength=len(lines))
    usable = counts >= 2
    if not usable.all():
        print(f"  dropped {int((~usable).sum())} line(s) with fewer than two points")
        coords = coords[usable[owner]]
        counts = counts[usable]
        frame = frame[usable].reset_index(drop=True)
        lines = frame.geometry.values
    offsets = np.concatenate([[0], np.cumsum(counts)]).astype(np.int64)

    first = coords[offsets[:-1]]
    last = coords[offsets[1:] - 1]
    ends = np.vstack([first, last])
    keys = np.round(ends / float(settings["node_tolerance_m"])).astype(np.int64)
    _, node = np.unique(keys, axis=0, return_inverse=True)
    node = node.ravel().astype(np.int32)
    nodes = int(node.max()) + 1
    origin = np.floor(coords.min(axis=0))

    category = np.zeros(len(frame), dtype=np.uint8)
    for code, name in enumerate(CATEGORIES, start=1):
        category[(frame["VEGKATEGOR"] == name).to_numpy()] = code

    flags = np.zeros(len(frame), dtype=np.uint8)
    flags[(frame["MEDIUM"] == "U").to_numpy()] |= TUNNEL
    flags[(frame["MEDIUM"] == "L").to_numpy()] |= BRIDGE
    flags[(frame["OBJTYPE"] == "Bilferjestrekning").to_numpy()] |= FERRY

    # Few distinct lane strings among millions of rows, so parse each once.
    lane_codes = {lanes: _oneway(lanes) for lanes in frame["VKJORFLT"].dropna().unique()}
    oneway = frame["VKJORFLT"].map(lane_codes).fillna(0).to_numpy(dtype=np.int8)
    # A ferry runs both ways whatever its lane field says.
    oneway[(flags & FERRY) != 0] = 0

    arrays = {
        "origin": origin,
        "edge_u": node[:len(frame)],
        "edge_v": node[len(frame):],
        "edge_length": shapely.length(lines).astype(np.float64),
        "edge_category": category,
        "edge_flags": flags,
        "edge_oneway": oneway,
        "edge_offsets": offsets,
        "coords": (coords - origin).astype(np.float32),
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    for name in ARRAYS:
        np.save(out_dir / f"{name}.npy", arrays[name])
    meta = {
        "source": str(source),
        "source_mtime": source.stat().st_mtime,
        "filter": settings["filter"],
        "node_tolerance_m": settings["node_tolerance_m"],
        "nodes": nodes,
        "edges": len(frame),
        "points": len(coords),
        "built": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    size = sum((out_dir / f"{name}.npy").stat().st_size for name in ARRAYS)
    print(f"  {nodes:,} junctions, {len(frame):,} edges, {len(coords):,} points "
          f"-> {out_dir} ({size / 1e6:.0f} MB) in {time.time() - started:.0f}s")
    return out_dir


# --- routing --------------------------------------------------------------


@dataclass(frozen=True)
class Snap:
    """Where a point lands on the network: an edge, and how far along it
    from its u end."""

    edge: int
    along_m: float
    distance_m: float


@dataclass(frozen=True)
class RoadRoute:
    """One drive. `xy` runs start to end on the 25833 grid; the stretches
    are (start_m, end_m) along it, measured on that grid as crux does."""

    xy: np.ndarray
    length_m: float
    drive_s: float
    tunnels: list[tuple[float, float]]
    ferries: list[tuple[float, float]]
    start_snap_m: float
    end_snap_m: float


class RoadNetwork:
    """The road graph, priced and ready to route on.

    Arcs are directed: a road both ways is two, a one-way road one. Between
    any two junctions only the cheapest arc is kept, both because that is
    the only one a shortest path could use and because the sparse matrix
    Dijkstra runs on would otherwise sum parallel roads into one.
    """

    def __init__(self, arrays: dict[str, np.ndarray]):
        self.origin = np.asarray(arrays["origin"], dtype=np.float64)
        self.edge_u = arrays["edge_u"]
        self.edge_v = arrays["edge_v"]
        self.edge_length = arrays["edge_length"]
        self.edge_flags = arrays["edge_flags"]
        self.edge_oneway = arrays["edge_oneway"]
        self.offsets = arrays["edge_offsets"]
        self.coords = arrays["coords"]

        self.node_count = int(max(self.edge_u.max(), self.edge_v.max())) + 1

        settings = config.ROAD_NETWORK
        if not settings.get("oneway", True):
            self.edge_oneway = np.zeros_like(self.edge_oneway)
        self.edge_cost = _edge_cost(arrays["edge_category"], self.edge_length,
                                    self.edge_flags, settings)
        self._arcs()

        # Each edge's bounding box, for finding the roads near a point
        # without an index structure: one vectorised comparison over every
        # edge is a few milliseconds, and costs nothing to build.
        starts = self.offsets[:-1]
        self.min_x = np.minimum.reduceat(self.coords[:, 0], starts)
        self.max_x = np.maximum.reduceat(self.coords[:, 0], starts)
        self.min_y = np.minimum.reduceat(self.coords[:, 1], starts)
        self.max_y = np.maximum.reduceat(self.coords[:, 1], starts)

    @classmethod
    def load(cls, directory: Optional[Path] = None) -> "RoadNetwork":
        directory = directory or paths.ROAD_NETWORK
        missing = [n for n in ARRAYS if not (directory / f"{n}.npy").is_file()]
        if missing:
            raise FileNotFoundError(
                f"No road network in {directory}. Build it with "
                "'python -m skimap.cli roads'.")
        return cls({name: np.load(directory / f"{name}.npy") for name in ARRAYS})

    def _arcs(self) -> None:
        """The directed arcs, sorted by tail, as the rows of a CSR matrix.

        Sorted once here so a route only has to append the start's own row
        at the end; the arc at each position is then known by position,
        which is how a path's junction pairs are turned back into edges.
        """
        edge = np.arange(len(self.edge_u), dtype=np.int32)
        forward = self.edge_oneway >= 0
        backward = self.edge_oneway <= 0
        tail = np.concatenate([self.edge_u[forward], self.edge_v[backward]])
        head = np.concatenate([self.edge_v[forward], self.edge_u[backward]])
        cost = np.concatenate([self.edge_cost[forward], self.edge_cost[backward]])
        which = np.concatenate([edge[forward], edge[backward]])
        reverse = np.concatenate([np.zeros(int(forward.sum()), dtype=bool),
                                  np.ones(int(backward.sum()), dtype=bool)])

        # A loop back to its own junction is never on a shortest path.
        keep = tail != head
        tail, head, cost, which, reverse = (a[keep] for a in (tail, head, cost, which, reverse))

        order = np.lexsort((cost, head, tail))
        tail, head, cost, which, reverse = (a[order] for a in (tail, head, cost, which, reverse))
        first = np.concatenate([[True], (tail[1:] != tail[:-1]) | (head[1:] != head[:-1])])
        tail, head, cost, which, reverse = (a[first] for a in (tail, head, cost, which, reverse))

        self.arc_head = head.astype(np.int32)
        self.arc_cost = cost
        self.arc_edge = which
        self.arc_reverse = reverse
        self.arc_indptr = np.concatenate(
            [[0], np.cumsum(np.bincount(tail, minlength=self.node_count))]).astype(np.int64)

    # --- snapping ---

    def snap(self, xy: tuple[float, float], what: str = "point") -> Snap:
        """The nearest point on any road, as an edge and a distance along it.

        Searched in widening boxes: a point beside a road finds it in the
        first, and only one far out in the country pays for the wide one.
        A hit inside the box's radius is the true nearest, since any road
        nearer still would have had its bounding box in the same search.
        """
        max_snap = float(config.ROAD_NETWORK["max_snap_m"])
        x, y = float(xy[0]) - self.origin[0], float(xy[1]) - self.origin[1]
        for radius in sorted({min(r, max_snap) for r in (250.0, 1000.0, max_snap)}):
            near = np.flatnonzero((self.min_x <= x + radius) & (self.max_x >= x - radius)
                                  & (self.min_y <= y + radius) & (self.max_y >= y - radius))
            if near.size == 0:
                continue
            found = self._nearest_on(near, np.array([x, y]))
            if found.distance_m <= radius:
                return found
        raise ValueError(f"No road within {max_snap:.0f} m of the {what}.")

    def snapped(self, xy: tuple[float, float], what: str = "point") -> tuple[float, float]:
        """Where `xy` lands on the roads, as a point on the 25833 grid - the
        spot a drive from or to `xy` actually starts or ends at."""
        found = self.snap(xy, what)
        x, y = self._cut(found.edge, found.along_m, found.along_m)[0]
        return float(x), float(y)

    def _nearest_on(self, edges: np.ndarray, point: np.ndarray) -> Snap:
        starts = self.offsets[edges]
        segments = self.offsets[edges + 1] - starts - 1
        total = int(segments.sum())
        within = np.arange(total) - np.repeat(np.cumsum(segments) - segments, segments)
        a_index = np.repeat(starts, segments) + within
        a = self.coords[a_index].astype(np.float64)
        step = self.coords[a_index + 1].astype(np.float64) - a
        squared = (step ** 2).sum(axis=1)
        t = np.clip(((point - a) * step).sum(axis=1) / np.where(squared > 0, squared, 1.0), 0.0, 1.0)
        distance = np.hypot(*(a + t[:, None] * step - point).T)

        k = int(np.argmin(distance))
        edge = int(np.repeat(edges, segments)[k])
        points = self.edge_points(edge)
        before = float(np.hypot(*np.diff(points[:within[k] + 1], axis=0).T).sum())
        return Snap(edge, before + float(t[k] * np.sqrt(squared[k])), float(distance[k]))

    def edge_points(self, edge: int) -> np.ndarray:
        """One edge's points on the 25833 grid, u end first."""
        return self.coords[self.offsets[edge]:self.offsets[edge + 1]].astype(np.float64) + self.origin

    # --- routing ---

    def _passable(self, edge: int, forward: bool) -> bool:
        way = int(self.edge_oneway[edge])
        return way >= 0 if forward else way <= 0

    def _part_cost(self, edge: int, metres: float) -> float:
        return float(self.edge_cost[edge] * metres / max(self.edge_length[edge], 1e-9))

    def route(self, start_xy: tuple[float, float], end_xy: tuple[float, float]) -> RoadRoute:
        """The quickest drive from one point to the other, on the roads.

        Each end is snapped onto its nearest road, and the network is entered
        and left part way along that road, so a start in the middle of a
        long rural road does not first drive to a junction it never needed.

        Raises ValueError for an end too far from any road, or two ends with
        no road between them - an island the ferries in NVDB do not reach.
        """
        from scipy.sparse import csr_matrix
        from scipy.sparse.csgraph import dijkstra

        start = self.snap(start_xy, "start point")
        end = self.snap(end_xy, "end point")

        # The start is one extra node, S, at the end of the matrix: its arcs
        # run along its own edge to whichever ends of it can be driven to.
        exits: dict[int, tuple[float, float]] = {}   # junction -> (cost, along_m there)
        edge, along = start.edge, start.along_m
        length = float(self.edge_length[edge])
        for forward, junction, target in ((False, self.edge_u[edge], 0.0),
                                          (True, self.edge_v[edge], length)):
            if self._passable(edge, forward):
                cost = self._part_cost(edge, abs(target - along))
                if int(junction) not in exits or cost < exits[int(junction)][0]:
                    exits[int(junction)] = (cost, target)

        s = self.node_count
        heads = np.array(sorted(exits), dtype=np.int32)
        # Never exactly zero: a start snapped onto a junction would make an
        # explicit zero, which a sparse graph is free to read as no arc.
        costs = np.array([max(exits[int(h)][0], 1e-6) for h in heads])
        graph = csr_matrix(
            (np.concatenate([self.arc_cost, costs]),
             np.concatenate([self.arc_head, heads]),
             np.concatenate([self.arc_indptr, [self.arc_indptr[-1] + len(heads)]])),
            shape=(s + 1, s + 1),
        )
        dist, pred = dijkstra(graph, directed=True, indices=s, return_predecessors=True)

        # The end, entered from whichever end of its edge is cheaper, or -
        # when both ends are on one edge - straight along it.
        edge, along = end.edge, end.along_m
        length = float(self.edge_length[edge])
        best: tuple[float, Optional[int], float] = (np.inf, None, 0.0)   # cost, junction, along there
        for forward, junction, origin in ((True, self.edge_u[edge], 0.0),
                                          (False, self.edge_v[edge], length)):
            if self._passable(edge, forward) and np.isfinite(dist[junction]):
                cost = float(dist[junction]) + self._part_cost(edge, abs(along - origin))
                if cost < best[0]:
                    best = (cost, int(junction), origin)

        direct = np.inf
        if start.edge == end.edge:
            forward = end.along_m >= start.along_m
            if self._passable(edge, forward):
                direct = self._part_cost(edge, abs(end.along_m - start.along_m))

        if not np.isfinite(min(best[0], direct)):
            raise ValueError("No road connects the start and end points - one of them "
                             "may be on an island the road data has no ferry to.")

        if direct <= best[0]:
            pieces = [(self._cut(edge, start.along_m, end.along_m), int(self.edge_flags[edge]))]
            drive_s = direct
        else:
            drive_s, last, entered_at = best
            nodes = [last]
            while pred[nodes[-1]] != s:
                nodes.append(int(pred[nodes[-1]]))
            nodes.reverse()

            first_edge = start.edge
            pieces = [(self._cut(first_edge, start.along_m, exits[nodes[0]][1]),
                       int(self.edge_flags[first_edge]))]
            for tail, head in zip(nodes[:-1], nodes[1:]):
                arc = self._arc(tail, head)
                points = self.edge_points(int(self.arc_edge[arc]))
                pieces.append((points[::-1] if self.arc_reverse[arc] else points,
                               int(self.edge_flags[self.arc_edge[arc]])))
            pieces.append((self._cut(end.edge, entered_at, end.along_m),
                           int(self.edge_flags[end.edge])))

        xy, stretches = _stitch(pieces)
        return RoadRoute(
            xy=xy,
            length_m=float(np.hypot(*np.diff(xy, axis=0).T).sum()),
            drive_s=float(drive_s),
            tunnels=stretches[TUNNEL],
            ferries=stretches[FERRY],
            start_snap_m=start.distance_m,
            end_snap_m=end.distance_m,
        )

    def _arc(self, tail: int, head: int) -> int:
        lo, hi = self.arc_indptr[tail], self.arc_indptr[tail + 1]
        return int(lo + np.flatnonzero(self.arc_head[lo:hi] == head)[0])

    def _cut(self, edge: int, from_m: float, to_m: float) -> np.ndarray:
        """The stretch of one edge between two distances along it, in the
        order asked for - backwards when `to_m` is nearer its u end."""
        points = self.edge_points(edge)
        along = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(points, axis=0).T))])
        lo, hi = sorted((from_m, to_m))

        def at(d: float) -> np.ndarray:
            return np.array([[np.interp(d, along, points[:, 0]),
                              np.interp(d, along, points[:, 1])]])

        inside = (along > lo) & (along < hi)
        part = np.vstack([at(lo), points[inside], at(hi)])
        return part[::-1] if to_m < from_m else part


def _edge_cost(category: np.ndarray, length: np.ndarray, flags: np.ndarray,
               settings: dict) -> np.ndarray:
    """Seconds to drive each edge, from config's speeds."""
    speed = np.full(len(length), float(settings["default_speed_kmh"]))
    for code, name in enumerate(CATEGORIES, start=1):
        if name in settings["speed_kmh"]:
            speed[category == code] = float(settings["speed_kmh"][name])
    cost = length / (speed / 3.6)
    ferry = (flags & FERRY) != 0
    cost[ferry] = (length[ferry] / (float(settings["ferry_speed_kmh"]) / 3.6)
                   + float(settings["ferry_wait_s"]))
    return np.maximum(cost, 1e-3)


def _stitch(pieces: list[tuple[np.ndarray, int]]) -> tuple[np.ndarray, dict]:
    """The pieces joined into one line, and where along it the tunnels and
    ferries are, adjacent ones run together."""
    xy = np.vstack([p for p, _ in pieces])
    moved = np.concatenate([[True], (np.diff(xy, axis=0) != 0.0).any(axis=1)])
    line = xy[moved]

    stretches: dict[int, list[tuple[float, float]]] = {TUNNEL: [], FERRY: []}
    at = 0.0
    for points, flags in pieces:
        length = float(np.hypot(*np.diff(points, axis=0).T).sum()) if len(points) > 1 else 0.0
        for flag, found in stretches.items():
            if flags & flag and length > 0:
                if found and abs(found[-1][1] - at) < 1e-6:
                    found[-1] = (found[-1][0], at + length)
                else:
                    found.append((at, at + length))
        at += length
    rounded = {flag: [(round(a, 1), round(b, 1)) for a, b in found]
               for flag, found in stretches.items()}
    return line, rounded
