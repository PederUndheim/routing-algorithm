# skimap app

A browser front end for looking at ski touring routes: route one between two
points or upload your own GPX/GeoJSON, keep several side by side, and let the
Crux Identifier mark where along one the terrain asks for attention.

Deliberately small. There is no account, no cloud storage, no run history and
no parameters - it routes through the cost surface exactly as `skimap.cli
route` would, and everything tunable stays in `config.py`. It runs entirely on
this machine and talks to nothing but the two tile servers the map draws from.

```
app/
  backend/     standard library, plus GDAL for the corridor
    server.py    the HTTP server, four endpoints
    service.py   lat/lng <-> EPSG:25833, and the one call into skimap.routing
    corridor.py  the corridor GeoTIFF -> a PNG the map can draw
  frontend/    React + Vite + MUI + react-leaflet
    scripts/
      vite.mjs           starts Vite or Vitest - see "The esbuild detour" below
    src/
      api.ts             the three fetches
      theme.ts           the colours
      types.ts           LatLng, PickMode, RouteResponse, CruxResult
      dangerClasses.ts   each Danger class's name and icon
      routes/            the route list: every Route and every action on it
      layers/            basemap and overlay definitions
      map/               the map and everything drawn on it
      routing/           the panel on the left
      ui/                markers, scale bar, buttons
```

The analysis itself is not in here: `/crux` calls `skimap.crux`, next to the
rest of the package, which is where its tests are too.

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

Nothing to install: the QGIS-bundled Python has no FastAPI, and a handful of
endpoints do not earn a dependency, so this is `http.server`.

