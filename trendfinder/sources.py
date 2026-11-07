"""Bounded, read-only collectors. A failed source is never a zero-demand signal.

Official APIs are preferred. Public HTML/RSS and unofficial Google Trends /
YouTube adapters may be blocked or change; per-source diagnostics survive that.
"""
from __future__ import annotations

import csv
import contextlib
import hashlib
import io
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote, urlparse
from xml.etree import ElementTree as ET

import requests
from bs4 import BeautifulSoup

from .catalog import discovered_pack, matches
from .models import Candidate, Observation, SourceResult, utcnow

FAMILIES = {"youtube": "creators", "google_trends": "search", "modrinth": "mods",
            "curseforge": "mods", "reddit": "community", "discord": "community",
            "server_lists": "servers", "reports": "reports", "feeds": "community", "imports": "community"}


class FetchError(Exception):
    pass


class Http:
    def __init__(self, timeout: int = 15):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "CZSK-Minecraft-Trendfinder/2.0 (research; public metadata only)"
        self.timeout = timeout

    def get(self, url: str, **kwargs) -> requests.Response:
        try:
            r = self.session.get(url, timeout=self.timeout, **kwargs)
            r.raise_for_status()
            if len(r.content) > 8_000_000:
                raise FetchError(f"Response too large from {urlparse(url).hostname}")
            return r
        except requests.RequestException as exc:
            code = exc.response.status_code if exc.response is not None else "connection/timeout"
            # Requests exceptions can contain API keys. Only return host/status.
            raise FetchError(f"{urlparse(url).hostname}: {code}; check access, quota and credentials") from None

    def json(self, url: str, **kwargs):
        try:
            return self.get(url, **kwargs).json()
        except ValueError:
            raise FetchError(f"{urlparse(url).hostname}: invalid JSON") from None


def _finish(source: str, observations: list, errors: list, successes: int) -> SourceResult:
    state = "partial" if errors and successes else "blocked" if errors else "ok"
    return SourceResult(source, state, "; ".join(dict.fromkeys(errors))[:1000], observations)


def _iso(value: str) -> str:
    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except ValueError:
        try:
            return parsedate_to_datetime(value).astimezone(timezone.utc).isoformat()
        except (ValueError, TypeError):
            return ""


def _recent(date: str, days: int) -> bool:
    if not date:
        return False
    try:
        dt = datetime.fromisoformat(date.replace("Z", "+00:00"))
        if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - timedelta(days=days) <= dt <= datetime.now(timezone.utc) + timedelta(minutes=5)
    except (ValueError, TypeError):
        return False


def _local(text: str) -> str:
    if re.search(r"\b(cz|sk|cesky|česky|slovensky|český|slovenský|slovakia|czech)\b", text, re.I):
        return "CZ/SK"
    return "GLOBAL"


def modrinth(http: Http, candidates: list[Candidate], cfg: dict) -> tuple[SourceResult, list[Candidate]]:
    hits, errors, successes = {}, [], 0
    searches = [("", "downloads"), ("", "newest")] + [(c.query, "relevance") for c in candidates]
    for query, index in searches:
        try:
            data = http.json("https://api.modrinth.com/v2/search", params={"query": query, "index": index,
                             "limit": 50, "facets": json.dumps([["project_type:modpack"]])})
            for hit in data.get("hits", []):
                if hit.get("server_side") != "unsupported":
                    hits[hit["project_id"]] = hit
            successes += 1
        except FetchError as exc:
            errors.append(str(exc))
            break  # a host denial is not cured by ten more requests
    discovered = []
    for h in sorted(hits.values(), key=lambda x: x.get("downloads", 0), reverse=True):
        text = h.get("title", "") + " " + h.get("description", "")
        if (not any(matches(text, c) for c in candidates) and h.get("downloads", 0) >= 5000
                and _recent(h.get("date_created", ""), 180)
                and len(discovered) < cfg["max_discovered_packs"]):
            discovered.append(discovered_pack(h["project_id"], h["title"], h["slug"]))
    observations = []
    for h in hits.values():
        for c in candidates + discovered:
            if c.project_id == h["project_id"] or matches(h.get("title", "") + " " + h.get("description", ""), c):
                observations.append(Observation(c.id, "modrinth", "mods", h["title"],
                    "https://modrinth.com/modpack/" + h["slug"], metric="downloads", value=float(h.get("downloads", 0)),
                    published_at=h.get("date_created", ""), attrs={"project_id": h["project_id"],
                    "updated": h.get("date_modified"), "server_side": h.get("server_side", "unknown"),
                    "license": "Verify on project page before redistribution", "cumulative": True}))
    return _finish("modrinth", observations, errors, successes), discovered


