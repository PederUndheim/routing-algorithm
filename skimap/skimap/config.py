"""Every tunable parameter for the national ski-touring map.

Nothing else in the package hardcodes a threshold or a weight.

A profile can override anything here for one experiment - see the bottom of
the file and skimap.lab.
"""

import json
import os
from pathlib import Path

# --- Grid and raster geometry ---
CRS_EPSG = 25833
PIXEL_SIZE = 10.0        # m
TILE_SIZE = 20_000.0     # m -> 2000 x 2000 px per tile
NODATA = -9999.0

# Pixel-edge offset of the national rasters. DEM, PRA, runout and windshelter
# all share this lattice, so a resampled layer must too, or every per-tile
# read costs a resample instead of an exact crop.
RASTER_ORIGIN = (5.0, 5.0)

# Lattice offset for the tile grid: cells land on GRID_ORIGIN + k * TILE_SIZE.
# Derive a new value with grid.lattice_origin() if this ever needs to change.
GRID_ORIGIN = (4500.0, 19500.0)

# --- Cost scale ---
MIN_COST = 1.0
ROAD_TRAIL_COST = 2.0
BASE_MAX_COST = 100.0    # ceiling of the terrain surface, before barriers
MAX_COST = 5000.0        # ceiling of the final surface
BARRIER_COST = MAX_COST
COST_NODATA = 65535      # output is uint16

# --- National layers ---
# Sources you provide sit in data/national/<theme>/, computed layers in
# data/derived/ - paths.layer() resolves either. Built by
# skimap.data_preprocessing, in this order (later ones read earlier ones).
DERIVED_LAYERS = (
    "road",                      # <- roads vector
    "tractorroad_trail",         # <- tractor_trails vector
    "ocean", "river", "lake", "glacier",   # <- water vector
    "slope",                     # <- dem
    "pra_runout",                # <- pra + runout
    "tractorroad_trail_forest",  # <- tractorroad_trail + forest
    "bridge",                    # <- river + tractorroad_trail
)

# What the cost surface actually reads.
COST_LAYERS = (
    "slope", "windshelter", "pra_runout",           # terrain, weighted sum
    "road", "tractorroad_trail_forest", "bridge",   # reductions
    "forest", "tracks",                             # track influence
)

# Hard barriers, combined with MAX at BARRIER_COST. Ocean is not optional;
# flip one of the rest on to make it impassable too.
BARRIERS = {
    "ocean": True,
    "river": False,
    "lake": False,
    "glacier": False,
}

# Rasterized straight from national vector sources: layer -> (source, filter).
VECTOR_LAYERS = {
    "road": ("roads", "OBJTYPE = 'VegSenterlinje' AND VEGSTATUS = 'V'"),  # existing centrelines only, no ferries
    "tractorroad_trail": ("tractor_trails", None),
    "ocean": ("water", "objtype = 'Havflate'"),
    "river": ("water", "(objtype = 'Elv' AND vannbredde >= 2) OR objtype = 'Kanal'"),  # vannbredde is a class (1-5), not metres
    "lake": ("water", "objtype = 'Innsjø'"),
    "glacier": ("water", "objtype = 'SnøIsbre'"),
}

# --- Terrain cost ---
# Avalanche release area + runout distance -> one cost layer. PRA is on its
# own 1-99 percent scale (not 0-1); -128 is nodata.
PRA_RUNOUT = {
    "release_threshold": 15.0,   # pra >= this counts as a release area
    "release_in": (15.0, 99.0),
    "release_out": (7.2, BASE_MAX_COST),
    "runout_in": (0.0, 0.99),
    "runout_out": (1.0, 7.2),
    "runout_max_distance": 10_000.0,
    "weibull_lambda": 0.016,     # 1/m
    "weibull_alpha": 0.82,
}

# Threshold-jump curve: near-flat below 30 deg, a sharp step through it,
# then a linear climb.
SLOPE = {
    "threshold": 30.0,
    "low_max": 0.05,
    "low_power": 3.0,
    "jump_start": 29.0,
    "jump_end": 30.0,
    "jump_to": 0.35,
    "tail_end": 45.0,
    "min_cost": 2.0,
    "max_cost": BASE_MAX_COST,
}

# Curvature-like index: negative on ridges, positive in bowls. Its national
# distribution is tightly peaked, so this is close to a constant offset
# rather than a real discriminator - inherited from the thesis pipeline.
WINDSHELTER = {"x0": 0.0, "k": 5.5, "min_cost": 5.0, "max_cost": 30.0}

