r"""The validation app's API.

    & "C:\Program Files\QGIS 4.2.0\bin\python-qgis.bat" -m validation_app.backend.server

Locally that keeps verdicts in data/validation/ (see store.FileStore) with
access code and admin key both "dev". In Azure the environment sets:

    VALIDATION_TABLES_CONNECTION  storage account connection string -> TableStore,
                                  plus daily snapshots to blob (snapshots.py)
    VALIDATION_ACCESS_CODE        the code every reviewer types once
    VALIDATION_ADMIN_KEY          for assignments and backups; never in the page
    VALIDATION_ALLOWED_ORIGIN     the Pages origin, comma-separated if several
    VALIDATION_TRACKS_DIR         the track tiles, mounted from the Azure Files share

Plain http.server, like the corridor review's. It is stateless - everything
is in the store - so it scales past one replica without a second thought,
and four reviewers is four short requests at a time.

## Routes

    GET  /health
    GET  /api/users                      [access code] the user list
    GET  /api/state?user=ID              [access code] assignment + verdicts
    POST /api/verdict                    [access code] {user, corridor, patch, opId, clientTs}
    POST /api/reset                      [access code] {user: "test"} only
    PUT  /api/admin/assignments          [admin key]   {assignments: {user: [ids]}}
    GET  /api/admin/dump                 [admin key]   everything, for export and backup
    GET  /tiles/tracks/index.json        [access code] which track tiles exist
    GET  /tiles/tracks/Z/X/Y.png         [access code] one track tile

The track tiles are served from here rather than from Pages because Pages
is public and the GPS tracks are only to be shown behind the access code.
For the same reason they are not in git or the image: in Azure they come
from the file share, locally from data/validation/tracks.
A map tile is an <img>, which cannot send a header, so these take the code
as ?code= as well.

There is no export route: export.py builds the spreadsheet from a dump, on a
machine with the corridor index and openpyxl, which keeps both out of here.
"""

from __future__ import annotations

import argparse
import hmac
import json
import os
import re
import sys
import time
import traceback
import unicodedata
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from . import store as store_module
from .verdicts import TEST_USER, USER_IDS, USERS, validate_patch

DEFAULT_DATA = Path(__file__).resolve().parents[2] / "data" / "validation"
TRACKS = Path(os.environ.get("VALIDATION_TRACKS_DIR") or DEFAULT_DATA / "tracks")
TILE_PATH = re.compile(r"^/tiles/tracks/(\d{1,2})/(\d{1,7})/(\d{1,7})\.png$")
MAX_BODY = 256 * 1024
WRONG_CODE_DELAY_S = 1.0   # makes guessing the access code slow, not impossible


def _normal(code: str) -> str:
    """A code as typed, give or take case and surrounding space. NFC so that
    composed and decomposed letters (å as one character or a + ring) match."""
    return unicodedata.normalize("NFC", code.strip()).casefold()


class HttpError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


