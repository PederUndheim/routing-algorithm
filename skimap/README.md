# skimap

A ski-touring cost surface for all of Norway, and least-cost routes through
it. Self-contained: nothing here imports from anywhere else in the repo.

Run everything from the repository root, with the QGIS-bundled Python:

```powershell
Set-Location "c:\Users\pund\Desktop\routing_algorithm_repo"
& "C:\Program Files\QGIS 4.2.0\bin\python-qgis.bat" -m skimap.cli <stage>
```

There is nothing to install - see `requirements.txt`. Add `-h` to any stage
for its flags.

## Pipeline

```bash
# Once, from the raw dumps. The grid comes first: every derived layer is
# built on its extent. `derived` takes hours and about 21 GB.
python -m skimap.cli grid --boundary skimap/data/national/boundary/kommuner.geojson
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
writes `data/output/cost_surface.tif`, a COG with nine overview levels down to
5 km per pixel. Open that, not the .vrt. QGIS reads either.

Overviews are NEAREST rather than the COG driver's default CUBIC: most of the
country sits at 4 and the sea at 5000, so an averaged overview pixel is a
value that exists nowhere in the data and draws as a passable shore.

Default symbology shows nothing - about 60% of mapped ground is between 1 and
5, so any even stretch flattens the country to one colour. Classify manually
on `config.DISPLAY_BREAKS` (3, 5, 8, 12, 20, 35, 60, 100, 300, 1500) or apply
`data/output/cost_surface.clr`, which `mosaic` writes from those same breaks.

### Debugging a tile

```bash
python -m skimap.cli cost --area jotunheimen_02 --debug
python -m skimap.cli cost --all-areas --debug --jobs 5
```

Writes the nine layers in `cost.surface.DEBUG_LAYERS` to `data/debug/<name>/`,
numbered in build order: the three basis costs, their weighted sum, the
barriers, the reduction gate, the surface after reductions, the cost units the
tracks took off, and the result. Layers 01-08 are Float32 in the same units as
the output; 09 is the uint16 surface, so one folder holds both the answer and
its working. The identity is exact: `09 = round(clip(max(07, 05) - 08))`.

About 62 MB per area - name what you want, do not run it over the grid.

`--area` takes a name from `config.STUDY_AREAS` and uses it for the folder.
Each study area is exactly one tile: they are 20 km squares on the grid's own
lattice, which is what `GRID_ORIGIN` is for.

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
something else - a barrier beside its own coastline, r.walk pairing elevation
with a neighbour's friction. So every check here works through COORDINATES;
comparing arrays index for index agrees perfectly even when the
georeferencing is wrong, which is exactly how it survived.

Five checks: `tile_origin()` against the cells `window()` reads for every
layer; everything on one lattice; tiles abutting exactly; the published COG
newer than its tiles; and the measured offset against the ocean mask, which
should be zero. `routing.py` runs the lattice check before every batch and
refuses to start if the surface and the DEM disagree.

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
2. Add `data/tours/tours.gpkg`, with `data/output/cost_surface.tif` beneath it
   and `cost_surface.clr` applied, so you can see what is walkable.
3. Add `data/national/roads/roads.gpkg` and snap to it. Trailheads belong on a
   road; a start one pixel into a cliff is a barrier with no route out of it.
4. Edit > Create > `tours` > Line. Click the start, double-click the summit.
   The tool stays active, so routes chain without re-selecting it.
5. **Draw everything first, name it afterwards** in the attribute table. One
   pass of mouse then one of keyboard beats alternating per feature.

## Routing

```bash
python -m skimap.cli route                     # every tour
python -m skimap.cli route --fid 12 --fid 13   # just these
python -m skimap.cli route --mode balanced     # one corridor mode, not three
```

Four GRASS steps per route: `r.walk` for the direction raster, `r.cost` from
both ends for the corridor, `r.path` to extract the line, `v.generalize` to
smooth it. Parameters in `config.ROUTING` and `config.CORRIDOR_MODES`.

`r.walk` is anisotropic, which is what makes it right for ski touring and why
it needs the DEM as well as the surface. `r.cost` is symmetric, and the
corridor needs that: `start->x` plus `end->x` is only a meaningful total when
both halves are measured the same way.

One GRASS session serves the whole batch, `r.external` links the 1.65 GB
surface without copying it, and the region is set per route to the pair's
bounding box plus a buffer scaled to the tour's own length - floored at
`region_buffer_floor_m` and capped at `region_buffer_m` in `config.ROUTING`,
so a short tour isn't padded out to the same window as a long one. About 12 s
per route.

### Output

```
data/routes/
  routes.gpkg                              all routes, one line each
  corridors/001_kyrkjetaket_balanced.tif   one per route per mode
```

`routes.gpkg` carries `tour_fid` (back to the tour), `name`, `length_m`,
`straight_m`, `detour` and `cost_opt`. One layer to open, style and query,
rather than a file per route. Corridors are flat and mode-suffixed so
`*_balanced.tif` globs the set you want.

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
python -m skimap.cli exposure --no-copy-all    # per-class rasters only
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
data/corridors/
  corridors_all/                     copy of every per-route corridor
  corridors_all.tif                  copy of the merged-everything raster
  corridors_colored/
    corridors_green.tif              merged corridors of the green routes
    corridors_blue.tif
    corridors_red.tif
    corridors_black.tif
```

`routes.gpkg` gains `exp_release`, `exp_runout`, `exp_score`, `exp_per_km`
and `colour`. The copies exist so `data/corridors` stands on its own and
`data/routes` can be re-routed underneath it without the two disagreeing.

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
