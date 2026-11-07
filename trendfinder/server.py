"""Single-user loopback dashboard with origin/host checks and a CSRF token."""
from __future__ import annotations

import json
import mimetypes
import re
import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .engine import scan

RUN_ID = re.compile(r"(?:demo|live)-[a-f0-9]{16}\Z")


def make_server(cfg: dict, data_dir: Path, port: int):
    token = secrets.token_urlsafe(32)
    lock = threading.Lock()
    state = {"running": False, "message": "Ready to collect. Demo data is synthetic.", "error": False}
    web = Path(__file__).parent / "web"
    data_dir.mkdir(parents=True, exist_ok=True)

    def worker(demo):
        try:
            def progress(msg):
                with lock: state["message"] = msg
            run = scan(cfg, data_dir, demo=demo, progress=progress)
            with lock:
                state.update(running=False, message="Complete" if run["outcome"] != "no_evidence" else "Report saved; no source evidence collected. Check source health.",
                             latest=run["id"], error=run["outcome"] == "no_evidence")
        except Exception as exc:
            with lock: state.update(running=False, error=True, message=f"Scan failed ({type(exc).__name__}); check the configuration and console.")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_): pass

        def _valid_host(self):
            return self.headers.get("Host") in {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}

        def respond(self, status, data, mime="application/json; charset=utf-8"):
            if not isinstance(data, bytes): data = json.dumps(data, ensure_ascii=False).encode()
            self.send_response(status); self.send_header("Content-Type", mime); self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store"); self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; frame-ancestors 'none'")
            self.end_headers(); self.wfile.write(data)

        def do_GET(self):
            if not self._valid_host(): return self.respond(403, {"error": "Invalid host"})
            path = urlsplit(self.path).path
            if path == "/api/status":
                with lock: snapshot = dict(state)
                snapshot["token"] = token
                snapshot["ai_enabled"] = cfg["ai"]["enabled"]
                return self.respond(200, snapshot)
            if path == "/api/runs":
                rows = []
                reports = sorted((data_dir / "reports").glob("*/report.json"), key=lambda p: p.stat().st_mtime, reverse=True)
                for file in reports[:25]:
                    try:
                        r = json.loads(file.read_text(encoding="utf-8"))
                        rows.append({k: r[k] for k in ("id", "created_at", "mode", "outcome")})
                    except (OSError, ValueError, KeyError): continue
                return self.respond(200, rows)
            if path.startswith("/api/report/"):
                rid = path.rsplit("/", 1)[-1]
                if not RUN_ID.fullmatch(rid): return self.respond(404, {"error": "Unknown report"})
                file = data_dir / "reports" / rid / "report.json"
                if file.is_file(): return self.respond(200, file.read_bytes())
            if path.startswith("/artifacts/"):
                parts = path.strip("/").split("/")
                if len(parts) == 3 and RUN_ID.fullmatch(parts[1]) and parts[2] in {"report.pdf", "report.json", "observations.csv"}:
                    file = data_dir / "reports" / parts[1] / parts[2]
                    if file.is_file(): return self.respond(200, file.read_bytes(), mimetypes.guess_type(file.name)[0] or "application/octet-stream")
            assets = {"/": "index.html", "/app.js": "app.js", "/style.css": "style.css"}
            if path in assets:
                file = web / assets[path]
                return self.respond(200, file.read_bytes(), {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8"}[file.suffix])
            return self.respond(404, {"error": "Not found"})

        def do_POST(self):
            origin = self.headers.get("Origin", "")
            expected = {f"http://127.0.0.1:{self.server.server_port}", f"http://localhost:{self.server.server_port}"}
            if not self._valid_host() or (origin and origin not in expected) or not secrets.compare_digest(self.headers.get("X-Radar-Token", ""), token):
                return self.respond(403, {"error": "Invalid origin/token"})
            if urlsplit(self.path).path != "/api/scan": return self.respond(404, {"error": "Not found"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 1024: raise ValueError
                body = json.loads(self.rfile.read(length))
                if body.get("mode") not in {"live", "demo"}: raise ValueError
            except (ValueError, AttributeError):
                return self.respond(400, {"error": "Expected mode live or demo"})
            with lock:
                if state["running"]: return self.respond(409, {"error": "A scan is already running"})
                state.update(running=True, error=False, message="Starting " + body["mode"] + " scan")
            threading.Thread(target=worker, args=(body["mode"] == "demo",), daemon=True).start()
            return self.respond(202, {"accepted": True})

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def serve(cfg, data_dir, port=8765, open_browser=False):
    server = make_server(cfg, data_dir, port)
    url = f"http://127.0.0.1:{server.server_port}"
    print("Local dashboard: " + url + " (Ctrl+C to stop)")
    if open_browser: webbrowser.open(url)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
