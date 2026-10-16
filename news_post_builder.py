
"""Build important crypto-news post drafts without publishing them."""

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

SCAN_FILE = Path(os.getenv("NEWS_SCAN_FILE", "news_scan.json"))
STATE_FILE = Path(os.getenv("NEWS_POST_STATE_FILE", "news_post_state.json"))
DRAFTS_FILE = Path(os.getenv("NEWS_DRAFTS_FILE", "news_post_drafts.json"))
MIN_IMPORTANCE_SCORE = int(os.getenv("NEWS_MIN_IMPORTANCE_SCORE", "6"))
MAX_POSTS_PER_SCAN = int(os.getenv("NEWS_MAX_POSTS_PER_SCAN", "5"))

KEYWORD_WEIGHTS = {
    "exploit": 5, "hack": 5, "stolen": 5, "security breach": 5,
    "bankruptcy": 5, "insolvency": 5, "lawsuit": 3, "charged": 3,
    "sec": 3, "court": 3, "regulation": 3, "ban": 3,
    "approval": 4, "approved": 4, "rejects": 3, "rejected": 3,
    "etf": 3, "exchange-traded fund": 3, "fed": 3,
    "interest rate": 3, "rate cut": 4, "rate hike": 4,
    "binance": 2, "coinbase": 2, "ethereum": 2, "bitcoin": 2,
    "stablecoin": 2, "liquidation": 3, "outage": 3,
    "mainnet": 2, "upgrade": 2, "partnership": 1,
    "funding round": 1, "price prediction": -2, "sponsored": -5,
}

HASHTAG_RULES = [
    ("bitcoin", "Bitcoin"), ("btc", "Bitcoin"),
    ("ethereum", "Ethereum"), ("eth", "Ethereum"),
    ("binance", "Binance"), ("etf", "CryptoETF"),
    ("sec", "CryptoRegulation"), ("regulation", "CryptoRegulation"),
    ("stablecoin", "Stablecoin"), ("solana", "Solana"),
    ("xrp", "XRP"), ("hack", "CryptoSecurity"),
    ("exploit", "CryptoSecurity"), ("fed", "FederalReserve"),
]
DEFAULT_HASHTAGS = ["CryptoNews", "Cryptocurrency", "Blockchain"]


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def load_json(path, default):
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except (OSError, json.JSONDecodeError):
        return default


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2)
    temporary.replace(path)


def canonical_url(url):
    url = (url or "").strip()
    if not url:
        return ""
    parts = urlsplit(url)
    return urlunsplit((
        parts.scheme.lower(),
        parts.netloc.lower(),
        parts.path.rstrip("/"),
        "",
        "",
    ))


def score_story(title, source=""):
    text = f"{title} {source}".lower()
    score = 0
    matched = []

    for keyword, weight in KEYWORD_WEIGHTS.items():
        if keyword in text:
            score += weight
            matched.append(keyword)

    if any(term in title.lower() for term in (
        "what happened today", "daily roundup", "price prediction"
    )):
        score -= 3

    return max(0, min(10, score)), matched


def choose_hashtags(title):
    lower = title.lower()
    tags = []

    for keyword, tag in HASHTAG_RULES:
        if keyword in lower and tag not in tags:
            tags.append(tag)

    for tag in DEFAULT_HASHTAGS:
        if tag not in tags:
            tags.append(tag)
        if len(tags) == 5:
            break

    return ["#" + tag for tag in tags[:5]]


