from __future__ import annotations
import math
import numpy as np
from typing import Dict, List, Tuple
from shapely.geometry import LineString, Point


def discrete_frechet(P, Q) -> float:
    n, m = len(P), len(Q)
    if n == 0 or m == 0:
        return float("nan")

    import math
    import numpy as np

    ca = np.empty((n, m), dtype=np.float64)

    def dist(i, j):
        dx = P[i][0] - Q[j][0]
        dy = P[i][1] - Q[j][1]
        return math.hypot(dx, dy)

    # initialize borders
    ca[0, 0] = dist(0, 0)
    for j in range(1, m):
        ca[0, j] = max(ca[0, j-1], dist(0, j))
    for i in range(1, n):
        ca[i, 0] = max(ca[i-1, 0], dist(i, 0))

    # fill interior
    for i in range(1, n):
        for j in range(1, m):
            ca[i, j] = max(min(ca[i-1, j], ca[i-1, j-1], ca[i, j-1]), dist(i, j))

    return float(ca[n-1, m-1])

def hausdorff_undirected(a: LineString, b: LineString) -> float:
    return max(a.hausdorff_distance(b), b.hausdorff_distance(a))

def overlap_percentage(a: LineString, b: LineString, buffer_m: float) -> Tuple[float, float, float]:
    if buffer_m <= 0: return (0.0, 0.0, 0.0)
    buf_b = b.buffer(buffer_m, cap_style=2, join_style=2)
    buf_a = a.buffer(buffer_m, cap_style=2, join_style=2)
    la = a.length or 1e-9
    lb = b.length or 1e-9
    a_in_b = 100.0 * (a.intersection(buf_b).length / la)
    b_in_a = 100.0 * (b.intersection(buf_a).length / lb)
    return a_in_b, b_in_a, 0.5 * (a_in_b + b_in_a)

def point_line_stats(samples: List[Point], ref: LineString) -> Dict[str, float]:
    d = np.array([ref.distance(p) for p in samples], dtype=float)
    if d.size == 0: return dict(mean=np.nan, median=np.nan, p95=np.nan, max=np.nan)
    return dict(mean=float(np.mean(d)), median=float(np.median(d)),
                p95=float(np.percentile(d, 95)), max=float(np.max(d)))


def match_score(
    overlap_mean_pct: float,
    d_frechet_m: float,
    d_hausdorff_m: float,
    p95_m: float,
    *,
    w_overlap=0.40, w_frechet=0.25, w_hausdorff=0.20, w_p95=0.15,
    norm_scale_m=100.0,
) -> float:
    def inv_norm(d): return max(0.0, 1.0 - min(1.0, d / max(1e-9, norm_scale_m)))
    s = (w_overlap * (overlap_mean_pct / 100.0) +
         w_frechet * inv_norm(d_frechet_m) +
         w_hausdorff * inv_norm(d_hausdorff_m) +
         w_p95 * inv_norm(p95_m))
    return float(100.0 * s)
