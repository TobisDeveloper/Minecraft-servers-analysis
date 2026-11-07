from __future__ import annotations

import csv
import json
import uuid
from pathlib import Path

from . import __version__
from .ai import synthesize
from .catalog import catalog, discovered_pack
from .demo import generate as demo_data
from .history import History
from .models import SourceResult, utcnow
from .report import generate as generate_pdf
from .scoring import rank
from .sources import Http, collect, modrinth


def _write_json(path: Path, data):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    tmp.replace(path)


def scan(cfg: dict, data_dir: Path, demo=False, progress=None) -> dict:
    data_dir = data_dir.resolve(); data_dir.mkdir(parents=True, exist_ok=True)
    run_id = ("demo-" if demo else "live-") + uuid.uuid4().hex[:16]
    directory = data_dir / "reports" / run_id; directory.mkdir(parents=True)
    candidates = catalog()
    for term in cfg.get("watch_terms", []):
        c = discovered_pack("custom-" + str(len(candidates)), term["name"], term.get("query", term["name"]))
        c.project_id = ""; c.aliases = term.get("aliases", [term["name"]]); c.query = term.get("query", term["name"])
        candidates.append(c)
    def notify(message):
        if progress: progress(message)
    if demo:
        notify("Building explicitly synthetic offline fixture")
        results = demo_data(candidates)
    else:
        http = Http(cfg["timeout"])
        results = []
        if "modrinth" in cfg["sources"]:
            notify("Collecting Modrinth and discovering new server modpacks")
            try:
                result, discovered = modrinth(http, candidates, cfg)
                results.append(result); candidates += discovered
            except Exception:
                results.append(SourceResult("modrinth", "error", "Unexpected adapter failure; no growth inferred"))
        for source in cfg["sources"]:
            if source == "modrinth": continue
            notify("Collecting " + source)
            results.append(collect(source, http, candidates, cfg))
        http.session.close()
    observations = list({o.id: o for result in results for o in result.observations}.values())
    history = History(data_dir / "history.sqlite3")
    try:
        if not demo: history.enrich(observations)
        rankings = rank(candidates, observations, cfg)
        run = {"schema_version": 1, "version": __version__, "id": run_id, "created_at": utcnow(),
               "mode": "demo" if demo else "live", "markets": cfg["markets"],
               "outcome": "demo" if demo else "collected" if observations else "no_evidence",
               "sources": [r.status() for r in results], "rankings": rankings,
               "observations": [o.to_dict() for o in observations],
               "economics_assumptions": cfg["economics"], "artifacts": {"pdf": "report.pdf", "json": "report.json", "csv": "observations.csv"}}
        notify("Calculating optional local AI notes")
        run["ai"] = synthesize(run, cfg)
        notify("Rendering dither PDF and evidence exports")
        generate_pdf(run, directory / "report.pdf", cfg)
        with (directory / "observations.csv").open("w", newline="", encoding="utf-8-sig") as f:
            columns = ["id", "candidate", "source", "family", "market", "title", "url", "metric", "value", "published_at", "observed_at"]
            writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore"); writer.writeheader()
            for o in observations:
                row = o.to_dict()
                # Prevent spreadsheet-formula injection from untrusted source titles.
                writer.writerow({k: "'" + v if isinstance(v, str) and v.startswith(("=", "+", "-", "@", "\t", "\r")) else v for k, v in row.items() if k in columns})
        _write_json(directory / "report.json", run)
        history.save(run, observations)
        _write_json(data_dir / "latest.json", {"id": run_id, "created_at": run["created_at"], "mode": run["mode"]})
        notify("Complete: " + str(directory / "report.pdf"))
        return run
    finally:
        history.close()
