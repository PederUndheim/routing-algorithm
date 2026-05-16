from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import rasterio
from shapely.geometry import LineString

from .config import DEFAULT_SETTINGS, EvaluationSettings
from .geometry import sample_points


def _sample_values(line: LineString, raster_path: Path, sample_step_m: float) -> list[float]:
    points = sample_points(line, sample_step_m)
    coords = [(point.x, point.y) for point in points]
    if not coords:
        return []
    with rasterio.open(raster_path) as ds:
        raw = np.array([sample[0] for sample in ds.sample(coords)], dtype=float)
        valid = np.isfinite(raw)
        if ds.nodata is not None:
            valid &= raw != ds.nodata
        return [float(v) for v in raw[valid]]


def categorical_route_summary(
    line: LineString,
    raster_path: str | Path,
    *,
    label: str,
    settings: EvaluationSettings = DEFAULT_SETTINGS,
) -> dict[str, Any]:
    path = Path(raster_path)
    prefix = f"terrain_{label}"
    if not path.exists():
        return {f"{prefix}_status": "missing", f"{prefix}_path": str(path)}

    values = _sample_values(line, path, settings.sample_step_m)
    if not values:
        return {f"{prefix}_status": "no_valid_samples", f"{prefix}_path": str(path)}

    counts: dict[str, int] = defaultdict(int)
    for value in values:
        if abs(value - round(value)) < 1e-6:
            key = str(int(round(value)))
        else:
            key = f"{value:g}"
        counts[key] += 1

    total = sum(counts.values())
    summary = {
        key: {"count": count, "pct": 100.0 * count / total}
        for key, count in sorted(counts.items(), key=lambda item: item[0])
    }
    dominant = max(summary.items(), key=lambda item: item[1]["count"])[0]
    return {
        f"{prefix}_status": "ok",
        f"{prefix}_path": str(path),
        f"{prefix}_dominant_class": dominant,
        f"{prefix}_classes_json": json.dumps(summary, sort_keys=True),
    }


def reference_deviation_by_class(
    reference_line: LineString,
    generated_line: LineString,
    raster_path: str | Path,
    *,
    label: str,
    settings: EvaluationSettings = DEFAULT_SETTINGS,
) -> dict[str, Any]:
    path = Path(raster_path)
    prefix = f"terrain_{label}_deviation"
    if not path.exists():
        return {f"{prefix}_status": "missing", f"{prefix}_path": str(path)}

    points = sample_points(reference_line, settings.sample_step_m)
    coords = [(point.x, point.y) for point in points]
    if not coords:
        return {f"{prefix}_status": "no_reference_samples", f"{prefix}_path": str(path)}

    grouped: dict[str, list[float]] = defaultdict(list)
    with rasterio.open(path) as ds:
        raw_values = np.array([sample[0] for sample in ds.sample(coords)], dtype=float)
        for point, value in zip(points, raw_values):
            if not np.isfinite(value):
                continue
            if ds.nodata is not None and value == ds.nodata:
                continue
            if abs(value - round(value)) < 1e-6:
                key = str(int(round(value)))
            else:
                key = f"{value:g}"
            grouped[key].append(float(generated_line.distance(point)))

    if not grouped:
        return {f"{prefix}_status": "no_valid_samples", f"{prefix}_path": str(path)}

    total = sum(len(values) for values in grouped.values())
    summary = {}
    for key, distances in sorted(grouped.items(), key=lambda item: item[0]):
        arr = np.array(distances, dtype=float)
        summary[key] = {
            "count": int(arr.size),
            "route_pct": 100.0 * float(arr.size) / total,
            "mean_m": float(np.mean(arr)),
            "median_m": float(np.median(arr)),
            "p95_m": float(np.percentile(arr, 95)),
            "max_m": float(np.max(arr)),
        }

    return {
        f"{prefix}_status": "ok",
        f"{prefix}_path": str(path),
        f"{prefix}_by_class_json": json.dumps(summary, sort_keys=True),
    }


def summarize_terrain_rasters(
    reference_line: LineString,
    generated_line: LineString,
    terrain_rasters: Mapping[str, str | Path],
    *,
    settings: EvaluationSettings = DEFAULT_SETTINGS,
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for label, path in terrain_rasters.items():
        out.update(categorical_route_summary(reference_line, path, label=label, settings=settings))
        out.update(reference_deviation_by_class(reference_line, generated_line, path, label=label, settings=settings))
    return out

