from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import Observation


class History:
    """Runs are append-only. Demo data never enters the live snapshot table."""
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, created TEXT NOT NULL, mode TEXT NOT NULL, summary TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS snapshots (run_id TEXT, observation_id TEXT, observed TEXT, value REAL, payload TEXT,
                PRIMARY KEY(run_id, observation_id));
            CREATE INDEX IF NOT EXISTS snapshots_lookup ON snapshots(observation_id, observed);
        """)

    def enrich(self, observations: list[Observation], now: datetime | None = None):
        now = now or datetime.now(timezone.utc)
        # >=24 hours avoids presenting repeated scans minutes apart as growth.
        cutoff = (now - timedelta(hours=24)).isoformat()
        oldest = (now - timedelta(days=60)).isoformat()
        for o in observations:
            if not (o.attrs.get("cumulative") or o.attrs.get("snapshot")): continue
            rows = self.db.execute("SELECT observed,value,payload FROM snapshots WHERE observation_id=? AND observed<=? AND observed>=? ORDER BY observed ASC",
                                   (o.id, cutoff, oldest)).fetchall()
            if not rows: continue
            date, previous, payload = min(rows, key=lambda r: abs((now - datetime.fromisoformat(r[0])).total_seconds() - 7 * 86400))
            days = (now - datetime.fromisoformat(date)).total_seconds() / 86400
            old = json.loads(payload)
            if o.attrs.get("snapshot") and old.get("attrs", {}).get("sample_size") != o.attrs.get("sample_size"):
                continue  # incompatible sample; don't manufacture growth
            delta = o.value - previous
            if o.attrs.get("cumulative") and delta < 0:
                o.attrs["history_warning"] = "Counter decreased; velocity unavailable"
                continue
            o.attrs["history"] = {"previous": previous, "days": round(days, 2), "delta": round(delta, 2),
                                  "per_day": round(delta / max(days, 1), 2), "previous_date": date}

    def save(self, run: dict, observations: list[Observation]):
        with self.db:
            self.db.execute("INSERT INTO runs VALUES (?,?,?,?)", (run["id"], run["created_at"], run["mode"], json.dumps(run)))
            if run["mode"] == "live":
                self.db.executemany("INSERT INTO snapshots VALUES (?,?,?,?,?)",
                    [(run["id"], o.id, o.observed_at, o.value, json.dumps(o.to_dict())) for o in observations])

    def close(self):
        self.db.close()
