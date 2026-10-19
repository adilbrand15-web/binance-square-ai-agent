import json
import os
import re
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from html import unescape

# ============================================================
# CRYPTO NEWS ENGINE
# Compatible with news_post_builder.py
# Output: news_scan.json
# Seen records: news_seen.json
# ============================================================

NEWS_SOURCES = {
    "Cointelegraph": "https://cointelegraph.com/rss",
    "CoinDesk": "https://www.coindesk.com/arc/outboundfeeds/rss/?outputType=xml",
    "The Block": "https://www.theblock.co/rss.xml",
}

NEWS_FILE = "news_seen.json"
OUTPUT_FILE = "news_scan.json"

MAX_AGE_HOURS = 24
MAX_NEWS_PER_SOURCE = 30
REQUEST_TIMEOUT_SECONDS = 20
SEEN_RETENTION_DAYS = 7

USER_AGENT = (
    "Mozilla/5.0 (compatible; CryptoNewsScanner/2.0; "
    "+https://github.com/)"
)

# A story is considered relevant if one or more terms match
# its title or summary/description.
KEYWORDS = [
    "bitcoin", "btc", "ethereum", "eth", "crypto",
    "cryptocurrency", "binance", "sec", "etf",
    "hack", "exploit", "regulation", "stablecoin",
    "market crash", "market rally", "liquidation",
    "fed", "interest rate", "solana", "xrp",
    "dogecoin", "doge", "altcoin", "blockchain",
    "defi", "web3", "token", "trading", "exchange",
    "cryptocurrency market", "digital asset",
    "crypto market", "trump", "treasury",
    "interest rates", "inflation", "tariff",
    "lawsuit", "sec approval", "spot bitcoin",
    "spot ethereum", "wallet", "cyberattack",
    "hackers", "price prediction", "bullish",
    "bearish", "all-time high", "all time high",
    "whale", "funding rate", "open interest",
    "futures", "mining", "reserve", "adoption",
]


def utc_now():
    return datetime.now(timezone.utc)


def clean_text(value):
    """Remove HTML tags and normalize whitespace."""
    if value is None:
        return ""

    value = unescape(str(value))
    value = re.sub(r"<script\b[^>]*>.*?</script>", " ", value,
                   flags=re.IGNORECASE | re.DOTALL)
    value = re.sub(r"<style\b[^>]*>.*?</style>", " ", value,
                   flags=re.IGNORECASE | re.DOTALL)
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def local_name(tag):
    """Return an XML tag name without its namespace."""
    return str(tag).rsplit("}", 1)[-1].split(":")[-1].lower()


def parse_published_date(value):
    """Parse RSS, Atom and ISO dates into aware UTC datetimes."""
    if not value:
        return None

    value = clean_text(value)

    try:
        parsed = parsedate_to_datetime(value)
        if parsed is not None:
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        pass

    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def child_text(element, accepted_names):
    """
    Find a direct child by local XML name.
    Handles RSS fields and Atom links.
    """
    accepted_names = {name.lower() for name in accepted_names}

    for child in list(element):
        name = local_name(child.tag)

        if name not in accepted_names:
            continue

        if name == "link":
            href = clean_text(child.attrib.get("href", ""))
            rel = child.attrib.get("rel", "alternate").lower()

            if href and rel in ("alternate", ""):
                return href

            text_value = clean_text(child.text)
            if text_value:
                return text_value

            # Remember a non-alternate link as a last resort.
            if href:
                return href

        value = clean_text("".join(child.itertext()))
        if value:
            return value

    return ""


def get_item_date(item):
    """Read common RSS and Atom publication-date fields."""
    return child_text(
        item,
        {
            "pubdate",
            "published",
            "updated",
            "date",
            "issued",
            "created",
        },
    )


def load_seen_news():
    if not os.path.exists(NEWS_FILE):
        return {}

    try:
        with open(NEWS_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)

        if isinstance(data, dict):
            return data

        print(f"WARNING: {NEWS_FILE} is not a JSON object.")
        return {}

    except (OSError, json.JSONDecodeError) as error:
        print(
            f"WARNING: Could not read {NEWS_FILE}: "
            f"{type(error).__name__}: {error}"
        )
        return {}