# Exposed ridges. windshelter below `threshold` is a wind-scoured crest and
# costs `extra` more, added to the terrain sum. The cut is taken from the
# windshelter tile directly, so no precomputed layer is needed; the same
# threshold is what data_preprocessing.ridges writes out to look at.
#
# windshelter is tightly peaked (sd ~0.067), so the useful range is a thin
# tail: -0.5 flags ~0.2% of a tile, -0.4 ~0.3%, -0.6 ~0.05%. Two thirds of
# those cells are already at the steep-slope barrier, so `extra` only bites
# on crests gentle enough to walk. Set `extra` to 0 to turn it off.
RIDGE_COST = {"threshold": -0.5, "extra": 10.0}

# Terrain layers, weighted and summed. Must total 1.0.
WEIGHTS = {
    "slope": 0.53,
    "windshelter": 0.12,
    "pra_runout": 0.35,
}

# Applied after road/trail reductions, so a road cannot reduce a cliff back
# to a walkable cost.
STEEP_SLOPE_BARRIER = {
    "start_deg": 45.0,
    "full_deg": 50.0,
    "start_value": 100.0,
    "barrier_value": 1500.0,
    "power": 3.0,
}

# Where road/trail/bridge reductions are allowed at all - a soft gate that
# fades out rather than switching off at a hard edge.
REDUCTION_GATE = {
    "slope_threshold": 30.0,
    "slope_width": 6.0,
    "pra_runout_threshold": 5.0,
    "pra_runout_width": 1.5,
}

# GPS track density reduces cost by up to `max_reduction` outside forest and
# `max_reduction_forest` inside it, scaled by `curve`:
#   "linear"      (density - lower) / (upper - lower), then ** power
#   "log"         same, on log density - counts are heavily skewed
#   "tile_bands"  per-tile percentile bands from `bands`; ignores power
# `bands` is [(percentile, weight)] ranked against each tile's own tracked
# cells, highest match wins. Below `min_positive_px` tracked cells, no
# reduction at all; passes below `min_density` are not a track.
#
# The forest split: in the open you can walk anywhere, so the line somebody
# else took is only weak evidence about the ground. Under trees that line is
# also the gap through them, which is worth more than the terrain says.
# Equal values mean no forest bonus, and that is what production is set to -
# the split exists so skimap.track_variants can try it without editing this
# file. Change these two only to move production itself.
TRACKS = {
    "max_reduction": 3.0,           # outside forest
    "max_reduction_forest": 3.0,    # inside it, read as forest > 0
    "power": 2.0,
    "curve": "tile_bands",
    "presence_floor": 0.0,
    "bands": [[50.0, 0.5], [80.0, 1.0]],
    "min_positive_px": 200,
    "min_density": 3.0,
}

# --- Routing ---
# Isotropic: two r.cost spreads, no elevation term. SLOPE and
# STEEP_SLOPE_BARRIER already price terrain difficulty.
ROUTING = {
    "smooth_threshold": 7.5,          # v.generalize Douglas-Peucker, metres
    "region_buffer_m": 5000.0,        # ceiling: buffer around start/end bbox
    "region_buffer_floor_m": 1500.0,  # floor: room to detour on short tours
    # A corridor whose live cells reach the edge of its own window was cut by
    # the box, not by the terrain - and the route inside it may not be the
    # best one, because r.cost never looked past the edge. Where that shows,
    # the tour is routed again in a window twice as wide, repeatedly, up to
    # this cap. Measured on 817 tours: 9 of them reach an edge, 8 of those
    # only had the corridor picture truncated, and 1 - a short tour whose
    # window sat well below the ceiling - had a route 3.4% dearer than the
    # one a wider window finds. Raising the floor for everyone would fix it
    # too, at roughly double the window area on every short tour; retrying
    # only where it shows costs the extra pass on about 1%.
    #
    # 0 disables the retry and restores the single-window behaviour.
    "region_buffer_retry_cap_m": 20000.0,
    "grass_memory_mb": 2500,
}

# Band of near-optimal ground around a route. `slack` bounds the budget as a
# share of the route's own cost, holding the corridor's shape on short tours;
# `max_gap` caps it outright, holding its extent on long ones. `gamma`
# sharpens the edge falloff.
CORRIDOR = {"slack": 0.2, "gamma": 4.0, "max_gap": 300.0}

