"""Read an ArcGIS .lyrx and hand back the colours it paints with.

The lab figures draw the cost surface under the same symbology you have open
in ArcGIS, so the picture and the map agree and re-styling the layer in Pro is
all it takes to change them. That is this module's whole job: parse the .lyrx
and return a matplotlib (cmap, norm).

A .lyrx is JSON - the CIM document Pro saves a layer as. For a raster the part
that matters is layerDefinitions[0].colorizer, and for the cost surface that
is a CIMRasterStretchColorizer: a stretch range, plus a colour ramp to stretch
across it.

Ramps nest. The cost surface's is a CIMMultipartColorRamp - eight two-colour
segments, with weights saying what share of the bar each one gets - and each
segment is a continuous ramp between two colours. The colours are not all in
one space either: this file mixes CIMRGBColor and CIMHSVColor stops, which is
why there is a converter here rather than a cast.

Nothing here is specific to the cost surface; black.lyrx and
track_reduction.lyrx parse the same way, which is what lab's `--style` is for.

## Hue takes the short way round

A CIMPolarContinuousColorRamp interpolates through HSV rather than RGB, and
carries a `polarDirection`. Read literally, "Counterclockwise" from yellow
(hue 60 deg) to hue 50 deg means travelling 350 degrees the long way and
sweeping the whole rainbow through a two-colour segment. Nothing in the cost
ramp wants that - every polar segment in it is a short hop between neighbouring
warm tones - so hue takes the shorter arc, and the segment endpoints are exact
either way. If a ramp ever genuinely wants the long way round, this is the line
to revisit.

Raises OSError, ValueError or KeyError on anything it cannot read. Those are
the three lab._style catches, so a broken style file costs you the ArcGIS
colours and not the run.
"""

from __future__ import annotations

import colorsys
import json
from pathlib import Path
from typing import Optional

from skimap import config, paths

RGB = tuple[float, float, float]

# Samples per two-colour segment. The ramp is rebuilt as a piecewise-linear
# list of stops, so this only has to be fine enough that a curved (polar)
# segment does not show its corners - 32 is well past that at figure size.
SAMPLES = 32


def _path(path: Optional[Path] = None) -> Path:
    p = Path(path) if path else paths.COST_STYLE
    if not p.exists():
        raise OSError(f"No .lyrx at {p}")
    return p


def _load(path: Optional[Path] = None) -> dict:
    # utf-8-sig: ArcGIS Pro writes these with a BOM.
    return json.loads(_path(path).read_text(encoding="utf-8-sig"))


def _colorizer(doc: dict) -> dict:
    layers = doc.get("layerDefinitions") or []
    if not layers:
        raise KeyError("no layerDefinitions in the .lyrx")
    colorizer = layers[0].get("colorizer")
    if not colorizer:
        raise KeyError(f"{layers[0].get('type', 'layer')} has no colorizer")
    return colorizer


def _rgb(color: dict) -> RGB:
    """One CIM colour as RGB floats in 0..1. Alpha is dropped.

    Alpha is dropped on purpose: these ramps carry alpha 100 throughout, and
    the figures decide their own transparency - the surface is drawn under
    corridor bands and route lines that need to stay readable over it.
    """
    kind = color.get("type")
    v = color.get("values")
    if not v:
        raise KeyError(f"{kind or 'colour'} has no values")

    if kind == "CIMRGBColor":
        return tuple(float(c) / 255.0 for c in v[:3])
    if kind == "CIMHSVColor":
        return colorsys.hsv_to_rgb(float(v[0]) / 360.0, float(v[1]) / 100.0, float(v[2]) / 100.0)
    if kind == "CIMGrayColor":
        g = 1.0 - float(v[0]) / 100.0    # CIM grey is ink, not light: 100 is black
        return (g, g, g)
    if kind == "CIMCMYKColor":
        c, m, y, k = (float(x) / 100.0 for x in v[:4])
        return ((1 - c) * (1 - k), (1 - m) * (1 - k), (1 - y) * (1 - k))
    raise ValueError(f"Unsupported colour type {kind!r}")


def _segment(ramp: dict) -> list[RGB]:
    """SAMPLES colours along one two-colour ramp, in its own colour space."""
    start, end = _rgb(ramp["fromColor"]), _rgb(ramp["toColor"])
    n = SAMPLES

    if ramp.get("type") == "CIMPolarContinuousColorRamp":
        h0, s0, v0 = colorsys.rgb_to_hsv(*start)
        h1, s1, v1 = colorsys.rgb_to_hsv(*end)
        dh = (h1 - h0) % 1.0
        if dh > 0.5:                      # the short way round; see module docstring
            dh -= 1.0
        return [
            colorsys.hsv_to_rgb((h0 + dh * t) % 1.0, s0 + (s1 - s0) * t, v0 + (v1 - v0) * t)
            for t in (i / (n - 1) for i in range(n))
        ]

    return [
        tuple(start[c] + (end[c] - start[c]) * t for c in range(3))
        for t in (i / (n - 1) for i in range(n))
    ]


