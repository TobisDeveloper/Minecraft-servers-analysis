import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from trendfinder.history import History
from trendfinder.models import Observation


class HistoryTests(unittest.TestCase):
    def test_live_growth_and_demo_isolation(self):
        with tempfile.TemporaryDirectory() as folder:
            h = History(Path(folder) / "history.db")
            try:
                old = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
                a = Observation("c", "modrinth", "mods", "Pack", "https://example.com/a", value=1000, attrs={"cumulative": True}, observed_at=old)
                h.save({"id": "live", "created_at": old, "mode": "live"}, [a])
                b = Observation("c", "modrinth", "mods", "Pack", "https://example.com/a", value=1700, attrs={"cumulative": True})
                h.enrich([b]); self.assertAlmostEqual(b.attrs["history"]["per_day"], 100, delta=1)
                h.save({"id": "demo", "created_at": old, "mode": "demo"}, [a])
                self.assertEqual(h.db.execute("SELECT count(*) FROM snapshots").fetchone()[0], 1)
                reset = Observation("c", "modrinth", "mods", "Pack", "https://example.com/a", value=5, attrs={"cumulative": True})
                h.enrich([reset]); self.assertNotIn("history", reset.attrs)
                self.assertIn("history_warning", reset.attrs)
            finally: h.close()

    def test_same_day_and_different_samples_are_not_growth(self):
        with tempfile.TemporaryDirectory() as folder:
            h = History(Path(folder) / "h.db")
            try:
                a = Observation("c", "modrinth", "mods", "Pack", "https://example.com/a", value=100, attrs={"cumulative": True})
                h.save({"id": "now", "created_at": a.observed_at, "mode": "live"}, [a])
                b = Observation("c", "modrinth", "mods", "Pack", "https://example.com/a", value=200, attrs={"cumulative": True})
                h.enrich([b]); self.assertNotIn("history", b.attrs)
                date = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
                a = Observation("c", "server_lists", "servers", "List", "https://example.com/l", value=4, attrs={"snapshot": True, "sample_size": 10}, observed_at=date)
                h.save({"id": "old", "created_at": date, "mode": "live"}, [a])
                b = Observation("c", "server_lists", "servers", "List", "https://example.com/l", value=8, attrs={"snapshot": True, "sample_size": 20})
                h.enrich([b]); self.assertNotIn("history", b.attrs)
            finally: h.close()
