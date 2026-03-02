from __future__ import annotations
from pathlib import Path
import os

from backend.storage.base import CorridorStorage
from backend.storage.blob_outputs import upload_tif

class AzureBlobStorage(CorridorStorage):
    def __init__(self, *, container: str | None = None):
        self.container = container or os.environ.get("BLOB_OUTPUTS_CONTAINER", "outputs")

    def put_corridor(self, *, run_name: str, tif_path: Path) -> str:
        blob_name = f"runs/{run_name}/{tif_path.name}"
        url = upload_tif(self.container, blob_name, tif_path)

        # optional cleanup (keep your current behavior)
        try:
            tif_path.unlink(missing_ok=True)
        except Exception:
            pass

        return url