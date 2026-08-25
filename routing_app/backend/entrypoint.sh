#!/bin/sh
set -e

# Find GRASS install path and python module path
GISBASE="$(grass --config path)"
GRASS_PYTHONPATH="$(grass --config python_path)"

export GISBASE
export PYTHONPATH="${GRASS_PYTHONPATH}:${PYTHONPATH}"
export PATH="${GISBASE}/bin:${GISBASE}/scripts:${PATH}"

export GRASS_DB="${GRASS_DB:-/root/grassdata}"
mkdir -p "$GRASS_DB"

exec "$@"