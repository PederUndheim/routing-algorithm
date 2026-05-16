from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
from shapely.geometry import LineString

from .config import DEFAULT_SETTINGS, EvaluationSettings, FailureThresholds
from .geometry import coarsened_step_for_pair, coordinate_pairs, densify, endpoints, sample_points


@dataclass(frozen=True)
class RouteComparison:
    metrics: dict[str, Any]


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def discrete_frechet(P: list[tuple[float, float]], Q: list[tuple[float, float]]) -> float:
    if not P or not Q:
        return float("nan")

    previous = [0.0] * len(Q)
    current = [0.0] * len(Q)

    for i, p in enumerate(P):
        for j, q in enumerate(Q):
            d = _distance(p, q)
            if i == 0 and j == 0:
                current[j] = d
            elif i == 0:
                current[j] = max(current[j - 1], d)
            elif j == 0:
                current[j] = max(previous[j], d)
            else:
                current[j] = max(min(previous[j], previous[j - 1], current[j - 1]), d)
        previous, current = current, previous

    return float(previous[-1])


def _distance_stats(values: list[float], prefix: str) -> dict[str, float | int]:
    arr = np.array(values, dtype=float)
    if arr.size == 0:
        return {
            f"{prefix}_count": 0,
            f"{prefix}_mean_m": float("nan"),
            f"{prefix}_median_m": float("nan"),
            f"{prefix}_p90_m": float("nan"),
            f"{prefix}_p95_m": float("nan"),
            f"{prefix}_max_m": float("nan"),
            f"{prefix}_rmse_m": float("nan"),
        }
    return {
        f"{prefix}_count": int(arr.size),
        f"{prefix}_mean_m": float(np.mean(arr)),
        f"{prefix}_median_m": float(np.median(arr)),
        f"{prefix}_p90_m": float(np.percentile(arr, 90)),
        f"{prefix}_p95_m": float(np.percentile(arr, 95)),
        f"{prefix}_max_m": float(np.max(arr)),
        f"{prefix}_rmse_m": float(math.sqrt(float(np.mean(arr * arr)))),
    }


def point_to_line_distances(line: LineString, other: LineString, sample_step_m: float) -> list[float]:
    return [float(other.distance(point)) for point in sample_points(line, sample_step_m)]


def orient_generated_to_reference(reference: LineString, generated: LineString) -> tuple[LineString, bool]:
    ref_start, ref_end = endpoints(reference)
    gen_start, gen_end = endpoints(generated)
    same_direction_error = _distance(ref_start, gen_start) + _distance(ref_end, gen_end)
    reversed_direction_error = _distance(ref_start, gen_end) + _distance(ref_end, gen_start)
    if reversed_direction_error < same_direction_error:
        return LineString(list(generated.coords)[::-1]), True
    return generated, False


def buffer_overlap_metrics(reference: LineString, generated: LineString, buffer_m: float) -> dict[str, float]:
    ref_len = max(float(reference.length), 1e-9)
    gen_len = max(float(generated.length), 1e-9)

    reference_buffer = reference.buffer(buffer_m, cap_style=2, join_style=2)
    generated_buffer = generated.buffer(buffer_m, cap_style=2, join_style=2)

    generated_in_reference = 100.0 * float(generated.intersection(reference_buffer).length) / gen_len
    reference_in_generated = 100.0 * float(reference.intersection(generated_buffer).length) / ref_len

    union_area = float(reference_buffer.union(generated_buffer).area)
    if union_area <= 0:
        jaccard = float("nan")
    else:
        jaccard = 100.0 * float(reference_buffer.intersection(generated_buffer).area) / union_area

    suffix = f"{int(buffer_m) if float(buffer_m).is_integer() else buffer_m:g}m"
    return {
        f"generated_in_reference_buffer_{suffix}_pct": generated_in_reference,
        f"reference_in_generated_buffer_{suffix}_pct": reference_in_generated,
        f"mean_buffer_overlap_{suffix}_pct": 0.5 * (generated_in_reference + reference_in_generated),
        f"buffer_jaccard_{suffix}_pct": jaccard,
    }


