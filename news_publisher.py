
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path.cwd()
STATE_FILE = ROOT / "news_publisher_state.json"
DRAFTS_FILE = Path(
    os.getenv("NEWS_DRAFTS_FILE", "news-artifact/news_post_drafts.json")
)

MIN_SCORE = int(os.getenv("NEWS_MIN_IMPORTANCE_SCORE", "6"))
MAX_POSTS = max(1, int(os.getenv("NEWS_MAX_POSTS_PER_RUN", "1")))
POST_SCRIPT = os.getenv("SQUARE_POST_SCRIPT", "")

def now():
    return datetime.now(timezone.utc).isoformat()

def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except (json.JSONDecodeError, OSError) as exc:
        raise RuntimeError(f"Cannot read {path}: {exc}") from exc

def save_state(state):
    temp = STATE_FILE.with_suffix(".tmp")
    temp.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp.replace(STATE_FILE)

def clean_url(value):
    return (value or "").strip().rstrip("/")

def normalize_state(state):
    state.setdefault("queue", [])
    state.setdefault("published", {})
    state.setdefault("failed", {})
    state.setdefault("uncertain", {})
    return state

def add_drafts(state, drafts):
    queued = {
        clean_url(item.get("link"))
        for item in state["queue"]
        if item.get("link")
    }
    published = set(state["published"])
    failed = set(state["failed"])
    uncertain = set(state["uncertain"])

    added = 0
    for draft in drafts:
        link = clean_url(draft.get("link"))
        text = (draft.get("post_text") or "").strip()

        try:
            score = int(draft.get("importance_score", 0))
        except (TypeError, ValueError):
            score = 0

        if not link or not text or score < MIN_SCORE:
            continue

        if link in queued or link in published or link in failed or link in uncertain:
            continue

        state["queue"].append({
            "link": link,
            "title": draft.get("title", ""),
            "source": draft.get("source", ""),
            "importance_score": score,
            "post_text": text,
            "added_at": now(),
            "attempts": 0,
        })
        queued.add(link)
        added += 1

    return added

def publish_one(item):
    if not os.getenv("BINANCE_SQUARE_OPENAPI_KEY"):
        raise RuntimeError(
            "Missing BINANCE_SQUARE_OPENAPI_KEY GitHub Secret."
        )

    if not POST_SCRIPT or not Path(POST_SCRIPT).is_file():
        raise RuntimeError(
            "Official post-text.mjs script was not found."
        )

    command = [
        "node",
        POST_SCRIPT,
        "--text",
        item["post_text"],
    ]

    print(f"Publishing: {item.get('title', 'Crypto news')}")
    print(f"Importance score: {item.get('importance_score')}")
    print("API key value will not be printed.")

    try:
        result = subprocess.run(
            command,
            cwd=str(Path(POST_SCRIPT).resolve().parent),
            capture_output=True,
            text=True,
            timeout=150,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "status": "uncertain",
            "reason": "Publisher timed out; check Square before retrying.",
            "output": str(exc),
        }

    output = "\n".join(
        part for part in [result.stdout, result.stderr] if part
    )
    print(output[-5000:])

    # The official script explicitly treats Success! with unavailable
    # ID/link as successful because the post may already have been submitted.
    if result.returncode == 0 and "Success!" in output:
        id_match = re.search(r"\bID:\s*(.+)", output)
        link_match = re.search(r"\bLink:\s*(.+)", output)

        post_id = id_match.group(1).strip() if id_match else ""
        post_link = link_match.group(1).strip() if link_match else ""

        return {
            "status": "published",
            "post_id": post_id,
            "post_link": post_link,
            "output": output[-2000:],
        }

    # Network/time-out errors may occur after a post was submitted.
    # Do not blindly retry, or the same news could be published twice.
    ambiguous = any(
        token in output.lower()
        for token in (
            "10004", "network error", "timeout",
            "timed out", "econnreset", "502", "503", "504",
            "connection reset",
        )
    )

    return {
        "status": "uncertain" if ambiguous else "failed",
        "reason": (
            "Publication may have reached Square. Check manually before retrying."
            if ambiguous
            else "The official publishing script reported a failure."
        ),
        "output": output[-3000:],
    }

def main():
    if not DRAFTS_FILE.is_file():
        raise RuntimeError(f"Draft file not found: {DRAFTS_FILE}")

    drafts_data = load_json(DRAFTS_FILE, {})
    drafts = drafts_data.get("drafts", [])

    if not isinstance(drafts, list):
        raise RuntimeError("The drafts field is not a list.")

    state = normalize_state(load_json(STATE_FILE, {}))
    added = add_drafts(state, drafts)
    print(f"New drafts added to queue: {added}")
    print(f"Queue size: {len(state['queue'])}")

    published_this_run = 0

    while state["queue"] and published_this_run < MAX_POSTS:
        item = state["queue"][0]
        item["attempts"] = int(item.get("attempts", 0)) + 1

        result = publish_one(item)
        link = item["link"]

        if result["status"] == "published":
            state["published"][link] = {
                "title": item.get("title", ""),
                "source": item.get("source", ""),
                "importance_score": item.get("importance_score", 0),
                "published_at": now(),
                "post_id": result.get("post_id", ""),
                "post_link": result.get("post_link", ""),
                "attempts": item["attempts"],
            }
            state["queue"].pop(0)
            published_this_run += 1
            print(f"Recorded as published: {link}")

        elif result["status"] == "uncertain":
            state["uncertain"][link] = {
                "title": item.get("title", ""),
                "recorded_at": now(),
                "reason": result.get("reason", ""),
                "attempts": item["attempts"],
            }
            state["queue"].pop(0)
            print(f"UNCERTAIN — manual Square check needed: {link}")

        else:
            state["failed"][link] = {
                "title": item.get("title", ""),
                "recorded_at": now(),
                "reason": result.get("reason", ""),
                "details": result.get("output", ""),
                "attempts": item["attempts"],
            }
            state["queue"].pop(0)
            print(f"FAILED — saved in state: {link}")

        save_state(state)

    state["last_run_at"] = now()
    state["last_run_published_count"] = published_this_run
    save_state(state)

    print(f"Published this run: {published_this_run}")
    print(f"Pending queue: {len(state['queue'])}")
    print(f"Total recorded published links: {len(state['published'])}")
    print(f"Saved state: {STATE_FILE}")

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        sys.exit(1)
