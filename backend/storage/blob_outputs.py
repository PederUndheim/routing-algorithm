from __future__ import annotations

import os
from pathlib import Path
from azure.storage.blob import BlobServiceClient, ContentSettings

def _bsc() -> BlobServiceClient:
    cs = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
    if not cs:
        raise RuntimeError("AZURE_STORAGE_CONNECTION_STRING is not set")
    return BlobServiceClient.from_connection_string(cs)

def upload_tif(container: str, blob_name: str, local_path: str | Path) -> str:
    p = Path(local_path)
    client = _bsc().get_blob_client(container=container, blob=blob_name)

    with p.open("rb") as f:
        client.upload_blob(
            f,
            overwrite=True,
            content_settings=ContentSettings(content_type="image/tiff"),
        )
    return client.url