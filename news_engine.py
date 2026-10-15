import json
import os
import time
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

NEWS_SOURCES = {
    "Cointelegraph": "https://cointelegraph.com/rss",
    "CoinDesk": "https://www.coindesk.com/arc/outboundfeeds/rss/?outputType=xml",
    "The Block": "https://www.theblock.co/rss.xml",
}

NEWS_FILE = "news_seen.json"
MAX_AGE_HOURS = 24
MAX_NEWS_PER_SOURCE = 30

KEYWORDS = [
    "bitcoin", "btc", "ethereum", "eth", "crypto",
    "cryptocurrency", "binance", "sec", "etf",
    "hack", "exploit", "regulation", "stablecoin",
    "market crash", "market rally", "liquidation",
    "fed", "interest rate", "solana", "xrp",
]


def load_seen_news():
    if not os.path.exists(NEWS_FILE):
        return {}

    try:
        with open(NEWS_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
            return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_seen_news(seen):
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    cleaned = {}

    for key, value in seen.items():
        try:
            timestamp = datetime.fromisoformat(
                value.replace("Z", "+00:00")
            )
            if timestamp >= cutoff:
                cleaned[key] = value
        except (ValueError, AttributeError):
            continue

    with open(NEWS_FILE, "w", encoding="utf-8") as file:
        json.dump(cleaned, file, ensure_ascii=False, indent=2)


def fetch_feed(source_name, feed_url):
    request = urllib.request.Request(
        feed_url,
        headers={"User-Agent": "CryptoNewsScanner/1.0"}
    )

    with urllib.request.urlopen(request, timeout=15) as response:
        xml_data = response.read()

    root = ET.fromstring(xml_data)
    items = root.findall(".//item")

    if not items:
        items = root.findall(".//{*}entry")

    news = []

    for item in items[:MAX_NEWS_PER_SOURCE]:
        title = item.findtext("title", default="").strip()

        link = item.findtext("link", default="").strip()
        if not link:
            link_element = item.find("{*}link")
            if link_element is not None:
                link = (
                    link_element.get("href", "")
                    or (link_element.text or "")
                ).strip()

        published = (
            item.findtext("pubDate")
            or item.findtext("{*}published")
            or item.findtext("{*}updated")
            or ""
        ).strip()

        if not title or not link:
            continue

        try:
            published_dt = parsedate_to_datetime(published)
            if published_dt.tzinfo is None:
                published_dt = published_dt.replace(
                    tzinfo=timezone.utc
                )
            published_dt = published_dt.astimezone(timezone.utc)
        except (TypeError, ValueError, OverflowError):
            continue

        age = datetime.now(timezone.utc) - published_dt

        if age < timedelta(minutes=-10):
            continue

        if age > timedelta(hours=MAX_AGE_HOURS):
            continue

        text = title.lower()
        if not any(keyword in text for keyword in KEYWORDS):
            continue

        news.append({
            "source": source_name,
            "title": title,
            "link": link,
            "published_at": published_dt.isoformat(),
        })

    return news


def scan_news():
    seen = load_seen_news()
    collected = []
    source_errors = []

    for source_name, feed_url in NEWS_SOURCES.items():
        try:
            items = fetch_feed(source_name, feed_url)
            collected.extend(items)
            print(f"{source_name}: {len(items)} تازہ خبریں ملیں")
        except (
            urllib.error.URLError,
            TimeoutError,
            ET.ParseError,
            OSError,
            ValueError,
        ) as error:
            source_errors.append(source_name)
            print(f"{source_name}: نیوز فیڈ دستیاب نہیں")

    fresh_news = []
    now = datetime.now(timezone.utc).isoformat()

    for item in collected:
        key = item["link"].strip().rstrip("/").lower()

        if key in seen:
            continue

        seen[key] = now
        fresh_news.append(item)

    save_seen_news(seen)

    output = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "new_count": len(fresh_news),
        "source_errors": source_errors,
        "news": fresh_news,
    }

    with open("news_scan.json", "w", encoding="utf-8") as file:
        json.dump(output, file, ensure_ascii=False, indent=2)

    print(f"نئی منفرد خبریں: {len(fresh_news)}")
    print("نتیجہ news_scan.json میں محفوظ ہوگیا۔")

    return output


if __name__ == "__main__":
    scan_news()