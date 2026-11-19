"""The consensus API end to end, on the file store, over real HTTP."""

from __future__ import annotations

import hashlib
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from consensus_app.backend import server as server_module
from consensus_app.backend.experts import FileExperts
from consensus_app.backend.store import FileStore

CODE, ADMIN = "kode-ø", "admin-1"
MEETING = "m20261123"


def _verdict(user: str, corridor: int, kast: str | None, **extra) -> dict:
    return {"user": user, "corridor": corridor, "kast": kast, "sub": 0, "size": 0,
            "note": "", "doubt": False, "problematic": False, **extra}


class ConsensusApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        # A validation dump, as `validation_app.admin backup` writes one.
        self.dump = self.root / "validering.json"
        self.dump.write_text(json.dumps({"current": [
            _verdict("havard", 5, "blue"), _verdict("finn", 5, "blue", sub=1),
            _verdict("andreas", 5, "red", note="bratt"), _verdict("markus", 5, "black"),
            _verdict("havard", 6, None),
        ]}), encoding="utf-8")
        self.dump_hash = hashlib.sha256(self.dump.read_bytes()).hexdigest()
        self._start()

    def _start(self) -> None:
        server_module.WRONG_CODE_DELAY_S = 0
        self.server = server_module.make_server(
            "127.0.0.1", 0, FileStore(self.root / "store"), FileExperts(self.dump),
            access_code=CODE, admin_key=ADMIN, allowed_origins={"http://example.test"})
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def _stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    def tearDown(self) -> None:
        self._stop()
        # The validation data is only ever read.
        self.assertEqual(hashlib.sha256(self.dump.read_bytes()).hexdigest(), self.dump_hash)
        self.tmp.cleanup()

    def call(self, method: str, path: str, body=None, *, code=CODE, admin=None):

        headers = {"Content-Type": "application/json", "X-Access-Code": quote(code)}
        if admin is not None:
            headers["X-Admin-Key"] = admin
        data = None if body is None else json.dumps(body).encode()
        request = Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with urlopen(request) as response:
                return response.status, json.loads(response.read())
        except HTTPError as e:
            return e.code, json.loads(e.read())

    def patch(self, corridor: int, patch: dict, op: str = "op000001", meeting: str = MEETING):
        return self.call("POST", "/api/consensus", {"meeting": meeting, "corridor": corridor,
                                                    "patch": patch, "opId": op, "clientTs": "t"})

    def test_needs_the_code(self) -> None:
        self.assertEqual(self.call("GET", "/api/meetings", code="feil")[0], 401)
        status, meetings = self.call("GET", "/api/meetings")
        self.assertEqual(status, 200)
        self.assertEqual([m["id"] for m in meetings], ["m20261123", "m20261130", "test"])
        self.assertEqual([e["name"] for e in meetings[0]["experts"]], ["Håvard", "Finn", "Andreas"])

    def test_experts_are_the_meetings_only(self) -> None:
        status, body = self.call("GET", f"/api/experts?meeting={MEETING}")
        self.assertEqual(status, 200)
        self.assertEqual(sorted(body["verdicts"]), ["andreas", "finn", "havard"])   # no Markus
        self.assertEqual(body["verdicts"]["andreas"]["5"]["kast"], "red")
        self.assertEqual(body["verdicts"]["andreas"]["5"]["note"], "bratt")
        self.assertIsNone(body["verdicts"]["havard"]["6"]["kast"])

    def test_write_read_and_since(self) -> None:
        status, first = self.call("GET", f"/api/state?meeting={MEETING}")
        self.assertEqual((status, first["consensus"]), (200, {}))
        status, body = self.patch(5, {"kast": "blue", "note": "enige etter diskusjon"})
        self.assertEqual(status, 200)
        self.assertEqual(body["consensus"]["kast"], "blue")
        self.assertEqual((body["consensus"]["sub"], body["consensus"]["size"]), (0, 0))
        # A retry of the same op is not a second write.
        self.patch(5, {"kast": "blue", "note": "enige etter diskusjon"})
        _, dump = self.call("GET", "/api/admin/dump", admin=ADMIN)
        self.assertEqual(len(dump["history"]), 1)
        # Only rows changed at or after `since` (inclusive, so a write in the
        # same millisecond as an answer is in the next one). The pause keeps
        # the write and the next answer in different milliseconds.
        time.sleep(0.01)
        _, later = self.call("GET", f"/api/state?meeting={MEETING}&since={quote(first['serverTs'])}")
        self.assertEqual(list(later["consensus"]), ["5"])
        _, none = self.call("GET", f"/api/state?meeting={MEETING}&since={quote(later['serverTs'])}")
        self.assertEqual(none["consensus"], {})
        # Patches merge: another field keeps the first.
        self.patch(5, {"problematic": True, "change": "flytt nedkjøring"}, op="op000002")
        _, state = self.call("GET", f"/api/state?meeting={MEETING}")
        row = state["consensus"]["5"]
        self.assertEqual((row["kast"], row["note"], row["problematic"]),
                         ("blue", "enige etter diskusjon", True))

    def test_meetings_are_apart(self) -> None:
        self.patch(5, {"kast": "red"})
        _, other = self.call("GET", "/api/state?meeting=m20261130")
        self.assertEqual(other["consensus"], {})

    def test_rejects_bad_input(self) -> None:
        self.assertEqual(self.patch(5, {"kast": "purple"})[0], 400)
        self.assertEqual(self.patch(5, {"sub": 2})[0], 400)
        self.assertEqual(self.patch(5, {"doubt": True})[0], 400)  # no Usikker either
        self.assertEqual(self.patch(5, {"kast": "red"}, meeting="nope")[0], 400)
        self.assertEqual(self.call("GET", f"/api/state?meeting={MEETING}&since=x")[0], 400)

    def test_follow_up_fields(self) -> None:
        self.patch(6, {"midpoint": True, "midpointWhere": "via toppen"})
        self.patch(6, {"split": True, "split1Kast": "red", "split1Sub": -1, "split2Where": "ned nordsida"},
                   op="op000002")
        _, state = self.call("GET", f"/api/state?meeting={MEETING}")
        row = state["consensus"]["6"]
        self.assertEqual((row["midpoint"], row["midpointWhere"], row["endpoint"]), (True, "via toppen", False))
        self.assertEqual((row["split1Kast"], row["split1Sub"], row["split2Kast"], row["split2Where"]),
                         ("red", -1, None, "ned nordsida"))
        self.assertEqual(self.patch(6, {"split2Kast": "purple"}, op="op000003")[0], 400)
        self.assertEqual(self.patch(6, {"endpoint": "ja"}, op="op000004")[0], 400)
        self.patch(6, {"other": True, "otherWhat": "sjekk parkering", "remove": True, "reopened": True,
                       "sizeSet": True}, op="op000005")
        _, state = self.call("GET", f"/api/state?meeting={MEETING}")
        row = state["consensus"]["6"]
        self.assertEqual((row["other"], row["otherWhat"], row["remove"], row["reopened"], row["sizeSet"]),
                         (True, "sjekk parkering", True, True, True))

    def test_only_the_test_meeting_resets(self) -> None:
        self.patch(5, {"kast": "red"})
        self.patch(5, {"kast": "red"}, meeting="test", op="op000002")
        self.assertEqual(self.call("POST", "/api/reset", {"meeting": MEETING})[0], 403)
        status, body = self.call("POST", "/api/reset", {"meeting": "test"})
        self.assertEqual((status, body["removed"]), (200, 1))
        _, kept = self.call("GET", f"/api/state?meeting={MEETING}")
        self.assertEqual(kept["consensus"]["5"]["kast"], "red")

    def test_survives_a_restart(self) -> None:
        self.patch(7, {"kast": "black", "sub": 1, "size": -1})
        self._stop()
        self._start()
        _, state = self.call("GET", f"/api/state?meeting={MEETING}")
        row = state["consensus"]["7"]
        self.assertEqual((row["kast"], row["sub"], row["size"]), ("black", 1, -1))

    def test_admin_needs_the_key(self) -> None:
        self.assertEqual(self.call("GET", "/api/admin/dump")[0], 401)
        self.assertEqual(self.call("GET", "/api/admin/dump", admin=CODE)[0], 401)


if __name__ == "__main__":
    unittest.main()
