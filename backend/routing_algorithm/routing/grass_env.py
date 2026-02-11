import os
import sys

GISBASE = "/Applications/GRASS-8.4.app/Contents/Resources"

GRASS_DB = os.path.expanduser("~/grassdata")
GRASS_LOCATION = "routing_algorithm"
GRASS_MAPSET = "PERMANENT"

def setup_grass_python_path():
    os.environ["GISBASE"] = GISBASE
    os.environ["PATH"] += os.pathsep + os.path.join(GISBASE, "bin")
    os.environ["PATH"] += os.pathsep + os.path.join(GISBASE, "scripts")

    grass_python = os.path.join(GISBASE, "etc", "python")
    if grass_python not in sys.path:
        sys.path.append(grass_python)