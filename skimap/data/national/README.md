# National source data

One dataset per theme, EPSG:25833, built from the raw dumps by
`python -m skimap.data_preprocessing.cli`. Nothing here is in git.

| Path | Format | Notes |
|---|---|---|
| `boundary/kommuner.geojson` | polygon | Kartverket kommuner. Bounded seaward by the *territorial limit*, not the coastline |
| `dem/dem.tif` | Float32 | metres. nodata −32767 |
| `pra/pra.tif` | Int8 | potential release areas, **integer percent 1–99**, not a 0–1 fraction. nodata −128 |
| `runout/runout.tif` | Int16 | nodata 10000 = beyond runout reach |
| `forest/forest.tif` | Int16 | stems ≥8 cm. **0 = no stems**, no nodata |
| `windshelter/windshelter.tif` | Float32 | shelter index, roughly −1.3…+1.4. nodata −9999 |
| `tracks/tracks.tif` | UInt16 | GPS density, nodata 0. **Partial coverage** |
| `roads/roads.gpkg` | line | NVDB. Layer `roads` |
| `water/water.gpkg` | polygon | FKB. Layer `water`, `objtype` in Innsjø/Elv/Havflate/Kanal/SnøIsbre |
| `tractor_trails/tractor_trails.gpkg` | line | FKB. Layer `tractor_trails`, `typeveg` in sti/traktorveg/stitrapp |

All rasters are 10 m on the lattice at `config.RASTER_ORIGIN` (5, 5), so a
tile window is an exact crop rather than a resample. Anything added later
must match, or be warped with `data_preprocessing.cli merge`.

**No band carries a scale or offset.** Every raster here and in
`data/derived/` holds the value it means, so it displays correctly in QGIS
without anyone remembering a factor. Keep it that way: `raster.read_tile`
would honour a scale, but nothing else in the stack — or in any GIS a
reader opens this in — reliably would.

Cached statistics in the `.tif.aux.xml` files are approximate, computed off
the AVERAGE overviews. They understate extremes badly: windshelter reads
−0.019…0.19 there against a true −1.23…1.34, and `pra.tif` reports a max
of 128 because the stats pass treats the Int8 nodata −128 as unsigned. Use
them for a smell test, never for calibrating a threshold.

Feature filters (which road counts, which water is a barrier) live in
`config.VECTOR_LAYERS`, not here — the GeoPackages carry whole layers.

## Known gaps

- **Tracks cover 753 of 1334 tiles.** The north and south source rasters do
  not meet: a 196 km band across Trøndelag/Helgeland has none, nor does
  eastern Finnmark or the coast west of x ≈ −14 km (Bergen included).
- **`boundary/` is administrative, not physical.** Kommune polygons run to
  the territorial limit, so the grid's outer ring holds sea-only tiles.
  Re-run the grid against a coastline (N50 Kystkontur) to drop them.
- **Windshelter has nodata holes inland, not just at its extent.** 637 land
  tiles carry at least one and some are two thirds hole, concentrated
  around x 264–305 km / y 6520–6580 km. `cost.surface` fills them at the
  logistic midpoint so they read as average shelter; see the note there
  for why renormalizing the other weights instead is not neutral.
