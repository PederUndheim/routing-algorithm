"""A daily copy of everything in the store, as a blob beside the tables.

History already makes every write recoverable from the tables themselves.
What it cannot survive is the tables going: a table deleted, an `az` command
pointed at the wrong name. So the API also writes the whole store - the same
dump `/api/admin/dump` returns - to `snapshots/validering_YYYY-MM-DD.json`
in a blob container of the same account.

One blob per day, rewritten through the day: blob versioning on the account
(deploy/validation.sh turns it on) keeps every rewrite, so a day's file is
the day's last state and its versions are the states before it.

Written at startup and then every INTERVAL_S while there have been writes
since the last one. The app scales to zero between sessions, which stops
this thread too - but the next start writes first thing, so the end of one
session is captured at the latest when the next begins.

It is no off-site copy: the account is still one point of failure, and
`python -m validation_app.admin backup` is how to take one home.
"""

from __future__ import annotations

import json
import sys
import threading
import time
import traceback
from datetime import datetime, timezone

CONTAINER = "snapshots"
INTERVAL_S = 600


class Snapshotter:
    def __init__(self, store, connection_string: str) -> None:
        from azure.storage.blob import BlobServiceClient

        self.store = store
        service = BlobServiceClient.from_connection_string(connection_string)
        self.container = service.get_container_client(CONTAINER)
        if not self.container.exists():
            self.container.create_container()
        self._dirty = threading.Event()
        self._dirty.set()   # always one at startup

    def mark(self) -> None:
        """A write happened; the next tick takes a snapshot."""
        self._dirty.set()

    def take(self) -> str:
        self._dirty.clear()
        dump = self.store.dump()
        name = f"validering_{datetime.now(timezone.utc):%Y-%m-%d}.json"
        self.container.upload_blob(name, json.dumps(dump, ensure_ascii=False).encode("utf-8"),
                                   overwrite=True)
        return name

    def run_forever(self) -> None:
        while True:
            if self._dirty.is_set():
                try:
                    name = self.take()
                    print(f"snapshot -> {CONTAINER}/{name}", flush=True)
                except Exception:   # noqa: BLE001 - a failed snapshot must not stop the next
                    self._dirty.set()
                    traceback.print_exc(file=sys.stderr)
            time.sleep(INTERVAL_S)

    def start(self) -> None:
        threading.Thread(target=self.run_forever, name="snapshots", daemon=True).start()
