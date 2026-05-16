from __future__ import annotations

from typing import List, Tuple
import math
import uuid

import grass.script as gs

from backend import config
from backend.routing_algorithm.routing.grass_mosaic import build_or_get_mosaic, mosaic_name


def _raster_max(name: str) -> float:
    txt = gs.read_command("r.univar", map=name, flags="g").strip().splitlines()
    d = dict(line.split("=", 1) for line in txt if "=" in line)
    n = float(d.get("n", "0") or "0")
    if n <= 0:
        return 0.0
    return float(d.get("max", "0") or "0")


def _raster_percentile(name: str, percentile: float) -> float:
    pct = max(0.0, min(100.0, float(percentile)))
    txt = gs.read_command(
        "r.univar",
        map=name,
        flags="ge",
        percentile=pct,
    ).strip().splitlines()
    d = dict(line.split("=", 1) for line in txt if "=" in line)

    n = float(d.get("n", "0") or "0")
    if n <= 0:
        return 0.0

    pct_key_int = f"percentile_{int(round(pct))}"
    if pct_key_int in d:
        return float(d[pct_key_int] or "0")

    pct_key_float = f"percentile_{pct}"
    if pct_key_float in d:
        return float(d[pct_key_float] or "0")

    for key, val in d.items():
        if key.startswith("percentile_"):
            try:
                return float(val or "0")
            except ValueError:
                continue

    return 0.0


def _tracks_legacy_scale_value(name: str, transform: str) -> float:
    norm_cfg = getattr(config, "TRACK_NORMALIZATION", {}) or {}
    method = str(norm_cfg.get("method", "max")).lower()

    if method == "percentile":
        pct = float(norm_cfg.get("percentile", 95.0))
        raw_scale = _raster_percentile(name, pct)
        if raw_scale > 0.0:
            if transform == "log1p":
                return float(math.log1p(raw_scale))
            return raw_scale

    raw_max = _raster_max(name)
    if raw_max <= 0.0:
        return 0.0
    if transform == "log1p":
        return float(math.log1p(raw_max))
    return raw_max


def _tracks_positive_percentile_range(name: str, transform: str) -> tuple[float, float]:
    norm_cfg = getattr(config, "TRACK_NORMALIZATION", {}) or {}
    lower_pct = float(norm_cfg.get("lower_percentile", 60.0))
    upper_pct = float(norm_cfg.get("upper_percentile", 98.0))
    lower_pct = max(0.0, min(100.0, lower_pct))
    upper_pct = max(0.0, min(100.0, upper_pct))
    if upper_pct <= lower_pct:
        raise ValueError("TRACK_NORMALIZATION upper_percentile must be greater than lower_percentile")

    if transform == "log1p":
        value_expr = f"log(1 + max({name}, 0))"
    elif transform == "linear":
        value_expr = f"max({name}, 0)"
    else:
        raise ValueError(f"Unsupported TRACK_NORMALIZATION transform: {transform}")

    tmp_name = f"tmp_tracks_positive_{uuid.uuid4().hex[:12]}"
    gs.mapcalc(
        f"{tmp_name} = if(isnull({name}), null(), if({name} <= 0, null(), {value_expr}))",
        overwrite=True,
    )
    try:
        low = _raster_percentile(tmp_name, lower_pct)
        high = _raster_percentile(tmp_name, upper_pct)
    finally:
        gs.run_command("g.remove", type="raster", name=tmp_name, flags="f", quiet=True)

    if high <= low:
        return 0.0, 0.0
    return low, high


