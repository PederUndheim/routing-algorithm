from __future__ import annotations
from dataclasses import dataclass
import os

@dataclass(frozen=True)
class RuntimeSettings:
    env: str  # "local" | "prod"
    enable_blob_upload: bool

def get_settings() -> RuntimeSettings:
    env = (os.getenv("APP_ENV") or "local").lower()

    if env in {"local", "dev", "development"}:
        return RuntimeSettings(env="local", enable_blob_upload=False)

    if env in {"prod", "production"}:
        return RuntimeSettings(env="prod", enable_blob_upload=True)

    # default safe behavior
    return RuntimeSettings(env="local", enable_blob_upload=False)