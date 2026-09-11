# skimap app

A browser front end for one route at a time: click a start, click an end,
press the button, look at the line.

Deliberately small. There is no account, no cloud storage, no run history and
no parameters - it routes through the cost surface exactly as `skimap.cli
route` would, and everything tunable stays in `config.py`. It runs entirely on
this machine and talks to nothing but the two tile servers the map draws from.

```
app/
  backend/     the routing endpoint - standard library, plus GDAL for the corridor
    server.py    the HTTP server, three endpoints
    service.py   lat/lng <-> EPSG:25833, and the one call into skimap.routing
    corridor.py  the corridor GeoTIFF -> a PNG the map can draw
  frontend/    React + Vite + MUI + react-leaflet
    scripts/
      vite.mjs           starts Vite - see "The esbuild detour" below
    src/
      api.ts             the two fetches
      theme.ts           the three colours
      types.ts           LatLng, PickMode, RouteResponse
      layers/            basemap and overlay definitions
      map/               the map and everything drawn on it
      routing/           the panel on the left
      ui/                markers, scale bar, buttons
```

## Running it

Two terminals. **Backend**, from the project directory - `skimap/`, the one
holding `skimap/`, `app/` and `data/`:

```powershell
Set-Location "c:\Users\pund\Desktop\routing_algorithm_repo\skimap"
& "C:\Program Files\QGIS 4.2.0\bin\python-qgis.bat" -m app.backend.server
```

It binds the port, then starts GRASS and links the cost surface, so there are
a few seconds between the command and `Ready on ...`. Nothing is answered
until that line, so `/health` still means genuinely ready - and a second copy
fails on the port before it can touch GRASS, which is the point of that
order. `--host` and `--port` are there if 8000 is taken; the front end reads
the address from `frontend/.env.development`.

Nothing to install: the QGIS-bundled Python has no FastAPI, and two endpoints
do not earn a dependency, so this is `http.server`.

**Frontend**, from `app/frontend/`, and this one does need Node
([nodejs.org](https://nodejs.org), LTS):

```powershell
npm install
npm run dev
```

Then open the address it prints - <http://localhost:5173>. `npm run typecheck`
is the type check on its own, and `npm run build` runs it before building.

### The esbuild detour

`npm install` runs esbuild's postinstall, which executes the native
`esbuild.exe` it just unpacked - and on this machine that fails:

```
Dette programmet er blokkert for gruppepolicy.
```

AppLocker here allows executables everywhere *except* `C:\Users\*`, which is
exactly where a checkout in your profile keeps `node_modules`. Nothing is
wrong with the binary; it is where it is sitting.

The policy allowlists a few directories for developer tooling, one of them
`C:\Users\*\.local\bin\*`, so a copy of esbuild there runs fine. That is what
`scripts/vite.mjs` uses: it sets `ESBUILD_BINARY_PATH` to
`~/.local/bin/esbuild.exe` before starting Vite, and the `dev`, `build` and
`preview` scripts go through it. On a machine without the restriction it does
nothing and you get a plain `vite`.

Two things follow. Install with **`npm install --ignore-scripts`**, or that
postinstall check fails the install; and if `~/.local/bin/esbuild.exe` is
missing, copy it from `node_modules/@esbuild/win32-x64/esbuild.exe` after
installing. Moving the repo somewhere outside `C:\Users\` removes the whole
problem, if that is ever convenient.

## What it does

Pick the two points, drag either marker to nudge it, press **Generate route**.
The panel reports the routed length, the straight-line distance, the ratio
between them, the route's cost and how long it took.

The **corridor** is drawn under the line: the band of near-optimal ground
around it, everywhere you could cross instead without the trip costing much
more. Navy along the route, fading out to nothing at the edge of the band,
in the same blue ArcGIS draws it. The panel toggles it and sets how strongly
it is drawn - it starts at 50%, because the terrain under it is usually the
reason you are looking, and 100% is the ArcGIS rendering exactly.

The map has the four Kartverket basemaps and NVE's two steepness overlays
behind the button top right, each with an opacity slider - the same layers the
cost surface is built to agree with, and the quickest way to see whether a
route makes sense.

A point outside the cost surface, or two points with no walkable ground
between them, comes back as a message in a red toast rather than a hang.

## What it does not do

No stops, no avalanche exposure score, no GPX or GeoJSON download, no saved
runs, no uploading your own layers, and no picking a corridor width - it is
whatever `config.CORRIDOR` says. `skimap.cli` does all of that; this is for
looking at one route quickly.

## Notes

**It works in its own mapset, `app`.** A computational region belongs to a
mapset, and `route_one` sets one per route. Serving out of PERMANENT
therefore breaks the moment you run `skimap.cli route` at the same time: the
batch and the server move the region out from under each other and both
return nonsense, or fail with `r.cost` errors that point nowhere near the
cause. The surface is still linked into PERMANENT, which every mapset reads.
Run the CLI and this server together as much as you like.

**One route at a time.** GRASS is process-global within one process - one
GISRC, one set of per-route map names - so `service.py` holds a lock across
the whole of `route_one`. The server is threaded so that a health check does
not queue behind a route, not so that two routes can run at once. Starting a
second server is caught by the port bind, before it reaches GRASS.

**The corridor is a picture, not a raster.** `route_one` writes it as a
Float32 GeoTIFF on the 25833 grid; `corridor.py` warps that to EPSG:3857 and
writes an RGBA PNG, because Web Mercator is the projection Leaflet stretches
an image overlay in - pinning the 25833 grid to WGS84 corners instead would
lean the band off its own route by hundreds of metres this far north. The
GeoTIFF is deleted as soon as it is converted, and only the last dozen PNGs
are kept. The app never touches `routes.gpkg` or the real `corridors/`.

**The colours are ArcGIS's.** They come from
`data/styles_arcgis/blue.lyrx` - the same file you would drop on a corridor
in Pro - so the app and the desktop map agree, and re-styling the layer there
changes both. It classifies the 0..1 score into twenty equal intervals, light
blue `(190, 210, 255)` at the bottom to navy `(0, 38, 115)` at the top, and
carries its own alpha: nothing below 0.05, then 42 and 84, then solid from
0.15 up. So the band is opaque along the route and fades out at its edge.
The panel's slider multiplies all of that: the shape of the fade stays the
style's, and the slider only decides how much map shows through the band.

This does not go through `skimap.lyrx`, which exists to read exactly these
files. That module reads `CIMRasterStretchColorizer` only and drops alpha,
both deliberately, and both wrong for this one - `blue.lyrx` is a
`CIMRasterClassifyColorizer` whose alpha is the entire fade. It also returns
matplotlib objects, which is a lot to load into a web server for a colour
lookup. `corridor.py` reads the class breaks itself, in about thirty lines.

**Direction.** `r.path` walks the direction raster backwards from the end, so
the line comes out of GRASS running end to start. `service._start_to_end`
turns it round, checking which end it starts at rather than assuming.