def curseforge(http: Http, candidates: list[Candidate], cfg: dict) -> SourceResult:
    key = os.getenv("CURSEFORGE_API_KEY")
    if not key:
        return SourceResult("curseforge", "skipped", "Optional CURSEFORGE_API_KEY is not set. Modrinth remains independent.")
    obs, errors, successes = [], [], 0
    for c in candidates:
        try:
            data = http.json("https://api.curseforge.com/v1/mods", headers={"x-api-key": key},
                             params={"gameId": 432, "classId": 4471, "searchFilter": c.query, "pageSize": 10,
                                     "sortField": 6, "sortOrder": "desc"})
            for h in data.get("data", []):
                if not matches(h.get("name", "") + " " + h.get("summary", ""), c):
                    continue
                obs.append(Observation(c.id, "curseforge", "mods", h["name"], h.get("links", {}).get("websiteUrl", ""),
                           metric="downloads", value=float(h.get("downloadCount", 0)), published_at=h.get("dateCreated", ""),
                           attrs={"project_id": str(h["id"]), "cumulative": True, "redistribution": "Check author permissions and license"}))
            successes += 1
        except FetchError as exc:
            errors.append(str(exc)); break
    return _finish("curseforge", obs, errors, successes)


def _youtube_api(http: Http, cfg: dict) -> list[dict]:
    key = os.environ["YOUTUBE_API_KEY"]
    root = "https://www.googleapis.com/youtube/v3/"
    videos = {}
    since = (datetime.now(timezone.utc) - timedelta(days=cfg["days"])).isoformat(timespec="seconds").replace("+00:00", "Z")
    yt = cfg["youtube"]
    searches = [{"q": q, "type": "video", "order": "date"} for q in yt["search_queries"]]
    searches += [{"channelId": channel, "type": "video", "order": "date"} for channel in yt["channel_ids"]]
    for search in searches:
        data = http.json(root + "search", params={**search, "part": "snippet", "maxResults": min(25, yt["results_per_query"]),
                                                 "publishedAfter": since, "key": key})
        for item in data.get("items", []):
            vid = item.get("id", {}).get("videoId")
            if vid:
                videos[vid] = item["snippet"]
    result = []
    ids = list(videos)
    for offset in range(0, len(ids), 50):
        data = http.json(root + "videos", params={"part": "statistics,snippet", "id": ",".join(ids[offset:offset + 50]), "key": key})
        result.extend(data.get("items", []))
    channels = list({x["snippet"]["channelId"] for x in result})
    subs = {}
    for offset in range(0, len(channels), 50):
        data = http.json(root + "channels", params={"part": "statistics,snippet", "id": ",".join(channels[offset:offset + 50]), "key": key})
        for item in data.get("items", []):
            stats = item.get("statistics", {})
            subs[item["id"]] = 0 if stats.get("hiddenSubscriberCount") else int(stats.get("subscriberCount", 0))
    return [{"title": x["snippet"]["title"], "description": x["snippet"].get("description", ""),
             "url": "https://www.youtube.com/watch?v=" + x["id"], "date": x["snippet"]["publishedAt"],
             "channel": x["snippet"]["channelTitle"], "channel_id": x["snippet"]["channelId"],
             "views": int(x.get("statistics", {}).get("viewCount", 0)), "subscribers": subs.get(x["snippet"]["channelId"], 0),
             "language": x["snippet"].get("defaultAudioLanguage", "")} for x in result]


