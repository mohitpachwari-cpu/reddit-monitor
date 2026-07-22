import os
import requests
import time
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
import random

# ─────────────────────────────────────────────
#  CONFIGURATION
# ─────────────────────────────────────────────

# Each subreddit has its own keyword list.
# Add/remove subreddits and keywords freely.
SUBREDDIT_KEYWORDS = {
    "IndiaDealsExchange": [
        "AI Coupon",
        "Economy",
        "Air India",
        "AI Points",
        "Maharaja",
        "Taj",
        "bonvoy",
        "krisflyer",
        "Marriot",
        "Supercoin",
        "Flight",
        "marriott bonvoy",
        "Easemytrip",
        "Yatra",
    ],
    "amexindia": [
        "AI Coupon",
        "Air India",
        "AI Points",
        "Maharaja",
        "marriott bonvoy",
        "bonvoy",
        "krisflyer",
        "Blinkit",
        "Taj",
        "points",
        "Yatra",
    ],
    "CreditCardsIndia": [
        "AI Coupon",
        "Air India",
        "Infinia",
        "marriott bonvoy",
        "Points",       # <-- these three were missing commas in the
        "MR points",    #     original, so Python glued them into one
        "AI Points",    #     keyword that never matched. Fixed.
        "Maharaja",
        "krisflyer",
        "Blinkit",
        "bonvoy",
        "Taj",
        "points",
        "Yatra",
    ],
    "airindia": [
        "points",
        "miles",
        "marriott bonvoy",
        "reward",
        "krisflyer",
        "bonvoy",
        "redeem",
        "flying returns",
    ],
}

# Derived — do not edit
SUBREDDITS = list(SUBREDDIT_KEYWORDS.keys())

# Secrets come from environment variables (set these in Railway → Variables).
# Nothing sensitive lives in this file anymore.
TELEGRAM_CONFIG = {
    "bot_token": os.environ.get("TELEGRAM_BOT_TOKEN", ""),
    "chat_id":   os.environ.get("TELEGRAM_CHAT_ID", ""),
}

# Reddit throttles unauthenticated RSS to roughly 1 request/minute per IP.
# We fetch one subreddit at a time and wait at least this long between fetches
# so every request is the first in a fresh window (no more random 429s).
MIN_GAP_BETWEEN_FETCHES = (65, 80)   # seconds, randomized
PAUSE_BETWEEN_SWEEPS    = (10, 30)   # small breather after each full sweep

# ─────────────────────────────────────────────
#  LOGGING
# ─────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────
#  ROTATING USER AGENTS
# ─────────────────────────────────────────────

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.1 Safari/605.1.15",
]

RSS_NS = "{http://www.w3.org/2005/Atom}"
consecutive_403s = 0

# ─────────────────────────────────────────────
#  FETCH POSTS FROM ONE SUBREDDIT
# ─────────────────────────────────────────────

def fetch_posts_from(subreddit):
    global consecutive_403s

    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
    }

    url = f"https://www.reddit.com/r/{subreddit}/new/.rss?limit=25"

    try:
        response = requests.get(url, headers=headers, timeout=15)

        if response.status_code == 200:
            consecutive_403s = 0
            root = ET.fromstring(response.content)
            posts = []
            for entry in root.findall(f"{RSS_NS}entry"):
                post_id = (entry.findtext(f"{RSS_NS}id") or "").split("_")[-1]
                title = entry.findtext(f"{RSS_NS}title") or ""
                content = entry.findtext(f"{RSS_NS}content") or ""
                permalink = ""
                link_el = entry.find(f"{RSS_NS}link")
                if link_el is not None:
                    permalink = link_el.get("href", "")
                author = ""
                author_el = entry.find(f"{RSS_NS}author")
                if author_el is not None:
                    author = (author_el.findtext(f"{RSS_NS}name") or "").replace("/u/", "")
                created_utc = 0
                updated = entry.findtext(f"{RSS_NS}updated") or ""
                if updated:
                    try:
                        dt = datetime.strptime(updated, "%Y-%m-%dT%H:%M:%S+00:00")
                        created_utc = dt.replace(tzinfo=timezone.utc).timestamp()
                    except Exception:
                        pass
                posts.append({
                    "id": f"{subreddit}_{post_id}",  # prefix avoids ID collisions across subs
                    "title": title,
                    "selftext": content,
                    "permalink": permalink,
                    "author": author,
                    "created_utc": created_utc,
                    "subreddit": subreddit,
                })
            return posts

        elif response.status_code == 403:
            consecutive_403s += 1
            wait = min(300, 60 * consecutive_403s)
            log.warning(f"r/{subreddit} — 403 blocked (#{consecutive_403s}). Waiting {wait}s...")
            time.sleep(wait)
            return []

        elif response.status_code == 429:
            # Reddit tells us exactly how long to wait — honor the headers
            # instead of guessing. Prefer Retry-After, fall back to the
            # rate-limit reset header, then a sane default.
            retry_after = response.headers.get("Retry-After")
            reset = response.headers.get("x-ratelimit-reset")
            if retry_after and retry_after.replace(".", "", 1).isdigit():
                wait = int(float(retry_after)) + 2
            elif reset and reset.replace(".", "", 1).isdigit():
                wait = int(float(reset)) + 2
            else:
                wait = 60
            wait = min(wait, 300)
            log.warning(f"r/{subreddit} — rate limited. Waiting {wait}s...")
            time.sleep(wait)
            return []

        else:
            log.warning(f"r/{subreddit} — Reddit returned status {response.status_code}")
            return []

    except Exception as e:
        log.error(f"r/{subreddit} — Fetch error: {e}")
        return []

