# skimap

A ski-touring cost surface for all of Norway, and least-cost routes through
it. Self-contained: nothing here imports from anywhere else in the repo.

Run everything from **this directory** - `skimap/`, the one holding `skimap/`
and `data/` - with the QGIS-bundled Python:

```powershell
Set-Location "c:\Users\pund\Desktop\routing_algorithm_repo\skimap"
& "C:\Program Files\QGIS 4.2.0\bin\python-qgis.bat" -m skimap.cli <stage>
```

Not the repository root: the package is `skimap/skimap/`, so from one level
up `skimap.cli` resolves to the project directory and is not found. There is
no `PYTHONPATH` workaround worth using here - `python-qgis.bat` calls
`o4w_env.bat`, which discards whatever `PYTHONPATH` you set.

```
skimap/            <- cd here
  skimap/          the package: config, cli, cost_surface/, data_preprocessing/
  data/            everything on disk, see below
  app/             a local browser front end: routes, uploads, cruxes
  tests/           unittest suite for skimap.crux, on synthetic rasters
  README.md
  requirements.txt
```

There is nothing to install - see `requirements.txt`. Add `-h` to any stage
for its flags.

`app/` is a test app, not part of the pipeline: click two points on a map and
see the line between them, or upload a GPX/GeoJSON of your own, and ask the
Crux Identifier (`skimap.crux`) where along a route the avalanche and fall
hazards begin. It reads the same surface through the same
`routing.route_one`, takes no parameters and writes nothing you keep. See
[app/README.md](app/README.md).

`tests/` holds the one automated suite, for `skimap.crux`. It needs none of
the national data - each test writes its own tiny rasters:

```powershell
& "C:\Program Files\QGIS 4.2.0\bin\python-qgis.bat" -m unittest discover -s tests -t . -v
```

## Corridor review

cd C:\Users\pund\Desktop\routing_algorithm_repo\skimap
& "C:\Program Files\QGIS 4.2.0\bin\python-qgis.bat" -m skimap.corridor_review serve


## Pipeline

```bash
# Once, from the raw dumps. The grid comes first: every derived layer is
# built on its extent. `derived` takes hours and about 21 GB.
python -m skimap.cli grid --boundary data/input/national/boundary/kommuner.geojson
python -m skimap.data_preprocessing.cli derived
python -m skimap.cli tracks

# The surface. Ten minutes at --jobs 8, 1.1 GB of tiles plus a 1.65 GB COG.
python -m skimap.cli cost --jobs 8
python -m skimap.cli mosaic --cog
python -m skimap.cli alignment          # always, after rebuilding

# Routes.
python -m skimap.cli tours init         # or: tours import-json --json <file>
python -m skimap.cli tours check
python -m skimap.cli route
python -m skimap.cli exposure       # score the routes, split corridors by class
```

`cost` and `route` are both resumable - work that already has an output is
skipped, so an interrupted run picks up where it stopped, and `--force`
rebuilds anyway. A failure is reported and the run continues; the exit status
is non-zero if anything failed.

