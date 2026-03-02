from __future__ import annotations
from pathlib import Path
from abc import ABC, abstractmethod

class CorridorStorage(ABC):
    @abstractmethod
    def put_corridor(self, *, run_name: str, tif_path: Path) -> str:
        """Return a URL the frontend can fetch."""
        raise NotImplementedError