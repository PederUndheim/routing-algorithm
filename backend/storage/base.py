from __future__ import annotations
from pathlib import Path
from abc import ABC, abstractmethod

class CorridorStorage(ABC):
    @abstractmethod
    def put_corridor_png(self, *, run_id: str, png_path: Path) -> str:
        raise NotImplementedError

    @abstractmethod
    def put_corridor_tif(self, *, run_id: str, tif_path: Path) -> str | None:
        """Optional, return url or None if you do not upload."""
        raise NotImplementedError

    @abstractmethod
    def put_route_geojson(self, *, run_id: str, geojson_path: Path) -> str:
        raise NotImplementedError

    @abstractmethod
    def put_route_gpx(self, *, run_id: str, gpx_path: Path) -> str:
        raise NotImplementedError

    @abstractmethod
    def get_route_geojson_url(self, *, run_id: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def get_route_gpx_url(self, *, run_id: str) -> str:
        raise NotImplementedError
    
    @abstractmethod
    def delete_run(self, *, run_id: str) -> None:
        """Best effort delete."""
        raise NotImplementedError