import json
import os
import re
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
OUTPUT_FILE = "news_scan.json"
MAX_AGE_HOURS = 24
MAX_NEWS_PER_SOURCE = 30
REQUEST_TIMEOUT_SECONDS = 15
SEEN_RETENTION_DAYS = 7
USER_AGENT = "Mozilla/5.0 (compatible; CryptoNewsScanner/1.0)"

KEYWORDS = [
    "bitcoin", "btc", "ethereum", "eth", "crypto",
    "cryptocurrency", "binance", "sec", "etf",
    "hack", "exploit", "regulation", "stablecoin",
    "market crash", "market rally", "liquidation",
    "fed", "interest rate", "solana", "xrp",
]


def utc_now():
    return datetime.now(timezone.utc)


def parse_published_date(value):
    """Parse common RSS/Atom dates and return an aware UTC datetime."""
    if not value:
        return None

    value = value.strip()
    try:
        parsed = parsedate_to_datetime(value)
        if parsed is not None:
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        pass

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def clean_text(value):
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def get_child_text(element, names):
    """Find a direct child by local XML name, regardless of namespace."""
    for child in list(element):
        local_name = child.tag.rsplit("}", 1)[-1].lower()
        if local_name not in names:
            continue

        if local_name == "link":
            href = clean_text(child.attrib.get("href", ""))
            rel = child.attrib.get("rel", "alternate").lower()
            if href and rel in ("alternate", ""):
                return href
            if child.text:
                return clean_text(child.text)
        elif child.text:
            return clean_text(child.text)
    return ""


def load_seen_news():
    if not os.path.exists(NEWS_FILE):
        return {}

    try:
        with open(NEWS_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        print(f"تنبیہ: {NEWS_FILE} پڑھا نہیں جا سکا؛ خالی ریکارڈ استعمال ہوگا۔")
        return {}


def save_seen_news(seen):
    cutoff = utc_now() - timedelta(days=SEEN_RETENTION_DAYS)
    cleaned = {}

    for key, value in seen.items():
        timestamp = parse_published_date(value)
        if timestamp is not None and timestamp >= cutoff:
            cleaned[key] = timestamp.isoformat()

    with open(NEWS_FILE, "w", encoding="utf-8") as file:
        json.dump(cleaned, file, ensure_ascii=False, indent=2)


def fetch_feed(source_name, feed_url):
    request = urllib.request.Request(
        feed_url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
        },
    )

    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        xml_data = response.read()

    root = ET.fromstring(xml_data)
    items = root.findall(".//item")
    if not items:
        items = [
            element for element in root.iter()
            if element.tag.rsplit("}", 1)[-1].lower() == "entry"
        ]

    news = []
    current_time = utc_now()

    for item in items[:MAX_NEWS_PER_SOURCE]:
        title = get_child_text(item, {"title"})
        link = get_child_text(item, {"link"})
        published = get_child_text(item, {"pubdate", "published", "updated", "date"})
        published_dt = parse_published_date(published)

        if not title or not link or published_dt is None:
            continue

        age = current_time - published_dt
        if age < timedelta(minutes=-10) or age > timedelta(hours=MAX_AGE_HOURS):
            continue

        title_lower = title.lower()
        if not any(keyword in title_lower for keyword in KEYWORDS):
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
    source_status = {}

    for source_name, feed_url in NEWS_SOURCES.items():
        try:
            items = fetch_feed(source_name, feed_url)
            collected.extend(items)
            source_status[source_name] = {
                "status": "ok",
                "fresh_items_found": len(items),
            }
            print(f"{source_name}: {len(items)} تازہ خبریں ملیں")
        except (urllib.error.URLError, TimeoutError, ET.ParseError, OSError, ValueError) as error:
            source_errors.append(source_name)
            source_status[source_name] = {
                "status": "error",
                "error_type": type(error).__name__,
                "message": str(error)[:300],
            }
            print(f"{source_name}: فیڈ کی جانچ ناکام ({type(error).__name__})")

    fresh_news = []
    now = utc_now().isoformat()

    for item in collected:
        key = item["link"].strip().rstrip("/").lower()
        if not key or key in seen:
            continue
        seen[key] = now
        fresh_news.append(item)

    fresh_news.sort(key=lambda item: item["published_at"], reverse=True)
    save_seen_news(seen)

    output = {
        "checked_at": now,
        "new_count": len(fresh_news),
        "source_count": len(NEWS_SOURCES),
        "successful_source_count": sum(
            1 for status in source_status.values() if status.get("status") == "ok"
        ),
        "source_errors": source_errors,
        "source_status": source_status,
        "news": fresh_news,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as file:
        json.dump(output, file, ensure_ascii=False, indent=2)

    print(f"نئی منفرد خبریں: {len(fresh_news)}")
    print(f"کامیاب نیوز فیڈز: {output['successful_source_count']}/{output['source_count']}")
    print(f"نتیجہ {OUTPUT_FILE} میں محفوظ ہوگیا۔")
    if source_errors:
        print("نوٹ: کچھ نیوز فیڈز ناکام ہوئیں؛ source_status میں تفصیل دیکھیں۔")
    elif not collected:
        print("نوٹ: فیڈز کھل گئیں، لیکن 24 گھنٹوں میں متعلقہ خبریں نہیں ملیں۔")

    return output


if __name__ == "__main__":
    scan_news()