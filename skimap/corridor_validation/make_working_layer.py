"""Make the layer ski tours are assigned in: the uphill legs, two empty fields.

Copies the `uphill` layer of up_down_tracks.gpkg into the validation
geodatabase as `uphill_working`, with TOUR_ID and TOUR_NAME left empty to
be filled in ArcGIS. track_fid and leg_no come along so an assigned leg can
always be traced back to its recording and its place in that day.

Run once, from skimap/:

    python -m corridor_validation.make_working_layer

It refuses to run if the layer already exists: from the first edit on it
holds hand work that no rerun could recreate. Close the geodatabase in
ArcGIS first - GDAL does not honour Esri's lock files.
"""

from __future__ import annotations

from osgeo import gdal, ogr

from corridor_validation.up_down_tracks import UP_DOWN, VALIDATION

gdal.UseExceptions()
ogr.UseExceptions()

GDB = VALIDATION / "corridor_validation_tracks.gdb"
LAYER = "uphill_working"


def main() -> None:
    if any(GDB.glob("*.lock")):
        raise SystemExit(f"{GDB.name} is open in ArcGIS (lock files present); close it first")

    src_ds = gdal.OpenEx(str(UP_DOWN), gdal.OF_VECTOR)
    src = src_ds.GetLayerByName("uphill")
    dst_ds = gdal.OpenEx(str(GDB), gdal.OF_VECTOR | gdal.OF_UPDATE)
    if dst_ds.GetLayerByName(LAYER) is not None:
        raise SystemExit(f"{LAYER} already exists in {GDB.name}; it holds hand edits, not overwriting")

    dst = dst_ds.CreateLayer(LAYER, srs=src.GetSpatialRef(), geom_type=ogr.wkbLineString)
    for name, kind, width in (("TOUR_ID", ogr.OFTInteger, 0), ("TOUR_NAME", ogr.OFTString, 255),
                              ("track_fid", ogr.OFTInteger, 0), ("leg_no", ogr.OFTInteger, 0)):
        field = ogr.FieldDefn(name, kind)
        if width:
            field.SetWidth(width)
        dst.CreateField(field)

    defn = dst.GetLayerDefn()
    dst.StartTransaction()
    for n, f in enumerate(src, 1):
        out = ogr.Feature(defn)
        out.SetGeometry(f.GetGeometryRef())
        out.SetField("track_fid", f.GetField("track_fid"))
        out.SetField("leg_no", f.GetField("leg_no"))
        dst.CreateFeature(out)
    dst.CommitTransaction()
    print(f"wrote {n} uphill legs to {GDB.name}/{LAYER}")


if __name__ == "__main__":
    main()
