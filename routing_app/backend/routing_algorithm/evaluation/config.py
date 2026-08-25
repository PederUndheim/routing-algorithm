from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class FailureThresholds:
    """Heuristic thresholds for inspection triage, not correctness claims."""

    excellent_p95_m: float = 75.0
    usable_p95_m: float = 150.0
    inspect_p95_m: float = 300.0

    excellent_buffer_50_pct: float = 80.0
    usable_reference_buffer_100_pct: float = 75.0
    inspect_reference_buffer_100_pct: float = 50.0

    min_usable_length_ratio: float = 0.55
    max_usable_length_ratio: float = 1.80


@dataclass(frozen=True)
class EvaluationSettings:
    metric_crs: str = "EPSG:25833"
    sample_step_m: float = 10.0
    frechet_step_m: float = 20.0
    buffer_distances_m: tuple[float, ...] = (25.0, 50.0, 100.0)
    max_frechet_cells: int = 5_000_000

    corridor_sample_step_m: float = 10.0
    corridor_score_threshold: float = 0.0
    corridor_strong_score_threshold: float = 0.5
    corridor_modes: tuple[str, ...] = ("conservative", "balanced", "explorative")

    evaluation_run_id: str = "generated_routes"
    provider_suffixes: tuple[str, ...] = ("_skiguide",)
    make_plots: bool = True
    thresholds: FailureThresholds = FailureThresholds()


DEFAULT_SETTINGS = EvaluationSettings()


def parse_buffer_distances(value: str | Sequence[float] | None) -> tuple[float, ...]:
    if value is None:
        return DEFAULT_SETTINGS.buffer_distances_m
    if isinstance(value, str):
        parts = [part.strip() for part in value.split(",") if part.strip()]
        if not parts:
            raise ValueError("At least one buffer distance is required")
        return tuple(float(part) for part in parts)
    return tuple(float(v) for v in value)