# ─────────────────────────────────────────────
#  KEYWORD CHECKER
# ─────────────────────────────────────────────

def contains_keyword(post):
    keywords = SUBREDDIT_KEYWORDS.get(post["subreddit"], [])
    combined = (post["title"] + " " + post["selftext"]).upper()
    for keyword in keywords:
        if keyword.upper() in combined:
            return keyword
    return None

# ─────────────────────────────────────────────
#  TELEGRAM SENDER
# ─────────────────────────────────────────────

def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_CONFIG['bot_token']}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CONFIG["chat_id"],
            "text": message,
        }
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            log.info("Telegram alert sent!")
        else:
            log.warning(f"Telegram API status: {response.status_code} — {response.text}")
    except Exception as e:
        log.error(f"Telegram send failed: {e}")

# ─────────────────────────────────────────────
#  MESSAGE BUILDER
# ─────────────────────────────────────────────

def build_message(post, matched_keyword):
    if post["created_utc"]:
        ts = datetime.fromtimestamp(post["created_utc"], tz=timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    else:
        ts = "Unknown"
    return (
        f"Keyword Alert: {matched_keyword}\n"
        f"Subreddit: r/{post['subreddit']}\n"
        f"------------------\n"
        f"Title: {post['title']}\n"
        f"Author: u/{post['author']}\n"
        f"Posted: {ts}\n"
        f"------------------\n"
        f"Link: {post['permalink']}"
    )

# ─────────────────────────────────────────────
#  MAIN LOOP
# ─────────────────────────────────────────────

def main():
    if not TELEGRAM_CONFIG["bot_token"] or not TELEGRAM_CONFIG["chat_id"]:
        log.error("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID environment variable. Exiting.")
        return

    log.info(f"Monitoring {len(SUBREDDITS)} subreddit(s):")
    for sub, kws in SUBREDDIT_KEYWORDS.items():
        log.info(f"  r/{sub} → {', '.join(kws)}")
    log.info(f"Waiting {MIN_GAP_BETWEEN_FETCHES[0]}-{MIN_GAP_BETWEEN_FETCHES[1]}s between each subreddit fetch")

    seen_ids = set()
    seen_order = []   # tracks insertion order so trimming keeps the NEWEST ids
    first_run = True

    while True:
        try:
            for subreddit in SUBREDDITS:
                posts = fetch_posts_from(subreddit)

                for post in posts:
                    post_id = post["id"]
                    if post_id in seen_ids:
                        continue
                    seen_ids.add(post_id)
                    seen_order.append(post_id)
                    if first_run:
                        continue
                    matched = contains_keyword(post)
                    if matched:
                        log.info(f"'{matched}' found in r/{subreddit}: {post['title'][:60]}")
                        message = build_message(post, matched)
                        send_telegram(message)
                        time.sleep(2)

                # Respect Reddit's ~1 request/minute limit: wait before the
                # next subreddit so every fetch starts in a fresh window.
                time.sleep(random.randint(*MIN_GAP_BETWEEN_FETCHES))

            if first_run:
                log.info(f"Indexed {len(seen_ids)} existing posts across all subreddits. Now watching...")
                first_run = False

            # Trim memory while correctly keeping the most recent ids
            if len(seen_order) > 5000:
                drop = seen_order[:-2000]
                seen_order = seen_order[-2000:]
                seen_ids.difference_update(drop)

            time.sleep(random.randint(*PAUSE_BETWEEN_SWEEPS))

        except Exception as e:
            log.error(f"Unexpected error: {e}. Continuing in 60s...")
            time.sleep(60)


if __name__ == "__main__":
    main()
