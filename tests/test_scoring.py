import unittest
from datetime import datetime, timedelta, timezone

from trendfinder.catalog import catalog, matches
from trendfinder.config import load
from trendfinder.demo import generate
from trendfinder.models import Observation
from trendfinder.scoring import score, series_metrics


def series(values):
    return [{"date": (datetime.now(timezone.utc) - timedelta(weeks=len(values)-i)).date().isoformat(), "value": v} for i, v in enumerate(values)]


class ScoringTests(unittest.TestCase):
    def test_no_evidence_cannot_be_an_opportunity(self):
        r = score(catalog()[0], [], load())
        self.assertEqual(r["score"], 0)
        self.assertEqual(r["confidence"], 0)
        self.assertEqual(r["stage"], "INSUFFICIENT EVIDENCE")

    def test_sustained_growth_beats_a_spike_and_sparse_series(self):
        rising = series_metrics(series(list(range(10, 62, 2))))
        spike = series_metrics(series([10] * 20 + [100] + [10] * 5))
        sparse = series_metrics(series([0] * 22 + [1, 0, 2, 8]))
        self.assertTrue(rising["sustained"])
        self.assertFalse(spike["sustained"])
        self.assertTrue(sparse["low_volume"])
        self.assertGreater(rising["signal"], spike["signal"])
        self.assertFalse(series_metrics(series([20] * 4))["usable"])

    def test_global_popularity_does_not_imply_local_demand(self):
        candidates = catalog()
        rows = [o for r in generate(candidates) for o in r.observations if o.market not in {"CZ", "SK", "CZ/SK"}]
        r = score(candidates[0], rows, load())
        self.assertEqual(r["stage"], "INSUFFICIENT EVIDENCE")
        self.assertEqual(r["local_evidence"], 0)

    def test_reports_cannot_create_a_positive_score(self):
        o = Observation("lifesteal", "reports", "reports", "Blog hype", "https://example.com/report", "CZ", value=99999)
        self.assertEqual(score(catalog()[0], [o], load())["score"], 0)

    def test_same_url_does_not_double_intent(self):
        date = datetime.now(timezone.utc).isoformat()
        a = Observation("lifesteal", "reddit", "community", "How to host?", "https://example.com/post", "CZ", "hosting_question", published_at=date)
        b = Observation("lifesteal", "imports", "community", "How to host?", "https://example.com/post", "CZ", "hosting_question", published_at=date)
        one, two = score(catalog()[0], [a], load()), score(catalog()[0], [a, b], load())
        self.assertEqual(one["signals"], two["signals"])
        self.assertEqual(one["score"], two["score"])

    def test_single_download_total_has_limited_influence(self):
        o = Observation("lifesteal", "modrinth", "mods", "Pack", "https://example.com/pack", metric="downloads", value=100_000_000)
        r = score(catalog()[0], [o], load())
        self.assertLessEqual(r["signals"]["mods"], 15)
        self.assertFalse(r["temporal_evidence"])

    def test_missing_sk_search_is_not_reweighted(self):
        cfg = load(); c = catalog()[0]
        cz = Observation(c.id, "google_trends", "search", "CZ", "https://example.com/cz", "CZ", series=series(list(range(10,62,2))))
        sk = Observation(c.id, "google_trends", "search", "SK", "https://example.com/sk", "SK", series=cz.series)
        one, both = score(c, [cz], cfg), score(c, [cz, sk], cfg)
        self.assertAlmostEqual(one["signals"]["search"] * 2, both["signals"]["search"], delta=.2)

    def test_alias_boundaries_and_diacritics(self):
        self.assertTrue(matches("LIFESTEAL SMP česky", catalog()[0]))
        self.assertFalse(matches("notlifestealbot", catalog()[0]))
        self.assertTrue(matches("100 dní s kamarády", catalog()[3]))


if __name__ == "__main__": unittest.main()
