from __future__ import annotations

from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
from shapely.geometry import LineString

from .geometry import sample_points_with_fraction


def write_comparison_geojson(
    out_path: str | Path,
    *,
    reference_line: LineString,
    generated_line: LineString,
    crs: str,
    properties: dict[str, Any] | None = None,
) -> Path:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    base = properties or {}
    gdf = gpd.GeoDataFrame(
        [
            {**base, "role": "reference", "geometry": reference_line},
            {**base, "role": "generated", "geometry": generated_line},
        ],
        crs=crs,
    )
    gdf.to_file(out, driver="GeoJSON")
    return out


def write_deviation_samples_geojson(
    out_path: str | Path,
    *,
    sampled_line: LineString,
    target_line: LineString,
    crs: str,
    sample_step_m: float,
    role: str,
    properties: dict[str, Any] | None = None,
) -> Path:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    base = properties or {}
    rows = []
    for point, fraction in sample_points_with_fraction(sampled_line, sample_step_m):
        rows.append(
            {
                **base,
                "role": role,
                "route_fraction": fraction,
                "distance_to_other_m": float(target_line.distance(point)),
                "geometry": point,
            }
        )
    gdf = gpd.GeoDataFrame(rows, crs=crs)
    gdf.to_file(out, driver="GeoJSON")
    return out


def plot_route_comparison(
    out_path: str | Path,
    *,
    reference_line: LineString,
    generated_line: LineString,
    sample_step_m: float,
    title: str,
    buffer_m: float = 50.0,
) -> Path | None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return None

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    generated_samples = sample_points_with_fraction(generated_line, sample_step_m)
    sample_points = [point for point, _ in generated_samples]
    distances = np.array([reference_line.distance(point) for point in sample_points], dtype=float)

    fig, ax = plt.subplots(figsize=(8, 7))
    try:
        reference_line.buffer(buffer_m, cap_style=2, join_style=2).boundary
        ref_buffer = reference_line.buffer(buffer_m, cap_style=2, join_style=2)
        gpd.GeoSeries([ref_buffer], crs="EPSG:25833").plot(ax=ax, color="#dde7f3", edgecolor="none", alpha=0.45)
    except Exception:
        pass

    ax.plot(*reference_line.xy, label="Reference route", color="#1f6f8b", linewidth=2.2)
    ax.plot(*generated_line.xy, label="Generated route", color="#c4472d", linewidth=1.8, linestyle="--")

    if sample_points:
        scatter = ax.scatter(
            [point.x for point in sample_points],
            [point.y for point in sample_points],
            c=distances,
            cmap="viridis",
            s=10,
            linewidth=0,
            alpha=0.9,
        )
        colorbar = fig.colorbar(scatter, ax=ax, fraction=0.046, pad=0.04)
        colorbar.set_label("Generated to reference distance (m)")

    ax.set_title(title)
    ax.set_aspect("equal")
    ax.legend(loc="upper right")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_xlabel("")
    ax.set_ylabel("")
    fig.tight_layout()
    fig.savefig(out, dpi=170)
    plt.close(fig)
    return out

