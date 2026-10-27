"""The validation API end to end, on the file store, over real HTTP."""

from __future__ import annotations

import json
import os
import tempfile
import uuid
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from validation_app.backend import server as server_module
from validation_app.backend.store import FileStore, TableStore

CODE, ADMIN = "code-1", "admin-1"

# Set to an Azurite (or real) connection string to run the suite on Table
# Storage as well; needs azure-data-tables importable.
TABLES = os.environ.get("VALIDATION_TEST_TABLES")


class ValidationApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self._start()

    def _store(self):
        return FileStore(self.root)

    def _start(self) -> None:
        server_module.WRONG_CODE_DELAY_S = 0
        self.server = server_module.make_server(
            "127.0.0.1", 0, self._store(), access_code=CODE, admin_key=ADMIN,
            allowed_origins={"http://example.test"})
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def _stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    def tearDown(self) -> None:
        self._stop()
        self.tmp.cleanup()

    def call(self, method: str, path: str, body=None, *, code=CODE, admin=None):
        headers = {"Content-Type": "application/json", "X-Access-Code": code}
        if admin is not None:
            headers["X-Admin-Key"] = admin
        data = None if body is None else json.dumps(body).encode()
        request = Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with urlopen(request) as response:
                return response.status, json.loads(response.read())
        except HTTPError as e:
            return e.code, json.loads(e.read())

    def patch(self, user, corridor, patch, op="op000001"):
        return self.call("POST", "/api/verdict", {
            "user": user, "corridor": corridor, "patch": patch,
            "opId": op, "clientTs": "2026-10-27T10:00:00Z"})

    def test_wrong_code_is_refused(self) -> None:
        status, _ = self.call("GET", "/api/users", code="nope")
        self.assertEqual(status, 401)
        status, users = self.call("GET", "/api/users")
        self.assertEqual(status, 200)
        self.assertIn("Håvard", [u["name"] for u in users])

    def test_a_code_with_an_o_slash_works_however_it_is_typed(self) -> None:
        from urllib.parse import quote
        self._stop()
        self.server = server_module.make_server(
            "127.0.0.1", 0, self._store(), access_code="fjellgøy", admin_key=ADMIN,
            allowed_origins=set())
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        for typed in ("fjellgøy", " Fjellgøy ", "FJELLGØY"):
            status, _ = self.call("GET", "/api/users", code=quote(typed))
            self.assertEqual(status, 200, repr(typed))
        status, _ = self.call("GET", "/api/users", code=quote("fjellgoy"))
        self.assertEqual(status, 401)

    def test_patches_merge_and_survive_a_restart(self) -> None:
        self.patch("markus", 12, {"kast": "blue", "sub": 1}, "op000001")
        status, body = self.patch("markus", 12, {"note": "bratt topp", "doubt": True}, "op000002")
        self.assertEqual(status, 200)
        self.assertEqual(body["verdict"]["kast"], "blue")
        self.assertEqual(body["verdict"]["sub"], 1)
        self.assertTrue(body["verdict"]["doubt"])

        self._stop()
        self._start()
        _, state = self.call("GET", "/api/state?user=markus")
        verdict = state["verdicts"]["12"]
        self.assertEqual((verdict["kast"], verdict["note"], verdict["size"]),
                         ("blue", "bratt topp", 0))

    def test_users_do_not_see_each_others_verdicts(self) -> None:
        self.patch("markus", 12, {"kast": "red"})
        _, state = self.call("GET", "/api/state?user=finn")
        self.assertEqual(state["verdicts"], {})

    def test_a_retried_write_is_recorded_once(self) -> None:
        self.patch("finn", 3, {"kast": "green"}, "sameop01")
        self.patch("finn", 3, {"kast": "green"}, "sameop01")
        _, dump = self.call("GET", "/api/admin/dump", admin=ADMIN)
        self.assertEqual(len(dump["history"]), 1)

    def test_bad_patches_are_rejected(self) -> None:
        for patch in ({"kast": "purple"}, {"sub": 2}, {"size": True}, {"colour": "red"}, {}):
            status, _ = self.patch("finn", 3, patch)
            self.assertEqual(status, 400, patch)
        status, _ = self.patch("nobody", 3, {"kast": "red"})
        self.assertEqual(status, 400)

    def test_kast_can_be_cleared(self) -> None:
        self.patch("andreas", 5, {"kast": "black"}, "op000001")
        _, body = self.patch("andreas", 5, {"kast": None}, "op000002")
        self.assertIsNone(body["verdict"]["kast"])

    def test_only_the_test_user_can_be_reset(self) -> None:
        self.patch("test", 1, {"kast": "red"})
        self.patch("havard", 1, {"kast": "red"})
        status, _ = self.call("POST", "/api/reset", {"user": "havard"})
        self.assertEqual(status, 403)
        status, body = self.call("POST", "/api/reset", {"user": "test"})
        self.assertEqual((status, body["removed"]), (200, 1))
        _, state = self.call("GET", "/api/state?user=havard")
        self.assertIn("1", state["verdicts"])

    def test_track_tiles_need_the_code(self) -> None:
        tracks = server_module.TRACKS
        if not (tracks / "index.json").exists():
            self.skipTest("no track tiles built")
        z, tiles = next(iter(json.loads((tracks / "index.json").read_text())["tiles"].items()))
        tile = f"/tiles/tracks/{z}/{tiles[0]}.png"
        with self.assertRaises(HTTPError) as refused:
            urlopen(self.base + tile)
        self.assertEqual(refused.exception.code, 401)
        with urlopen(f"{self.base}{tile}?code={CODE}") as response:
            self.assertEqual(response.headers["Content-Type"], "image/png")
        status, _ = self.call("GET", "/tiles/tracks/../../server.py")
        self.assertEqual(status, 404)

    def test_assignments_need_the_admin_key(self) -> None:
        status, _ = self.call("PUT", "/api/admin/assignments",
                              {"assignments": {"finn": [3, 1]}}, admin="wrong")
        self.assertEqual(status, 401)
        status, _ = self.call("PUT", "/api/admin/assignments",
                              {"assignments": {"finn": [3, 1]}}, admin=ADMIN)
        self.assertEqual(status, 200)
        _, state = self.call("GET", "/api/state?user=finn")
        self.assertEqual(state["assigned"], [1, 3])
        _, state = self.call("GET", "/api/state?user=markus")
        self.assertIsNone(state["assigned"])
        _, state = self.call("GET", "/api/state?user=test")
        self.assertIsNone(state["assigned"])



@unittest.skipUnless(TABLES, "VALIDATION_TEST_TABLES not set")
class ValidationApiOnTablesTest(ValidationApiTest):
    """The same suite on TableStore, each test on tables of its own."""

    def setUp(self) -> None:
        self.prefix = "t" + uuid.uuid4().hex[:12]
        super().setUp()

    def _store(self):
        return TableStore(TABLES, prefix=self.prefix)


if __name__ == "__main__":
    unittest.main()
