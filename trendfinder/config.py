from __future__ import annotations

import json
from pathlib import Path

DEFAULT = {
    "markets": ["CZ", "SK"],
    "sources": ["modrinth", "youtube", "google_trends", "reddit", "server_lists", "reports", "feeds", "imports", "curseforge", "discord"],
    "timeout": 15,
    "days": 90,
    "youtube": {"backend": "auto", "search_queries": ["Minecraft SMP CZ SK", "Minecraft nový server", "Minecraft modpack", "Minecraft but", "Minecraft civilization"], "results_per_query": 8, "channel_ids": [], "local_creator_names": ["SirYakari", "GEJMR", "MenT", "House", "Wedry", "StudioMoonTV", "Asimister", "Duklock"]},
    "google_trends": {"markets": ["CZ", "SK", "US"], "timeframe": "today 12-m", "delay_seconds": 2.0},
    "reddit": {"communities": ["admincraft", "feedthebeast", "Minecraft"], "limit": 60},
    "server_lists": [
        {"name": "Craftlist CZ", "url": "https://craftlist.org/cz/", "market": "CZ"},
        {"name": "Minecraft MP CZ", "url": "https://minecraft-mp.com/country/czech-republic/", "market": "CZ"},
        {"name": "Minecraft MP SK", "url": "https://minecraft-mp.com/country/slovakia/", "market": "SK"},
        {"name": "Minecraft Server List newest", "url": "https://minecraft-server-list.com/sort/New/", "market": "GLOBAL"},
    ],
    "feeds": [],
    "discord_channel_ids": [],
    "import_dir": "imports",
    "max_discovered_packs": 5,
    "max_discovered_formats": 5,
    "watch_terms": [],
    "report_top": 5,
    "ai": {"enabled": False, "endpoint": "http://127.0.0.1:11434", "model": "qwen2.5:3b", "timeout": 120},
    "economics": {"currency": "EUR", "price_per_month": 12.0, "ram_cost_per_gb": 0.65, "cpu_storage_per_month": 2.0, "support_cost_per_hour": 12.0, "support_minutes_per_month": 10.0, "payment_fee_percent": 3.0, "fixed_fee": 0.3},
}


def merge(base: dict, changes: dict) -> dict:
    result = dict(base)
    for key, value in changes.items():
        result[key] = merge(result[key], value) if isinstance(value, dict) and isinstance(result.get(key), dict) else value
    return result


def load(path: str | Path | None = None) -> dict:
    cfg = json.loads(json.dumps(DEFAULT))
    if path:
        with open(path, encoding="utf-8") as f:
            cfg = merge(cfg, json.load(f))
    if cfg["markets"] != ["CZ", "SK"]:
        raise ValueError('This radar targets both markets; markets must be ["CZ", "SK"].')
    if not 1 <= int(cfg["report_top"]) <= 10 or not 1 <= int(cfg["days"]) <= 365:
        raise ValueError("report_top must be 1..10 and days 1..365")
    if not 1 <= int(cfg["timeout"]) <= 60:
        raise ValueError("timeout must be 1..60 seconds")
    if not 0 <= int(cfg["max_discovered_packs"]) <= 20:
        raise ValueError("max_discovered_packs must be 0..20")
    if not 0 <= int(cfg["max_discovered_formats"]) <= 20:
        raise ValueError("max_discovered_formats must be 0..20")
    if cfg["google_trends"]["timeframe"] != "today 12-m":
        raise ValueError("Use today 12-m: search scoring expects a year of weekly observations")
    return cfg
