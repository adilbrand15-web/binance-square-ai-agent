
"""Build important crypto-news drafts with detailed diagnostics.
This module creates drafts only; it never publishes to Binance Square.
"""

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
MAX_POSTS_PER_SCAN = max(
    0, int(os.getenv("NEWS_MAX_POSTS_PER_SCAN", "5"))
)

KEYWORD_WEIGHTS = {
    "exploit": 5,
    "hack": 5,
    "stolen": 5,
    "security breach": 5,
    "bankruptcy": 5,
    "insolvency": 5,
    "lawsuit": 3,
    "charged": 3,
    "sec": 3,
    "court": 3,
    "regulation": 3,
    "ban": 3,
    "approval": 4,
    "approved": 4,
    "rejects": 3,
    "rejected": 3,
    "etf": 3,
    "exchange-traded fund": 3,
    "fed": 3,
    "interest rate": 3,
    "rate cut": 4,
    "rate hike": 4,
    "binance": 2,
    "coinbase": 2,
    "ethereum": 2,
    "bitcoin": 2,
    "stablecoin": 2,
    "liquidation": 3,
    "outage": 3,
    "mainnet": 2,
    "upgrade": 2,
    "partnership": 1,
    "funding round": 1,
    "price prediction": -2,
    "sponsored": -5,
}

HASHTAG_RULES = [
    ("bitcoin", "Bitcoin"),
    ("btc", "Bitcoin"),
    ("ethereum", "Ethereum"),
    ("eth", "Ethereum"),
    ("binance", "Binance"),
    ("etf", "CryptoETF"),
    ("sec", "CryptoRegulation"),
    ("regulation", "CryptoRegulation"),
    ("stablecoin", "Stablecoin"),
    ("solana", "Solana"),
    ("xrp", "XRP"),
    ("hack", "CryptoSecurity"),
    ("exploit", "CryptoSecurity"),
    ("fed", "FederalReserve"),
]

DEFAULT_HASHTAGS = ["CryptoNews", "Cryptocurrency", "Blockchain"]


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def load_json(path, default):
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError:
        print(f"[WARN] File not found: {path}")
        return default
    except json.JSONDecodeError as exc:
        print(f"[WARN] Invalid JSON in {path}: {exc}")
        return default
    except OSError as exc:
        print(f"[WARN] Cannot read {path}: {exc}")
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
    """Score a story from title and source; returns score and matched terms."""
    text = f"{title} {source}".lower()
    score = 0
    matched = []

    for keyword, weight in KEYWORD_WEIGHTS.items():
        if keyword in text:
            score += weight
            matched.append(f"{keyword} ({weight:+d})")

    title_lower = title.lower()

    if any(term in title_lower for term in (
        "what happened today",
        "daily roundup",
        "price prediction",
    )):
        score -= 3
        matched.append("generic/prediction headline (-3)")

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

        if len(tags) >= 5:
            break

    return ["#" + tag for tag in tags[:5]]