class Handler(BaseHTTPRequestHandler):
    store: store_module.Store
    access_code: str
    admin_key: str
    allowed_origins: set[str]
    snapshots: Any = None   # a snapshots.Snapshotter on Azure, told of every write

    def _written(self) -> None:
        if self.snapshots is not None:
            self.snapshots.mark()

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write(f"{self.address_string()} {fmt % args}\n")

    # --- plumbing ----------------------------------------------------------

    def _cors(self) -> None:
        origin = self.headers.get("Origin")
        if origin and (origin in self.allowed_origins or "*" in self.allowed_origins):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Headers",
                             "Content-Type, X-Access-Code, X-Admin-Key")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, OPTIONS")
            self.send_header("Access-Control-Max-Age", "86400")

    def _json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            raise HttpError(413, "body too large")
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError as e:
            raise HttpError(400, f"invalid JSON: {e}") from None
        if not isinstance(body, dict):
            raise HttpError(400, "body must be a JSON object")
        return body

    def _check(self, header: str, secret: str, query: dict | None = None) -> None:
        # The page sends the code percent-encoded: a header carries Latin-1 at
        # best, and a code may have an ø in it. ?code= arrives decoded already.
        given = unquote(self.headers.get(header) or "") or ((query or {}).get("code") or [""])[0]
        if not hmac.compare_digest(_normal(given).encode(), _normal(secret).encode()):
            time.sleep(WRONG_CODE_DELAY_S)
            raise HttpError(401, "wrong code")

    def _user(self, value: Any) -> str:
        if value not in USER_IDS:
            raise HttpError(400, f"unknown user {value!r}")
        return value

    def _dispatch(self, method: str) -> None:
        try:
            url = urlparse(self.path)
            route = (method, url.path.rstrip("/") or "/")
            if route == ("GET", "/health"):
                return self._json({"ok": True, "store": self.store.name,
                                   "version": os.environ.get("VALIDATION_VERSION", "dev")})
            if url.path.startswith("/tiles/tracks/"):
                self._check("X-Access-Code", self.access_code, parse_qs(url.query))
                return self._tile(url.path)
            if url.path.startswith("/api/admin/"):
                self._check("X-Admin-Key", self.admin_key)
            elif url.path.startswith("/api/"):
                self._check("X-Access-Code", self.access_code)
            handler = ROUTES.get(route)
            if handler is None:
                raise HttpError(404, f"no route {method} {url.path}")
            self._json(handler(self, parse_qs(url.query)))
        except HttpError as e:
            self._json({"error": str(e)}, e.status)
        except Exception as e:      # noqa: BLE001 - the client must hear something
            traceback.print_exc()
            self._json({"error": f"{type(e).__name__}: {e}"}, 500)

    def _tile(self, path: str) -> None:
        if path == "/tiles/tracks/index.json":
            file, content_type = TRACKS / "index.json", "application/json"
        else:
            match = TILE_PATH.match(path)
            if not match:
                raise HttpError(404, "no such tile")
            z, x, y = match.groups()
            file, content_type = TRACKS / z / x / f"{y}.png", "image/png"
        if not file.is_file():
            raise HttpError(404, "no such tile")
        body = file.read_bytes()
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        # The index says which build is current, so it is never cached; the
        # tiles carry that build in their URL and can be.
        self.send_header("Cache-Control", "no-cache" if content_type == "application/json"
                         else "private, max-age=86400")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:      # noqa: N802
        self._dispatch("GET")

    def do_POST(self) -> None:     # noqa: N802
        self._dispatch("POST")

    def do_PUT(self) -> None:      # noqa: N802
        self._dispatch("PUT")

    # --- routes --------------------------------------------------------------

    def users(self, _query: dict) -> Any:
        return USERS

    def state(self, query: dict) -> Any:
        user = self._user((query.get("user") or [None])[0])
        verdicts = self.store.state(user)
        return {"user": user, "assigned": self.store.assignment(user),
                "verdicts": {str(cid): v for cid, v in verdicts.items()}}

    def verdict(self, _query: dict) -> Any:
        body = self._body()
        user = self._user(body.get("user"))
        corridor = body.get("corridor")
        if isinstance(corridor, bool) or not isinstance(corridor, int) or not 0 < corridor < 10000:
            raise HttpError(400, "corridor must be an id")
        op_id = body.get("opId")
        if not isinstance(op_id, str) or not 8 <= len(op_id) <= 64 or not op_id.isalnum():
            raise HttpError(400, "opId must be 8-64 letters and digits")
        try:
            patch = validate_patch(body.get("patch"))
        except ValueError as e:
            raise HttpError(400, str(e)) from None
        verdict = self.store.apply(user, corridor, patch, op_id, str(body.get("clientTs", ""))[:40])
        self._written()
        return {"corridor": corridor, "verdict": verdict}

    def reset(self, _query: dict) -> Any:
        if self._body().get("user") != TEST_USER:
            raise HttpError(403, "only the test user can be reset")
        removed = self.store.reset(TEST_USER)
        self._written()
        return {"removed": removed}

    def put_assignments(self, _query: dict) -> Any:
        assignments = self._body().get("assignments")
        if not isinstance(assignments, dict):
            raise HttpError(400, "assignments must be an object of user -> ids")
        for user, ids in assignments.items():
            self._user(user)
            if not isinstance(ids, list) or not all(
                    isinstance(i, int) and not isinstance(i, bool) for i in ids):
                raise HttpError(400, f"{user}: ids must be a list of integers")
        self.store.set_assignments({u: sorted(set(ids)) for u, ids in assignments.items()})
        self._written()
        return {"ok": True, "users": {u: len(ids) for u, ids in assignments.items()}}

    def dump(self, _query: dict) -> Any:
        return self.store.dump()


ROUTES = {
    ("GET", "/api/users"): Handler.users,
    ("GET", "/api/state"): Handler.state,
    ("POST", "/api/verdict"): Handler.verdict,
    ("POST", "/api/reset"): Handler.reset,
    ("PUT", "/api/admin/assignments"): Handler.put_assignments,
    ("GET", "/api/admin/dump"): Handler.dump,
}


def make_server(host: str, port: int, store: store_module.Store, *,
                access_code: str, admin_key: str,
                allowed_origins: set[str], snapshots: Any = None) -> ThreadingHTTPServer:
    handler = type("BoundHandler", (Handler,), {
        "store": store, "access_code": access_code, "admin_key": admin_key,
        "allowed_origins": allowed_origins, "snapshots": snapshots,
    })
    return ThreadingHTTPServer((host, port), handler)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m validation_app.backend.server",
                                     description=__doc__.split("\n\n")[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8790)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA,
                        help="where the file store keeps its log, when no "
                             "VALIDATION_TABLES_CONNECTION is set")
    args = parser.parse_args(argv)

    in_azure = bool(os.environ.get("VALIDATION_TABLES_CONNECTION"))
    access_code = os.environ.get("VALIDATION_ACCESS_CODE", "" if in_azure else "dev")
    admin_key = os.environ.get("VALIDATION_ADMIN_KEY", "" if in_azure else "dev")
    if not access_code or not admin_key:
        print("VALIDATION_ACCESS_CODE and VALIDATION_ADMIN_KEY must be set", file=sys.stderr)
        return 2
    origins = os.environ.get("VALIDATION_ALLOWED_ORIGIN", "http://localhost:5174")

    store = store_module.open_store(args.data)
    snapshots = None
    if in_azure:
        from .snapshots import Snapshotter
        snapshots = Snapshotter(store, os.environ["VALIDATION_TABLES_CONNECTION"])
        snapshots.start()
    server = make_server(args.host, args.port, store, access_code=access_code,
                         admin_key=admin_key,
                         allowed_origins={o.strip() for o in origins.split(",") if o.strip()},
                         snapshots=snapshots)
    print(f"validation API on http://{args.host}:{args.port}  (store: {store.name})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