def save_seen_news(seen):
    """Retain only valid seen records from the last seven days."""
    cutoff = utc_now() - timedelta(days=SEEN_RETENTION_DAYS)
    cleaned = {}

    for key, value in seen.items():
        timestamp = parse_published_date(value)

        if timestamp is not None and timestamp >= cutoff:
            cleaned[key] = timestamp.isoformat()

    with open(NEWS_FILE, "w", encoding="utf-8") as file:
        json.dump(cleaned, file, ensure_ascii=False, indent=2)


def canonical_url(url):
    """Normalize URLs for duplicate detection without changing queries."""
    url = clean_text(url)

    if not url:
        return ""

    url = url.strip().rstrip("/")
    return url.lower()


def extract_feed_items(root):
    """Support RSS item elements and Atom entry elements."""
    items = [
        element
        for element in root.iter()
        if local_name(element.tag) == "item"
    ]

    if not items:
        items = [
            element
            for element in root.iter()
            if local_name(element.tag) == "entry"
        ]

    return items


def keyword_matches(title, summary):
    text = f"{title} {summary}".lower()

    return [
        keyword
        for keyword in KEYWORDS
        if keyword in text
    ]


def fetch_feed(source_name, feed_url):
    """Fetch one feed and return accepted stories plus diagnostics."""
    request = urllib.request.Request(
        feed_url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": (
                "application/rss+xml, application/atom+xml, "
                "application/xml, text/xml, */*"
            ),
        },
    )

    with urllib.request.urlopen(
        request, timeout=REQUEST_TIMEOUT_SECONDS
    ) as response:
        status_code = getattr(response, "status", 200)
        xml_data = response.read()

    if status_code != 200:
        raise urllib.error.HTTPError(
            feed_url, status_code, "Unexpected HTTP status", None, None
        )

    root = ET.fromstring(xml_data)
    items = extract_feed_items(root)
    current_time = utc_now()

    accepted = []
    diagnostics = {
        "status": "ok",
        "http_status": status_code,
        "feed_items": len(items),
        "accepted_before_deduplication": 0,
        "skipped_missing_title": 0,
        "skipped_missing_link": 0,
        "skipped_missing_date": 0,
        "skipped_outside_age_window": 0,
        "skipped_irrelevant": 0,
    }

    print(f"\n--- {source_name} ---")
    print(f"Feed items found: {len(items)}")

    for item in items[:MAX_NEWS_PER_SOURCE]:
        title = child_text(item, {"title"})
        link = child_text(item, {"link", "guid", "id"})

        # If an RSS guid/id was used as the link, validate it.
        if link and not link.lower().startswith(("http://", "https://")):
            link = child_text(item, {"link"})

        summary = child_text(
            item,
            {
                "description",
                "summary",
                "encoded",
                "content",
                "subtitle",
            },
        )

        published_text = get_item_date(item)
        published_dt = parse_published_date(published_text)

        if not title:
            diagnostics["skipped_missing_title"] += 1
            print("SKIP: missing title")
            continue

        if not link or not link.lower().startswith(("http://", "https://")):
            diagnostics["skipped_missing_link"] += 1
            print(f"SKIP: invalid/missing link | {title[:100]}")
            continue

        if published_dt is None:
            diagnostics["skipped_missing_date"] += 1
            print(f"SKIP: missing/unreadable date | {title[:100]}")
            continue

        age = current_time - published_dt

        if (
            age < timedelta(minutes=-10)
            or age > timedelta(hours=MAX_AGE_HOURS)
        ):
            diagnostics["skipped_outside_age_window"] += 1
            print(
                f"SKIP: outside {MAX_AGE_HOURS}-hour window "
                f"| {title[:100]} | published={published_text}"
            )
            continue

        matched = keyword_matches(title, summary)

        if not matched:
            diagnostics["skipped_irrelevant"] += 1
            print(f"SKIP: no keyword match | {title[:100]}")
            continue

        story = {
            "source": source_name,
            "title": title,
            "link": link,
            "published_at": published_dt.isoformat(),
            "summary": summary[:1500],
            "matched_keywords": matched,
        }

        accepted.append(story)
        print(
            f"ACCEPT: {title[:100]} | "
            f"keywords={','.join(matched[:8])}"
        )

    diagnostics["accepted_before_deduplication"] = len(accepted)

    print(
        f"Accepted: {len(accepted)} | "
        f"missing date: {diagnostics['skipped_missing_date']} | "
        f"old/future: {diagnostics['skipped_outside_age_window']} | "
        f"irrelevant: {diagnostics['skipped_irrelevant']}"
    )

    return accepted, diagnostics


