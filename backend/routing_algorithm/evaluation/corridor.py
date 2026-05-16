from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import numpy as np
import rasterio
from shapely.geometry import LineString

from .config import DEFAULT_SETTINGS, EvaluationSettings
from .geometry import sample_points


def _sample_raster(line: LineString, raster_path: Path, sample_step_m: float) -> tuple[np.ndarray, np.ndarray]:
    points = sample_points(line, sample_step_m)
    coords = [(point.x, point.y) for point in points]
    if not coords:
        empty = np.array([], dtype=float)
        return empty, np.array([], dtype=bool)

    with rasterio.open(raster_path) as ds:
        values = np.array([sample[0] for sample in ds.sample(coords)], dtype=float)
        nodata = ds.nodata
        valid = np.isfinite(values)
        if nodata is not None:
            valid &= values != nodata
        return values, valid


def evaluate_corridor(
    reference_line: LineString,
    raster_path: str | Path,
    *,
    mode: str,
    settings: EvaluationSettings = DEFAULT_SETTINGS,
) -> dict[str, Any]:
    path = Path(raster_path)
    prefix = f"corridor_{mode}"
    if not path.exists():
        return {
            f"{prefix}_path": str(path),
            f"{prefix}_status": "missing",
            f"{prefix}_sample_count": 0,
        }

    values, valid = _sample_raster(reference_line, path, settings.corridor_sample_step_m)
    if values.size == 0:
        return {
            f"{prefix}_path": str(path),
            f"{prefix}_status": "no_valid_samples",
            f"{prefix}_sample_count": 0,
        }

    valid_values = values[valid]
    if valid_values.size == 0:
        return {
            f"{prefix}_path": str(path),
            f"{prefix}_status": "no_valid_samples",
            f"{prefix}_sample_count": int(values.size),
            f"{prefix}_valid_sample_pct": 0.0,
            f"{prefix}_coverage_pct": 0.0,
            f"{prefix}_strong_coverage_pct": 0.0,
        }

    covered = valid & (values > settings.corridor_score_threshold)
    strong = valid & (values >= settings.corridor_strong_score_threshold)

    return {
        f"{prefix}_path": str(path),
        f"{prefix}_status": "ok",
        f"{prefix}_sample_count": int(values.size),
        f"{prefix}_valid_sample_pct": 100.0 * float(np.mean(valid)),
        f"{prefix}_coverage_pct": 100.0 * float(np.mean(covered)),
        f"{prefix}_strong_coverage_pct": 100.0 * float(np.mean(strong)),
        f"{prefix}_score_mean": float(np.mean(valid_values)),
        f"{prefix}_score_median": float(np.median(valid_values)),
        f"{prefix}_score_p10": float(np.percentile(valid_values, 10)),
        f"{prefix}_score_p90": float(np.percentile(valid_values, 90)),
        f"{prefix}_score_max": float(np.max(valid_values)),
    }


def evaluate_corridors(
    reference_line: LineString,
    corridor_paths: Mapping[str, str | Path],
    *,
    settings: EvaluationSettings = DEFAULT_SETTINGS,
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for mode in settings.corridor_modes:
        path = corridor_paths.get(mode)
        if path is None:
            out.update(
                {
                    f"corridor_{mode}_status": "missing",
                    f"corridor_{mode}_sample_count": 0,
                }
            )
            continue
        out.update(evaluate_corridor(reference_line, path, mode=mode, settings=settings))
    return out
