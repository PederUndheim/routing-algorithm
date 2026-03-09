from __future__ import annotations
from pathlib import Path
from urllib.parse import quote
import shutil

from backend.storage.base import CorridorStorage

class LocalOutputsStorage(CorridorStorage):
    def __init__(self, *, output_root: Path, base_url: str):
        self.output_root = output_root.resolve()
        self.base_url = base_url.rstrip("/")

    def _safe_rel(self, p: Path) -> str:
        p = p.resolve()
        if self.output_root not in p.parents and p != self.output_root:
            raise RuntimeError("Output path outside output_root")
        return str(p.relative_to(self.output_root))

    def put_corridor_png(self, *, run_id: str, png_path: Path) -> str:
        rel = self._safe_rel(png_path)
        return f"{self.base_url}/outputs/{quote(rel)}"

    def put_corridor_tif(self, *, run_id: str, tif_path: Path) -> str | None:
        rel = self._safe_rel(tif_path)
        return f"{self.base_url}/outputs/{quote(rel)}"

    def put_route_geojson(self, *, run_id: str, geojson_path: Path) -> str:
        rel = self._safe_rel(geojson_path)
        return f"{self.base_url}/outputs/{quote(rel)}"

    def put_route_gpx(self, *, run_id: str, gpx_path: Path) -> str:
        rel = self._safe_rel(gpx_path)
        return f"{self.base_url}/outputs/{quote(rel)}"

    def get_route_geojson_url(self, *, run_id: str) -> str:
        rel = quote(f"runs_output/{run_id}/route/route.geojson")
        return f"{self.base_url}/outputs/{rel}"

    def get_route_gpx_url(self, *, run_id: str) -> str:
        rel = quote(f"runs_output/{run_id}/route/route.gpx")
        return f"{self.base_url}/outputs/{rel}"
    
    def delete_run(self, *, run_id: str) -> None:
        run_dir = (self.output_root / "runs_output" / run_id).resolve()
        if self.output_root not in run_dir.parents:
            return
        shutil.rmtree(run_dir, ignore_errors=True)