**Frontend**, from `app/frontend/`, and this one does need Node
([nodejs.org](https://nodejs.org), LTS):

```powershell
npm install --ignore-scripts
npm run dev
```

Then open the address it prints - <http://localhost:5173>. `npm run typecheck`
is the type check on its own, and `npm run build` runs it before building.

### Tests

The two halves are tested where their logic is, at one entry point each.

- **The route list**, from `app/frontend/`: `npm test`. Vitest with jsdom,
  which supplies the XML parser GPX uploads are read with. The tests perform
  actions on the list - add, upload, select, hide, delete, attach a crux
  result - and look at the Routes that come out.
- **The Crux Identifier**, from the project directory:

  ```powershell
  & "C:\Program Files\QGIS 4.2.0\bin\python-qgis.bat" -m unittest discover -s tests -t . -v
  ```

  `unittest`, because the QGIS Python has no pytest. Each test writes tiny
  synthetic GeoTIFFs to a temporary directory, so it needs none of the
  national data.

The HTTP handlers and the map drawing are thin and are checked by hand.

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
`~/.local/bin/esbuild.exe` before starting Vite, and the `dev`, `build`,
`preview` and `test` scripts go through it - Vitest transforms with the same
esbuild. On a machine without the restriction it does nothing and you get a
plain `vite` or `vitest`.

Two things follow. Install with **`npm install --ignore-scripts`**, or that
postinstall check fails the install; and if `~/.local/bin/esbuild.exe` is
missing, copy it from `node_modules/@esbuild/win32-x64/esbuild.exe` after
installing. Moving the repo somewhere outside `C:\Users\` removes the whole
problem, if that is ever convenient.

## Deployed

The front end is on GitHub Pages at
<https://pederundheim.github.io/routing-algorithm/>, and the backend is a
Container App on Azure (Azure for Students, `rg-skimap`). Both deploy from a
push to `main`:

- `.github/workflows/deploy-pages.yml` tests and builds the front end. The API
  address comes from `frontend/.env.production`.
- `.github/workflows/deploy-skimap-api.yml` builds `skimap/Dockerfile`: GRASS
  8.5 plus this code, smoke-tested to check that GRASS starts. The workflow
  pushes the image to `ghcr.io/pederundheim/skimap-api` and points the
  Container App at it.

The rasters are not in the image. `cost_surface.tif`, `pra.tif`, `runout.tif`
and `slope.tif` (~20 GB) are on the Azure Files share `skimap-data`, laid out
like `data/` and mounted read-only over `data/input` and `data/cost_surface`.
A rebuilt layer is uploaded there with azcopy, and the app restarted. The
Azure resources themselves come from `skimap/deploy/azure.sh`, run in Cloud
Shell.

The deployed backend runs one replica. Routes run one at a time behind a
lock, and each corridor PNG is on the disk of the replica that drew it, so a
second replica would break both. It scales to zero when idle, so the first
request after a quiet spell waits for a cold start.

## What it does

**Routing.** Pick the two points, drag either marker to nudge it, press
**Generate route**. Each route is added to the list as "Route 1", "Route 2"
and so on, rather than replacing the last one, and moving a point afterwards
leaves every route alone.

**Uploading.** **Upload GPX/GeoJSON** takes several files at once, and so
does dropping them on the map. Every GPX track and route (`<trk>`, `<rte>`)
becomes a Route of its own, as does every LineString or MultiLineString in a
GeoJSON Feature, FeatureCollection or bare geometry. Segments and parts are
joined in order; waypoints, elevation and time are ignored. Routes are named
after their file, with " (2)", " (3)" on repeats. A file that cannot be used
is reported by name and reason, and the rest of the upload still loads. A
GeoJSON in projected coordinates is refused as "must be WGS84 (lat/lon)"
rather than dropped somewhere wrong.

**The route list.** The newest Route is the Selected route and the map zooms
to it. Select another by its row or by clicking its line - except while a
start or end is being picked, when the click is the picker's. The rest are
drawn thinner and faded. The eye hides a Route and everything that belongs
to it without changing the selection; deleting the Selected route selects
the one above. The list is gone on a reload.

The panel shows the Selected route's length, and for a routed one the
straight-line distance, the ratio between them, the route's cost and how
long it took. Its **corridor** is drawn under the line: the band of
near-optimal ground around it, everywhere you could cross instead without
the trip costing much more. Navy along the route, fading out to nothing at
the edge of the band, in the same blue ArcGIS draws it. Only the Selected
route's, and only a routed one's - several overlapping bands would bury the
terrain. The panel toggles it and sets how strongly it is drawn - it starts
at 50%, because the terrain under it is usually the reason you are looking,
and 100% is the ArcGIS rendering exactly.

**Identifying cruxes.** **Identify cruxes** runs the Crux Identifier on the
Selected route, and only when pressed. The line is redrawn green where no
Danger class applies, red through every Danger zone and grey dashed where
there is no terrain data, and a numbered marker with the Danger class's icon
sits at each Crux. Its popup gives the class, the distance from the start,
the zone's length and, for a Probable release area or a Fall hazard, the
highest release probability or the steepest slope in it. The panel lists
the Cruxes in order - click one to go there - and says how much of the route
could not be analysed. Each Route keeps its own result until it is run
again; a Route not yet analysed stays teal.

The map has the four Kartverket basemaps and NVE's two steepness overlays
behind the button top right, each with an opacity slider - the same layers the
cost surface is built to agree with, and the quickest way to see whether a
route makes sense.

A point outside the cost surface, or two points with no walkable ground
between them, comes back as a message in a red toast rather than a hang.

## What it does not do

No stops, no avalanche exposure score, no GPX or GeoJSON download, no saved
runs or routes, no renaming or editing a route, no uploading your own map
layers, and no picking a corridor width - it is whatever `config.CORRIDOR`
says. `skimap.cli` does most of that; this is for looking at routes quickly.

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

**`/crux` does not queue behind a route.** It only reads rasters - the
national PRA, the derived slope layer and the Flow-Py runout - so it runs
outside that lock. It reads them a few kilometres of line at a time, which
keeps a 50 km Route as cheap as a short one, and takes a body of up to 4 MB,
where `/route` keeps its 8 KB. Uploaded files are parsed in the browser, so
all the backend ever sees is a WGS84 line.

**PRA and runout nodata are answers, not holes.** PRA's −128 is where the
model found no release area and the runout raster's 10000 is ground beyond
its reach; on a mountain window those are two thirds and a quarter of all
cells. The Crux Identifier reads both as "no hazard here" and treats only
slope nodata, and anything off a raster's edge, as No data. See the
docstring in `skimap/crux.py`.

**The corridor is a picture, not a raster.** `route_one` writes it as a
Float32 GeoTIFF on the 25833 grid; `corridor.py` warps that to EPSG:3857 and
writes an RGBA PNG, because Web Mercator is the projection Leaflet stretches
an image overlay in - pinning the 25833 grid to WGS84 corners instead would
lean the band off its own route by hundreds of metres this far north. The
GeoTIFF is deleted as soon as it is converted, and only the last dozen PNGs
are kept - so a Route routed long ago in a busy session can find its
corridor gone. The app never touches `routes.gpkg` or the real `corridors/`.

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
turns it round, checking which end it starts at rather than assuming. The
Crux Identifier depends on that: a Crux is where a zone begins in the
direction of travel.
