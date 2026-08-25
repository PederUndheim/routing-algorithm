"""Every tunable parameter for the national ski-touring map.

Nothing else in the package hardcodes a threshold or a weight.
"""

# --- Grid and raster geometry ---
CRS_EPSG = 25833
PIXEL_SIZE = 10.0        # m
TILE_SIZE = 20_000.0     # m -> 2000 x 2000 px per tile
NODATA = -9999.0

# Pixel-edge offset of the national rasters within one PIXEL_SIZE step.
# The DEM, PRA, runout and windshelter all sit on this lattice, so anything
# resampled must be put on it too - otherwise every per-tile read costs a
# half-pixel resample instead of being an exact crop. Tile templates snap
# here, which is why they sit 5 m off the tile polygons; that offset is
# internal and never leaves the raster pipeline.
RASTER_ORIGIN = (5.0, 5.0)

# Lattice offset within one TILE_SIZE step. Cells land on
# GRID_ORIGIN + k * TILE_SIZE, which puts them on the same lattice as the
# earlier 20 km grid rather than on round coordinates. Derive it from
# another grid with grid.lattice_origin() if that ever needs to change.
GRID_ORIGIN = (4500.0, 19500.0)

# --- Cost scale ---
MIN_COST = 1.0
ROAD_TRAIL_COST = 2.0
BASE_MAX_COST = 100.0    # ceiling of the terrain surface, before barriers
MAX_COST = 5000.0        # ceiling of the final surface
BARRIER_COST = MAX_COST
COST_NODATA = 65535      # output is uint16

# --- National layers ---
# Everything is national and on one grid: sources you provide sit in
# data/national/<theme>/, computed layers in data/derived/. paths.layer()
# resolves a name to whichever it is, so nothing downstream cares.
#
# These are built by skimap.data_preprocessing, in this order - later ones
# read earlier ones.
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

# Hard barriers, combined with MAX at BARRIER_COST. Ocean is not optional.
# The rest are built and ready; flip one on to make it impassable.
BARRIERS = {
    "ocean": True,
    "river": False,
    "lake": False,
    "glacier": False,
}

# Rasterized straight from the national vector files: layer -> (source, filter).
VECTOR_LAYERS = {
    # NVDB carries ferry routes (Bilferjestrekning) and duplicates each road
    # as Kjorebane/Kjorefelt on top of VegSenterlinje. Taking only existing
    # centrelines avoids burning a cheap corridor straight across a fjord.
    "road": ("roads", "OBJTYPE = 'VegSenterlinje' AND VEGSTATUS = 'V'"),
    "tractorroad_trail": ("tractor_trails", None),
    "ocean": ("water", "objtype = 'Havflate'"),
    # vannbredde is an FKB width CLASS (1..5), not metres - do not "fix" it
    # to a metre threshold. >= 2 drops only the narrowest class, which is
    # almost nothing here because narrow streams are mapped as lines rather
    # than polygons and never reach this layer.
    # https://register.geonorge.no/sosi-kodelister/fkb/vann/5.0/vannbredde
    # Kanal is a channelled watercourse - same barrier behaviour as a river,
    # and it has no vannbredde, so it is taken whole.
    "river": ("water", "(objtype = 'Elv' AND vannbredde >= 2) OR objtype = 'Kanal'"),
    "lake": ("water", "objtype = 'Innsjø'"),
    "glacier": ("water", "objtype = 'SnøIsbre'"),
}

# --- Avalanche: release area + runout distance -> one cost layer ---
# Release areas take the upper part of the range, runout the lower.
#
# NOTE the release thresholds are on PRA's OWN scale. The national PRA is
# integer percent, 1..99, with -128 as nodata - NOT the 0..1 fraction the
# thesis pipeline used. At a 0.15 threshold every mapped pixel would count
# as a release area and the whole country would sit at maximum avalanche
# cost, silently.
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

# --- Terrain transforms ---
# Slope uses a threshold-jump curve: near-flat cost below 30 deg, a sharp
# step through it, then a linear climb. The thesis also carried logistic /
# richards / hyperbolic variants; only this one was ever configured.
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

