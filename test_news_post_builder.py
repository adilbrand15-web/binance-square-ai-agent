
import unittest

from news_post_builder import (
    build_drafts,
    canonical_url,
    choose_hashtags,
    score_story,
)


class NewsPostBuilderTests(unittest.TestCase):

    def test_canonical_url_removes_tracking_query(self):
        self.assertEqual(
            canonical_url("https://EXAMPLE.com/story/?utm_source=x#part"),
            "https://example.com/story",
        )

    def test_security_news_scores_high(self):
        score, matches = score_story(
            "Major exchange reports hack and stolen funds",
            "CoinDesk",
        )
        self.assertGreaterEqual(score, 6)
        self.assertTrue(matches)

    def test_hashtags_max_five(self):
        self.assertLessEqual(
            len(choose_hashtags("Bitcoin ETF and SEC regulation")),
            5,
        )

    def test_deduplicates_and_filters_low_importance(self):
        scan = {
            "checked_at": "2026-10-16T00:00:00+00:00",
            "news": [
                {
                    "title": "Major exchange suffers security hack",
                    "source": "CoinDesk",
                    "link": "https://example.com/hack",
                    "published_at": "2026-10-16T00:00:00+00:00",
                },
                {
                    "title": "Here is what happened in crypto today",
                    "source": "Cointelegraph",
                    "link": "https://example.com/roundup",
                    "published_at": "2026-10-16T00:00:00+00:00",
                },
            ],
        }

        state = {"processed_urls": {}}
        output, new_state = build_drafts(scan, state)

        self.assertEqual(output["draft_count"], 1)
        self.assertEqual(output["drafts"][0]["status"], "draft_only")
        self.assertFalse(output["publishing_enabled"])

        output2, _ = build_drafts(scan, new_state)
        self.assertEqual(output2["draft_count"], 0)


if __name__ == "__main__":
    unittest.main()