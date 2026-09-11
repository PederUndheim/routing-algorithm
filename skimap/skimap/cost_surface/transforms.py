"""Terrain value -> cost curves. Pure functions on arrays."""

from __future__ import annotations

import numpy as np

from skimap import config


def _f32(a: np.ndarray) -> np.ndarray:
    return a.astype(np.float32, copy=False)


def logistic(x: np.ndarray, *, x0: float, k: float) -> np.ndarray:
    """Maps x to [0, 1]. x0 is the midpoint, k the steepness."""
    y = 1.0 / (1.0 + np.exp(-k * (_f32(x) - x0)))
    return np.clip(y, 0.0, 1.0).astype(np.float32)


def threshold_jump(
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
    """Near-flat below the threshold, a sharp step through it, then a linear climb.

    The step is what makes 30 degrees behave as a real decision boundary
    rather than one more point on a smooth curve.
    """
    if jump_end <= jump_start:
        raise ValueError("jump_end must be greater than jump_start")
    if tail_end <= jump_end:
        raise ValueError("tail_end must be greater than jump_end")

    s = _f32(slope)

    below = low_max * np.clip(s / threshold, 0.0, 1.0) ** low_power
    jump_start_value = low_max * np.clip(jump_start / threshold, 0.0, 1.0) ** low_power

    jump_t = np.clip((s - jump_start) / (jump_end - jump_start), 0.0, 1.0)
    jump_ramp = jump_start_value + (jump_to - jump_start_value) * jump_t

    tail_t = np.clip((s - jump_end) / (tail_end - jump_end), 0.0, 1.0)
    tail = jump_to + (1.0 - jump_to) * tail_t

    u = np.where(s < jump_start, below, jump_ramp)
    u = np.where(s < jump_end, u, tail)
    return np.clip(u, 0.0, 1.0).astype(np.float32)


def to_cost(unit: np.ndarray, *, min_cost: float, max_cost: float) -> np.ndarray:
    """Map [0, 1] onto [min_cost, max_cost]."""
    return (min_cost + unit * (max_cost - min_cost)).astype(np.float32, copy=False)


def slope_cost(slope: np.ndarray) -> np.ndarray:
    params = dict(config.SLOPE)
    min_cost = params.pop("min_cost")
    max_cost = params.pop("max_cost")
    return to_cost(threshold_jump(slope, **params), min_cost=min_cost, max_cost=max_cost)


def windshelter_cost(windshelter: np.ndarray) -> np.ndarray:
    params = dict(config.WINDSHELTER)
    min_cost = params.pop("min_cost")
    max_cost = params.pop("max_cost")
    return to_cost(logistic(windshelter, **params), min_cost=min_cost, max_cost=max_cost)


def ridge_cost(windshelter: np.ndarray) -> np.ndarray:
    """Extra cost on exposed ridges: `extra` where windshelter is below the cut.

    Returned as its own layer rather than applied, so the debug output shows
    what was charged and not only where it landed.
    """
    ridge = config.RIDGE_COST
    return np.where(_f32(windshelter) <= ridge["threshold"], ridge["extra"], 0.0).astype(np.float32)
