import os
import sys
import subprocess

def _grass_config(key: str) -> str | None:
    try:
        out = subprocess.check_output(["grass", "--config", key], text=True).strip()
        return out or None
    except Exception:
        return None

# Prefer env vars, then ask grass, then fallback to Mac path (dev only)
GISBASE = (
    os.environ.get("GISBASE")
    or _grass_config("path")
    or "/Applications/GRASS-8.4.app/Contents/Resources"
)

GRASS_DB = os.environ.get("GRASS_DB") or os.path.expanduser("~/grassdata")
GRASS_LOCATION = os.environ.get("GRASS_LOCATION", "routing_algorithm")
GRASS_MAPSET = os.environ.get("GRASS_MAPSET", "PERMANENT")

def setup_grass_python_path() -> None:
    os.environ["GISBASE"] = GISBASE

    # Ensure grass binaries are reachable
    os.environ["PATH"] = os.pathsep.join(
        [
            os.path.join(GISBASE, "bin"),
            os.path.join(GISBASE, "scripts"),
            os.environ.get("PATH", ""),
        ]
    )

    # Prefer grass --config python_path if available
    grass_python = os.environ.get("GRASS_PYTHONPATH") or _grass_config("python_path")

    # Fallback used by many distros
    if not grass_python:
        grass_python = os.path.join(GISBASE, "etc", "python")

    if grass_python and grass_python not in sys.path:
        sys.path.append(grass_python)