from __future__ import annotations

import os
from pathlib import Path
from azure.storage.blob import BlobServiceClient, ContentSettings
from azure.core.exceptions import ResourceExistsError

def _bsc() -> BlobServiceClient:
    cs = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
    if not cs:
        raise RuntimeError("AZURE_STORAGE_CONNECTION_STRING is not set")
    return BlobServiceClient.from_connection_string(cs)

def upload_file(
    *,
    container: str,
    blob_name: str,
    local_path: str | Path,
    content_type: str,
    cache_control: str | None = None,
) -> str:
    p = Path(local_path)
    bsc = _bsc()

    cc = bsc.get_container_client(container)
    try:
        cc.create_container()
    except ResourceExistsError:
        pass

    client = bsc.get_blob_client(container=container, blob=blob_name)
    settings = ContentSettings(content_type=content_type, cache_control=cache_control)

    with p.open("rb") as f:
        client.upload_blob(f, overwrite=True, content_settings=settings)

    return client.url


def get_blob_url(*, container: str, blob_name: str) -> str:
    client = _bsc().get_blob_client(container=container, blob=blob_name)
    return client.url
