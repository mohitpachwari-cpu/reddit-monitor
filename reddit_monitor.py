import os
import requests
import time
import logging
from datetime import datetime, timezone
import random

# ─────────────────────────────────────────────
#  DATA SOURCE
# ─────────────────────────────────────────────
# Reddit shut down RSS feeds on 13 Nov 2026 and closed its API to new
# developers. This version reads new posts from Arctic Shift, a free,
# keyless community archive of Reddit (no uptime guarantee).
ARCTIC_SHIFT_URL = "https://arctic-shift.photon-reddit.com/api/posts/search"
USER_AGENT = "personal-deal-alert-bot/1.0 (single user, polls every few minutes)"

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
        "Ai Voucher",
        "PE Air India Voucher",
        "Maharaja",
        "Mr Points",
        "Taj",
        "bonvoy",
        "krisflyer",
        "Amex Points",
        "Marriot",
        "Supercoin",
        "Flight",
        "EMT",
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
        "Cathay",
        "Taj",
        "points",
        "Yatra",
    ],
    "AirTravelIndia": [
        "AI Coupon",
        "Air India",
        "AI Points",
        "Maharaja",
        "marriott bonvoy",
        "bonvoy",
        "krisflyer",
        "Taj",
        "points",
        "Yatra",
    ],
    "BonvoyPointsExchange": [
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
    "travel_deals": [
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
    "IndiaBuySell": [
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
        "MR points",
        "AI Points",
        "Maharaja",
        "krisflyer",
        "bonvoy",
        "Taj",
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
    "delhi_marketplace": [
        "AI Coupon",
        "Economy",
        "Air India",
        "AI Points",
        "Ai Voucher",
        "PE Air India Voucher",
        "Maharaja",
        "Taj",
        "bonvoy",
        "krisflyer",
        "Marriot",
        "Supercoin",
        "Flight",
        "marriott bonvoy",
        "Easemytrip",
        "EMT",
        "Yatra",
    ],
    "BangaloreMarketplace": [
        "AI Coupon",
        "Economy",
        "Air India",
        "AI Points",
        "Ai Voucher",
        "PE Air India Voucher",
        "Maharaja",
        "Taj",
        "bonvoy",
        "krisflyer",
        "Marriot",
        "Supercoin",
        "Flight",
        "marriott bonvoy",
        "Easemytrip",
        "EMT",
        "Yatra",
    ],
    "delhimarketplace": [
        "AI Coupon",
        "Economy",
        "Air India",
        "AI Points",
        "Ai Voucher",
        "PE Air India Voucher",
        "Maharaja",
        "Taj",
        "bonvoy",
        "krisflyer",
        "Marriot",
        "Supercoin",
        "Flight",
        "marriott bonvoy",
        "Easemytrip",
        "EMT",
        "Yatra",
    ],
    "MumbaiMarketplace": [
        "AI Coupon",
        "Economy",
        "Air India",
        "AI Points",
        "Ai Voucher",
        "PE Air India Voucher",
        "Maharaja",
        "Taj",
        "bonvoy",
        "krisflyer",
        "Marriot",
        "Supercoin",
        "Flight",
        "marriott bonvoy",
        "Easemytrip",
        "EMT",
        "Yatra",
    ],
}

# Derived — do not edit
SUBREDDITS = list(SUBREDDIT_KEYWORDS.keys())

# Secrets come from environment variables (set these in Railway → Variables).
TELEGRAM_CONFIG = {
    "bot_token": os.environ.get("TELEGRAM_BOT_TOKEN", ""),
    "chat_id":   os.environ.get("TELEGRAM_CHAT_ID", ""),
}

# Timing. Arctic Shift is a free volunteer service, so we stay polite:
# a short gap between subreddits, then a longer pause before the next sweep.
# 12 subs × ~10s + ~135s pause ≈ a full scan every ~4-5 minutes.
GAP_BETWEEN_SUBREDDITS = (8, 12)     # seconds
PAUSE_BETWEEN_SWEEPS   = (120, 150)  # seconds
POSTS_PER_SUBREDDIT    = 25

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
#  FETCH NEW POSTS FROM ONE SUBREDDIT
# ─────────────────────────────────────────────

def fetch_posts_from(subreddit):
    params = {
        "subreddit": subreddit,
        "sort": "desc",                       # newest first
        "limit": POSTS_PER_SUBREDDIT,
        # No "fields" filter: Arctic Shift rejects the whole request (400)
        # if any listed field name is unknown, so take the full post object.
    }
    try:
        response = requests.get(
            ARCTIC_SHIFT_URL,
            params=params,
            headers={"User-Agent": USER_AGENT},
            timeout=30,
        )

        if response.status_code == 200:
            items = (response.json() or {}).get("data") or []
            posts = []
            for p in items:
                post_id = p.get("id") or ""
                if not post_id:
                    continue
                sub = p.get("subreddit") or subreddit
                permalink = p.get("permalink") or f"/r/{sub}/comments/{post_id}/"
                if permalink.startswith("/"):
                    permalink = "https://www.reddit.com" + permalink
                posts.append({
                    "id": f"{subreddit.lower()}_{post_id}",
                    "title": p.get("title") or "",
                    "selftext": p.get("selftext") or "",
                    "permalink": permalink,
                    "author": p.get("author") or "unknown",
                    "created_utc": p.get("created_utc") or 0,
                    "subreddit": subreddit,
                })
            return posts

        elif response.status_code == 429:
            reset = response.headers.get("X-RateLimit-Reset") or response.headers.get("Retry-After")
            try:
                wait = int(float(reset)) + 2
            except (TypeError, ValueError):
                wait = 60
            wait = max(10, min(wait, 300))
            log.warning(f"r/{subreddit} — Arctic Shift rate limit. Waiting {wait}s...")
            time.sleep(wait)
            return []

        else:
            detail = (response.text or "").strip().replace("\n", " ")[:300]
            log.warning(f"r/{subreddit} — Arctic Shift returned status {response.status_code}: {detail}")
            return []

    except requests.exceptions.Timeout:
        log.warning(f"r/{subreddit} — Arctic Shift timed out, will retry next sweep")
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
        ts = datetime.fromtimestamp(float(post["created_utc"]), tz=timezone.utc).strftime("%d %b %Y, %H:%M UTC")
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

    log.info(f"Source: Arctic Shift. Monitoring {len(SUBREDDITS)} subreddit(s).")
    est_lo = len(SUBREDDITS) * GAP_BETWEEN_SUBREDDITS[0] + PAUSE_BETWEEN_SWEEPS[0]
    est_hi = len(SUBREDDITS) * GAP_BETWEEN_SUBREDDITS[1] + PAUSE_BETWEEN_SWEEPS[1]
    log.info(f"Estimated full cycle: {est_lo/60:.1f}-{est_hi/60:.1f} minutes")

    seen_ids = set()
    seen_order = []
    first_run = True

    while True:
        try:
            for subreddit in SUBREDDITS:
                posts = fetch_posts_from(subreddit)

                if first_run:
                    log.info(f"  r/{subreddit}: {len(posts)} recent posts found")

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
                        send_telegram(build_message(post, matched))
                        time.sleep(2)

                time.sleep(random.randint(*GAP_BETWEEN_SUBREDDITS))

            if first_run:
                log.info(f"Indexed {len(seen_ids)} existing posts. Now watching...")
                first_run = False

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