`route` also prunes: a route whose tour has been deleted, moved or renamed is
dropped, with its corridor, before anything is routed. Editing tours.gpkg and
re-running is therefore enough to bring the outputs back in step - see
[Editing tours](#editing-tours).

## Layout

```
config.py             every weight, threshold and tunable
paths.py              where things live on disk
grid.py               the 20 km tile grid
raster.py             tile windows in and out of the national layers
data_preprocessing/   raw dumps -> national layers (run once)
cost/                 national layers -> per-tile cost surface
mosaic.py             tiles -> one national raster
tours.py              start/end pairs to route
routing.py            tours -> routes and corridors
exposure.py           routes -> avalanche exposure score and colour classes
alignment.py          the georeferencing checks
```

Everything is national and on one pixel grid, so a tile is a plain window
read - no warping and no per-tile intermediates.

## Cost surface

Weighted sum of slope, windshelter and avalanche exposure; ocean and very
steep slopes MAXed in as barriers; roads, forest trails and bridges MINed in
as reductions, gated so they only apply where the terrain is walkable anyway;
the barriers MAXed back in so no reduction can undo a cliff or the sea; GPS
track density subtracted last. Parameters in `config.py`.

The barriers really do have to go back in. The reduction gate opens on gentle,
low-avalanche ground, and open water is exactly that, so without the second
pass every coastal road pixel that `all_touched` bleeds into a Havflate
polygon becomes a cost-2 hole in the middle of a fjord. Tracks are left able
to dent a barrier by their few units, because a cliff at 1497 routes the same
as one at 1500.

### Looking at it

ArcGIS does not read a GDAL VRT, so `mosaic --cog` is not optional there - it
writes `data/cost_surface/cost_surface.tif`, a COG with nine overview levels down to
5 km per pixel. Open that, not the .vrt. QGIS reads either.

Overviews are NEAREST rather than the COG driver's default CUBIC: most of the
country sits at 4 and the sea at 5000, so an averaged overview pixel is a
value that exists nowhere in the data and draws as a passable shore.

Default symbology shows nothing - about 60% of mapped ground is between 1 and
5, so any even stretch flattens the country to one colour. Classify manually
manually - the pipeline writes no colour file, symbology is yours to set.

### Debugging a tile

```bash
python -m skimap.cli cost --tile tile_144500_6839500 --debug
```

Writes the nine layers in `cost.surface.DEBUG_LAYERS` to `data/debug/<tile_id>/`,
numbered in build order: the three basis costs, their weighted sum, the
barriers, the reduction gate, the surface after reductions, the cost units the
tracks took off, and the result. Layers 01-08 are Float32 in the same units as
the output; 09 is the uint16 surface, so one folder holds both the answer and
its working. The identity is exact: `09 = round(clip(max(07, 05) - 08))`.

About 62 MB per tile - name what you want, do not run it over the grid.

## Exposed ridges

```bash
python -m skimap.data_preprocessing.cli ridges --list
python -m skimap.data_preprocessing.cli ridges --area 04_isfjorden
python -m skimap.data_preprocessing.cli ridges --area 03_voss --threshold -0.2 -0.3 -0.4
python -m skimap.data_preprocessing.cli ridges --bbox 99446 6946619 101567 6949740 --label lyngen
python -m skimap.data_preprocessing.cli ridges --national
```

Run these **from `skimap/`**, the project directory - the package is at
`skimap/skimap/`.

windshelter is negative on convex ground and positive in bowls, so the
cheapest ridge detector there is is a cut across it: at or below
`config.RIDGE["threshold"]` is an exposed ridge, above it is not. That is the
whole method, and its output is **`exposed_ridge.tif`**, 0/1.

### What this replaced

This was a GRASS `r.geomorphon` build: eight lines of sight per cell out to a
search radius, looked up in a table of idealized landforms, plus an
`arete.tif` pass measuring cross-ridge steepness in degrees, plus the halo
both needed. It asked the better question - "is the ground 150 m that way
lower than me" is what a ridge answers to, and one cell of windshelter cannot
ask it.

What the threshold buys is everything else: no GRASS, so `prep ridges` runs
anywhere `prep derived` does; no halo, because a per-cell cut needs no
neighbours, and therefore no tiling, no worker pool and no mosaic. The
national build is one streamed pass instead of 1334 tiles and ~31 hours. And
the parameter moves in seconds.

The old outputs are kept under `data/ridges/areas/<area>/geomorphon_previous/`
where they exist, because they are no longer reproducible and they are the
natural thing to check a cut against.

### Choosing the threshold

windshelter is very tightly peaked - mean ~0, sd ~0.067, 91% of cells within
+/-0.1 - so a threshold sits far out in a thin tail and small moves change the
answer a lot. An area build writes one mask per candidate into `candidates/`
and records the coverage in `thresholds.json`, so the comparison is a folder
of layers you flip through rather than a re-run.

Measured against the geomorphon `exposed_ridge` it replaced, on the two areas
that still have one. *Recall* is how much of the old answer a cut finds,
*precision* how much of the cut the old answer agrees with:

| threshold | Isfjorden area% | recall | precision | Romsdalen area% | recall | precision |
|---|---|---|---|---|---|---|
| -0.15 | 3.03% | 93% | 2% | 7.02% | 89% | 3% |
| -0.20 | 1.72% | 91% | 3% | 4.71% | 88% | 4% |
| -0.30 | 0.66% | 85% | 8% | 2.14% | 81% | 7% |
| -0.40 | 0.26% | 76% | 19% | 0.89% | 72% | 16% |
| -0.50 | 0.11% | 63% | 37% | 0.32% | 56% | 35% |
| -0.60 | 0.05% | 45% | 65% | 0.12% | 35% | 55% |

Read it as: windshelter is reliably low on the crests geomorphon found - a
loose cut catches ~90% of them - but it is low on a great deal of other
convex ground too, so a loose cut flags fifty times more area than geomorphon
did. Best overlap is around **-0.5 to -0.6**, where coverage lands in the same
order as geomorphon's own 0.055% / 0.195%. That is what `threshold` is set to;
loosen it if you want the broader "convex and windblown" reading rather than
crests specifically.

### Areas before the country

The unit of work is an area, because the threshold is not one you can pick off
a table. A named area, a tile id, or a bounding box, written to
`data/ridges/areas/<label>/` - `exposed_ridge.tif` at the committed cut,
`candidates/` for the rest, `thresholds.json` for the coverage, and
`windshelter.tif` cut to the same extent so the values behind a mask are one
layer away instead of somewhere in a 16 GB national file.

Name your own areas in `data/ridges/areas.json` - `{"lyngen": {"tile": "..."}}`
or `{"lyngen": {"bbox": [...]}}` - and that file replaces the built-in set.

There is no halo and no per-tile national build, because a per-cell cut is a
function of one cell. An extent is read as given, and a cut-out agrees with
the national layer by construction rather than by check.


## Alignment

```bash
python -m skimap.cli alignment
```

The surface is written on the RASTER lattice, not the tile lattice. Those are
half a pixel apart: `window()` floors onto the raster lattice, so the cells a
tile covers start 5 m outside its polygon, and `raster.tile_origin()` is where
the output has to be georeferenced. Writing it at the polygon corner instead
moves every value 5 m east and 5 m south.

That bug shipped once, and it is worth knowing why nothing caught it: the
arrays are unaffected, so statistics, histograms, invariants and even
tile-to-tile seams all pass. It only shows when the surface is laid against
something else - a barrier beside its own coastline, or a resampled layer
landing half a pixel off. So every check here works through COORDINATES;
comparing arrays index for index agrees perfectly even when the
georeferencing is wrong, which is exactly how it survived.

Five checks: `tile_origin()` against the cells `window()` reads for every
layer; everything on one lattice; tiles abutting exactly; the published COG
newer than its tiles; and the measured offset against the ocean mask, which
should be zero.

`routing.py` used to run a lattice check of its own before every batch,
because `r.walk` read the surface and the DEM as one grid and half a pixel
between them silently paired each elevation with a neighbouring cell's
friction. Routing is isotropic now and never opens the DEM, so that check is
gone with it - anything that brings elevation back into the router has to
bring the check back too.

## Tours

A tour is **one two-vertex line plus a name** - that is the whole schema. The
pairing is the geometry, so there are no ids to keep in step and no way to
orphan half a pair. Extra vertices are ignored: only the first and last are
used. Extra attribute fields are ignored too, so adding one in ArcGIS later
breaks nothing.

```bash
python -m skimap.cli tours init                    # empty layer to draw into
python -m skimap.cli tours import-json --json <f>  # older {area: [...]} format
python -m skimap.cli tours check                   # validate before routing
```

`check` reports anything that will not route - endpoints off the map,
endpoints on a barrier (with the distance to the nearest walkable cell), and
pairs too close together - before a batch spends hours finding out.

Any OGR-readable source works, so a File Geodatabase is fine:
`--path <x.gdb> --layer <name>`.

### Digitizing in ArcGIS Pro

1. **Set the map coordinate system to ETRS89 / UTM 33N (EPSG:25833)** first.
   It is what the cost surface is on, so nothing reprojects and no rounding
   creeps into which 10 m pixel a trailhead lands in.
2. Add `data/tours/tours.gpkg`, with `data/cost_surface/cost_surface.tif` beneath it
   symbolized so you can see what is walkable.
3. Add `data/input/national/roads/roads.gpkg` and snap to it. Trailheads belong on a
   road; a start one pixel into a cliff is a barrier with no route out of it.
4. Edit > Create > `tours` > Line. Click the start, double-click the summit.
   The tool stays active, so routes chain without re-selecting it.
5. **Draw everything first, name it afterwards** in the attribute table. One
   pass of mouse then one of keyboard beats alternating per feature.

## Routing

```bash
python -m skimap.cli route                     # every tour
python -m skimap.cli route --fid 12 --fid 13   # just these
```

Three GRASS steps per route: `r.cost` from both ends, `r.path` to extract
the line, `v.generalize` to smooth it. Parameters in `config.ROUTING` and
`config.CORRIDOR`.

Two spreads, not three, because the start-side `r.cost` also writes the
direction raster `r.path` walks - so it serves the line and the corridor's
`start->x` half at once. `start->x` plus `end->x` is the cost of the best
route through a cell, and that is only a meaningful total because both halves
are measured the same way.

Routing used to draw the line with `r.walk`, which is anisotropic - the right
model for ski touring in principle, since uphill and downhill are not the same
journey. Measured over 808 tours routed both ways, it was not worth its keep:
the cost surface already prices steepness, so 45% of the lines land within
50 m of each other everywhere, 84% within 250 m, and the median worst
separation is 60 m. Dropping it took the DEM out of routing altogether and
made a route about 41% cheaper.

The one thing `r.walk` contributed that nothing here replaces is a penalty on
**re-ascent** - no cost layer knows you have already climbed something. That
shows on long tours in complex terrain: 22 of the 808 diverge by more than a
kilometre, with a median length of 7.0 km against 4.0 km overall. Worth
knowing when reading a long route.

One GRASS session serves the whole batch, `r.external` links the 1.65 GB
surface without copying it, and the region is set per route to the pair's
bounding box plus a buffer scaled to the tour's own length - floored at
`region_buffer_floor_m` and capped at `region_buffer_m` in `config.ROUTING`,
so a short tour isn't padded out to the same window as a long one. About 12 s
per route.

### Output

```
data/routing_output/
  routes.gpkg                              all routes, one line each
  corridors_all.tif                        every corridor merged
  corridors/001_kyrkjetaket.tif            one per route
```

`routes.gpkg` carries `tour_fid` (back to the tour), `name`, `length_m`,
`straight_m`, `detour` and `cost_opt`. One layer to open, style and query,
rather than a file per route. Corridors are flat and named
`<fid>_<slug>.tif`, which is what `exposure` reads them back by.

### Corridor width

The corridor is every cell within `max_gap` of the optimal cost, where a
cell's gap is `(cost start->cell) + (cost cell->end) - cost_opt` - how much
worse the whole trip gets if you route through it.

```python
max_gap = min(slack * cost_opt, CORRIDOR["max_gap"])
```

Both terms are load-bearing and they do opposite jobs:

- `slack * cost_opt` keeps the budget under the trip's own cost, preserving
  the corridor's **shape**. Let the budget approach `cost_opt` and the
  start/end cost sum degenerates into distance-from-the-midpoint, which is a
  disc rather than a band. This governs short tours.
- `max_gap` stops the budget running away, preserving the corridor's
  **extent**. This governs long or expensive ones.

Without the ceiling the budget tracked total cost, which rises both with
length and with difficulty, so the longest and the most avalanche-exposed
tours got the widest corridors - a 4 km black tour was handed enough budget
to wander 7 km off its own line. A *floor* was tried and rejected: on a
0.35 km tour it exceeds the whole trip cost and the corridor collapses to a
disc.

Units: `r.cost` accumulates the surface value once per 10 m cell, and the
median cell along a route costs about 2, so `max_gap` 300 buys roughly
1500 m of extra travel over easy ground - about 750 m of sideways room.

Two things about the result. The line runs **summit to trailhead**, because
r.path walks the direction raster back from the end - the endpoints are exact
either way. And a route that reaches the edge of its window was clipped by
the window rather than by terrain; `--buffer` raises the ceiling that window
is scaled against.

### Editing tours

Edit `tours.gpkg` and re-run `route`. Before routing anything it drops every
route that no longer matches the tour file, and the corridor with it:

| what you did to a tour | what happens |
| --- | --- |
| deleted it | route and corridor removed |
| moved an endpoint | route and corridor removed, then re-routed |
| renamed it | route and corridor removed, then re-routed |
| added one | routed |
| left it alone | skipped, as before |

Deletion is the case that matters most, because it is the one that corrupts
output rather than merely going out of date: `merge_corridors` globs the
corridor directory, so an orphaned corridor keeps being folded into
`corridors_all.tif` and into the exposure classes long after its tour is gone.

Moves are detected by comparing the route's stored `straight_m` against the
tour's current straight-line distance, so an endpoint nudged by one pixel is
caught but a re-save that changes nothing is not.

**Pruning is off automatically with `--fid`**, and must stay that way: that
flag hands the batch a subset of the tour file, and to pruning every tour left
out of the subset is indistinguishable from a deleted one - it would take
`routes.gpkg` down to the routes being redone. `--no-prune` turns it off for a
full run too.

Re-run `exposure` afterwards to rebuild the class rasters from the corrected
set.

## Exposure

```bash
python -m skimap.cli exposure                  # score routes, split corridors
```

Its own stage, after `route`: routing is the hours and scoring is the
seconds, so retuning a weight or a class break must not mean re-walking the
cost surface.

The score is NVE's ExpScore. Each line is walked at 10 m and every sample
adds a release term (`pra/100`, rescaled into `[rr, 1]`) and a runout term
(`exp(-(lambda*d)^alpha)`, `d` = metres to the nearest release area), both
summed along the line with the runout total scaled by `rr`. That `rr` -
accidents attributed to each kind of ground over time spent in it, about
0.073 - is what puts the two on one scale.

The score is a **dose, not a rate**: twice the distance through the same
terrain is twice the score. `config.EXPOSURE_CLASSES` is therefore in
absolute score, and `exp_per_km` is written beside it so the length term
stays visible.

```
data/colored_corridors/
  corridors_green.tif                merged corridors of the green routes
  corridors_blue.tif
  corridors_red.tif
  corridors_black.tif
```

`routes.gpkg` gains `exp_release`, `exp_runout`, `exp_score`, `exp_per_km`
and `colour`.

Four files, and nothing else: the per-route corridors and
`corridors_all.tif` stay in `data/routing_output/`, where `route` wrote
them. The trade is that this directory does **not** stand alone - these
rasters describe the routes that existed when `exposure` last ran, so
re-running `route` leaves them stale. Re-run `exposure` after `route`.

### Class breaks

`config.EXPOSURE_CLASSES` is set from the **p50 / p85 / p97 of the national
routed set** - 3.2 / 9.5 / 20.8 - which lands the classes at roughly

| colour | share |
| --- | --- |
| green | 50% |
| blue | 35% |
| red | 12% |
| black | 3% |

That is the shape of the ski-slope scale the colours borrow: most runs green,
black rare.

These are deliberately **not** the 5 / 40 / 100 of the published ExpScore
work. Those were calibrated on recorded GPS tracks, which cross avalanche
terrain because that is where people chose to ski; these routes are least-cost
paths that avoid start zones by construction. On the same 788 routes the
published breaks give 67% green, 33% blue, one red and no black - two of the
four classes empty.

So a score is only comparable to another score from the same cost surface.
Change the weights and the breaks need re-deriving, which is a percentile of
the new distribution rather than a judgement.

## Tuning

Changing a weight and looking at the result nationally is not a loop anyone
can think in: 1334 tiles, a 1.65 GB COG and 842 routes is most of a day.
`skimap.lab` runs the same pipeline over a handful of tours you picked, on
only the tiles those tours can reach, and renders one PNG per tour with the
current route drawn beside the new one.

```bash
python -m skimap.lab init steeper --fid 42 --fid 562 --fid 716
# put the change in the profile's "config", then
python -m skimap.lab run steeper --jobs 8
```

Twelve tours in three clusters reach thirteen tiles - one percent of the
country - so the surface rebuilds in under a minute. `run` is
`surface -> route -> compare -> figures`, and each is its own stage, so
re-rendering figures does not re-route and re-routing does not rebuild.

Everything lands in `data/test/lab/<name>/`, and nothing there touches
`data/cost_surface` or `data/routing_output`.

### Profiles

A profile is a JSON file naming the tours and the parameters:

```json
{
  "name": "steeper",
  "note": "does a 32 deg slope threshold pull routes off the ridges?",
  "tours": [42, 562, 716],
  "config": {"SLOPE": {"threshold": 32.0}}
}
```

`config` replaces names in `config.py`, dicts merging key by key, so
`{"WEIGHTS": {"slope": 0.6}}` leaves windshelter and pra_runout alone. An
unknown name is an error rather than a no-op: a profile is written once and
its output is looked at for an hour, and a typo'd `WEIGTHS` that silently
changes nothing is the one failure this must not have.

It is applied **inside `config.py`, at import, from the `SKIMAP_PROFILE`
environment variable**, and that is not a stylistic choice. `build_all` runs
a `ProcessPoolExecutor`, and on Windows those children are spawned - a fresh
interpreter that imports `config` from source and knows nothing of anything
the parent patched at runtime. The env var is inherited, so every worker
re-derives the same overlay. Patch the module from the parent instead and the
workers quietly build the production surface while the log says otherwise.
`lab` sets the variable before importing anything that reads a parameter, and
refuses to run any stage if `config.PROFILE` does not match.

What it cannot do is re-derive a constant computed from another one:
`SLOPE["max_cost"]` and `STEEP_SLOPE_BARRIER` read `BASE_MAX_COST` at the
moment those lines ran. Override a base and set what depends on it in the
same profile.

A profile may say `"extends": "baseline"` instead of listing `tours`, and
inherit that profile's tour set. Only the tour list is inherited, never
`config`, and the asymmetry is deliberate: the tours are a fixed test set
shared by every experiment, so duplicating them per profile means adding one
tour later is an edit to every file and a set that has silently drifted apart
makes two runs incomparable with nothing looking wrong. The parameters are
the opposite case - a profile is read months later to answer "what did this
one change?", and it can only answer that if the whole change is written in
it.

`tours` are FIDs in `data/tours/tours.gpkg`, not a copied `tours_test.gpkg`.
Copy features to a new GeoPackage and OGR renumbers them, so `tour_fid` no
longer points at the tour production routed under that id, and two
experiments started from different copies cannot be compared to each other
either. One tour file, one set of ids.

### The baseline is free

`compare` measures against `data/routing_output/routes.gpkg` - the routes you
have now. There is no baseline run: production already routed these tours
through the unmodified surface, so the numbers are per tour the metres the
line moved, the length difference and the cost difference. It prints worst
first, because on most runs most tours will not have moved at all.

This only holds while the production routes are current. If `routes.gpkg` is
older than the tour file or the national surface, some of the difference is
drift rather than your change - `compare` checks the dates and says so.

### Figures

`data/test/lab/<name>/figures/index.html`, worst-moved first. The background
is the surface the new route actually walked, which is what makes the picture
answer *why there*: the line follows the cheap ground you can see underneath
it. The corridor is a banded white veil - banded rather than smooth because
over flat ground a balanced corridor covers the whole frame, and a continuous
wash over all of it just desaturates the surface.

Colours come from **`data/styles_arcgis/cost_surface.tif.lyrx`**, read at
render time by `skimap.lyrx`, so a figure looks like the layer you already
have open and re-styling in ArcGIS then re-running `lab figures` is the whole
loop. Point `--style` at another `.lyrx` for one run. If the file cannot be
read it falls back to a stock ramp and says which it used.

That is a `CIMRasterStretchColorizer`: a linear stretch pinned to 1..100 with
everything above it taking the ramp's last colour, which is what puts every
barrier and the whole sea at black. The classification lives in the ramp's
segment **weights** rather than in class bounds - the green segment's 0.044
holds all of 1..5.4, and the two wide segments spread 15..60 and 60..99 - so
it is the only place the figures get their colours.

The **GPS tracks** are drawn over the surface in magenta, under the routes,
so you can see whether a route followed one. Alpha carries the *normalized*
density - the same [0,1] the cost surface reduces on - but floors at a
visible value wherever there is any track at all: the national scale starts
at the 60th percentile of positive pixels, so a single passage normalizes to
zero, and "nobody has been here" and "somebody has, and it earned no
discount" are exactly the two cases the overlay exists to separate. Magenta
because it appears nowhere in the ramp and nowhere in the route colours.
`--hide-tracks` turns it off; a window the national track rasters do not
reach simply gets nothing, which is normal for about 44% of tiles.

The routes are drawn white (production) and blue (the profile), each over a
dark casing. Both hues are absent from that ramp on purpose: the first
version drew the new route in orange, which vanished into steep orange ground
exactly where you most want to see where it went.

### The track reduction as a map

```bash
python -m skimap.lab reduction <name>
```

Writes `track_reduction.tif` (and a .vrt) beside the profile's cost surface,
Float32, one value per cell: the cost units the track step takes off there
under that profile's settings. Same origin, same size, same lattice as the
surface, so it overlays cell for cell - open it on top and you can see where
the tracks are paying and where they are not.

Computed directly rather than differenced out of two built surfaces. The
surfaces are uint16 and rounded, and the mean delivered reduction is a few
tenths of a cost unit, so subtracting one from the other would quantize most
of the signal away and draw a map of rounding error.

Classify on 0.01 / 0.1 / 0.25 / 0.5 / 1 / 2 / 4. A linear stretch shows
almost nothing, for the same reason it does not work on the surface.

### What each scheme pays

```bash
python -m skimap.lab tracks <name>
```

`figures/track_curves.png`: five tour windows spanning the profile's range
from least tracked to most, each showing every scheme's density-to-reduction
curve drawn over a histogram of the densities actually present there. The
curve alone says nothing about whether a scheme helps a quiet area - what
matters is where that area's distribution sits under it.

Schemes are read off the profiles in `data/test/lab/profiles/`, so one you
invented by writing a profile is in the comparison automatically. The curves
are drawn by calling `normalize()` itself, not by reimplementing it.

### Then check it nationally

Three areas will overfit. A change that helps alpine Jotunheimen can quietly
wreck coastal Lofoten or the forested Hemsedal valleys - the reduction gate
and `TRACKS` in particular behave differently under forest. Before a profile
graduates into `config.py`, route the full set on a national surface once.
`skimap.track_variants` is that run, for the track reduction specifically.

## Track variants

How much should a track take off, and is a track under trees worth more than
one above the treeline? A variant is a name, a pair of numbers and a full
national build - its own tiles, mosaic, routes and corridors, under its own
directory. Production stays put and is the baseline each is measured against.

```bash
python -m skimap.track_variants list
python -m skimap.track_variants run max2       --jobs 8
python -m skimap.track_variants run forest_1_2 --jobs 8
```

`run` is surface -> mosaic -> route -> compare, and each is its own stage too,
so re-routing does not rebuild 1334 tiles. Two ship:

| variant | outside forest | in forest |
| --- | --- | --- |
| production (`config.TRACKS`) | 3.0 | 3.0 |
| `max2` | 2.0 | 2.0 |
| `forest_1_2` | 1.0 | 2.0 |

Add your own with `init softer --max 0.5 --forest 1.5`. Everything lands in
`data/test/track_variants/<name>/`, about 2.9 GB and the better part of a day
each, of which the 841 tours is the long pole.

Both shipped variants take strictly less off than production does, so their
ground can only be dearer: a variant route must cost at least what the
production route for that tour cost. `compare` checks that and says so if it
fails, because a negative `cost_diff` means the two surfaces differ by
something other than these numbers.

The numbers reach the tile workers through a file, not a runtime patch:
`build_all` spawns its workers fresh on Windows and they inherit the
environment, so the profile goes into `SKIMAP_PROFILE` before anything that
reads a parameter is imported. Every stage checks it really took - a national
build showing no change looks exactly like a change that did nothing.

### The forest split

`config.TRACKS` has `max_reduction` and `max_reduction_forest`. Production
sets both to 3.0, which is no split at all; the two keys exist so a variant
can try one without editing `config.py`. "In forest" is `forest > 0`, the same
reading `data_preprocessing.derived` gives the layer when it builds
`tractorroad_trail_forest`, so trails-in-forest and this agree on where the
forest is.

## Track scenarios

```bash
python -m skimap.track_scenarios init      # write settings.json
python -m skimap.track_scenarios rasters   # the ten tifs, about 20 s
python -m skimap.track_scenarios run       # rasters, then routes
```

Four tools now touch the track layer, and they answer four questions:

| | asks | costs |
| --- | --- | --- |
| `track_test` | are the tracks worth anything at all, nationally? | a day |
| `track_variants` | how much should a track take off, nationally? | a day each |
| `lab` | did this change move the routes I care about? | ten minutes |
| `track_scenarios` | what do these settings take off, and where? | twenty seconds |

This one is the raster loop. Five tiles, ten files, one settings file. The
filenames never change, so you keep them open in ArcGIS, edit a number,
re-run, and refresh - the symbology and the map you built around them survive
every run. That is the whole point, and it is why this is not another lab
profile: a profile makes a new directory per experiment, and a new directory
is a layer you have to re-add and re-style.

Everything lands in `data/test/track_scenarios/`:

```
01_etne_cost.tif        the cost surface, uint16, as the router reads it
01_etne_reduction.tif   cost units the tracks took off, Float32
...                     the same two for each of the five areas
settings.json           the one file you edit
settings_used.json      every parameter as the last run actually applied it
stats.csv               one row per area per run, appended
routes.gpkg             routes through these tiles, after `run` or `route`
```

Ten rasters, and never an eleventh. A run builds into `_work/` and then
replaces the published files, so a half-written raster is never what ArcGIS is
drawing, and an interrupted run leaves the previous set whole and drawable.

Classify `*_reduction.tif` on 0.01 / 0.1 / 0.25 / 0.5 / 1 / 2 / 4, the same
breaks `lab reduction` recommends, and for the same reason: the delivered
reduction is a few tenths of a cost unit almost everywhere, so a linear
stretch shows nothing.

### The five areas

Picked by measuring, not by reputation - every tile in the grid was scanned
for track coverage. They span it:

| area | place | why it is in the set |
| --- | --- | --- |
| `01_etne` | Etne, Sunnhordland | the sparse coast: 0.12% of the tile tracked, and 82% of that earns nothing |
| `02_bykle` | Bykle, Setesdal | 54% of tracked pixels in forest - the only tile where the forest coefficient is legible |
| `03_voss` | Voss | 7.3% coverage, mixed forest and alpine: the ordinary case |
| `04_isfjorden` | Isfjorden, Molde | the national maximum density, 2258 on one pixel; where `upper` and `power` bite |
| `05_sjodalen` | Sjodalen, eastern Jotunheimen | 11% coverage and 2% forest - dense and treeless |

Ordered by coverage, sparse first, so they sort that way in the ArcGIS table
of contents. `python -m skimap.track_scenarios areas` prints the set with the
tile ids. Swap one by editing `AREAS` in the module, or override the whole set
with an `"areas"` object in `settings.json`.

### The settings file

```json
{
  "note":   "does presence_floor rescue the sparse coast?",
  "config": {"TRACKS": {"presence_floor": 0.25}},
  "scale":  {"lower": 2.0, "upper": 11.0}
}
```

`config` is a `config.py` overlay applied through `SKIMAP_PROFILE`, the same
mechanism `lab` uses and for the same reasons - including that a misspelled
parameter is an error rather than a silent no-op.

`scale` is the one knob that is **not** in `config.py`. The track
normalization is a pair of density values computed once nationally into
`data/grid/track_scale.json`; `TRACK_NORMALIZATION` holds the percentiles it
was derived *from*, not the answer, and re-deriving it is a full pass over the
national track raster. So this takes the two numbers directly. Omit it, or set
it to `null`, for the national pair.

Those two numbers do half the work, which is the thing worth seeing on a map.
At the national `lower` of 2.0 with the linear curve, every pixel carrying one
or two passages maps to exactly zero - on Etne that is 82% of all the track
evidence there is, on Bykle 90%.

### Reading stats.csv

The rasters are overwritten in place, so `stats.csv` is the only record that a
setting was ever tried. One row per area per run, and the `settings` column
carries the whole parameter set, so every row says what produced it.

```
area           tours   trk%  zero%  sat% forest% mean_red p95_red max_red  bite% delta
01_etne            1   0.12   82.0   0.2     1.1    0.053   0.222   2.000    4.3  1.14
02_bykle           5   0.89   89.6   0.1    53.6    0.028   0.049   4.000    2.9  1.17
03_voss            5   7.30   72.4   4.4    23.3    0.203   1.778   4.000   11.4  1.54
04_isfjorden      12   8.81   59.8  14.3    15.9    0.427   2.000   4.000   23.0  1.78
05_sjodalen        2  10.96   64.1   5.2     1.9    0.199   2.000   4.000   19.0  1.35
```

`trk%` is the share of the tile carrying any track; `zero%` the share of
*that* earning no reduction from the curve itself, before rounding is even in
it. `mean_red` against a nominal 2.0 / 4.0 is the number that shows how little
of the headline coefficient is ever delivered.

`bite%` is not a threshold on the reduction - `clip_round` in `surface.py`
rounds the cost *after* tracks are subtracted, not the reduction itself, so a
reduction of 0.9 can round away to nothing and, rarely, one of 0.2 can flip
the integer, depending on where the pre-track cost's fractional part sits.
`bite%` reconstructs the real before/after integer cost with the same
`clip_round` the build calls, and reports the share of tracked pixels where it
actually differs; `delta` is the mean size of that difference, in cost units,
where it happened. That is the number that answers "does this change what the
router sees" - not `mean_red`, which is the curve's output before rounding
ever touches it.

The numbers are read back off the published `_reduction.tif` and the
intermediates in `_work/layers/` from the same build, rather than recomputed
from the parameters - so they describe what the last build actually produced,
not what the settings should have produced.

### Routing

`run` also routes every tour with **both** endpoints inside one of the five
tiles, into a `routes.gpkg` that is overwritten like the rasters, with
`sep_max_m` against the production route for the same tour. Both endpoints,
not either: a tour that finishes two tiles away is mostly a test of ground
this run did not build.

The router reads a window, not a tile - `g.region` is the endpoints' bounding
box plus a buffer scaled to the tour's length, and that spills over a tile
edge on most tours. So `route` builds the five **plus every tile those windows
reach** and mosaics the lot. Only the five are published; the neighbours stay
in `_work/`. Build only the five and a route that leaves one is clipped at a
nodata edge, which on the map is indistinguishable from terrain turning it
back.

### When ArcGIS has the files open

ArcGIS Pro keeps an open handle on every raster in an open map, and Windows
will not replace a file another process holds. The build therefore goes to
`_work/` and only the final move can fail, which means a locked file leaves
the *previous* raster whole rather than half-overwritten. The run says which
files it could not replace and stops there:

```bash
# close the layers in ArcGIS - remove them, not just the map - then
python -m skimap.track_scenarios publish
```

Nothing is rebuilt; `publish` just moves what is already on disk. `routes.gpkg`
is the one file with no staging, because `run_batch` deletes it up front - it
already refuses to run rather than half-delete, and says so.

### What this does not touch

`data/cost_surface` and `data/routing_output`, ever. Worth stating because the
obvious way to do this by hand does not have that property: `cost --tile X
--debug` writes its tile straight into `data/cost_surface/tiles/`, so running
the production CLI under experimental track settings quietly replaces
production tiles with them, and nothing says so.

## Corridor review

The national metrics cannot tell you which cost surface is *right*. They
average. A setting that finds the sensible line up one valley overshoots in
the next, and `score` reports the mean of those two as a small change in
exposure per kilometre - which is exactly the information you do not need.
Somebody has to look at the corridors.

This is the looking. One panel per model, side by side over NVE's slope
tiles, all locked to the same pan and zoom, each corridor drawn in the
exposure class it scored. Pick the best one, adjust its class if you
disagree with `classify()`, and move on when you are ready to.

Picking does not advance. It used to, and it was wrong: dragging the map to
look around ends in a click on the panel, so panning recorded a verdict and
moved you off the tour before you saw it happen - the pick was wrong and the
tour it belonged to was already gone. A click that travelled more than a few
pixels is now a drag and not a choice, and moving on is always something you
ask for.

```bash
python -m skimap.corridor_review init      # write data/review/config.json
python -m skimap.corridor_review prepare   # score the models it names
python -m skimap.corridor_review serve     # http://127.0.0.1:8765
python -m skimap.corridor_review status
python -m skimap.corridor_review export
```

Keyboard: `1`..`9` pick that panel, `left`/`right` step, `Enter`
jumps to the next unreviewed tour, `u`/`s`/`d` set the class shift before you
pick, `f` flags the tour as needing fixing, `Backspace` drops a verdict, `l`
opens the tour list.

Layers, per the footer: slope and runout from NVE, the route line, and the
GPS tracks. Tracks are off by default and fetched only when switched on -
the overlay is a warp of a national raster, so a reviewer who never wants it
never waits for one. Alpha carries the normalized density, the same [0,1] the
router is paid on, floored wherever there is any track at all: the two cases
you have to tell apart are "nobody has been here" and "somebody has, and it
earned no discount", and on a plain ramp a single passage is invisible. The
footer says `(none here)` where a tour has no tracks near it, so an empty
layer is never mistaken for a broken one.

### It builds nothing

`config.json` names models by **path to output that already exists**:

```json
{"name": "forest_1_2", "label": "1.0 open / 2.0 forest",
 "routes": "test/track_variants/forest_1_2/routes.gpkg",
 "corridors": "test/track_variants/forest_1_2/corridors"}
```

Rebuilding a model in place is therefore the way to update one: re-route it,
and the next `serve` picks up the new corridors, re-scores them if `route`
dropped the exposure fields, and re-renders the overlays - the cache compares
mtimes, so a corridor newer than its cached picture is drawn again rather
than served stale. What does **not** update is the verdicts: they record a
model *name*, not a snapshot, so picks made against the old corridors will
silently read as picks against the new ones. Give a rebuilt model a new name
in `config.json` if that matters - `status` reports verdicts naming a model
the config no longer lists, rather than dropping them.

Routing 842 tours against one surface is the better part of a day. A review
that built its own models would be a multi-day tool, and every round would
redo work already on disk - so it does neither. To review a model you do not
have, build it first with `skimap.lab` or `skimap.track_variants`, then add
it to the list. The three the default config names are the builds this repo
already has, and a round over them starts in seconds.

The one thing `prepare` does write is exposure fields. The variant builds
under `data/test/` carry the comparison fields `compare` wrote and nothing
about avalanche exposure, because scoring is a separate stage nobody ran on
them - and a corridor with no class has no colour to be drawn in. Scoring is
a pass along each line against `pra.tif` and `runout.tif`: minutes for 842
routes, against a day to route them.

### The shift is the point

A verdict records the class `classify()` computed, the reviewer's shift, and
the class that results - all three, never just the answer:

```
python -m skimap.corridor_review status --shifted

   fid  model          computed -> kept     note
    14  forest_1_2     green    -> blue     corridor fans into the bowl
    32  no_tracks      blue     -> green    tracks were dragging it too low
```

`config.EXPOSURE_CLASSES` is four numbers picked once. Nothing in the
pipeline ever tells you whether they are the right four. A run of tours where
the reviewer pushed green to blue is the only evidence that exists that a
break is in the wrong place, and storing only the final colour throws it
away.

### Tours that need fixing

Reviewing corridors is the fastest way anybody will find a bad tour: you are
looking at the ground it was routed over, at the right zoom, with the slope
underneath. `f`, or the **fix tour data** box, flags the tour and takes an
optional note about what is wrong with it.

`needs_fix` is its own map in `review.json`, not a verdict field, because it
answers a different question. "This is the best of the three corridors" and
"the tour these were routed from is wrong" can both be true, either can be
true alone, and a new round that re-picks every corridor must not quietly
drop a list of tours somebody found broken. Flagging does not advance the
tour and does not touch the pick.

```bash
python -m skimap.corridor_review status --needs-fix
```

`export` carries it into the layer as `needs_fix` and `fix_note`, so the
tours to re-digitize are one attribute filter away in ArcGIS - including
tours flagged before anybody picked a corridor for them.

### Rounds

`round` bumps the number. Verdicts already recorded stay and each carries the
round it was made in, so a second pass that revisits only the doubtful tours
leaves the rest standing as the current answer. Every superseded verdict goes
to `history` in `review.json` rather than being overwritten - a changed mind
is data too.

`export` writes `tours_reviewed.gpkg`: every tour, with the review fields and
the chosen model's route geometry. Tours with no verdict yet get the straight
start-to-end line from `tours.gpkg`, and `review_geom` says which of the two
you are looking at - so a half-finished review is a usable layer rather than
a misleading one. Beside it, the winning corridors merged per exposure class,
drawn from whichever model won each tour. That merged set is the output of the
whole exercise: the best corridor for every tour in Norway, each from the
surface that got it right.

### Why the front end is hand-written

`app/` is React and Vite and needs `npm run build`. This is one HTML file,
one stylesheet, one script, and Leaflet from a CDN - no build step, so it
runs anywhere the QGIS Python does. The server is `http.server` from the
standard library, for the same reason `app/backend/server.py` is: the
QGIS-bundled Python has no FastAPI, and a review tool should not be the thing
that makes this repo need a package manager.

`data/review/review.json` is the one file here that the pipeline cannot
reproduce. It is re-included in `.gitignore` on purpose - `cache/` and
`export/` are rebuildable, and hours of somebody looking at maps are not.