def _youtube_public(cfg: dict) -> list[dict]:
    # No login/cookies; public metadata only. Many deployments block this adapter.
    import yt_dlp
    class Quiet:
        def debug(self, *_): pass
        def warning(self, *_): pass
        def error(self, *_): pass
    result = []
    opts = {"quiet": True, "no_warnings": True, "skip_download": True, "extract_flat": "in_playlist",
            "socket_timeout": min(cfg["timeout"], 8), "retries": 0, "extractor_retries": 0,
            "logger": Quiet(), "playlistend": cfg["youtube"]["results_per_query"]}
    with yt_dlp.YoutubeDL(opts) as ydl:
        for query in cfg["youtube"]["search_queries"]:
            try:
                data = ydl.extract_info(f'ytsearchdate{cfg["youtube"]["results_per_query"]}:{query}', download=False)
            except Exception:
                raise FetchError("Public YouTube search unavailable. Configure YOUTUBE_API_KEY for the official adapter.") from None
            for x in (data or {}).get("entries", []):
                if not x: continue
                date = ""
                if x.get("timestamp"):
                    date = datetime.fromtimestamp(x["timestamp"], timezone.utc).isoformat()
                result.append({"title": x.get("title", ""), "description": x.get("description", ""),
                    "url": x.get("url", ""), "date": date, "channel": x.get("channel", ""),
                    "channel_id": x.get("channel_id", ""), "views": x.get("view_count") or 0,
                    "subscribers": x.get("channel_follower_count") or 0, "language": ""})
    return result


def youtube(http: Http, candidates: list[Candidate], cfg: dict) -> SourceResult:
    backend = cfg["youtube"]["backend"]
    if backend == "api" and not os.getenv("YOUTUBE_API_KEY"):
        return SourceResult("youtube", "skipped", "YOUTUBE_API_KEY required by configured API backend")
    official = bool(os.getenv("YOUTUBE_API_KEY")) and backend != "public"
    rows = _youtube_api(http, cfg) if official else _youtube_public(cfg)
    # Discover named SMPs and creator challenges before matching this collection.
    # One viral title is only a hypothesis; the cross-source/local pilot gate still applies.
    discovered = 0
    for x in rows:
        if discovered >= cfg["max_discovered_formats"]: break
        if x["views"] < 50_000 or not _recent(x["date"], cfg["days"]): continue
        if any(matches(x["title"], c) for c in candidates): continue
        named = re.search(r"\b([\w-]{3,24})\s+SMP\b", x["title"], re.I)
        challenge = re.search(r"\bMinecraft\s*,?\s+(?:but|ale)\s+([^|!?]{5,45})", x["title"], re.I)
        name = (named.group(0) if named else challenge.group(0) if challenge else "").strip()
        if not name: continue
        slug = "creator-" + hashlib.sha256(name.casefold().encode()).hexdigest()[:10]
        c = discovered_pack(slug, name, name)
        c.id = slug; c.project_id = ""; c.ram_gb = 4
        c.stack = "Creator-format hypothesis: determine whether a plugin, datapack or modpack can reproduce it legally"
        c.risks = ["Single-title discovery; format may not generalize to a public server", "Creator/name/trademark permissions", "Technical implementation and RAM budget unverified"]
        candidates.append(c); discovered += 1
    obs, seen = [], set()
    for x in rows:
        if x["url"] in seen: continue
        seen.add(x["url"])
        if x["date"] and not _recent(x["date"], cfg["days"]): continue
        for c in candidates:
            if not matches(x["title"] + " " + x["description"][:500], c): continue
            known_local = x["channel"].casefold() in {n.casefold() for n in cfg["youtube"]["local_creator_names"]}
            market = "CZ/SK" if x["language"].startswith(("cs", "sk")) or known_local else _local(x["title"] + " " + x["channel"])
            obs.append(Observation(c.id, "youtube", "creators", x["title"], x["url"], market,
                "views", float(x["views"]), x["date"], attrs={"subscribers": x["subscribers"], "channel": x["channel"],
                "channel_id": x["channel_id"], "mid_size": 50_000 <= x["subscribers"] <= 500_000,
                "locality": "Language/title heuristic, not verified audience geography",
                "breakout_method": "Views/subscribers proxy; not a channel historical baseline"}))
    return SourceResult("youtube", "ok" if official else "partial",
        "Official YouTube Data API; views/subscribers proxy, no channel baseline." if official else
        "Public search metadata: subscriber counts or dates may be absent. Use API key for stronger creator evidence.", obs)


