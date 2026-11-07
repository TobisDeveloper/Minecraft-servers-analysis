"""Explicitly synthetic offline fixture. Never presented as current research."""
from datetime import datetime, timedelta, timezone

from .models import Observation, SourceResult


def generate(candidates: list) -> list[SourceResult]:
    now = datetime.now(timezone.utc)
    results = {s: SourceResult(s, "demo", "SYNTHETIC fixture, not live platform data")
               for s in ("youtube", "google_trends", "modrinth", "reddit", "server_lists", "reports")}
    for idx, c in enumerate(candidates):
        strength = max(.1, 1 - idx * .1)
        for market in ("CZ", "SK", "US"):
            values = [20 + (i % 4) for i in range(52)]
            for i in range(36, 52): values[i] = 24 + (i - 36) * strength * (3 if market == "US" else 2.5)
            results["google_trends"].observations.append(Observation(c.id, "google_trends", "search", f"DEMO {c.query} / {market}",
                "https://example.com/demo/search/" + c.id + "/" + market, market, "search_interest", values[-1],
                series=[{"date": (now - timedelta(weeks=51 - i)).date().isoformat(), "value": v} for i, v in enumerate(values)],
                attrs={"synthetic": True}))
        for j in range(3 if idx < 3 else 1):
            results["youtube"].observations.append(Observation(c.id, "youtube", "creators", f"DEMO: {c.name} creator series #{j + 1}",
                f"https://example.com/demo/video/{c.id}/{j}", "CZ/SK" if j == 0 else "GLOBAL", "views", 180_000 * strength,
                (now - timedelta(days=4 + j * 4)).isoformat(), attrs={"subscribers": 100_000, "channel": f"Demo channel {j}", "channel_id": str(j), "synthetic": True}))
        results["modrinth"].observations.append(Observation(c.id, "modrinth", "mods", "DEMO modpack: " + c.name,
            "https://example.com/demo/pack/" + c.id, metric="downloads", value=200_000 * strength,
            attrs={"cumulative": True, "synthetic": True, "history": {"per_day": 4000 * strength, "days": 7, "delta": 28000 * strength}}))
        for j in range(7 if idx < 2 else 2):
            results["reddit"].observations.append(Observation(c.id, "reddit", "community", f"DEMO: How do I host {c.name} with friends? #{j}",
                f"https://example.com/demo/community/{c.id}/{j}", "CZ/SK" if j % 2 == 0 else "GLOBAL", "hosting_question",
                published_at=(now - timedelta(days=j + 1)).isoformat(), attrs={"synthetic": True}))
        results["server_lists"].observations.append(Observation(c.id, "server_lists", "servers", "DEMO local listings",
            "https://example.com/demo/listings/" + c.id, "CZ", "listing_count", 2 if idx < 3 else 30,
            attrs={"sample_size": 100, "snapshot": True, "synthetic": True, "history": {"delta": 1, "days": 7}}))
    return list(results.values())