def build_post(item, score, matched):
    title = re.sub(r"\s+", " ", str(item.get("title", "")).strip())
    source = str(item.get("source", "Crypto news source")).strip()
    link = str(item.get("link", "")).strip()
    hashtags = choose_hashtags(title)

    reason = "This development may be relevant to crypto-market participants."

    if any(word in title.lower() for word in (
        "hack", "exploit", "stolen", "security breach"
    )):
        reason = (
            "Security-related developments can affect users, "
            "platforms, and market confidence."
        )
    elif any(word in title.lower() for word in (
        "sec", "regulation", "court", "lawsuit", "ban",
        "approved", "approval"
    )):
        reason = (
            "Regulatory and legal developments can influence "
            "market access and sentiment."
        )
    elif any(word in title.lower() for word in (
        "fed", "interest rate", "rate cut", "rate hike"
    )):
        reason = (
            "Macro-policy decisions can affect risk appetite "
            "across crypto markets."
        )

    body = (
        f"📰 Crypto News Update\n\n{title}\n\n"
        f"Why it matters: {reason}\n\n"
        f"Source: {source}\n"
        f"Read the original report: {link}\n\n"
        + " ".join(hashtags)
    )

    return {
        "title": title,
        "source": source,
        "link": link,
        "published_at": item.get("published_at"),
        "importance_score": score,
        "matched_signals": matched,
        "hashtags": hashtags,
        "post_text": body,
        "status": "draft_only",
        "note": "Draft only; no post has been published.",
    }


def build_drafts(scan=None, state=None):
    scan = scan if scan is not None else load_json(SCAN_FILE, {})
    state = state if state is not None else load_json(STATE_FILE, {})

    if not isinstance(scan, dict):
        scan = {}
    if not isinstance(state, dict):
        state = {}

    processed = state.get("processed_urls", {})
    if not isinstance(processed, dict):
        processed = {}

    stories = scan.get("news", [])
    if not isinstance(stories, list):
        stories = []

    candidates = []
    skipped = 0

    for item in stories:
        if not isinstance(item, dict):
            continue

        title = str(item.get("title", "")).strip()
        link = str(item.get("link", "")).strip()

        if not title or not link:
            skipped += 1
            continue

        key = canonical_url(link)

        if not key or key in processed:
            skipped += 1
            continue

        score, matched = score_story(title, item.get("source", ""))

        if score < MIN_IMPORTANCE_SCORE:
            processed[key] = {
                "processed_at": utc_now_iso(),
                "status": "ignored_low_importance",
                "score": score,
            }
            skipped += 1
            continue

        candidates.append((score, item, key, matched))

    candidates.sort(
        key=lambda row: (row[0], str(row[1].get("published_at", ""))),
        reverse=True,
    )

    selected = candidates[:max(0, MAX_POSTS_PER_SCAN)]
    drafts = []

    for score, item, key, matched in selected:
        drafts.append(build_post(item, score, matched))
        processed[key] = {
            "processed_at": utc_now_iso(),
            "status": "draft_created",
            "score": score,
        }

    state_out = {
        "updated_at": utc_now_iso(),
        "processed_urls": processed,
    }

    output = {
        "built_at": utc_now_iso(),
        "scan_checked_at": scan.get("checked_at"),
        "input_news_count": len(stories),
        "draft_count": len(drafts),
        "minimum_importance_score": MIN_IMPORTANCE_SCORE,
        "max_drafts_per_scan": MAX_POSTS_PER_SCAN,
        "skipped_count": skipped,
        "publishing_enabled": False,
        "drafts": drafts,
    }

    return output, state_out


def main():
    scan = load_json(SCAN_FILE, None)

    if not isinstance(scan, dict):
        raise SystemExit(
            f"ERROR: {SCAN_FILE} missing or invalid. "
            "Run news_engine.py first."
        )

    output, state = build_drafts(scan=scan)
    save_json(DRAFTS_FILE, output)
    save_json(STATE_FILE, state)

    print(f"Input stories: {output['input_news_count']}")
    print(f"Drafts created: {output['draft_count']}")
    print(f"Stories skipped: {output['skipped_count']}")
    print(f"Minimum importance score: {MIN_IMPORTANCE_SCORE}/10")
    print("Publishing: DISABLED (draft-only safety mode)")
    print(f"Drafts saved to {DRAFTS_FILE}")


if __name__ == "__main__":
    main()