def _stops(ramp: dict) -> list[tuple[float, RGB]]:
    """(position 0..1, colour) along a ramp of any supported type."""
    kind = ramp.get("type")

    if kind == "CIMMultipartColorRamp":
        parts = ramp.get("colorRamps") or []
        if not parts:
            raise KeyError("CIMMultipartColorRamp with no colorRamps")
        weights = ramp.get("weights") or [1.0] * len(parts)
        total = float(sum(weights)) or 1.0

        out: list[tuple[float, RGB]] = []
        at = 0.0
        for part, weight in zip(parts, weights):
            share = float(weight) / total
            colours = _segment(part)
            last = len(colours) - 1
            out += [(at + share * i / last, c) for i, c in enumerate(colours)]
            at += share
        return out

    if kind in ("CIMLinearContinuousColorRamp", "CIMPolarContinuousColorRamp"):
        colours = _segment(ramp)
        last = len(colours) - 1
        return [(i / last, c) for i, c in enumerate(colours)]

    if kind == "CIMFixedColorRamp":
        colours = [_rgb(c) for c in ramp.get("colors") or []]
        if not colours:
            raise KeyError("CIMFixedColorRamp with no colors")
        last = max(len(colours) - 1, 1)
        return [(i / last, c) for i, c in enumerate(colours)]

    raise ValueError(f"Unsupported colour ramp {kind!r}")


def _stretch(colorizer: dict) -> tuple[float, float]:
    """The value range the ramp is stretched over.

    customStretchMin/Max when the file carries them - on the cost surface they
    are 1 and 100, which is MIN_COST to BASE_MAX_COST, so the ramp spends
    itself on terrain and everything above (a barrier, a cliff) sits on the
    black end. Falling back to those constants keeps that true for a style
    saved without them.
    """
    lo = colorizer.get("customStretchMin")
    hi = colorizer.get("customStretchMax")
    if lo is None or hi is None:
        lo, hi = config.MIN_COST, config.BASE_MAX_COST
    lo, hi = float(lo), float(hi)
    if hi <= lo:
        raise ValueError(f"stretch max {hi:g} is not above min {lo:g}")
    return lo, hi


def colormap(path: Optional[Path] = None):
    """(cmap, norm) for imshow, from the .lyrx at `path`.

    Masked cells come out fully transparent, so the figure's background shows
    through where the surface has no data.
    """
    from matplotlib.colors import LinearSegmentedColormap, Normalize

    p = _path(path)
    colorizer = _colorizer(_load(p))
    kind = colorizer.get("type")
    if kind != "CIMRasterStretchColorizer":
        raise ValueError(f"{p.name} uses {kind}, and only CIMRasterStretchColorizer is read")

    ramp = colorizer.get("colorRamp")
    if not ramp:
        raise KeyError(f"{p.name} has a stretch colorizer with no colorRamp")

    stops = _stops(ramp)
    # Floating error over eight weighted segments leaves the last stop a few
    # ulp off 1.0, which from_list rejects outright.
    stops = [(min(max(pos, 0.0), 1.0), c) for pos, c in stops]
    stops[0] = (0.0, stops[0][1])
    stops[-1] = (1.0, stops[-1][1])
    for i in range(1, len(stops)):
        if stops[i][0] < stops[i - 1][0]:
            stops[i] = (stops[i - 1][0], stops[i][1])

    cmap = LinearSegmentedColormap.from_list(p.stem, stops)
    cmap.set_bad((1, 1, 1, 0))

    lo, hi = _stretch(colorizer)
    return cmap, Normalize(vmin=lo, vmax=hi)


def describe(path: Optional[Path] = None) -> str:
    """One line naming what was read, for the figures stage to print."""
    p = _path(path)
    colorizer = _colorizer(_load(p))
    ramp = colorizer.get("colorRamp") or {}
    parts = len(ramp.get("colorRamps") or []) or 1
    lo, hi = _stretch(colorizer)
    gamma = colorizer.get("gammaValue")
    tail = f", gamma {gamma:g} ignored" if gamma not in (None, 1, 1.0) else ""
    return f"from {p.name}: {parts} ramp segment(s), stretch {lo:g}..{hi:g}{tail}"
