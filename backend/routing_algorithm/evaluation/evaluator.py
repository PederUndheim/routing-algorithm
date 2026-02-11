# src/evaluation/evaluator.py
from __future__ import annotations
import os, json
import geopandas as gpd
from typing import Any, Dict, Optional
from shapely.geometry import LineString

from .pairing import list_auto_files, list_expert_files
from .geometry import ensure_single_line, densify, sample_points
from .metrics import (discrete_frechet, hausdorff_undirected, overlap_percentage, point_line_stats, match_score)
from .plotting import plot_pair  

EXPERT_DIR = "data/geojson/evaluation_paths"
AUTO_DIR   = "output/path_geojson/wgs84"

# Distances in meters
BUFFER_M      = 30.0
SAMPLE_M      = 10.0
NORM_SCALE_M  = 100.0

# Metric CRS for distance calculations (pick correct UTM zone!)
FORCE_CRS: Optional[str] = "EPSG:25833"

# Outputs
OUT_CSV  = "output/eval/route_eval.csv"
PLOT_DIR = "output/eval/plots"

# Guard for Fréchet DP size (n*m cells). Auto-coarsen if exceeded.
MAX_FRECHET_CELLS = 5_000_000


def _assert_4326_and_project(path: str, project_to: Optional[str]) -> LineString:
    """
    Load a GeoJSON that MUST be EPSG:4326; raise if not.
    Then project to 'project_to' (metric CRS) for distance work.
    """
    gdf = gpd.read_file(path)
    if gdf.crs is None:
        raise ValueError(f"{path}: CRS missing. Expected EPSG:4326.")
    epsg = gdf.crs.to_epsg()
    if epsg != 4326:
        raise ValueError(f"{path}: CRS is EPSG:{epsg}, expected EPSG:4326.")
    if project_to:
        gdf = gdf.to_crs(project_to)
    return ensure_single_line(gdf)

def _auto_coarsen(auto_line: LineString, expert_line: LineString, step_m: float) -> tuple[LineString, LineString, float]:
    """Increase sampling step if Fréchet DP table would be too large."""
    a_d = densify(auto_line, step_m)
    e_d = densify(expert_line, step_m)
    len_a = len(list(a_d.coords))
    len_e = len(list(e_d.coords))
    cells = len_a * len_e
    if cells <= MAX_FRECHET_CELLS:
        return a_d, e_d, step_m
    import math
    factor = math.sqrt(cells / MAX_FRECHET_CELLS)
    new_step = max(step_m * factor, step_m)
    a_d = densify(auto_line, new_step)
    e_d = densify(expert_line, new_step)
    return a_d, e_d, new_step

def _save_csv_row(path: str, data: Dict[str, Any], header_written: bool):
    import csv
    fields = [
        "mountain","auto","expert",
        "length_auto","length_expert",
        "buffer_m","sample_m",
        "overlap_auto_in_expert_pct","overlap_expert_in_auto_pct","overlap_mean_pct",
        "frechet_m","hausdorff_m",
        "pt2line_mean_m","pt2line_median_m","pt2line_p95_m","pt2line_max_m",
        "match_score"
    ]
    mode = "a" if header_written else "w"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, mode, newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if not header_written:
            w.writeheader()
        w.writerow({k: data.get(k, "") for k in fields})


def evaluate_one(auto_path: str, expert_path: str) -> Dict[str, Any]:
    # Load inputs (must be 4326), project to metric CRS
    line_auto   = _assert_4326_and_project(auto_path, FORCE_CRS)
    line_expert = _assert_4326_and_project(expert_path, FORCE_CRS)

    # Densify + auto-coarsen if needed
    auto_d, expt_d, used_step = _auto_coarsen(line_auto, line_expert, SAMPLE_M)

    # Metrics
    a_in_b, b_in_a, mean_ov = overlap_percentage(auto_d, expt_d, BUFFER_M)
    dF = discrete_frechet(list(auto_d.coords), list(expt_d.coords))
    dH = hausdorff_undirected(auto_d, expt_d)
    stats = point_line_stats(sample_points(auto_d, used_step), expt_d)
    score = match_score(mean_ov, dF, dH, stats["p95"], norm_scale_m=NORM_SCALE_M)

    return dict(
        length_auto=float(line_auto.length),
        length_expert=float(line_expert.length),
        buffer_m=float(BUFFER_M),
        sample_m=float(used_step),
        overlap_auto_in_expert_pct=float(a_in_b),
        overlap_expert_in_auto_pct=float(b_in_a),
        overlap_mean_pct=float(mean_ov),
        frechet_m=float(dF),
        hausdorff_m=float(dH),
        pt2line_mean_m=float(stats["mean"]),
        pt2line_median_m=float(stats["median"]),
        pt2line_p95_m=float(stats["p95"]),
        pt2line_max_m=float(stats["max"]),
        match_score=float(score),
    )


def main():
    # Ensure output dirs exist
    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    os.makedirs(PLOT_DIR, exist_ok=True)

    # Remove existing CSV
    if os.path.exists(OUT_CSV):
        os.remove(OUT_CSV)
    header_written = False

    autos   = list_auto_files(AUTO_DIR)     # {key: auto_path}
    experts = list_expert_files(EXPERT_DIR) # {key: expert_path}

    if not autos:
        print(f"[WARN] No auto files in: {AUTO_DIR}")
    if not experts:
        print(f"[WARN] No expert files in: {EXPERT_DIR}")

    header_written = os.path.exists(OUT_CSV) and os.path.getsize(OUT_CSV) > 0
    n_rows = 0

    # Pair strictly 1:1 by mountain key
    for key, expert_path in experts.items():
        auto_path = autos.get(key)
        if not auto_path:
            print(f"[SKIP] No auto route for '{key}'.")
            continue

        metrics = evaluate_one(auto_path, expert_path)

        row = dict(
            mountain=key,
            auto=os.path.basename(auto_path),
            expert=os.path.basename(expert_path),
            **metrics,
        )
        _save_csv_row(OUT_CSV, row, header_written)
        header_written = True
        n_rows += 1

        plot_path = os.path.join(PLOT_DIR, f"{key}.png")
        auto_line_full   = _assert_4326_and_project(auto_path, FORCE_CRS)
        expert_line_full = _assert_4326_and_project(expert_path, FORCE_CRS)
        plot_pair(plot_path, auto_line_full, expert_line_full, sample_m=metrics["sample_m"])

    print(json.dumps({
        "mountains_evaluated": n_rows,
        "csv": OUT_CSV,
        "plot_dir": PLOT_DIR
    }, indent=2))


if __name__ == "__main__":
    main()