def google_trends(http: Http, candidates: list[Candidate], cfg: dict) -> SourceResult:
    from pytrends.request import TrendReq
    obs, errors, successes = [], [], 0
    g = cfg["google_trends"]
    # pytrends is unofficial; a rejected market is not retried for every term.
    for market in g["markets"]:
        try:
            # pytrends prints its own proxy-rotation advice even when no proxy list
            # is configured. Surface our diagnostic instead, retaining inherited trust.
            with contextlib.redirect_stdout(io.StringIO()):
                client = TrendReq(hl="en-US", tz=0, timeout=(min(cfg["timeout"], 10), cfg["timeout"]), retries=0)
            for start in range(0, len(candidates), 5):
                batch = candidates[start:start + 5]
                terms = [c.query for c in batch]
                client.build_payload(terms, timeframe=g["timeframe"], geo=market)
                frame = client.interest_over_time()
                successes += 1
                for c in batch:
                    if c.query not in frame.columns: continue
                    series = [{"date": date.date().isoformat(), "value": float(row[c.query])}
                              for date, row in frame.iterrows() if not row.get("isPartial", False)]
                    obs.append(Observation(c.id, "google_trends", "search", f'{c.query} / {market} / 12 months',
                        f'https://trends.google.com/trends/explore?date=today%2012-m&geo={market}&q={quote(c.query)}',
                        market, "search_interest", series=series,
                        value=sum(p["value"] for p in series[-4:]) / max(1, len(series[-4:])),
                        attrs={"relative_index": True, "query": c.query, "partial_week_removed": True,
                               "warning": "0-100 index, not search volume; compare momentum within each series only"}))
                time.sleep(max(0, g["delay_seconds"]))
        except Exception:
            errors.append(f"Google Trends {market}: unavailable/rate limited (unofficial adapter); no demand value imputed")
    return _finish("google_trends", obs, errors, successes)


HOSTING = re.compile(r"\b(host|hosting|server|setup|set up|friends|multiplayer|dedicated|how do|how to|jak|ako|kamarad|kamarát)\b", re.I)


def reddit(http: Http, candidates: list[Candidate], cfg: dict) -> SourceResult:
    obs, errors, successes = [], [], 0
    for community in cfg["reddit"]["communities"]:
        try:
            data = http.json(f"https://www.reddit.com/r/{quote(community, safe='')}/new.json",
                             params={"limit": min(100, cfg["reddit"]["limit"]), "raw_json": 1})
            successes += 1
            for item in data.get("data", {}).get("children", []):
                x = item["data"]
                date = datetime.fromtimestamp(x["created_utc"], timezone.utc).isoformat()
                if not _recent(date, cfg["days"]): continue
                text = x.get("title", "") + " " + x.get("selftext", "")[:3000]
                for c in candidates:
                    if matches(text, c):
                        obs.append(Observation(c.id, "reddit", "community", x["title"],
                            "https://www.reddit.com" + x["permalink"], _local(text), "hosting_question" if HOSTING.search(text) else "mention",
                            published_at=date, attrs={"community": community, "score": x.get("score", 0),
                            "comments": x.get("num_comments", 0), "sampling": "Most recent posts; not a complete archive"}))
        except FetchError as exc:
            errors.append(str(exc)); break
    return _finish("reddit", obs, errors, successes)


