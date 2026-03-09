from __future__ import annotations

import os
from pathlib import Path

from backend.storage.base import CorridorStorage
from backend.storage.blob_helpers import upload_file, delete_prefix, get_blob_url

class AzureBlobStorage(CorridorStorage):
    def __init__(self, *, container: str | None = None):
        self.container = container or os.environ.get("BLOB_OUTPUTS_CONTAINER", "outputs")

    def put_corridor_png(self, *, run_id: str, png_path: Path) -> str:
        blob_name = f"runs_output/{run_id}/{png_path.name}"
        return upload_file(
            container=self.container,
            blob_name=blob_name,
            local_path=png_path,
            content_type="image/png",
            cache_control="no-store",
        )

    def put_corridor_tif(self, *, run_id: str, tif_path: Path) -> str | None:
        blob_name = f"runs_output/{run_id}/{tif_path.name}"
        return upload_file(
            container=self.container,
            blob_name=blob_name,
            local_path=tif_path,
            content_type="image/tiff",
            cache_control="no-store",
        )

    def put_route_geojson(self, *, run_id: str, geojson_path: Path) -> str:
        blob_name = f"runs_output/{run_id}/{geojson_path.name}"
        return upload_file(
            container=self.container,
            blob_name=blob_name,
            local_path=geojson_path,
            content_type="application/geo+json",
            cache_control="no-store",
        )

    def put_route_gpx(self, *, run_id: str, gpx_path: Path) -> str:
        blob_name = f"runs_output/{run_id}/{gpx_path.name}"
        return upload_file(
            container=self.container,
            blob_name=blob_name,
            local_path=gpx_path,
            content_type="application/gpx+xml",
            cache_control="no-store",
        )

    def get_route_geojson_url(self, *, run_id: str) -> str:
        blob_name = f"runs_output/{run_id}/route.geojson"
        return get_blob_url(container=self.container, blob_name=blob_name)

    def get_route_gpx_url(self, *, run_id: str) -> str:
        blob_name = f"runs_output/{run_id}/route.gpx"
        return get_blob_url(container=self.container, blob_name=blob_name)

    def delete_run(self, *, run_id: str) -> None:
        # delete everything under runs_output/<run_id>/
        delete_prefix(container=self.container, prefix=f"runs_output/{run_id}/")