# Windshelter is a curvature-like index, negative on ridges and positive in
# bowls - confirmed against topographic position, correlation -0.52 over a
# national sample, so the curve rising with shelter is the right way round.
#
# Its documented range is (-1, 1) and the extremes do reach about +/-1.2,
# but the distribution is tightly peaked: p25 = -0.019, p50 = -0.003,
# p75 = +0.010. At k = 5.5 the middle half of the country therefore spans
# just 1.0 of the 25-unit cost band, and after the 0.12 weight it moves the
# final cost by 0.12 - windshelter is very nearly a constant offset rather
# than a discriminator.
#
# This is INHERITED, not introduced here: the per-area rasters the thesis
# pipeline used have the same distribution to within a few percent, so the
# national surface reproduces the model that was evaluated. Raising k to
# ~40 would spread p5..p95 over 6..28 instead of 15..20; that is a change
# to the model, not a bug fix, and it would break comparability with the
# earlier evaluation. Left alone deliberately.
WINDSHELTER = {"x0": 0.0, "k": 5.5, "min_cost": 5.0, "max_cost": 30.0}

WEIGHTS = {
    "slope": 0.53,
    "windshelter": 0.12,
    "pra_runout": 0.35,
}

# Very steep terrain, applied after road/trail reductions so a road cannot
# reduce a cliff back down to a walkable cost.
STEEP_SLOPE_BARRIER = {
    "start_deg": 45.0,
    "full_deg": 50.0,
    "start_value": 100.0,
    "barrier_value": 1500.0,
    "power": 3.0,
}

# Where road/trail/bridge cost reductions are allowed at all. A soft gate,
# so the reduction fades out rather than switching off at a hard edge.
REDUCTION_GATE = {
    "slope_threshold": 30.0,
    "slope_width": 6.0,
    "pra_runout_threshold": 5.0,
    "pra_runout_width": 1.5,
}

# --- GPS track density ---
# Tracks reduce cost by a fixed number of cost units, more inside forest.
TRACKS = {
    "max_reduction_outside": 2.0,
    "max_reduction_forest": 4.0,
    "power": 2.0,
}

# --- Display ---
# Class breaks for looking at the finished surface, as (lower bound, colour).
# Lower inclusive, upper exclusive, the last running to MAX_COST.
#
# Cost is nowhere near linear: about 60% of mapped ground sits between 1 and
# 5, and the sea sits at 5000. Any even stretch - min/max, percent clip, two
# standard deviations - therefore renders the whole country as one flat
# colour with a bright coastline. These breaks are roughly logarithmic, and
# they change colour family at 35, where terrain stops being walkable.
DISPLAY_BREAKS = (
    (1, "#08306b"), (3, "#2171b5"), (5, "#4292c6"), (8, "#6baed6"),
    (12, "#9ecae1"), (20, "#c6dbef"), (35, "#fee391"), (60, "#fec44f"),
    (100, "#ec7014"), (300, "#cc4c02"), (1500, "#8c2d04"),
)

# --- Study areas ---
# The master thesis study areas, each exactly one tile. They are 20 km
# squares sitting on the same lattice as the grid, which is why GRID_ORIGIN
# is (4500, 19500) and not a round number - the fishnet was built to line up
# with these, so an area is a tile rather than a window across four of them.
#
# Used to give debug output a name you can find: data/debug/jotunheimen_02/
# rather than data/tiles/tile_144500_6839500/debug/.
STUDY_AREAS = {
    "hemsedal_01":       "tile_124500_6759500",
    "hemsedal_02":       "tile_144500_6759500",
    "isfjorden_01":      "tile_124500_6959500",
    "jotunheimen_01":    "tile_124500_6839500",
    "jotunheimen_02":    "tile_144500_6839500",
    "jotunheimen_03":    "tile_124500_6819500",
    "jotunheimen_04":    "tile_144500_6819500",
    "kattfjordeidet_01": "tile_624500_7719500",
    "sogndal_01":        "tile_64500_6819500",
    "svolvaer_01":       "tile_464500_7559500",
}