def compose_tracks_influence_for_request(
    area_ids: List[str],
    *,
    base_cost_name: str,
    track_influence_mode: str,
) -> str:
    mode = track_influence_mode.lower()
    if mode not in config.TRACK_INFLUENCE_PARAMS:
        raise ValueError(f"Unsupported track_influence_mode: {track_influence_mode}")

    mode_params = config.TRACK_INFLUENCE_PARAMS[mode]
    max_reduction_outside = float(mode_params["max_reduction_outside"])
    max_reduction_forest = float(mode_params["max_reduction_forest"])
    track_power = float(mode_params.get("track_power", 1.0))
    if max_reduction_outside <= 0.0 and max_reduction_forest <= 0.0:
        return base_cost_name
    if track_power <= 0.0:
        raise ValueError(f"track_power must be > 0 for mode: {track_influence_mode}")

    tracks_name = build_or_get_mosaic(area_ids, kind="tracks")
    forest_name = build_or_get_mosaic(area_ids, kind="forest")
    norm_cfg = getattr(config, "TRACK_NORMALIZATION", {}) or {}
    normalization_method = str(norm_cfg.get("method", "max")).lower()
    normalization_transform = str(norm_cfg.get("transform", "linear")).lower()

    request_cost_name = mosaic_name(f"cost_tracks_{mode}", area_ids)

    max_reduction_expr = (
        f"({max_reduction_outside} + ({max_reduction_forest} - {max_reduction_outside}) * "
        f"if(isnull({forest_name}), 0, if({forest_name} > 0, 1, 0)))"
    )
    t_raw_expr = (
        f"if(isnull({tracks_name}), 0, "
        f"max({tracks_name}, 0))"
    )
    if normalization_transform == "log1p":
        t_value_expr = f"log(1 + ({t_raw_expr}))"
    elif normalization_transform == "linear":
        t_value_expr = t_raw_expr
    else:
        raise ValueError(f"Unsupported TRACK_NORMALIZATION transform: {normalization_transform}")

    if normalization_method == "positive_percentile_range":
        tracks_low, tracks_high = _tracks_positive_percentile_range(
            tracks_name,
            normalization_transform,
        )
        if tracks_high <= tracks_low:
            return base_cost_name
        t_norm_expr = f"min(max(({t_value_expr} - {tracks_low}) / ({tracks_high} - {tracks_low}), 0), 1)"
    else:
        tracks_scale = _tracks_legacy_scale_value(tracks_name, normalization_transform)
        if tracks_scale <= 0.0:
            return base_cost_name
        t_norm_expr = f"min(max(({t_value_expr}) / {tracks_scale}, 0), 1)"

    if abs(track_power - 1.0) < 1e-9:
        t_expr = t_norm_expr
    else:
        t_expr = f"pow({t_norm_expr}, {track_power})"

    gs.mapcalc(
        f"{request_cost_name} = max({float(config.MIN_COST)}, {base_cost_name} - ({max_reduction_expr}) * ({t_expr}))",
        overwrite=True,
    )

    return request_cost_name


def compose_cost_surface_for_request(
    area_ids: List[str],
    *,
    base_cost_name: str,
    avoid_lake: bool,
    avoid_glacier: bool,
    avoid_river: bool,
    track_influence_mode: str,
) -> str:
    gs.run_command("g.region", raster=base_cost_name, quiet=True)

    with_tracks = compose_tracks_influence_for_request(
        area_ids,
        base_cost_name=base_cost_name,
        track_influence_mode=track_influence_mode,
    )

    if not avoid_lake and not avoid_glacier and not avoid_river:
        return with_tracks

    hard_barrier_masks: List[str] = []
    if avoid_lake:
        hard_barrier_masks.append(build_or_get_mosaic(area_ids, kind="lake"))
    if avoid_glacier:
        hard_barrier_masks.append(build_or_get_mosaic(area_ids, kind="glacier"))

    request_cost_name = mosaic_name("cost_req", area_ids)
    request_expr = with_tracks

    if avoid_river:
        try:
            river_name = build_or_get_mosaic(area_ids, kind="river_with_bridge")
            river_mask_expr = f"if(isnull({river_name}), 0, {river_name})"
            request_expr = (
                f"if(({river_mask_expr}) == 2, {float(config.MIN_COST)}, "
                f"if(({river_mask_expr}) == 1, max({with_tracks}, {float(config.BARRIER_COST)}), {request_expr}))"
            )
        except FileNotFoundError:
            river_name = build_or_get_mosaic(area_ids, kind="river")
            river_mask_expr = f"if(isnull({river_name}), 0, {river_name})"
            request_expr = (
                f"if(({river_mask_expr}) > 0, "
                f"max({with_tracks}, {float(config.BARRIER_COST)}), {request_expr})"
            )

    if hard_barrier_masks:
        hard_barrier_mask_expr = " + ".join(
            f"if(isnull({name}), 0, {name})" for name in hard_barrier_masks
        )
        request_expr = (
            f"if(({hard_barrier_mask_expr}) > 0, {float(config.BARRIER_COST)}, {request_expr})"
        )

    gs.mapcalc(
        f"{request_cost_name} = {request_expr}",
        overwrite=True,
    )

    return request_cost_name


def set_region_local(
    mosaic_raster: str,
    start_xy: Tuple[float, float],
    end_xy: Tuple[float, float],
    buffer_m: float,
) -> None:
    gs.run_command("g.region", raster=mosaic_raster, quiet=True)

    minx = min(start_xy[0], end_xy[0]) - buffer_m
    maxx = max(start_xy[0], end_xy[0]) + buffer_m
    miny = min(start_xy[1], end_xy[1]) - buffer_m
    maxy = max(start_xy[1], end_xy[1]) + buffer_m

    gs.run_command("g.region", n=maxy, s=miny, e=maxx, w=minx, quiet=True)
