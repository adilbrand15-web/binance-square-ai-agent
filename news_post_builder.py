"""Build crypto-news drafts with improved scoring and diagnostics.

This module creates drafts only.
It never publishes directly to Binance Square.
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

MIN_IMPORTANCE_SCORE = max(
    0, min(10, int(os.getenv("NEWS_MIN_IMPORTANCE_SCORE", "6")))
)
MAX_POSTS_PER_SCAN = max(
    0, int(os.getenv("NEWS_MAX_POSTS_PER_SCAN", "5"))
)

# Scoring rules are additive, then normalized to 0-10.
# Terms are matched in the title and source.
KEYWORD_WEIGHTS = {
    # Critical security incidents
    "security breach": 6,
    "private keys stolen": 6,
    "funds stolen": 6,
    "wallets drained": 6,
    "drains wallets": 6,
    "exploit": 5,
    "hacked": 5,
    "hack": 5,
    "stolen": 5,
    "cyberattack": 5,
    "unauthorized mint": 5,
    "bridge attack": 5,
    "vulnerability": 4,
    "outage": 3,

    # Insolvency and major legal/regulatory developments
    "bankruptcy": 5,
    "insolvency": 5,
    "collapses": 4,
    "collapse": 4,
    "lawsuit": 3,
    "charged": 3,
    "court": 3,
    "sec": 3,
    "regulation": 3,
    "regulatory": 3,
    "ban": 3,
    "banned": 3,
    "approved": 4,
    "approval": 4,
    "rejects": 3,
    "rejected": 3,
    "settlement": 3,
    "investigation": 3,

    # ETFs and institutional activity
    "etf": 3,
    "exchange-traded fund": 3,
    "inflows": 3,
    "outflows": 3,
    "institutional": 2,
    "institutional clients": 3,
    "jpmorgan": 2,
    "blackrock": 3,
    "fidelity": 2,
    "asset manager": 2,
    "fund deposits": 2,

    # Macroeconomics
    "federal reserve": 3,
    "fed": 2,
    "interest rate": 3,
    "rate cut": 4,
    "rate hike": 4,
    "inflation": 2,
    "tariff": 2,
    "treasury": 2,
    "global pmi": 2,

    # Major crypto assets and companies
    "bitcoin": 2,
    "btc": 2,
    "ethereum": 2,
    "ether": 2,
    "binance": 2,
    "coinbase": 2,
    "solana": 2,
    "xrp": 2,
    "dogecoin": 2,
    "stablecoin": 2,
    "crypto": 1,
    "cryptocurrency": 1,
    "blockchain": 1,
    "defi": 2,
    "uniswap": 2,

    # Market movement and derivatives
    "liquidation": 3,
    "liquidations": 3,
    "market crash": 4,
    "market rally": 3,
    "all-time high": 3,
    "all time high": 3,
    "record high": 3,
    "price surge": 2,
    "price drops": 2,
    "plunges": 2,
    "surges": 2,
    "funding rate": 2,
    "open interest": 2,
    "futures": 1,
    "trading volume": 2,

    # Network and ecosystem developments
    "mainnet": 2,
    "upgrade": 2,
    "network launch": 2,
    "partnership": 1,
    "funding round": 1,
    "adoption": 2,
    "token launch": 2,
    "delisting": 3,
    "listed on": 2,
    "listing": 2,

    # Negative signals
    "price prediction": -2,
    "sponsored": -5,
    "advertisement": -3,
}

HASHTAG_RULES = [
    ("bitcoin", "Bitcoin"),
    ("btc", "Bitcoin"),
    ("ethereum", "Ethereum"),
    ("ether", "Ethereum"),
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
    ("uniswap", "Uniswap"),
    ("dogecoin", "Dogecoin"),
]

DEFAULT_HASHTAGS = [
    "CryptoNews",
    "Cryptocurrency",
    "Blockchain",
]


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
    """Normalize URLs for matching existing state records."""
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


def score_story(title, source="", summary=""):
    """Return a 0-10 score, matched terms and scoring breakdown."""
    title_text = str(title or "").lower()
    source_text = str(source or "").lower()
    summary_text = str(summary or "").lower()

    full_text = f"{title_text} {source_text} {summary_text}"

    raw_score = 0
    matched = []

    for keyword, weight in KEYWORD_WEIGHTS.items():
        if keyword in full_text:
            raw_score += weight
            matched.append(f"{keyword} ({weight:+d})")

    # Additional importance for urgent, high-impact headlines.
    # Each bonus is applied only once.
    bonuses = [
        (
            "major security incident",
            ("hack", "hacked", "exploit", "security breach",
             "wallets drained", "funds stolen", "cyberattack"),
            2,
        ),
        (
            "major market movement",
            ("market crash", "market rally", "liquidations",
             "all-time high", "all time high", "record high"),
            1,
        ),
        (
            "institutional or ETF development",
            ("etf", "institutional", "blackrock", "fidelity",
             "jpmorgan", "fund inflows", "fund outflows"),
            1,
        ),
    ]

    for label, terms, bonus in bonuses:
        if any(term in full_text for term in terms):
            raw_score += bonus
            matched.append(f"{label} bonus (+{bonus})")

    generic_headlines = (
        "what happened today",
        "daily roundup",
        "hodler's digest",
        "hodlers digest",
        "week ahead",
    )

    if any(term in title_text for term in generic_headlines):
        raw_score -= 2
        matched.append("generic roundup headline (-2)")

    if "price prediction" in title_text:
        raw_score -= 2
        matched.append("prediction headline (-2)")

    if "sponsored" in title_text or "advertisement" in title_text:
        raw_score -= 4
        matched.append("promotional content penalty (-4)")

    score = max(0, min(10, raw_score))

    return score, matched


def choose_hashtags(title):
    lower = str(title or "").lower()
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
    title = re.sub(
        r"\s+", " ", str(item.get("title", "")).strip()
    )
    source = str(
        item.get("source", "Crypto news source")
    ).strip()
    link = str(item.get("link", "")).strip()
    hashtags = choose_hashtags(title)

    reason = (
        "This development may be relevant to crypto-market participants."
    )

    title_lower = title.lower()

    if any(word in title_lower for word in (
        "hack", "exploit", "stolen", "security breach",
        "wallets drained", "cyberattack", "unauthorized mint",
    )):
        reason = (
            "This security incident may affect users, platforms, "
            "fund safety, and market confidence."
        )
    elif any(word in title_lower for word in (
        "sec", "regulation", "regulatory", "court", "lawsuit",
        "ban", "approved", "approval", "investigation",
    )):
        reason = (
            "This legal or regulatory development may influence "
            "market access, compliance, and investor sentiment."
        )
    elif any(word in title_lower for word in (
        "etf", "inflows", "outflows", "institutional",
        "jpmorgan", "blackrock", "fidelity",
    )):
        reason = (
            "Institutional activity and fund flows can provide "
            "useful context about crypto-market participation."
        )
    elif any(word in title_lower for word in (
        "fed", "interest rate", "rate cut", "rate hike",
        "inflation", "tariff",
    )):
        reason = (
            "Macroeconomic developments can influence risk appetite "
            "across crypto markets."
        )
    elif any(word in title_lower for word in (
        "liquidation", "market crash", "market rally",
        "all-time high", "all time high", "price surge",
        "plunges", "surges",
    )):
        reason = (
            "This market development may be relevant to volatility, "
            "liquidity, and trader sentiment."
        )

    body = (
        f"📰 Crypto News Update\n\n"
        f"{title}\n\n"
        f"Why it matters: {reason}\n\n"
        f"Importance score: {score}/10\n"
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


def previous_status(processed_entry):
    if isinstance(processed_entry, dict):
        return str(processed_entry.get("status", "unknown"))

    return "unknown"


def is_permanently_processed(status):
    """Statuses that should not be re-drafted automatically."""
    return status in {
        "published",
        "published_successfully",
        "posted",
        "draft_created",
        "queued_for_publishing",
        "publishing",
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
    seen_in_this_scan = set()

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
        summary = str(item.get("summary", "")).strip()

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

        if not key or urlsplit(key).scheme not in {"http", "https"}:
            skipped += 1
            diagnostics.append({
                "index": index,
                "title": title,
                "decision": "SKIPPED_INVALID_URL",
            })
            print("Decision: SKIPPED_INVALID_URL")
            continue

        if key in seen_in_this_scan:
            skipped += 1
            diagnostics.append({
                "index": index,
                "title": title,
                "decision": "SKIPPED_DUPLICATE_IN_CURRENT_SCAN",
            })
            print("Decision: SKIPPED_DUPLICATE_IN_CURRENT_SCAN")
            continue

        seen_in_this_scan.add(key)

        existing = processed.get(key)
        status = previous_status(existing)

        if existing is not None and is_permanently_processed(status):
            skipped += 1
            diagnostics.append({
                "index": index,
                "title": title,
                "decision": "SKIPPED_ALREADY_PROCESSED",
                "previous_status": status,
            })
            print("Decision: SKIPPED_ALREADY_PROCESSED")
            print("Previous status:", status)
            continue

        score, matched = score_story(
            title=title,
            source=source,
            summary=summary,
        )

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