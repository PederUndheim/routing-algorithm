r"""The local HTTP server behind the corridor review.

Standard library only, for the same reason app.backend.server is: the
QGIS-bundled Python has no FastAPI, and this should run with nothing to
install. The front end is one hand-written page with Leaflet from a CDN, so
there is no build step either - which matters, because the React app beside
this one cannot be built on every machine that needs to review corridors.

    & "C:\Program Files\QGIS 4.2.0\bin\python-qgis.bat" -m skimap.corridor_review serve

    GET  /                        the review page
    GET  /static/<file>           its css and js
    GET  /api/session             models, exposure classes, progress
    GET  /api/tours               every tour, with its verdict if it has one
    GET  /api/tour/<fid>          one tour: a panel per model, plus geometry
    POST /api/verdict             record a pick, get the next fid back
    POST /api/clear               drop a verdict
    POST /api/flag                mark a tour as needing work in tours.gpkg
    GET  /corridor/<model>/<fid>.png   one corridor overlay, rendered on demand
    GET  /tracks/<fid>.json       where this tour's GPS tracks go, or none
    GET  /tracks/<fid>.png        that overlay

Everything the page needs about a tour arrives in one /api/tour call, so
paging is one request plus one image per model. The images are cached to
disk on first render (see render.cached_png), which is what makes the second
pass through 842 tours quick.

Errors come back as {"message": ...} with a 4xx, the way the app's do.
"""

from __future__ import annotations

import json
import re
import sys
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional

from skimap import config
from skimap.corridor_review import models as models_module
from skimap.corridor_review import render, sources
from skimap.corridor_review.store import LADDER, Store

STATIC = Path(__file__).resolve().parent / "static"

# A verdict is a few hundred bytes. Anything larger is not ours, and reading
# it would only be a way to be handed an unbounded body.
MAX_BODY_BYTES = 16 * 1024

# Anchored and character-classed, so nothing reaching the filesystem can hold
# a separator or a "..". The whole path is matched, not searched.
CORRIDOR_PATH = re.compile(r"/corridor/(?P<model>[A-Za-z0-9_.-]{1,64})/(?P<fid>\d{1,9})\.png")
TOUR_PATH = re.compile(r"/api/tour/(?P<fid>\d{1,9})")
STATIC_PATH = re.compile(r"/static/(?P<name>[A-Za-z0-9_.-]{1,64})")

# Tracks are fetched separately from the tour, not folded into it: building
# the overlay warps a national raster, and a reviewer who leaves the layer
# off should never pay for one. Off by default for that reason.
TRACKS_JSON = re.compile(r"/tracks/(?P<fid>\d{1,9})\.json")
TRACKS_PNG = re.compile(r"/tracks/(?P<fid>\d{1,9})\.png")

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".png": "image/png",
    ".svg": "image/svg+xml",
}


