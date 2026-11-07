import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import requests

from trendfinder.ai import synthesize
from trendfinder.config import load
from trendfinder.engine import scan
from trendfinder.models import Observation, SourceResult
from trendfinder.server import make_server


class IntegrationTests(unittest.TestCase):
    def test_demo_writes_pdf_ledger_csv_and_never_live_snapshots(self):
        with tempfile.TemporaryDirectory() as folder:
            cfg = load(); cfg["report_top"] = 1
            run = scan(cfg, Path(folder), demo=True)
            directory = Path(folder) / "reports" / run["id"]
            self.assertTrue((directory / "report.pdf").read_bytes().startswith(b"%PDF"))
            self.assertGreater((directory / "report.pdf").stat().st_size, 20000)
            ledger = json.loads((directory / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(ledger["mode"], "demo")
            self.assertEqual(len(ledger["observations"]), 96)
            self.assertTrue((directory / "observations.csv").read_bytes().startswith(b"\xef\xbb\xbf"))
            db = sqlite3.connect(Path(folder) / "history.sqlite3")
            try: self.assertEqual(db.execute("SELECT count(*) FROM snapshots").fetchone()[0], 0)
            finally: db.close()

    def test_all_blocked_still_generates_an_honest_report(self):
        with tempfile.TemporaryDirectory() as folder:
            cfg = load(); cfg["sources"] = ["reddit", "youtube"]; cfg["report_top"] = 1
            with patch("trendfinder.engine.collect", side_effect=lambda name,*a: SourceResult(name, "blocked", "Network denied")):
                run = scan(cfg, Path(folder))
            self.assertEqual(run["outcome"], "no_evidence")
            self.assertTrue(all(r["stage"] == "INSUFFICIENT EVIDENCE" and r["score"] == 0 for r in run["rankings"]))
            self.assertTrue((Path(folder) / "reports" / run["id"] / "report.pdf").is_file())

    def test_csv_formula_is_neutralized(self):
        with tempfile.TemporaryDirectory() as folder:
            cfg = load(); cfg["sources"] = ["imports"]; cfg["report_top"] = 1
            obs = Observation("lifesteal", "imports", "community", "=HYPERLINK(1)", "https://example.com/item", "SK")
            with patch("trendfinder.engine.collect", return_value=SourceResult("imports", observations=[obs])):
                run = scan(cfg, Path(folder))
            content = (Path(folder) / "reports" / run["id"] / "observations.csv").read_text(encoding="utf-8-sig")
            self.assertIn("'=HYPERLINK", content)

    def test_local_ai_is_optional_and_remote_endpoint_is_rejected(self):
        cfg = load()
        self.assertEqual(synthesize({}, cfg)["state"], "disabled")
        cfg["ai"].update(enabled=True, endpoint="https://remote.example.com")
        with patch("requests.Session.post") as post:
            self.assertEqual(synthesize({}, cfg)["state"], "error")
            post.assert_not_called()

    def test_ai_rejects_hallucinated_citations_and_survives_unavailable_model(self):
        cfg = load(); cfg["ai"]["enabled"] = True
        run = {"rankings": [{"candidate": {"id": "c"}, "evidence_ids": ["e"], "stage": "WATCH", "score": 1, "caveats": []}],
               "observations": [{"id": "e", "title": "evidence", "source": "test", "market": "CZ"}]}
        class Response:
            def raise_for_status(self): pass
            def json(self): return {"response": json.dumps({"notes": [{"candidate_id": "c", "evidence_ids": ["invented"], "hypothesis": "h", "experiment": "e"}]})}
        with patch("requests.Session.post", return_value=Response()):
            self.assertEqual(synthesize(run, cfg)["notes"], [])
        with patch("requests.Session.post", side_effect=requests.ConnectionError):
            self.assertEqual(synthesize(run, cfg)["state"], "unavailable")

    def test_dashboard_host_origin_and_artifact_boundaries(self):
        with tempfile.TemporaryDirectory() as folder:
            server = make_server(load(), Path(folder), 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            url = f"http://127.0.0.1:{server.server_port}"
            try:
                with requests.Session() as session:
                    session.trust_env = False
                    self.assertEqual(session.get(url + "/").status_code, 200)
                    self.assertEqual(session.get(url + "/", headers={"Host": "evil.example"}).status_code, 403)
                    state = session.get(url + "/api/status").json()
                    self.assertIn("token", state)
                    self.assertEqual(session.post(url + "/api/scan", json={"mode": "demo"}).status_code, 403)
                    headers = {"X-Radar-Token": state["token"], "Origin": "https://evil.example"}
                    self.assertEqual(session.post(url + "/api/scan", headers=headers, json={"mode": "demo"}).status_code, 403)
                    headers["Origin"] = url
                    self.assertEqual(session.post(url + "/api/scan", headers=headers, json={"mode": "invalid"}).status_code, 400)
                    self.assertEqual(session.get(url + "/artifacts/live-aaaaaaaaaaaaaaaa/../../history.sqlite3").status_code, 404)
                    self.assertEqual(session.get(url + "/api/report/not-a-run").status_code, 404)
                    self.assertEqual(session.get(url + "/app.js").headers["X-Content-Type-Options"], "nosniff")
            finally:
                server.shutdown(); thread.join(timeout=5); server.server_close()