# Normalization is computed ONCE nationally and cached. Per-tile scaling
# would map the same track density to different reductions on either side
# of a tile edge, and the mosaic would show a grid of seams.
TRACK_NORMALIZATION = {
    "lower_percentile": 60.0,   # positive pixels below this get no reduction
    "upper_percentile": 95.0,   # at/above this gets the full reduction
}

# --- Routing ---
# r.walk weighs walking time against the cost surface as friction; lambda is
# how much the friction counts. Everything here matches the parameters the
# thesis routed with, so national routes stay comparable to those.
ROUTING = {
    "lambda": 0.6,
    "smooth_threshold": 7.5,          # v.generalize Douglas-Peucker, metres
    "region_buffer_m": 5000.0,        # ceiling: buffer around the start/end bbox
    "region_buffer_floor_m": 1500.0,  # floor: even a short tour gets room to detour
    "grass_memory_mb": 2500,
}

# Corridors: the band of near-optimal ground around a route. `slack` is how
# much worse than the optimal cost still counts as being in the corridor;
# `gamma` sharpens the falloff, so a high gamma keeps the corridor tight
# around the line and a low one lets it spread.
CORRIDOR_MODES = {
    "conservative": {"slack": 0.1, "gamma": 6.0},
    "balanced":     {"slack": 0.2, "gamma": 4.0},
    "explorative":  {"slack": 0.3, "gamma": 1.5},
}

# Written unless --mode asks for others. One corridor per route keeps the
# folder a flat list of tours rather than the same tours three times over.
DEFAULT_CORRIDOR_MODE = "balanced"

# --- Exposure ---
# Avalanche exposure of a finished route, summed along the line.
#
# Kept as its own block rather than folded into PRA_RUNOUT above: that one
# shapes the cost surface the router walks, this one scores what the router
# came back with. Both read the same two national rasters and both fit the
# same runout curve, but retuning the surface must not silently move the
# scores a route was classified on, so the constants are separate on purpose.
EXPOSURE = {
    "sample_spacing_m": 10.0,       # one sample per cell of the 10 m rasters

    # Weibull decay of exposure with distance from a release area, fitted to
    # the national runout simulation. The same curve as PRA_RUNOUT's, at the
    # precision it was fitted to rather than rounded for the cost scale.
    "weibull_lambda": 0.01639453,   # 1/m
    "weibull_alpha": 0.8153966,

    # Share of recorded accidents attributed to release areas and to runout
    # ground, over the share of trip time spent in each. Their ratio is what
    # puts a unit of runout exposure on the same scale as a unit of release
    # exposure - see exposure.accident_ratio().
    "accident_release": 0.75,
    "accident_runout": 0.25,
    "trip_release": 0.1794,
    "trip_runout": 0.8206,
}

# Exposure classes, as (lower bound, colour). Lower inclusive, upper
# exclusive, the last unbounded.
#
# The score is a dose summed along the route, not a rate, so these breaks
# are absolute: a long route through avalanche terrain is more exposure than
# a short one through the same terrain, and is meant to classify higher.
#
# Set from the p50 / p85 / p97 of the national routed set, which puts the
# classes at roughly 50 / 35 / 12 / 3 percent - the shape of the ski-slope
# scale the colours borrow, where most runs are green and black is rare.
#
# NOT the 5 / 40 / 100 of the published ExpScore work. Those were calibrated
# on recorded GPS tracks, which cross avalanche terrain because that is where
# people chose to ski. These routes are least-cost paths through a surface
# that weights pra_runout at 0.35, so they avoid start zones by construction
# and score far lower: on the same 788 routes the published breaks leave 67%
# green, 33% blue, one red and no black at all. Re-derive these if the cost
# surface weights change, and note that a score is only comparable to another
# score from the same surface.
EXPOSURE_CLASSES = (
    (0.0, "green"),
    (3.2, "blue"),
    (9.5, "red"),
    (20.8, "black"),
)
