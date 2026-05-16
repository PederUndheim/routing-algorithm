from __future__ import annotations

import numpy as np

from backend.routing_algorithm.testing import config


def _as_float(a: np.ndarray) -> np.ndarray:
    return a.astype(np.float32, copy=False)


def logistic(x: np.ndarray, *, x0: float, k: float) -> np.ndarray:
    x = _as_float(x)
    y = 1.0 / (1.0 + np.exp(-k * (x - x0)))
    return np.clip(y, 0.0, 1.0).astype(np.float32)


def threshold_jump_slope(
    slope: np.ndarray,
    *,
    threshold: float,
    low_max: float,
    low_power: float,
    jump_start: float,
    jump_end: float,
    jump_to: float,
    tail_end: float,
) -> np.ndarray:
    if jump_end <= jump_start:
        raise ValueError("jump_end must be greater than jump_start")
    if tail_end <= jump_end:
        raise ValueError("tail_end must be greater than jump_end")

    s = _as_float(slope)

    below = low_max * np.clip(s / threshold, 0.0, 1.0) ** low_power
    jump_start_value = low_max * np.clip(jump_start / threshold, 0.0, 1.0) ** low_power

    jump_t = np.clip((s - jump_start) / (jump_end - jump_start), 0.0, 1.0)
    jump_ramp = jump_start_value + (jump_to - jump_start_value) * jump_t

    tail_t = np.clip((s - jump_end) / (tail_end - jump_end), 0.0, 1.0)
    linear_tail = jump_to + (1.0 - jump_to) * tail_t

    u = np.where(s < jump_start, below, jump_ramp)
    u = np.where(s < jump_end, u, linear_tail)
    return np.clip(u, 0.0, 1.0).astype(np.float32)


def to_cost_x_y(
    unit_0_to_1: np.ndarray,
    *,
    min_cost: float = config.MIN_COST,
    max_cost: float = config.MAX_COST,
) -> np.ndarray:
    out = min_cost + unit_0_to_1 * (max_cost - min_cost)
    return out.astype(np.float32, copy=False)


def slope_cost(transform: str, slope: np.ndarray, *, min_cost: float, max_cost: float, **params) -> np.ndarray:
    if transform == "threshold_jump":
        u = threshold_jump_slope(slope, **params)
    else:
        raise ValueError(f"Unknown experimental slope transform: {transform}")
    return to_cost_x_y(u, min_cost=min_cost, max_cost=max_cost)


def curvature_cost(curvature: np.ndarray, *, x0: float, k: float, min_cost: float, max_cost: float) -> np.ndarray:
    u = logistic(curvature, x0=x0, k=k)
    return to_cost_x_y(u, min_cost=min_cost, max_cost=max_cost)