def server_lists(http: Http, candidates: list[Candidate], cfg: dict) -> SourceResult:
    obs, errors, successes = [], [], 0
    for site in cfg["server_lists"]:
        try:
            soup = BeautifulSoup(http.get(site["url"]).text, "html.parser")
            for node in soup(["script", "style", "nav", "footer", "header"]): node.decompose()
            # Strip global tag navigation. Count matching listing-sized containers,
            # not repeated keyword occurrences in the site's navigation.
            containers = soup.select("article, .server, .server-entry, .listing-item, .server-row, .server-item, .server-card, tr")
            # Don't count both a card and a nested table row as separate servers.
            container_ids = {id(n) for n in containers}
            containers = [n for n in containers if not any(id(p) in container_ids for p in n.parents)]
            if not containers:
                errors.append(f'{site["name"]}: listing markup unrecognized; no saturation estimate')
                continue
            text_rows = list(dict.fromkeys(n.get_text(" ", strip=True) for n in containers))
            text_rows = [t for t in text_rows if 20 < len(t) < 15_000]
            if not text_rows:
                errors.append(f'{site["name"]}: no usable listing rows'); continue
            successes += 1
            for c in candidates:
                count = sum(matches(t, c) for t in text_rows)
                obs.append(Observation(c.id, "server_lists", "servers", site["name"] + " / sampled listings", site["url"],
                    site["market"], "listing_count", float(count), attrs={"sample_size": len(text_rows), "site": site["name"],
                    "sampling": "First-page sample, not total market share or verified new listings", "snapshot": True}))
        except FetchError as exc:
            errors.append(str(exc))
    return _finish("server_lists", obs, errors, successes)


def feed_entries(xml: str) -> list[dict]:
    root = ET.fromstring(xml)
    result = []
    for node in root.iter():
        if node.tag.rsplit("}", 1)[-1] not in {"item", "entry"}: continue
        fields = {}
        for child in node:
            tag = child.tag.rsplit("}", 1)[-1]
            if tag == "link":
                fields["url"] = child.get("href") or child.text or ""
            elif tag in {"title", "description", "summary", "content", "published", "updated", "pubDate"}:
                fields[tag] = "".join(child.itertext())
        result.append({"title": fields.get("title", ""), "text": fields.get("description", fields.get("summary", fields.get("content", ""))),
                       "url": fields.get("url", ""), "date": _iso(fields.get("published", fields.get("pubDate", fields.get("updated", ""))))})
    return result


def feeds(http: Http, candidates: list[Candidate], cfg: dict, reports: bool = False) -> SourceResult:
    source = "reports" if reports else "feeds"
    sites = ([{"url": "https://news.google.com/rss/search?q=Minecraft+server+trends+modpack&hl=en-US&gl=US&ceid=US:en",
               "name": "General reporting (lagging signal)", "market": "GLOBAL", "family": "reports"}]
             if reports else list(cfg["feeds"]))
    if not reports:
        sites += [{"url": "https://www.youtube.com/feeds/videos.xml?channel_id=" + quote(ch),
                   "name": "Watched YouTube channel", "market": "CZ/SK", "family": "creators"}
                  for ch in cfg["youtube"]["channel_ids"]]
    if not sites:
        return SourceResult(source, "skipped", "No authorized RSS/Atom feeds or watched channel IDs configured; see config.example.json")
    obs, errors, successes = [], [], 0
    for site in sites:
        try:
            entries = feed_entries(http.get(site["url"]).text)
            successes += 1
            for x in entries[:100]:
                if not _recent(x["date"], cfg["days"]): continue
                text = x["title"] + " " + x["text"]
                for c in candidates:
                    if matches(text, c):
                        family = "reports" if reports else site.get("family", "community")
                        if family not in {"community", "creators", "reports"}: family = "community"
                        obs.append(Observation(c.id, source, family, x["title"], x["url"], site.get("market", "GLOBAL"),
                            "hosting_question" if family == "community" and HOSTING.search(text) else "mention",
                            published_at=x["date"], attrs={"feed": site.get("name", "RSS"), "locality": "Configured feed market"}))
        except (FetchError, ET.ParseError) as exc:
            errors.append(str(exc) if isinstance(exc, FetchError) else "Malformed RSS/Atom feed")
    return _finish(source, obs, errors, successes)


