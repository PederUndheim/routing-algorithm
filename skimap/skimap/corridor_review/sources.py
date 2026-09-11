"""Reading what the models already produced: routes, scores, geometry.

Everything here is a read of output that exists. The one exception is
`ensure_scored`, which writes exposure fields into a model's routes.gpkg if
they are not there yet - the variant builds under data/test carry the
comparison fields that `compare` wrote and nothing about avalanche exposure,
because scoring is a separate stage that was never run on them.

That matters for the review, where a corridor's colour is half the
information on screen. Scoring is a pass along each line against pra.tif and
runout.tif, not a re-route: minutes for 842 routes, against the better part
of a day to route them. So it is done on demand, once, in place.

Geometry comes back as WGS84 GeoJSON because that is what Leaflet draws.
The stored lines are EPSG:25833; the transform is per-request rather than
cached, which is cheap next to reading the feature at all.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from osgeo import ogr, osr

from skimap import exposure, paths, tours as tours_module
from skimap.corridor_review.models import Model

ogr.UseExceptions()

WGS84_EPSG = 4326
PROJECT_EPSG = 25833

# Read off each model's routes.gpkg and shown in the panel. Ordered as the
# panel shows them; `colour` drives which style the corridor is drawn in.
ROUTE_FIELDS = (
    "length_m", "cost_opt", "exp_score", "exp_per_km",
    "exp_release", "exp_runout", "colour",
)


@lru_cache(maxsize=1)
def _to_wgs84() -> osr.CoordinateTransformation:
    source, target = osr.SpatialReference(), osr.SpatialReference()
    source.ImportFromEPSG(PROJECT_EPSG)
    target.ImportFromEPSG(WGS84_EPSG)
    source.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    target.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    return osr.CoordinateTransformation(source, target)


def tour_order() -> list[dict[str, Any]]:
    """Every tour, in fid order: the review's spine.

    Read from tours.gpkg rather than from any one model's routes, so the list
    is the same no matter which models are configured and a tour that failed
    to route still appears - with no panels, which is itself worth seeing.
    """
    found = tours_module.read_tours(paths.TOURS)
    return [{"fid": tour.fid, "name": tour.label} for tour in found]


def ensure_scored(model: Model, *, verbose: bool = True) -> bool:
    """Give `model` exposure fields if it has none. True if it scored now."""
    datasource = ogr.Open(str(model.routes))
    layer = datasource.GetLayer(0)
    definition = layer.GetLayerDefn()
    present = {definition.GetFieldDefn(i).GetName()
               for i in range(definition.GetFieldCount())}
    scored = "colour" in present and "exp_score" in present
    if scored:
        # Present but empty happens when `route` rewrote the file after a
        # scoring pass; treat an all-null colour column as unscored.
        any_colour = any(feature.GetField("colour") for feature in layer)
        layer.ResetReading()
        if any_colour:
            datasource = None
            return False
    datasource = None

    if verbose:
        print(f"  {model.name}: no exposure scores, scoring {model.routes.name}")
    exposure.score_routes(model.routes)
    return True


def model_rows(model: Model) -> dict[int, dict[str, Any]]:
    """tour_fid -> the fields the panel shows, for every route in the model."""
    datasource = ogr.Open(str(model.routes))
    layer = datasource.GetLayer(0)
    definition = layer.GetLayerDefn()
    present = {definition.GetFieldDefn(i).GetName()
               for i in range(definition.GetFieldCount())}

    rows: dict[int, dict[str, Any]] = {}
    for feature in layer:
        tour_fid = feature.GetField("tour_fid")
        if tour_fid is None:
            continue
        row: dict[str, Any] = {}
        for name in ROUTE_FIELDS:
            row[name] = feature.GetField(name) if name in present else None
        rows[int(tour_fid)] = row
    datasource = None
    return rows


def route_geojson(model: Model, fid: int) -> Optional[dict[str, Any]]:
    """The model's line for one tour, as WGS84 GeoJSON, or None."""
    datasource = ogr.Open(str(model.routes))
    layer = datasource.GetLayer(0)
    # A quoted attribute filter rather than a scan: routes.gpkg has an index
    # on nothing in particular, but 842 features is small and OGR does the
    # filtering in C either way.
    layer.SetAttributeFilter(f"tour_fid = {int(fid)}")
    feature = layer.GetNextFeature()
    if feature is None:
        datasource = None
        return None

    geometry = feature.GetGeometryRef().Clone()
    datasource = None

    geometry.Transform(_to_wgs84())
    points = geometry.GetPoints() or []
    if not points:
        return None
    return {"type": "LineString",
            "coordinates": [[float(x), float(y)] for x, y, *_ in points]}


def corridor_paths(model: Model) -> dict[int, Path]:
    """tour_fid -> its corridor .tif, off the `<fid>_<slug>.tif` naming."""
    return exposure.corridors_by_fid(model.corridors)