class Review:
    """Everything read once at startup, so a request touches no GeoPackage.

    842 tours times a handful of models is a few thousand rows; holding them
    is a few megabytes and saves reopening three GeoPackages per keystroke.
    The corridors are held as paths, not rasters - those are rendered on
    demand and cached as PNGs.
    """

    def __init__(self, config_path: Optional[Path] = None,
                 review_path: Optional[Path] = None):
        self.config = models_module.load(config_path)
        self.store = Store(review_path)
        self.lock = threading.Lock()

        print(f"review round {self.store.round}: {len(self.config.models)} models")
        for model in self.config.models:
            sources.ensure_scored(model)

        self.rows = {m.name: sources.model_rows(m) for m in self.config.models}
        self.corridors = {m.name: sources.corridor_paths(m) for m in self.config.models}
        self.tours = sources.tour_order()
        self.index = {tour["fid"]: i for i, tour in enumerate(self.tours)}

        # Which tours a non-main group can actually show. A group built for a
        # handful of tours has nothing to say about the rest, and the page
        # greys its switch rather than offering three empty maps - so the
        # answer has to be known per tour, not per group.
        self.group_fids = {
            group: {fid for model in members
                    for fid in set(self.rows[model.name]) | set(self.corridors[model.name])}
            for group, _, members in self.config.groups()
            if group != models_module.MAIN_GROUP
        }

        for group, label, members in self.config.groups():
            if group != models_module.MAIN_GROUP:
                print(f"  group {group!r} ({label}) - "
                      f"{len(self.group_fids[group])} tours")
            for model in members:
                print(f"  {model.name:16s} {len(self.rows[model.name]):4d} routes, "
                      f"{len(self.corridors[model.name]):4d} corridors")
        print(f"  {len(self.tours)} tours, {self._reviewed()} already reviewed")
        orphaned = len(self.store.verdicts) - self._reviewed()
        if orphaned:
            print(f"  ({orphaned} verdicts on tours no longer in tours.gpkg, "
                  f"kept in review.json but not counted)")

    def _reviewed(self) -> int:
        """Verdicts on tours that still exist. See Store.current."""
        return len(self.store.current(self.index))

    # --- payloads --------------------------------------------------------

    def session(self) -> dict[str, Any]:
        return {
            "round": self.store.round,
            "note": self.config.note,
            "models": [{"name": m.name, "label": m.label, "group": m.group}
                       for m in self.config.models],
            # The page builds one bench of panels per group and swaps between
            # them, so it needs them grouped rather than flat - and it must
            # not have to guess which one to open on. main is first.
            "groups": [{"name": group, "label": label,
                        "models": [{"name": m.name, "label": m.label} for m in members],
                        "tours": len(self.group_fids.get(group, self.index))}
                       for group, label, members in self.config.groups()],
            "classes": [{"from": lower, "colour": colour}
                        for lower, colour in config.EXPOSURE_CLASSES],
            "ladder": list(LADDER),
            "total": len(self.tours),
            "reviewed": self._reviewed(),
            "needs_fix": len(self.store.fix_list(self.index)),
            "by_model": self.store.counts_by_model(self.index),
            "by_colour": self.store.counts_by_colour(self.index),
        }

    def tour_list(self) -> list[dict[str, Any]]:
        out = []
        for tour in self.tours:
            verdict = self.store.get(tour["fid"])
            out.append({
                "fid": tour["fid"],
                "name": tour["name"],
                "model": verdict["model"] if verdict else None,
                "colour": verdict["colour"] if verdict else None,
                "shift": verdict["shift"] if verdict else 0,
                "needs_fix": self.store.fix(tour["fid"]) is not None,
                # The non-main groups with something to show for this tour.
                # Drives both the greyed switch and the list's own filter.
                "groups": sorted(g for g, fids in self.group_fids.items()
                                 if tour["fid"] in fids),
            })
        return out

    def tour(self, fid: int) -> dict[str, Any]:
        if fid not in self.index:
            raise KeyError(f"no tour with fid {fid}")
        position = self.index[fid]
        name = self.tours[position]["name"]

        panels = []
        for model in self.config.models:
            row = self.rows[model.name].get(fid)
            corridor = self.corridors[model.name].get(fid)
            if row is None and corridor is None:
                continue
            colour = (row or {}).get("colour") or "blue"
            panels.append({
                "model": model.name,
                "label": model.label,
                "group": model.group,
                "colour": colour,
                "has_corridor": corridor is not None,
                "png": f"/corridor/{model.name}/{fid}.png" if corridor else None,
                "bounds": (render.cached_bounds(model.name, fid, corridor)
                           if corridor else None),
                "route": sources.route_geojson(model, fid),
                "metrics": {k: (row or {}).get(k) for k in sources.ROUTE_FIELDS
                            if k != "colour"},
            })

        verdict = self.store.get(fid)
        return {
            "fid": fid,
            "name": name,
            "position": position,
            "total": len(self.tours),
            "prev": self.tours[position - 1]["fid"] if position > 0 else None,
            "next": (self.tours[position + 1]["fid"]
                     if position + 1 < len(self.tours) else None),
            "panels": panels,
            "groups": sorted({panel["group"] for panel in panels}),
            "verdict": verdict,
            "needs_fix": self.store.fix(fid),
        }

    def next_unreviewed(self, after: int) -> Optional[int]:
        """The next tour with no verdict, wrapping once, or None if done."""
        if after not in self.index:
            return None
        start = self.index[after]
        order = list(range(start + 1, len(self.tours))) + list(range(0, start + 1))
        for position in order:
            fid = self.tours[position]["fid"]
            if self.store.get(fid) is None:
                return fid
        return None

    # --- writes ----------------------------------------------------------

    def record(self, body: dict[str, Any]) -> dict[str, Any]:
        fid = int(body["fid"])
        model_name = str(body["model"])
        if fid not in self.index:
            raise KeyError(f"no tour with fid {fid}")
        if self.config.model(model_name) is None:
            raise KeyError(f"{model_name!r} is not a configured model")

        row = self.rows[model_name].get(fid) or {}
        computed = row.get("colour") or "blue"

        with self.lock:
            verdict = self.store.record(
                fid, model=model_name, colour_computed=computed,
                shift=int(body.get("shift", 0)), note=str(body.get("note", "")),
            )
        return {
            "verdict": verdict,
            "next": self.next_unreviewed(fid),
            "reviewed": self._reviewed(),
        }

    def flag(self, body: dict[str, Any]) -> dict[str, Any]:
        """Mark, or unmark, this tour as needing work in tours.gpkg.

        Does not advance to the next tour and does not touch the verdict -
        noticing a bad tour is not the same act as judging its corridors, and
        you often want to do both on the same screen.
        """
        fid = int(body["fid"])
        if fid not in self.index:
            raise KeyError(f"no tour with fid {fid}")
        with self.lock:
            entry = self.store.set_fix(fid, bool(body.get("on", True)),
                                       str(body.get("note", "")))
        return {"needs_fix": entry, "count": len(self.store.fix_list(self.index))}

    def clear(self, body: dict[str, Any]) -> dict[str, Any]:
        fid = int(body["fid"])
        with self.lock:
            dropped = self.store.clear(fid)
        return {"cleared": dropped, "reviewed": self._reviewed()}

    def _tracks(self, fid: int) -> Optional[tuple[Path, dict]]:
        if fid not in self.index:
            raise KeyError(f"no tour with fid {fid}")
        tifs = [self.corridors[m.name][fid] for m in self.config.models
                if fid in self.corridors[m.name]]
        return render.tracks_overlay(fid, tifs)

    def tracks(self, fid: int) -> dict[str, Any]:
        """Where this tour's track overlay goes, or that there is none.

        An empty answer is a real one - "nobody has been here" is information
        about the tour, so the page says so rather than showing a layer with
        nothing in it. Uncommon, since tours are digitized on the same ground
        the tracks are on, but it has to be said rather than looked like a
        layer that failed to load.
        """
        result = self._tracks(fid)
        if result is None:
            return {"empty": True}
        _, bounds = result
        return {"png": f"/tracks/{fid}.png", "bounds": bounds}

    def tracks_png(self, fid: int) -> Path:
        result = self._tracks(fid)
        if result is None:
            raise KeyError(f"no track data near tour {fid}")
        return result[0]

    def corridor_png(self, model_name: str, fid: int) -> Path:
        model = self.config.model(model_name)
        if model is None:
            raise KeyError(f"{model_name!r} is not a configured model")
        corridor = self.corridors[model_name].get(fid)
        if corridor is None:
            raise KeyError(f"{model_name} has no corridor for tour {fid}")
        colour = (self.rows[model_name].get(fid) or {}).get("colour") or "blue"
        png, _ = render.cached_png(model_name, fid, corridor, colour)
        return png


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "skimap-corridor-review"
    sys_version = ""

    review: Review   # set on the server, read through the instance

    # --- plumbing --------------------------------------------------------

    def log_message(self, fmt: str, *args: Any) -> None:
        # One line per keystroke is noise; failures are logged where they are
        # caught instead.
        pass

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def _error(self, status: int, message: str) -> None:
        self._json({"message": message}, status=status)

    def _file(self, path: Path) -> None:
        if not path.is_file():
            self._error(404, f"no such file: {path.name}")
            return
        self._send(200, path.read_bytes(),
                   CONTENT_TYPES.get(path.suffix, "application/octet-stream"))

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            raise ValueError("empty request body")
        if length > MAX_BODY_BYTES:
            raise ValueError("request body is too large")
        return json.loads(self.rfile.read(length).decode("utf-8"))

    # --- routes ----------------------------------------------------------

    def do_GET(self) -> None:      # noqa: N802 - BaseHTTPRequestHandler's name
        try:
            path = self.path.split("?", 1)[0]

            if path in ("/", "/index.html"):
                self._file(STATIC / "index.html")
                return

            match = STATIC_PATH.fullmatch(path)
            if match:
                self._file(STATIC / match.group("name"))
                return

            if path == "/api/session":
                self._json(self.review.session())
                return

            if path == "/api/tours":
                self._json(self.review.tour_list())
                return

            match = TOUR_PATH.fullmatch(path)
            if match:
                self._json(self.review.tour(int(match.group("fid"))))
                return

            match = CORRIDOR_PATH.fullmatch(path)
            if match:
                png = self.review.corridor_png(match.group("model"),
                                               int(match.group("fid")))
                self._file(png)
                return

            match = TRACKS_JSON.fullmatch(path)
            if match:
                self._json(self.review.tracks(int(match.group("fid"))))
                return

            match = TRACKS_PNG.fullmatch(path)
            if match:
                self._file(self.review.tracks_png(int(match.group("fid"))))
                return

            self._error(404, f"no route for {path}")
        except KeyError as problem:
            self._error(404, str(problem))
        except Exception as problem:                       # noqa: BLE001
            traceback.print_exc()
            self._error(500, f"{type(problem).__name__}: {problem}")

    def do_POST(self) -> None:     # noqa: N802
        try:
            path = self.path.split("?", 1)[0]
            if path == "/api/verdict":
                self._json(self.review.record(self._body()))
                return
            if path == "/api/clear":
                self._json(self.review.clear(self._body()))
                return
            if path == "/api/flag":
                self._json(self.review.flag(self._body()))
                return
            self._error(404, f"no route for {path}")
        except (KeyError, ValueError) as problem:
            self._error(400, str(problem))
        except Exception as problem:                       # noqa: BLE001
            traceback.print_exc()
            self._error(500, f"{type(problem).__name__}: {problem}")


def serve(host: str = "127.0.0.1", port: int = 8765, *,
          config_path: Optional[Path] = None,
          review_path: Optional[Path] = None) -> None:
    # A server's stdout is a pipe more often than a console, and a block
    # buffer means the startup report - which models loaded, how many
    # corridors each has - arrives only once the process is killed. That is
    # exactly the information you need before deciding to trust the page.
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except (AttributeError, ValueError):
        pass

    review = Review(config_path, review_path)

    handler = type("BoundHandler", (Handler,), {"review": review})
    server = ThreadingHTTPServer((host, port), handler)
    # A held connection should not keep the process alive after Ctrl-C.
    server.daemon_threads = True

    print(f"\nreview at http://{host}:{port}/   (Ctrl-C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()
