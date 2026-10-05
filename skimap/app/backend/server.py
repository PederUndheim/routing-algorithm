r"""The local HTTP server behind the skimap test app.

Standard library only. The QGIS-bundled Python has no FastAPI and, like the
rest of skimap, this should run with nothing to install. A handful of
endpoints is not enough to earn a dependency.

Run it from the project directory - `skimap/`, the one holding `skimap/`,
`app/` and `data/`:

    & "C:\Program Files\QGIS 4.2.0\bin\python-qgis.bat" -m app.backend.server

    GET  /health              {"status": "ok"}, once GRASS is up
    POST /route               {"start": {"lat": .., "lng": ..}, "end": {...}}
                              -> the line as WGS84 GeoJSON, its length and
                                 cost, and where to fetch its corridor
    GET  /corridor/<id>.png   that corridor, as an overlay for the map
    POST /crux                {"route": <GeoJSON LineString, WGS84>}
                              -> its Danger zones and Cruxes - see
                                 skimap.crux for the shape

Errors come back as {"message": ...} with a 4xx, which is what the front end
puts in its error toast.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app.backend import service
from skimap import crux

# A start/end pair is a couple of hundred bytes. Anything larger is not ours,
# and reading it would only be a way to be handed an unbounded body.
MAX_ROUTE_BODY_BYTES = 8 * 1024

# A route to find cruxes on is a whole line, and an uploaded Route recorded
# over a long day is tens of thousands of points - around a megabyte as GeoJSON.
MAX_CRUX_BODY_BYTES = 4 * 1024 * 1024

# Anchored and hex-only, so nothing that reaches the filesystem can contain a
# separator or a "..". The whole path is matched, not searched.
CORRIDOR_PATH = re.compile(r"/corridor/(?P<id>[0-9a-f]{12})\.png")

# Vite serves the page from :5173 and this answers on :8000, so every request
# is cross-origin. Locally anything goes; the deployed copy sets this to the
# GitHub Pages origin, so only the published front end can call it.
ALLOWED_ORIGIN = os.environ.get("SKIMAP_ALLOWED_ORIGIN", "*")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "skimap"
    sys_version = ""

    # --- endpoints ---

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send(200, {"status": "ok"})
            return

        corridor = CORRIDOR_PATH.fullmatch(self.path)
        if corridor:
            self._send_corridor(corridor.group("id"))
            return

        self._send(404, {"message": f"No such endpoint: GET {self.path}"})

    def _send_corridor(self, corridor_id: str) -> None:
        """One corridor PNG, by the id the route it came from was given.

        The id is matched against CORRIDOR_PATH before it gets here, so it is
        twelve hex digits and cannot climb out of the scratch directory.
        """
        path = service.corridor_file(corridor_id)
        if not path.is_file():
            # Expected, not exceptional: only the last few are kept, so a
            # browser holding an older route's URL asks for one that is gone.
            self._send(404, {"message": "That corridor is no longer available."})
            return

        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(body)))
        # The id is unique per route, so the picture at a given URL never
        # changes and the browser need never ask twice.
        self.send_header("Cache-Control", "public, max-age=86400, immutable")
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        if self.path == "/route":
            self._post_route()
        elif self.path == "/crux":
            self._post_crux()
        else:
            self._send(404, {"message": f"No such endpoint: POST {self.path}"})

    def _post_route(self) -> None:
        try:
            payload = self._read_json(MAX_ROUTE_BODY_BYTES, "a start and an end")
            start = _point(payload, "start")
            end = _point(payload, "end")
        except ValueError as exc:
            self._send(400, {"message": str(exc)})
            return

        try:
            self._send(200, service.route(start, end))
        except Exception as exc:  # noqa: BLE001 - reported, the server stays up
            # The traceback goes to the console, the message to the browser:
            # GRASS's own errors ("NULL at end_0_app", and so on) already say
            # what went wrong in terms the front end can show.
            traceback.print_exc()
            self._send(400, {"message": f"{type(exc).__name__}: {exc}"})

    def _post_crux(self) -> None:
        """The Crux Identifier on one line.

        Outside service's GRASS lock: it only reads rasters, so it can run
        while a route is being computed rather than queue behind it.
        """
        try:
            payload = self._read_json(MAX_CRUX_BODY_BYTES, "a route")
            result = crux.identify(payload.get("route"))
        except ValueError as exc:
            self._send(400, {"message": str(exc)})
            return
        except Exception as exc:  # noqa: BLE001 - reported, the server stays up
            traceback.print_exc()
            self._send(400, {"message": f"{type(exc).__name__}: {exc}"})
            return
        self._send(200, result)

    def do_OPTIONS(self) -> None:
        # Preflight for the POST: the dev server is a different origin.
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    # --- plumbing ---

    def _read_json(self, max_bytes: int, holding: str) -> dict:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if length <= 0 or length > max_bytes:
            # The body stays unread, so whatever comes next on this
            # connection would be parsed starting inside it. Close instead.
            self.close_connection = True
            if length > max_bytes:
                raise ValueError(f"Body too large: this endpoint takes at most "
                                 f"{_size(max_bytes)}.")
            raise ValueError(f"Expected a JSON body holding {holding}.")
        try:
            payload = json.loads(self.rfile.read(length))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Body is not JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError("Body must be a JSON object.")
        return payload

    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGIN)
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def log_message(self, fmt: str, *args) -> None:
        print(f"  {fmt % args}", flush=True)


def _size(n_bytes: int) -> str:
    if n_bytes >= 1024 * 1024:
        return f"{n_bytes / (1024 * 1024):g} MB"
    return f"{n_bytes / 1024:g} KB"


def _point(payload: dict, key: str) -> tuple[float, float]:
    point = payload.get(key)
    if not isinstance(point, dict):
        raise ValueError(f'Missing {key!r}: expected {{"lat": .., "lng": ..}}')
    try:
        lat, lng = float(point["lat"]), float(point["lng"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"{key!r} needs a numeric lat and lng.") from exc
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
        raise ValueError(f"{key!r} is not a WGS84 coordinate: {lat}, {lng}")
    return lat, lng


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Serve the skimap test app's routing endpoint.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    # Bind first. Two of these sharing one GRASS mapset would write each
    # other's maps - the names are per-route, not per-process - so a second
    # copy has to fail before it touches GRASS, not after. Binding is what
    # detects it, and the constructor binds.
    server = ThreadingHTTPServer((args.host, args.port), Handler)

    # Nothing is answered until serve_forever, so a request that arrives in
    # the meantime waits in the backlog rather than being told "ok" early:
    # the port is open from here, but /health still means genuinely ready.
    print("Starting GRASS and linking the cost surface...", flush=True)
    service.start()
    print(f"  surface: {service.surface_name()}", flush=True)

    print(f"Ready on http://{args.host}:{args.port} - ctrl-c to stop", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