def build_post(item, score, matched):
    title = re.sub(r"\s+", " ", str(item.get("title", "")).strip())
    source = str(item.get("source", "Crypto news source")).strip()
    link = str(item.get("link", "")).strip()
    hashtags = choose_hashtags(title)

    reason = (
        "This development may be relevant to crypto-market participants."
    )

    title_lower = title.lower()

    if any(word in title_lower for word in (
        "hack", "exploit", "stolen", "security breach"
    )):
        reason = (
            "Security-related developments can affect users, "
            "platforms, and market confidence."
        )
    elif any(word in title_lower for word in (
        "sec", "regulation", "court", "lawsuit", "ban",
        "approved", "approval"
    )):
        reason = (
            "Regulatory and legal developments can influence "
            "market access and sentiment."
        )
    elif any(word in title_lower for word in (
        "fed", "interest rate", "rate cut", "rate hike"
    )):
        reason = (
            "Macro-policy decisions can affect risk appetite "
            "across crypto markets."
        )

    body = (
        f"📰 Crypto News Update\n\n"
        f"{title}\n\n"
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
    diagnostics = []

    print("\n========== NEWS DRAFT DIAGNOSTICS ==========")
    print("Scan file:", SCAN_FILE)
    print("State file:", STATE_FILE)
    print("Draft output:", DRAFTS_FILE)
    print("Minimum score:", MIN_IMPORTANCE_SCORE)
    print("Maximum drafts per scan:", MAX_POSTS_PER_SCAN)
    print("Stories received:", len(stories))
    print("Previously processed URLs:", len(processed))

    for index, item in enumerate(stories, start=1):
        if not isinstance(item, dict):
            skipped += 1
            diagnostics.append({
                "index": index,
                "decision": "SKIPPED_INVALID_ITEM",
            })
            print(f"\n[NEWS {index}] SKIPPED: item is not an object")
            continue

        title = str(item.get("title", "")).strip()
        link = str(item.get("link", "")).strip()
        source = str(item.get("source", "")).strip()

        print(f"\n[NEWS {index}]")
        print("Title:", title or "(missing)")
        print("Source:", source or "(missing)")
        print("Link:", link or "(missing)")

        if not title or not link:
            skipped += 1
            diagnostics.append({
                "index": index,
                "title": title,
                "decision": "SKIPPED_MISSING_TITLE_OR_LINK",
            })
            print("Decision: SKIPPED_MISSING_TITLE_OR_LINK")
            continue

        key = canonical_url(link)

        if not key:
            skipped += 1
            diagnostics.append({
                "index": index,
                "title": title,
                "decision": "SKIPPED_INVALID_URL",
            })
            print("Decision: SKIPPED_INVALID_URL")
            continue

        if key in processed:
            skipped += 1
            previous = processed[key]
            previous_status = (
                previous.get("status", "unknown")
                if isinstance(previous, dict)
                else "unknown"
            )

            diagnostics.append({
                "index": index,
                "title": title,
                "decision": "SKIPPED_ALREADY_PROCESSED",
                "previous_status": previous_status,
            })

            print("Decision: SKIPPED_ALREADY_PROCESSED")
            print("Previous status:", previous_status)
            continue

        score, matched = score_story(title, source)

        print("Importance score:", score, "/ 10")
        print("Matched terms:", matched or "(none)")

        if score < MIN_IMPORTANCE_SCORE:
            processed[key] = {
                "processed_at": utc_now_iso(),
                "status": "ignored_low_importance",
                "score": score,
                "title": title,
                "source": source,
            }

            skipped += 1

            diagnostics.append({
                "index": index,
                "title": title,
                "score": score,
                "decision": "SKIPPED_LOW_IMPORTANCE",
                "matched_terms": matched,
            })

            print(
                f"Decision: SKIPPED_LOW_IMPORTANCE "
                f"({score} < {MIN_IMPORTANCE_SCORE})"
            )
            continue

        candidates.append((score, item, key, matched))

        diagnostics.append({
            "index": index,
            "title": title,
            "score": score,
            "decision": "ELIGIBLE",
            "matched_terms": matched,
        })

        print("Decision: ELIGIBLE_FOR_DRAFT")

    candidates.sort(
        key=lambda row: (
            row[0],
            str(row[1].get("published_at", "")),
        ),
        reverse=True,
    )

    selected = candidates[:MAX_POSTS_PER_SCAN]
    drafts = []

    for score, item, key, matched in selected:
        draft = build_post(item, score, matched)
        drafts.append(draft)

        processed[key] = {
            "processed_at": utc_now_iso(),
            "status": "draft_created",
            "score": score,
            "title": draft["title"],
            "source": draft["source"],
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
        "eligible_count": len(candidates),
        "publishing_enabled": False,
        "diagnostics": diagnostics,
        "drafts": drafts,
    }

    print("\n========== SUMMARY ==========")
    print("Input stories:", len(stories))
    print("Eligible stories:", len(candidates))
    print("Drafts created:", len(drafts))
    print("Stories skipped:", skipped)
    print("Publishing: DISABLED (draft-only safety mode)")
    print("============================================\n")

    return output, state_out


def main():
    print("Starting crypto news draft builder...")

    scan = load_json(SCAN_FILE, None)

    if not isinstance(scan, dict):
        raise SystemExit(
            f"ERROR: {SCAN_FILE} is missing or invalid. "
            "Run news_engine.py first."
        )

    output, state = build_drafts(scan=scan)

    save_json(DRAFTS_FILE, output)
    save_json(STATE_FILE, state)

    print("Drafts saved to:", DRAFTS_FILE)
    print("State saved to:", STATE_FILE)
    print("Final draft count:", output["draft_count"])


if __name__ == "__main__":
    main()
