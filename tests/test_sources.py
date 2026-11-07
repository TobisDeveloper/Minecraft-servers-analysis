import csv
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from trendfinder.catalog import catalog
from trendfinder.config import load
from trendfinder.models import safe_url
from trendfinder.sources import FetchError, Http, _iso, collect, discord, feed_entries, google_trends, imports, modrinth, reddit, server_lists, youtube


class FakeResponse:
    def __init__(self, text): self.text = text


class CollectorTests(unittest.TestCase):
    def test_errors_are_visible_and_do_not_impute_zero_demand(self):
        class Denied:
            def json(self, *a, **k): raise FetchError("www.reddit.com: 403")
        r = collect("reddit", Denied(), catalog(), load())
        self.assertEqual(r.state, "blocked")
        self.assertEqual(r.observations, [])
        self.assertIn("403", r.message)

    def test_modpack_discovery_and_client_only_exclusion(self):
        class Modrinth:
            def json(self, *a, **k): return {"hits": [
                {"project_id": "new", "title": "Unusual Test Pack", "slug": "unusual-test", "description": "A unique cooperative world", "downloads": 50001, "server_side": "required", "date_created": datetime.now(timezone.utc).isoformat()},
                {"project_id": "client", "title": "Client FPS Pack", "server_side": "unsupported", "downloads": 999999},
            ]}
        result, discovered = modrinth(Modrinth(), catalog(), load())
        self.assertEqual(len(discovered), 1)
        self.assertEqual(discovered[0].project_id, "new")
        self.assertEqual(result.observations[0].value, 50001)

    def test_youtube_official_metrics_and_mid_size(self):
        cfg = load(); cfg["youtube"]["search_queries"] = ["minecraft"]
        class Youtube:
            def json(self, url, **kwargs):
                snippet = {"title": "Lifesteal SMP CZ", "channelId": "channel1", "channelTitle": "Local creator", "publishedAt": datetime.now(timezone.utc).isoformat()}
                if url.endswith("search"): return {"items": [{"id": {"videoId": "video1"}, "snippet": snippet}]}
                if url.endswith("videos"): return {"items": [{"id": "video1", "snippet": snippet, "statistics": {"viewCount": "200000"}}]}
                return {"items": [{"id": "channel1", "statistics": {"subscriberCount": "100000"}}]}
        with patch.dict(os.environ, {"YOUTUBE_API_KEY": "not-a-real-key"}):
            result = youtube(Youtube(), catalog(), cfg)
        self.assertEqual(result.state, "ok")
        self.assertEqual(result.observations[0].market, "CZ/SK")
        self.assertTrue(result.observations[0].attrs["mid_size"])

    def test_listing_navigation_and_nested_rows_are_not_supply(self):
        class Lists:
            def get(self, *a, **k): return FakeResponse('<nav>Lifesteal Lifesteal</nav><article><table><tr><td>Cozy vanilla server with friends online</td></tr></table></article><article>Lifesteal SMP players online now</article>')
        cfg = load(); cfg["server_lists"] = [{"name": "Test", "url": "https://example.com/list", "market": "CZ"}]
        result = server_lists(Lists(), catalog(), cfg)
        lifesteal = next(o for o in result.observations if o.candidate == "lifesteal")
        self.assertEqual(lifesteal.value, 1)
        self.assertEqual(lifesteal.attrs["sample_size"], 2)

    def test_rss_and_atom_dates_and_url_safety(self):
        rss = '<rss><channel><item><title>hello</title><link>https://example.com/a</link><pubDate>Wed, 01 Jul 2026 12:00:00 GMT</pubDate></item></channel></rss>'
        atom = '<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>hello</title><link href="https://example.com/b"/><published>2026-07-01T14:00:00+02:00</published></entry></feed>'
        self.assertEqual(feed_entries(rss)[0]["date"], feed_entries(atom)[0]["date"])
        self.assertEqual(_iso("2026-07-01T14:00:00+02:00"), "2026-07-01T12:00:00+00:00")
        self.assertEqual(safe_url("javascript:alert(1)"), "")
        self.assertEqual(safe_url("https://user:secret@example.com"), "")
        self.assertNotIn("secret", safe_url("https://example.com/?api_key=secret&q=minecraft"))

    def test_authorized_csv_deduplicated_by_engine_and_bad_dates_ignored(self):
        with tempfile.TemporaryDirectory() as folder:
            cfg = load(); cfg["import_dir"] = folder
            with (Path(folder) / "community.csv").open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=["title", "url", "published_at", "market"]); w.writeheader()
                w.writerow({"title": "How to host Lifesteal SMP?", "url": "https://example.com/post", "published_at": datetime.now(timezone.utc).isoformat(), "market": "SK"})
                w.writerow({"title": "Lifesteal", "url": "https://example.com/old", "published_at": "invalid", "market": "SK"})
            r = imports(None, catalog(), cfg)
            self.assertEqual(r.state, "ok"); self.assertEqual(len(r.observations), 1)
            self.assertEqual(r.observations[0].metric, "hosting_question")

    def test_optional_credentials_are_not_required(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(collect("curseforge", None, catalog(), load()).state, "skipped")
            self.assertEqual(collect("discord", None, catalog(), load()).state, "skipped")

    def test_new_creator_format_discovered_without_calling_it_validated(self):
        cfg = load(); cfg["youtube"]["backend"] = "public"
        rows = [{"title": "CrystalForge SMP with friends", "description": "Minecraft", "url": "https://youtube.com/watch?v=test",
                 "date": datetime.now(timezone.utc).isoformat(), "views": 100000, "channel": "Test", "channel_id": "x", "subscribers": 100000, "language": "cs"}]
        candidates = catalog()
        with patch("trendfinder.sources._youtube_public", return_value=rows):
            result = youtube(None, candidates, cfg)
        self.assertEqual(len(candidates), 11)
        self.assertEqual(candidates[-1].name, "CrystalForge SMP")
        self.assertEqual(result.observations[0].candidate, candidates[-1].id)

    def test_google_trends_discards_partial_week_and_collects_both_markets(self):
        import pandas as pd
        class Trends:
            def __init__(self, **kwargs): pass
            def build_payload(self, terms, **kwargs): self.terms = terms
            def interest_over_time(self):
                data = {term: list(range(14)) for term in self.terms}
                data["isPartial"] = [False] * 13 + [True]
                return pd.DataFrame(data, index=pd.date_range("2026-01-01", periods=14, freq="W"))
        cfg = load(); cfg["google_trends"].update(markets=["CZ", "SK"], delay_seconds=0)
        with patch("pytrends.request.TrendReq", Trends):
            r = google_trends(None, catalog()[:1], cfg)
        self.assertEqual(r.state, "ok")
        self.assertEqual({o.market for o in r.observations}, {"CZ", "SK"})
        self.assertEqual(len(r.observations[0].series), 13)

    def test_reddit_dated_setup_question_is_classified(self):
        class Reddit:
            def json(self, *a, **k): return {"data": {"children": [{"data": {
                "title": "How do I host Cobblemon with friends?", "selftext": "", "created_utc": datetime.now(timezone.utc).timestamp(),
                "permalink": "/r/admincraft/comments/test", "score": 5, "num_comments": 4}}]}}
        cfg = load(); cfg["reddit"]["communities"] = ["admincraft"]
        result = reddit(Reddit(), catalog(), cfg)
        self.assertEqual(len(result.observations), 1)
        self.assertEqual(result.observations[0].metric, "hosting_question")

    def test_discord_retains_no_message_body_and_uses_guild_permalink(self):
        class Discord:
            def json(self, url, **k):
                if url.endswith("/messages"):
                    return [{"id": "999", "timestamp": datetime.now(timezone.utc).isoformat(), "content": "Private message: how to host Cobblemon with friends?", "author": {"username": "private-person"}}]
                return {"guild_id": "123456789012345678"}
        cfg = load(); cfg["discord_channel_ids"] = ["223456789012345678"]
        with patch.dict(os.environ, {"DISCORD_BOT_TOKEN": "not-a-real-token"}):
            r = discord(Discord(), catalog(), cfg)
        payload = str(r.observations[0].to_dict())
        self.assertNotIn("private-person", payload)
        self.assertNotIn("Private message:", payload)
        self.assertIn("/123456789012345678/223456789012345678/999", payload)

    def test_request_errors_never_leak_api_key(self):
        import requests
        http = Http()
        error = requests.HTTPError("https://api.example.com/?key=super-secret")
        error.response = requests.Response(); error.response.status_code = 403
        try:
            with patch.object(http.session, "get", side_effect=error):
                with self.assertRaises(FetchError) as result:
                    http.get("https://api.example.com/data", params={"key": "super-secret"})
            self.assertNotIn("super-secret", str(result.exception))
            self.assertIn("403", str(result.exception))
        finally: http.session.close()