# Band around a line the router did not make - drawn, uploaded or edited; see
# routing.line_corridor. Its own settings so the two kinds can be tuned apart;
# slack, gamma and max_gap start equal to CORRIDOR's so they read alike on the
# map.
#
# `min_length_m` floors the budget for short lines: one shorter than this gets
# the budget it would have at this length, through the same ground. The budget
# scales with the line's cost and so with its length, which in even terrain
# makes the band reach about slack/2 of the length to each side - a 1 km line
# had ~100 m, half of it faded below what the map draws. A floor in cost units
# instead would mean ten times the room on cheap ground as on dear ground.
#
# Not on CORRIDOR: a routed corridor grows from both ends, and extra budget on
# a short tour turns it into a disc instead of a wider band.
LINE_CORRIDOR = {"slack": 0.2, "gamma": 4.0, "max_gap": 300.0, "min_length_m": 2000.0}

# --- Exposure ---
# Avalanche exposure of a finished route, summed along the line. Separate
# from PRA_RUNOUT: that shapes the surface the router walks, this scores
# what it came back with.
EXPOSURE = {
    "sample_spacing_m": 10.0,       # one sample per cell of the 10 m rasters
    "weibull_lambda": 0.01639453,   # 1/m, fitted to the runout simulation
    "weibull_alpha": 0.8153966,
    # Share of accidents / of trip time spent on release vs. runout ground -
    # puts both on one scale, see exposure.accident_ratio().
    "accident_release": 0.75,
    "accident_runout": 0.25,
    "trip_release": 0.1794,
    "trip_runout": 0.8206,
}

# (lower bound, colour) - lower inclusive, upper exclusive, last unbounded.
# Originally the p50/p85/p97 of the national routed set (3.2/9.5/20.8).
# Replaced 2026-09-18 with the least-wrong split against round 1 of the
# corridor review - data/review/stats/exposure_thresholds.csv, produced by
# `python -m skimap.corridor_review stats` - which showed green/blue in
# particular pulling far too low: 89 reviewed tours scored under 3.2 but
# were still called blue. Re-derive the same way after a weight change or a
# national reroute; a score only compares within the surface that produced
# it.
EXPOSURE_CLASSES = (
    (0.0, "green"),
    (2.3, "blue"),
    (9.0, "red"),
    (20.4, "black"),
)

# Where an easier tour's line runs along a harder one, the harder corridor
# fades out so the shared ground draws once, in the easier colour - see
# skimap.overlap. Weight 0 closer than near_m, 1 beyond far_m; keep far_m
# under a typical corridor half-width or a gap opens where the lines split.
# A faded stretch must add up to min_shared_m, so a crossing is not sharing.
# Where bands still compete, a tour one class harder must be easier_priority
# times stronger to take a cell - raise it if harder bands eat the easier one.
# Only where the easier membership is at least priority_floor, or its faint
# fringe holds the harder band back and it starts along a hard edge.
OVERLAP = {
    "step_m": 5.0,
    "near_m": 30.0,
    "far_m": 100.0,
    "min_shared_m": 200.0,
    "easier_priority": 2.0,
    "priority_floor": 0.25,
    # Softening where colours meet, 0 = off. seam_m: width of the cross-fade
    # between two colours - 40 m tried best on Isfjorden. fade_in_m: the
    # harder tour comes in over this much route past a shared stretch; off,
    # because on Isfjorden it moved the hard edge rather than softening it,
    # and drew more of the harder tour's own ground in the easier colour.
    "fade_in_m": 0.0,
    "seam_m": 40.0,
}


# --- Crux Identifier ---
# Where along one Route the terrain asks for attention - see skimap.crux.
# Separate from PRA_RUNOUT and SLOPE: those price ground for the router,
# these decide what a ski tourer is told about the line it came back with.
CRUX = {
    # What a sample is. Slope decides; runout is the fallback.
    "steep_threshold": 30.0,     # degrees, at or above: Steep slope
    "runout_reach": 10_000.0,    # runout >= 0 and below this: Runout area
    "sample_spacing_m": 10.0,    # one sample per cell of the 10 m rasters

    # What a Steep slope area turns out to be. Neither makes a class of its
    # own: they mark the area's Crux and turn it red. PRA is a percentage,
    # 0 to 100 - the raster's own scale, not a 0-1 probability.
    "pra_threshold": 50.0,       # PRA % above this anywhere: probable release area
    "fall_threshold": 50.0,      # degrees, at or above anywhere: fall hazard

    # --- Merging runs into areas (see crux._areas) ---
    # One area is one segment, one colour and at most one Crux, so these
    # decide both what the line looks like and how many markers it carries.
    "min_runout_m": 20.0,        # a shorter Runout area reads as none
    "split_gap_m": 40.0,         # safe ground shorter than this is no break
    "steep_gap_m": 100.0,        # runout shorter than this between two steep
                                 # areas joins them into one
}


