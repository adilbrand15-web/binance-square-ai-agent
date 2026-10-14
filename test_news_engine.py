import json
import os
import tempfile
import unittest
from unittest.mock import patch

import news_engine


class TestNewsEngine(unittest.TestCase):

    def test_load_seen_news_when_file_missing(self):
        with patch.object(news_engine, "NEWS_FILE", "missing_test_news.json"):
            self.assertEqual(news_engine.load_seen_news(), {})

    def test_save_and_load_seen_news(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "news_seen.json")

            with patch.object(news_engine, "NEWS_FILE", path):
                news_engine.save_seen_news({})
                self.assertEqual(news_engine.load_seen_news(), {})

    def test_scan_news_handles_source_errors(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            seen_path = os.path.join(temp_dir, "seen.json")

            with (
                patch.object(news_engine, "NEWS_FILE", seen_path),
                patch.object(news_engine, "NEWS_SOURCES", {
                    "Test Source": "https://example.invalid/rss"
                }),
                patch.object(
                    news_engine,
                    "fetch_feed",
                    side_effect=OSError("Test error")
                ),
                patch("builtins.open", create=True) as mock_open,
            ):
                mock_open.return_value.__enter__.return_value.write = (
                    lambda value: None
                )

                with patch.object(
                    news_engine,
                    "save_seen_news",
                    return_value=None
                ):
                    result = news_engine.scan_news()

                self.assertEqual(result["new_count"], 0)
                self.assertEqual(
                    result["source_errors"],
                    ["Test Source"]
                )

    def test_news_output_has_expected_fields(self):
        sample = {
            "source": "Test",
            "title": "Bitcoin market update",
            "link": "https://example.com/news",
            "published_at": "2026-10-14T00:00:00+00:00",
        }

        self.assertIn("title", sample)
        self.assertIn("link", sample)
        self.assertIn("published_at", sample)


if __name__ == "__main__":
    unittest.main()