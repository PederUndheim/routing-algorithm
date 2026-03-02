from __future__ import annotations
from pathlib import Path
from urllib.parse import quote

from backend.storage.base import CorridorStorage

class LocalOutputsStorage(CorridorStorage):
    def __init__(self, *, output_root: Path, base_url: str):
        self.output_root = output_root.resolve()
        self.base_url = base_url.rstrip("/")

    def _safe_rel(self, p: Path) -> str:
        p = p.resolve()
        if self.output_root not in p.parents and p != self.output_root:
            raise RuntimeError("Output path outside OUTPUT_ROOT")
        return str(p.relative_to(self.output_root))

    def put_corridor(self, *, run_name: str, tif_path: Path) -> str:
        rel = self._safe_rel(tif_path)
        return f"{self.base_url}/outputs/{quote(rel)}"