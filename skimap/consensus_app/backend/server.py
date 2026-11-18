r"""The consensus app's API.

    & "C:\Program Files\QGIS 4.2.0\bin\python-qgis.bat" -m consensus_app.backend.server

Locally that keeps decisions in data/consensus/ (see store.FileStore), reads
the experts from the newest validation backup in data/validation/backup, and
takes "dev" as access code and admin key. In Azure the environment sets:

    CONSENSUS_TABLES_CONNECTION  this app's own storage account -> TableStore,
                                 plus daily snapshots to blob (snapshots.py)
    CONSENSUS_EXPERTS_ENDPOINT   the validation account's table endpoint
    CONSENSUS_EXPERTS_SAS        a read-only SAS for its valcurrent table
    CONSENSUS_ACCESS_CODE        the code everyone in the meeting types once
    CONSENSUS_ADMIN_KEY          for the export and backups; never in the page
    CONSENSUS_ALLOWED_ORIGIN     the Pages origin, comma-separated if several
    CONSENSUS_TRACKS_DIR         the track tiles, from the same file share
                                 folder the validation app uses (read-only)

A separate app from the validation API on purpose: nothing here can change
the validation app or its data. Stateless, like that one.

## Routes

    GET  /health
    GET  /api/meetings                  [access code] the meetings and their corridors
    GET  /api/state?meeting=ID[&since=TS]
                                        [access code] decisions changed after `since`
    GET  /api/experts?meeting=ID        [access code] the meeting's experts' verdicts
    POST /api/consensus                 [access code] {meeting, corridor, patch, opId, clientTs}
    POST /api/reset                     [access code] {meeting: "test"} only
    GET  /api/admin/dump                [admin key]   everything, for export and backup
    GET  /api/admin/experts?meeting=ID  [admin key]   as /api/experts, for the export
    GET  /tiles/tracks/index.json       [access code] which track tiles exist
    GET  /tiles/tracks/Z/X/Y.png        [access code] one track tile
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
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from . import store as store_module
from .consensus import MEETINGS, MEETING_IDS, TEST_MEETING, meetings, validate_patch
from .experts import Experts, FileExperts, TableExperts, newest_backup

DATA = Path(__file__).resolve().parents[2] / "data"
DEFAULT_DATA = DATA / "consensus"
TRACKS = Path(os.environ.get("CONSENSUS_TRACKS_DIR") or DATA / "validation" / "tracks")
TILE_PATH = re.compile(r"^/tiles/tracks/(\d{1,2})/(\d{1,7})/(\d{1,7})\.png$")
TIMESTAMP = re.compile(r"^\d{4}-\d\d-\d\dT[\d:.]+\+00:00$")
MAX_BODY = 256 * 1024
WRONG_CODE_DELAY_S = 1.0


def _normal(code: str) -> str:
    """A code as typed, give or take case and surrounding space."""
    return unicodedata.normalize("NFC", code.strip()).casefold()


class HttpError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


class Handler(BaseHTTPRequestHandler):
    store: store_module.Store
    experts: Experts
    access_code: str
    admin_key: str
    allowed_origins: set[str]
    snapshots: Any = None

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
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
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
        given = unquote(self.headers.get(header) or "") or ((query or {}).get("code") or [""])[0]
        if not hmac.compare_digest(_normal(given).encode(), _normal(secret).encode()):
            time.sleep(WRONG_CODE_DELAY_S)
            raise HttpError(401, "wrong code")

    def _meeting(self, value: Any) -> str:
        if value not in MEETING_IDS:
            raise HttpError(400, f"unknown meeting {value!r}")
        return value

    def _dispatch(self, method: str) -> None:
        try:
            url = urlparse(self.path)
            route = (method, url.path.rstrip("/") or "/")
            if route == ("GET", "/health"):
                return self._json({"ok": True, "store": self.store.name,
                                   "experts": self.experts.name,
                                   "version": os.environ.get("CONSENSUS_VERSION", "dev")})
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

    # --- routes --------------------------------------------------------------

    def meetings(self, _query: dict) -> Any:
        return meetings()

    def state(self, query: dict) -> Any:
        meeting = self._meeting((query.get("meeting") or [None])[0])
        since = (query.get("since") or [None])[0]
        if since is not None and not TIMESTAMP.match(since):
            raise HttpError(400, "since must be a timestamp from an earlier answer")
        # Taken before the read, so a row written while it runs is in this
        # answer or the next one, never neither.
        now = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        rows = self.store.state(meeting, since)
        return {"meeting": meeting, "serverTs": now,
                "consensus": {str(cid): v for cid, v in rows.items()}}

    def experts_route(self, query: dict) -> Any:
        meeting = self._meeting((query.get("meeting") or [None])[0])
        experts = next(m["experts"] for m in MEETINGS if m["id"] == meeting)
        verdicts = self.experts.verdicts(experts)
        return {"meeting": meeting,
                "verdicts": {e: {str(cid): v for cid, v in rows.items()}
                             for e, rows in verdicts.items()}}

    def consensus(self, _query: dict) -> Any:
        body = self._body()
        meeting = self._meeting(body.get("meeting"))
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
        row = self.store.apply(meeting, corridor, patch, op_id, str(body.get("clientTs", ""))[:40])
        self._written()
        return {"corridor": corridor, "consensus": row}

    def reset(self, _query: dict) -> Any:
        if self._body().get("meeting") != TEST_MEETING:
            raise HttpError(403, "only the test meeting can be reset")
        removed = self.store.reset(TEST_MEETING)
        self._written()
        return {"removed": removed}

    def dump(self, _query: dict) -> Any:
        return self.store.dump()


ROUTES = {
    ("GET", "/api/meetings"): Handler.meetings,
    ("GET", "/api/state"): Handler.state,
    ("GET", "/api/experts"): Handler.experts_route,
    ("POST", "/api/consensus"): Handler.consensus,
    ("POST", "/api/reset"): Handler.reset,
    ("GET", "/api/admin/dump"): Handler.dump,
    ("GET", "/api/admin/experts"): Handler.experts_route,
}


def make_server(host: str, port: int, store: store_module.Store, experts: Experts, *,
                access_code: str, admin_key: str,
                allowed_origins: set[str], snapshots: Any = None) -> ThreadingHTTPServer:
    handler = type("BoundHandler", (Handler,), {
        "store": store, "experts": experts, "access_code": access_code, "admin_key": admin_key,
        "allowed_origins": allowed_origins, "snapshots": snapshots,
    })
    return ThreadingHTTPServer((host, port), handler)


def open_experts() -> Experts:
    endpoint = os.environ.get("CONSENSUS_EXPERTS_ENDPOINT")
    if endpoint:
        return TableExperts(endpoint, os.environ["CONSENSUS_EXPERTS_SAS"])
    path = os.environ.get("CONSENSUS_EXPERTS_FILE")
    file = Path(path) if path else newest_backup(DATA / "validation" / "backup")
    if file is None or not file.exists():
        raise SystemExit("No expert verdicts: set CONSENSUS_EXPERTS_FILE to a validation "
                         "backup, or run `python -m validation_app.admin backup`.")
    print(f"experts from {file}", flush=True)
    return FileExperts(file)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m consensus_app.backend.server",
                                     description=__doc__.split("\n\n")[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8791)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA,
                        help="where the file store keeps its log, when no "
                             "CONSENSUS_TABLES_CONNECTION is set")
    args = parser.parse_args(argv)

    in_azure = bool(os.environ.get("CONSENSUS_TABLES_CONNECTION"))
    access_code = os.environ.get("CONSENSUS_ACCESS_CODE", "" if in_azure else "dev")
    admin_key = os.environ.get("CONSENSUS_ADMIN_KEY", "" if in_azure else "dev")
    if not access_code or not admin_key:
        print("CONSENSUS_ACCESS_CODE and CONSENSUS_ADMIN_KEY must be set", file=sys.stderr)
        return 2
    origins = os.environ.get("CONSENSUS_ALLOWED_ORIGIN", "http://localhost:5175")

    store = store_module.open_store(args.data)
    experts = open_experts()
    snapshots = None
    if in_azure:
        from .snapshots import Snapshotter
        snapshots = Snapshotter(store, os.environ["CONSENSUS_TABLES_CONNECTION"])
        snapshots.start()
    server = make_server(args.host, args.port, store, experts, access_code=access_code,
                         admin_key=admin_key,
                         allowed_origins={o.strip() for o in origins.split(",") if o.strip()},
                         snapshots=snapshots)
    print(f"consensus API on http://{args.host}:{args.port}  "
          f"(store: {store.name}, experts: {experts.name})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