def imports(http: Http, candidates: list[Candidate], cfg: dict) -> SourceResult:
    directory = Path(cfg["import_dir"])
    files = sorted(directory.glob("*.csv")) if directory.exists() else []
    if not files:
        return SourceResult("imports", "skipped", "No CSV exports in import_dir; private TikTok/Facebook/Discord data is not assumed accessible")
    obs, errors, successes = [], [], 0
    allowed = {"community", "creators", "reports"}
    for path in files[:30]:
        try:
            if path.stat().st_size > 5_000_000:
                errors.append(path.name + ": exceeds 5 MB"); continue
            with path.open(encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                if not {"title", "url", "published_at", "market"} <= set(reader.fieldnames or []):
                    raise ValueError("required columns: title,url,published_at,market")
                for i, row in enumerate(reader):
                    if i >= 10_000: break
                    date = _iso(row["published_at"])
                    if not _recent(date, cfg["days"]): continue
                    family = row.get("family", "community")
                    if family not in allowed: raise ValueError("family must be community, creators or reports")
                    market = row["market"].upper()
                    if market not in {"CZ", "SK", "CZ/SK", "GLOBAL", "US", "GB"}: raise ValueError("invalid market")
                    text = row["title"] + " " + row.get("text", "")
                    for c in candidates:
                        if matches(text, c):
                            obs.append(Observation(c.id, "imports", family, row["title"], row["url"], market,
                                "hosting_question" if HOSTING.search(text) and family == "community" else "mention",
                                published_at=date, attrs={"import_file": path.name, "provenance": "User-supplied export; not platform verified"}))
            successes += 1
        except (OSError, ValueError, csv.Error):
            errors.append(path.name + ": invalid export; check schema, dates and encoding")
    return _finish("imports", obs, errors, successes)


def discord(http: Http, candidates: list[Candidate], cfg: dict) -> SourceResult:
    token = os.getenv("DISCORD_BOT_TOKEN")
    channels = cfg["discord_channel_ids"]
    if not token or not channels:
        return SourceResult("discord", "skipped", "Optional bot token and explicitly authorized channel IDs are not configured")
    obs, errors, successes = [], [], 0
    for channel in channels:
        if not re.fullmatch(r"\d{15,22}", str(channel)):
            errors.append("Invalid Discord channel ID"); continue
        try:
            info = http.json(f"https://discord.com/api/v10/channels/{channel}", headers={"Authorization": "Bot " + token})
            guild = str(info.get("guild_id") or "@me")
            rows = http.json(f"https://discord.com/api/v10/channels/{channel}/messages", params={"limit": 100},
                             headers={"Authorization": "Bot " + token})
            successes += 1
            for x in rows:
                if x.get("author", {}).get("bot") or not _recent(x.get("timestamp", ""), cfg["days"]): continue
                text = x.get("content", "")
                for c in candidates:
                    if matches(text, c):
                        # Don't persist message text/user names. Citation needs channel permission to view.
                        obs.append(Observation(c.id, "discord", "community", f"Authorized channel: {c.name} discussion",
                            f'https://discord.com/channels/{guild}/{channel}/{x["id"]}', "CZ/SK",
                            "hosting_question" if HOSTING.search(text) else "mention", published_at=x["timestamp"],
                            attrs={"private": True, "sampling": "Last 100 messages; requires message-content permission"}))
        except FetchError as exc:
            errors.append(str(exc)); break
    return _finish("discord", obs, errors, successes)


def collect(name: str, http: Http, candidates: list[Candidate], cfg: dict) -> SourceResult:
    adapters = {"curseforge": curseforge, "youtube": youtube, "google_trends": google_trends,
                "reddit": reddit, "server_lists": server_lists, "reports": lambda *a: feeds(*a, reports=True),
                "feeds": feeds, "imports": imports, "discord": discord}
    if name not in adapters:
        return SourceResult(name, "error", "Unknown source in configuration")
    try:
        return adapters[name](http, candidates, cfg)
    except Exception as exc:
        # Keep running independent sources; avoid logging URLs containing credentials.
        return SourceResult(name, "blocked" if isinstance(exc, FetchError) else "error",
                            str(exc) if isinstance(exc, FetchError) else f"Adapter failed ({type(exc).__name__}); no values imputed")
