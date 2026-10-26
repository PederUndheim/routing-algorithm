"""NVE's avalanche forecast regions, and which one a corridor belongs to.

The regions are NVE's varslingsregioner (data/area-data), 46 polygons that
between them cover the mainland and Svalbard: the A regions get a daily
forecast, the B regions do not. Both kinds are regions here - a corridor in
Hedmark belongs to Hedmark, not to a catch-all - and `OTHER` only catches
a corridor outside every polygon, out to sea or over the border.

Region order is NVE's own numbering, omrID 3001 - 3046, which runs north to
south: Svalbard, Finnmark, Troms, Nordland, Trondelag, Moere, Fjordane,
Sogn, Hordaland, Telemark and on round the south. It is the order varsom.no
lists them in, so it is the one a reader already knows.

A corridor belongs to the region holding most of its route. 34 tours start
in one region and top out in another; the start alone would file a long
tour under the valley it leaves from, the summit alone under a ridge it
barely crosses into.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from osgeo import gdal, ogr, osr

from skimap import config

gdal.UseExceptions()
ogr.UseExceptions()


@dataclass(frozen=True)
class Region:
    id: Optional[int]       # NVE omrID; None for OTHER
    name: str
    kind: str               # "A" forecast, "B" not forecast, "" for OTHER
    rank: int               # 1 = first in order
    wkb: bytes = b""        # EPSG:25833, 2D

    @property
    def geometry(self) -> Optional[ogr.Geometry]:
        return ogr.CreateGeometryFromWkb(self.wkb) if self.wkb else None


def load(path: Path) -> list[Region]:
    """Every region in NVE order, then OTHER."""
    options = [f"ENCODING={_encoding(path)}"] if _encoding(path) else []
    datasource = gdal.OpenEx(str(path), gdal.OF_VECTOR, open_options=options)
    if datasource is None:
        raise SystemExit(f"Cannot open the forecast regions at {path}")
    layer = datasource.GetLayer(0)

    target = osr.SpatialReference()
    target.ImportFromEPSG(config.CRS_EPSG)
    target.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    # NVE ships them in WGS84 / UTM 33, the tours are ETRS89 / UTM 33. The
    # two differ by well under a metre in Norway; transforming anyway costs
    # nothing and keeps the rule that everything here is EPSG:25833.
    source = layer.GetSpatialRef()
    transform = None
    if source is not None and not source.IsSame(target):
        source.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        transform = osr.CoordinateTransformation(source, target)

    rows = []
    for feature in layer:
        geometry = feature.GetGeometryRef().Clone()
        geometry.FlattenTo2D()      # the shapefile is PolygonZ
        if transform is not None:
            geometry.Transform(transform)
        if not geometry.IsValid():
            geometry = geometry.MakeValid()
        rows.append((int(feature.GetField("omrID")),
                     str(feature.GetField("omrNavn") or ""),
                     str(feature.GetField("regionType") or ""),
                     geometry.ExportToWkb()))
    datasource = None

    rows.sort(key=lambda row: row[0])
    regions = [Region(id=rid, name=name, kind=kind, rank=rank, wkb=wkb)
               for rank, (rid, name, kind, wkb) in enumerate(rows, start=1)]
    return regions + [other(len(regions) + 1)]


def _encoding(path: Path) -> str:
    """A shapefile's .cpg as GDAL wants it. NVE's says "ANSI 1252", which
    GDAL does not recognise, and then hands back the raw bytes - every
    region with an o-slash in it comes out mangled."""
    cpg = path.with_suffix(".cpg")
    if path.suffix.lower() != ".shp" or not cpg.is_file():
        return ""
    text = cpg.read_text(encoding="ascii", errors="ignore").strip()
    digits = text.split()[-1] if text else ""
    return f"CP{digits}" if digits.isdigit() else text


def other(rank: int) -> Region:
    return Region(id=None, name="other", kind="", rank=rank)


class Assigner:
    """Region lookups against the polygons, each parsed once."""

    def __init__(self, regions: list[Region]):
        self.regions = regions
        self._shapes = [(r, r.geometry) for r in regions if r.wkb]
        self._envelopes = [g.GetEnvelope() for _, g in self._shapes]
        self.other = next(r for r in regions if r.id is None)

    def by_length(self, lines: Iterable[ogr.Geometry]) -> Region:
        """The region holding the most of `lines`, OTHER if none holds any.
        A tie goes to the region first in order."""
        share: dict[int, float] = {}
        for line in lines:
            minx, maxx, miny, maxy = line.GetEnvelope()
            for i, ((region, shape), env) in enumerate(zip(self._shapes, self._envelopes)):
                if env[1] < minx or env[0] > maxx or env[3] < miny or env[2] > maxy:
                    continue
                inside = line.Intersection(shape)
                if inside is not None and not inside.IsEmpty():
                    share[i] = share.get(i, 0.0) + inside.Length()
        if not share or max(share.values()) <= 0:
            return self.other
        best = max(share, key=lambda i: (share[i], -i))
        return self._shapes[best][0]