def _value(metrics: dict[str, Any], name: str, default: float = float("nan")) -> float:
    try:
        return float(metrics.get(name, default))
    except (TypeError, ValueError):
        return default


def classify_quality(metrics: dict[str, Any], thresholds: FailureThresholds) -> tuple[str, str, bool]:
    p95 = _value(metrics, "distance_symmetric_p95_m")
    length_ratio = _value(metrics, "length_ratio_generated_to_reference")
    ref_50 = _value(metrics, "reference_in_generated_buffer_50m_pct", 0.0)
    gen_50 = _value(metrics, "generated_in_reference_buffer_50m_pct", 0.0)
    ref_100 = _value(metrics, "reference_in_generated_buffer_100m_pct", ref_50)

    length_is_usable = thresholds.min_usable_length_ratio <= length_ratio <= thresholds.max_usable_length_ratio

    if (
        p95 <= thresholds.excellent_p95_m
        and min(ref_50, gen_50) >= thresholds.excellent_buffer_50_pct
        and length_is_usable
    ):
        return "excellent", "low", False
    if p95 <= thresholds.usable_p95_m and ref_100 >= thresholds.usable_reference_buffer_100_pct and length_is_usable:
        return "usable", "medium", False
    if p95 <= thresholds.inspect_p95_m and ref_100 >= thresholds.inspect_reference_buffer_100_pct:
        return "inspect", "high", True
    return "likely_bad_failure", "severe", True


def compare_routes(
    reference: LineString,
    generated: LineString,
    *,
    settings: EvaluationSettings = DEFAULT_SETTINGS,
) -> RouteComparison:
    generated, generated_reversed = orient_generated_to_reference(reference, generated)

    reference_length = float(reference.length)
    generated_length = float(generated.length)
    length_ratio = generated_length / reference_length if reference_length > 0 else float("nan")
    length_diff_pct = 100.0 * (generated_length - reference_length) / reference_length if reference_length > 0 else float("nan")

    ref_start, ref_end = endpoints(reference)
    gen_start, gen_end = endpoints(generated)

    gen_to_ref = point_to_line_distances(generated, reference, settings.sample_step_m)
    ref_to_gen = point_to_line_distances(reference, generated, settings.sample_step_m)
    symmetric = gen_to_ref + ref_to_gen

    frechet_step = coarsened_step_for_pair(
        reference,
        generated,
        settings.frechet_step_m,
        settings.max_frechet_cells,
    )
    reference_frechet = densify(reference, frechet_step)
    generated_frechet = densify(generated, frechet_step)

    metrics: dict[str, Any] = {
        "reference_length_m": reference_length,
        "generated_length_m": generated_length,
        "length_ratio_generated_to_reference": length_ratio,
        "length_diff_pct": length_diff_pct,
        "sample_step_m": float(settings.sample_step_m),
        "frechet_step_m": float(frechet_step),
        "generated_reversed_to_match_reference": bool(generated_reversed),
        "start_endpoint_error_m": _distance(ref_start, gen_start),
        "end_endpoint_error_m": _distance(ref_end, gen_end),
        "frechet_m": discrete_frechet(coordinate_pairs(reference_frechet), coordinate_pairs(generated_frechet)),
        "hausdorff_m": float(reference.hausdorff_distance(generated)),
    }

    metrics.update(_distance_stats(gen_to_ref, "distance_generated_to_reference"))
    metrics.update(_distance_stats(ref_to_gen, "distance_reference_to_generated"))
    metrics.update(_distance_stats(symmetric, "distance_symmetric"))

    buffer_distances = sorted({float(v) for v in settings.buffer_distances_m} | {50.0, 100.0})
    for buffer_m in buffer_distances:
        metrics.update(buffer_overlap_metrics(reference, generated, float(buffer_m)))

    quality_label, inspection_priority, needs_visual_review = classify_quality(metrics, settings.thresholds)
    metrics.update(
        {
            "quality_label": quality_label,
            "inspection_priority": inspection_priority,
            "needs_visual_review": bool(needs_visual_review),
        }
    )
    return RouteComparison(metrics=metrics)


def comparison_to_dict(comparison: RouteComparison) -> dict[str, Any]:
    return dict(comparison.metrics)
