"""GPS-track density -> the weight the cost reduction is scaled by.

Two scopes live here, and they answer different questions.

The NATIONAL scale (compute_scale) is a pair of density values taken once
over all track data in the country and cached. Every tile then applies that
same constant, so a given density means the same thing everywhere and the
mosaic has no seams. curve="linear" and "log" use it.

The PER-TILE bands (_tile_bands) rank a tile's tracked cells against each
other instead, so the best-used ground in a quiet area still registers as
well used. That is a different claim, and it does put seams at tile edges:
the same density can land in different bands on either side of one. The
reduction is capped at a few cost units against a surface where barriers sit
at 1500, so the seam is small - but it is real, and it is the price of the
scope.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import numpy as np
from osgeo import gdal

from skimap import config, paths

gdal.UseExceptions()

_BINS = 65536   # tracks is UInt16, so a full histogram is exact and cheap

# Percentiles the national (lower, upper) scale is derived from. Only used
# by compute_scale() below - config.TRACKS reads the cached result, not this.
_PERCENTILES = {"lower_percentile": 60.0, "upper_percentile": 95.0}


def compute_scale(out_path: Path = paths.TRACK_SCALE) -> tuple[float, float]:
    """Percentile scale over the national tracks data. Caches to out_path.

    Percentiles are taken over positive pixels only - the zero background
    is most of the country and would otherwise drag the scale down until
    sparse, one-pass tracks read as busy routes.

    Note the scale comes from the ~56% of tiles the source rasters cover.
    That is correct rather than convenient: uncovered ground has no tracks,
    so it gets no reduction, and including its zeros would only distort the
    scale for the ground that does have data.

    Exact, not sampled: the source is UInt16, so one 65536-bin histogram
    holds the whole national distribution and the percentiles come straight
    out of its cumulative sum. Sampling would make the scale depend on
    which pixels were drawn, and the whole point of computing it once is
    that it never moves.
    """
    src = paths.layer("tracks")
    ds = gdal.Open(str(src))
    band = ds.GetRasterBand(1)
    w, h = ds.RasterXSize, ds.RasterYSize
    if band.DataType != gdal.GDT_UInt16:
        raise ValueError(
            f"{src.name} is {gdal.GetDataTypeName(band.DataType)}, expected UInt16 - "
            "the exact histogram below assumes it"
        )

    counts = np.zeros(_BINS, dtype=np.int64)
    block = 256   # rows; at national width one row is ~84k px
    for y in range(0, h, block):
        ny = min(block, h - y)
        arr = band.ReadAsArray(0, y, w, ny)
        counts += np.bincount(arr.ravel(), minlength=_BINS)
        if (y // block) % 50 == 0:
            print(f"  {100 * (y + ny) / h:5.1f}%", flush=True)
    ds = None

    background = int(counts[0])
    counts[0] = 0   # nodata and untravelled ground are the same thing here
    positive = int(counts.sum())
    if positive == 0:
        raise ValueError(f"No positive pixels in {src} - nothing to normalize against")

    cum = np.cumsum(counts)
    p = _PERCENTILES
    lower = float(np.searchsorted(cum, positive * p["lower_percentile"] / 100.0))
    upper = float(np.searchsorted(cum, positive * p["upper_percentile"] / 100.0))
    if upper <= lower:
        raise ValueError(
            f"Track percentiles collapsed: p{p['lower_percentile']:g}={lower:g} "
            f">= p{p['upper_percentile']:g}={upper:g}. The density values are too "
            "coarse for this pair of percentiles to separate."
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "source": src.name,
                "lower_percentile": p["lower_percentile"],
                "upper_percentile": p["upper_percentile"],
                "lower": lower,
                "upper": upper,
                "positive_px": positive,
                "background_px": background,
                "max": float(np.flatnonzero(counts)[-1]),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        f"{positive:,} positive px of {positive + background:,} "
        f"({100 * positive / (positive + background):.2f}%)\n"
        f"p{p['lower_percentile']:g} = {lower:g}, p{p['upper_percentile']:g} = {upper:g} "
        f"-> {out_path}"
    )
    return lower, upper


def load_scale(path: Path = paths.TRACK_SCALE) -> tuple[float, float]:
    if not path.exists():
        raise FileNotFoundError(
            f"No track scale at {path}. Build it with 'python -m skimap.cli tracks'."
        )
    d = json.loads(path.read_text(encoding="utf-8"))
    return float(d["lower"]), float(d["upper"])


def band_thresholds(reference: np.ndarray,
                    params: Optional[dict] = None) -> list[tuple[float, float, float, float]]:
    """(percentile, weight, density threshold, share of positive cells at or above).

    The tuning readout for curve="tile_bands": what the percentiles in
    `bands` actually resolve to on this tile's data, and how much of it each
    band ends up covering. Track density is a small integer with heavy ties -
    70% of Etne's tracked cells are exactly 1 - so a percentile lands ON a
    tied value more often than not, and "the top half" can cover anywhere
    from 18% to 100% of the cells depending on where the ties fall. That is
    not a bug to hide; it is the thing to look at before choosing a
    percentile.

    The population this ranks over already excludes anything below
    `min_density` - see normalize().
    """
    t = params if params is not None else config.TRACKS
    pos = reference[reference >= float(t.get("min_density", 1.0))]
    out = []
    if pos.size == 0:
        return out
    for pct, weight in sorted(t.get("bands") or [], key=lambda b: float(b[0])):
        threshold = float(np.percentile(pos, float(pct)))
        share = float((pos >= threshold).mean())
        out.append((float(pct), float(weight), threshold, share))
    return out


def _tile_bands(values: np.ndarray, reference: np.ndarray, params: dict) -> np.ndarray:
    """Per-tile percentile bands: rank this tile's cells against each other.

    `reference` is the population the percentiles are taken over - the tile
    being built, normally. It is a separate argument only so a figure can
    evaluate the mapping on a synthetic density axis while still deriving the
    thresholds from real data.
    """
    bands = params.get("bands") or []
    if not bands:
        raise ValueError(
            'TRACKS["curve"] is "tile_bands" but TRACKS["bands"] is empty. '
            "Give it [[percentile, weight], ...]."
        )

    unit = np.zeros(np.shape(values), dtype=np.float32)
    min_density = float(params.get("min_density", 1.0))
    pos = reference[reference >= min_density]
    # Too few tracked cells to rank. Returning zero says "no evidence here",
    # which is the honest answer - the alternative is handing full weight to
    # the top fifth of a dozen cells left by one passing skier.
    if pos.size < int(params.get("min_positive_px", 0)):
        return unit

    # Low to high, each overwriting the last, so the highest band a cell
    # qualifies for is the one it keeps. No separate check against
    # min_density here: every threshold comes from `pos`, which already
    # excludes anything below it, so `values >= threshold` alone can never
    # admit a cell that didn't clear the floor.
    for pct, weight in sorted(bands, key=lambda b: float(b[0])):
        threshold = np.percentile(pos, float(pct))
        unit = np.where(values >= threshold, np.float32(weight), unit)
    return np.clip(unit, 0.0, 1.0).astype(np.float32)


def normalize(tracks: np.ndarray, scale: tuple[float, float], *,
              params: Optional[dict] = None,
              reference: Optional[np.ndarray] = None) -> np.ndarray:
    """Map track density onto the [0, 1] weight the coefficients are scaled by.

    This is the whole density-to-weight mapping, `power` included. It used to
    stop short of `power`, leaving every caller to apply it - which was
    survivable for the continuous curves and is not for "tile_bands", where
    squaring a 0.5 band silently turns 1.0 cost units into 0.25.

    Two of the three curves use the national `scale`; see compute_scale for
    why that is computed once. "tile_bands" deliberately does not - it ranks
    each tile against itself and accepts the seams that follow.

    `params` overrides config.TRACKS, for comparing candidate schemes without
    mutating global state. `reference` overrides the population the per-tile
    percentiles are taken over, which only a figure needs.

    `min_density` decides what counts as a track at all - see config.TRACKS.
    Below it, a cell is untracked ground: zero credit, and for "tile_bands",
    not even counted into the tile's own population. This is checked once,
    here, for every curve - not left to each branch to remember.

    `presence_floor` lifts every pixel that DOES clear `min_density`, and
    only those, to at least `floor`: zero density stays zero, so untracked
    ground is untouched. It applies to all three curves.
    """
    t = params if params is not None else config.TRACKS
    curve = t.get("curve", "linear")
    has_track = tracks >= float(t.get("min_density", 1.0))

    if curve == "tile_bands":
        unit = _tile_bands(tracks, reference if reference is not None else tracks, t)
    else:
        lo, hi = scale
        if hi <= lo:
            return np.zeros_like(tracks, dtype=np.float32)
        if curve == "log":
            # Density is a count, skewed by orders of magnitude; log is the
            # scale it lives on. Clamped at 1 because log(0) is undefined and
            # a zero pixel is masked out below regardless.
            lo_l, hi_l = np.log(max(lo, 1.0)), np.log(max(hi, max(lo, 1.0) + 1e-9))
            unit = (np.log(np.maximum(tracks, 1.0)) - lo_l) / (hi_l - lo_l)
        elif curve == "linear":
            unit = (tracks - lo) / (hi - lo)
        else:
            raise ValueError(
                f"Unknown TRACKS['curve'] {curve!r}; use 'linear', 'log' or 'tile_bands'."
            )
        unit = np.clip(unit, 0.0, 1.0) ** float(t.get("power", 1.0))
        unit = np.where(has_track, unit, 0.0)

    floor = float(t.get("presence_floor", 0.0))
    if floor:
        unit = np.where(has_track, floor + (1.0 - floor) * unit, 0.0)
    return unit.astype(np.float32)
