from __future__ import annotations
from fastapi import Request

from backend.api.runtime import get_settings
from backend.storage.base import CorridorStorage
from backend.storage.local_outputs import LocalOutputsStorage
from backend.storage.prod_outputs import AzureBlobStorage

def get_corridor_storage(request: Request) -> CorridorStorage:
    settings = get_settings()

    if settings.enable_blob_upload:
        import os
        if not os.getenv("AZURE_STORAGE_CONNECTION_STRING"):
            raise RuntimeError("APP_ENV=prod but AZURE_STORAGE_CONNECTION_STRING is missing")
        return AzureBlobStorage()

    # Local only
    output_root = request.app.state.output_root
    base_url = str(request.base_url).rstrip("/")
    return LocalOutputsStorage(output_root=output_root, base_url=base_url)