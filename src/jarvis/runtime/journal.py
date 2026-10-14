"""Single-owner durable call ledger. Unfinished effects are never replayed."""
import json
import sqlite3
import threading

from jarvis.runtime.protocol import Rejected, digest


class Journal:
    def __init__(self, path):
        self.lock = threading.Lock()
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("CREATE TABLE IF NOT EXISTS calls(id TEXT PRIMARY KEY, hash TEXT NOT NULL, result TEXT)")
        self.db.commit()

    def begin(self, call):
        with self.lock, self.db:
            old = self.db.execute("SELECT hash,result FROM calls WHERE id=?", (call["call_id"],)).fetchone()
            if old:
                if old[0] != digest(call):
                    raise Rejected("call_id_collision")
                return (json.loads(old[1]) if old[1] else None), False
            self.db.execute("INSERT INTO calls VALUES(?,?,NULL)", (call["call_id"], digest(call)))
            return None, True

    def finish(self, call, result):
        with self.lock, self.db:
            self.db.execute("UPDATE calls SET result=? WHERE id=? AND hash=?",
                            (json.dumps(result), call["call_id"], digest(call)))

    def close(self):
        self.db.close()