# --- Corridor segments ---
# Hand-divided corridors: EXPOSURE_CLASSES gives a whole route one colour,
# this gives one route several from geometry you draw. Colours are that
# tuple's names, or the digits 1..4 for its positions.
#
# A LINE cuts the corridor perpendicular to the route at each end, across
# its full width - cells are stationed by arc length, so only where the ends
# land matters and it can be drawn roughly. Overshooting a route end is free,
# stopping short is not (see end_snap_m).
#
# A POLYGON is a stencil, painted after the lines resolve: the corridor under
# it takes its colour exactly as drawn. Use it where a perpendicular cut goes
# wrong - side lobes, alternative lines, anywhere a short window in a wide
# corridor fans out. Measured on one AOI, a 50 m window claimed cells a
# median of 331 m away, six times its own length.
SEGMENTS = {
    "step_m": 5.0,             # route densification for stationing
    "end_snap_m": 200.0,       # an endpoint this close to a route end IS it
    "gap_heal_m": 300.0,       # lines this far apart meet at the midpoint
    # Where corridors overlap the more dangerous colour wins, but only from a
    # tour with a real claim - a membership at least this share of the best
    # any tour has there. At 0 one corridor's faintest fringe repaints
    # another's core, which renders as holes.
    "claim_fraction": 0.25,
    # The router excludes expensive patches mid-band, which is true but reads
    # as damage. Enclosed holes only, so filling never pushes a corridor
    # outward, and the cap keeps a genuinely impassable massif excluded.
    "fill_holes": True,
    "max_hole_cells": 6000,
    "default": "green",        # stretches no drawn feature covers
}

# --- Experiment profiles ---
# A JSON file whose "config" replaces names above, merged dict by dict - see
# skimap.lab. Applied here at import via an environment variable rather than
# at runtime: build_all's workers are spawned fresh on Windows and inherit
# the environment, not a runtime patch to this module.
#
# An unknown key is an error, not a no-op - a typo must not silently change
# nothing. A value derived from another constant (e.g. SLOPE["max_cost"]
# from BASE_MAX_COST) is fixed at import and will not re-derive from an
# override; set it directly if you change the base.
PROFILE = None


def _apply_profile() -> None:
    global PROFILE

    path = os.environ.get("SKIMAP_PROFILE")
    if not path:
        return

    PROFILE = Path(path).resolve()
    # utf-8-sig: profiles are hand-edited on Windows, where Notepad and
    # PowerShell's Out-File both write a BOM.
    overrides = json.loads(PROFILE.read_text(encoding="utf-8-sig")).get("config", {})
    if not overrides:
        return

    applied = []
    for key, value in overrides.items():
        if key not in globals() or key.startswith("_"):
            raise KeyError(
                f"{PROFILE.name} overrides {key!r}, which is not a parameter in "
                f"config.py. Check the spelling - it is upper case."
            )
        current = globals()[key]
        if isinstance(current, dict):
            if not isinstance(value, dict):
                raise TypeError(f"{key} is a dict; the profile gives {type(value).__name__}")
            unknown = set(value) - set(current)
            if unknown:
                raise KeyError(f"{key} has no key(s) {sorted(unknown)}; known: {sorted(current)}")
            globals()[key] = {**current, **value}
            applied += [f"{key}[{k!r}] {current[k]!r} -> {v!r}" for k, v in value.items()]
        else:
            applied.append(f"{key} {current!r} -> {value!r}")
            globals()[key] = value

    # Only the parent prints - every spawned worker applies the same
    # overlay silently, and eight identical lines per build is noise.
    import multiprocessing

    if multiprocessing.current_process().name == "MainProcess":
        print(f"profile {PROFILE.stem}: " + "; ".join(applied))


_apply_profile()