def scan_news():
    print("=" * 60)
    print("CRYPTO NEWS ENGINE STARTING")
    print(f"UTC time: {utc_now().isoformat()}")
    print(f"Sources configured: {len(NEWS_SOURCES)}")
    print(f"Maximum age: {MAX_AGE_HOURS} hours")
    print("=" * 60)

    seen = load_seen_news()
    print(f"Previously recorded URLs: {len(seen)}")

    collected = []
    source_errors = []
    source_status = {}

    for source_name, feed_url in NEWS_SOURCES.items():
        try:
            items, diagnostics = fetch_feed(source_name, feed_url)
            collected.extend(items)

            source_status[source_name] = diagnostics

        except (
            urllib.error.URLError,
            urllib.error.HTTPError,
            TimeoutError,
            ET.ParseError,
            OSError,
            ValueError,
        ) as error:
            source_errors.append(source_name)
            source_status[source_name] = {
                "status": "error",
                "error_type": type(error).__name__,
                "message": str(error)[:300],
            }

            print(
                f"\nFEED ERROR: {source_name} | "
                f"{type(error).__name__}: {str(error)[:200]}"
            )

        except Exception as error:
            # Record unexpected source-specific failures rather than
            # silently ending the complete scan.
            source_errors.append(source_name)
            source_status[source_name] = {
                "status": "error",
                "error_type": type(error).__name__,
                "message": str(error)[:300],
            }

            print(
                f"\nUNEXPECTED FEED ERROR: {source_name} | "
                f"{type(error).__name__}: {str(error)[:200]}"
            )

    fresh_news = []
    duplicate_count = 0
    now = utc_now().isoformat()

    for item in collected:
        key = canonical_url(item.get("link", ""))

        if not key:
            continue

        if key in seen:
            duplicate_count += 1
            continue

        # Mark only relevant, fresh items as seen.
        seen[key] = now
        fresh_news.append(item)

    fresh_news.sort(
        key=lambda item: item.get("published_at", ""),
        reverse=True,
    )

    save_seen_news(seen)

    successful_sources = sum(
        1
        for status in source_status.values()
        if status.get("status") == "ok"
    )

    output = {
        "checked_at": now,
        "new_count": len(fresh_news),
        "collected_count": len(collected),
        "duplicate_count": duplicate_count,
        "source_count": len(NEWS_SOURCES),
        "successful_source_count": successful_sources,
        "source_errors": source_errors,
        "source_status": source_status,
        "news": fresh_news,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as file:
        json.dump(output, file, ensure_ascii=False, indent=2)

    print("\n" + "=" * 60)
    print("CRYPTO NEWS SCAN SUMMARY")
    print(f"Collected relevant stories: {len(collected)}")
    print(f"Already seen / duplicates: {duplicate_count}")
    print(f"New unique stories: {len(fresh_news)}")
    print(f"Successful feeds: {successful_sources}/{len(NEWS_SOURCES)}")
    print(f"Failed feeds: {source_errors}")
    print(f"Output saved: {OUTPUT_FILE}")
    print("=" * 60)

    if not collected:
        print(
            "DIAGNOSIS: No relevant fresh stories passed the feed "
            "date and keyword filters. Check source_status for details."
        )
    elif not fresh_news:
        print(
            "DIAGNOSIS: Relevant stories were found, but all were "
            "already recorded in news_seen.json."
        )

    return output


if __name__ == "__main__":
    scan_news()