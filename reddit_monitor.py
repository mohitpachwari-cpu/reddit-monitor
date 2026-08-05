import os
import re
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

# Case-insensitive lookup, because Reddit permalinks may not preserve the
# exact capitalization you typed in the dict above.
KEYWORDS_BY_LOWER = {s.lower(): kws for s, kws in SUBREDDIT_KEYWORDS.items()}

# ─── SPEED: combine subreddits into multireddit feeds ────────────
# Reddit supports r/sub1+sub2+sub3/new/.rss — one request covers several subs.
# Fewer requests = faster full cycle, while still respecting ~1 req/min.
SUBS_PER_GROUP = 6          # 12 subs / 4 = 3 requests per cycle → ~4 min cycle
FEED_LIMIT     = 100        # max posts per combined feed (Reddit caps at 100)

def build_groups(subs, size):
    return [subs[i:i + size] for i in range(0, len(subs), size)]

SUB_GROUPS = build_groups(SUBREDDITS, SUBS_PER_GROUP)

# Secrets come from environment variables (set these in Railway → Variables).
TELEGRAM_CONFIG = {
    "bot_token": os.environ.get("TELEGRAM_BOT_TOKEN", ""),
    "chat_id":   os.environ.get("TELEGRAM_CHAT_ID", ""),
}

# Reddit throttles unauthenticated RSS to roughly 1 request/minute per IP.
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

SUB_FROM_URL = re.compile(r"reddit\.com/r/([^/]+)/", re.I)

# ─────────────────────────────────────────────
#  FETCH POSTS FROM ONE GROUP OF SUBREDDITS
# ─────────────────────────────────────────────

def fetch_posts_from_group(group):
    """Fetch a combined multireddit feed covering several subreddits at once."""
    global consecutive_403s

    label = "+".join(group)
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
    }

    url = f"https://www.reddit.com/r/{'+'.join(group)}/new/.rss?limit={FEED_LIMIT}"

    try:
        response = requests.get(url, headers=headers, timeout=20)

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

                # Which subreddit did this post come from? The combined feed
                # mixes several, so read it back out of the permalink.
                subreddit = ""
                m = SUB_FROM_URL.search(permalink)
                if m:
                    subreddit = m.group(1)
                if not subreddit:
                    # Fallback: <category term="subname">
                    cat = entry.find(f"{RSS_NS}category")
                    if cat is not None:
                        subreddit = cat.get("term", "")
                if not subreddit:
                    continue  # can't attribute it, skip rather than mis-match

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
                    "id": f"{subreddit.lower()}_{post_id}",
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
            log.warning(f"[{label}] — 403 blocked (#{consecutive_403s}). Waiting {wait}s...")
            time.sleep(wait)
            return []

        elif response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            reset = response.headers.get("x-ratelimit-reset")
            if retry_after and retry_after.replace(".", "", 1).isdigit():
                wait = int(float(retry_after)) + 2
            elif reset and reset.replace(".", "", 1).isdigit():
                wait = int(float(reset)) + 2
            else:
                wait = 60
            wait = min(wait, 300)
            log.warning(f"[{label}] — rate limited. Waiting {wait}s...")
            time.sleep(wait)
            return []

        elif response.status_code == 404:
            log.warning(f"[{label}] — 404. One of these subreddit names may be wrong.")
            return []

        else:
            log.warning(f"[{label}] — Reddit returned status {response.status_code}")
            return []

    except Exception as e:
        log.error(f"[{label}] — Fetch error: {e}")
        return []

# ─────────────────────────────────────────────
#  KEYWORD CHECKER
# ─────────────────────────────────────────────

def contains_keyword(post):
    keywords = KEYWORDS_BY_LOWER.get(post["subreddit"].lower(), [])
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

    log.info(f"Monitoring {len(SUBREDDITS)} subreddit(s) in {len(SUB_GROUPS)} combined feed(s):")
    for g in SUB_GROUPS:
        log.info(f"  [{'+'.join(g)}]")
    est_lo = len(SUB_GROUPS) * (MIN_GAP_BETWEEN_FETCHES[0] + 1) + PAUSE_BETWEEN_SWEEPS[0]
    est_hi = len(SUB_GROUPS) * (MIN_GAP_BETWEEN_FETCHES[1] + 1) + PAUSE_BETWEEN_SWEEPS[1]
    log.info(f"Estimated full cycle: {est_lo/60:.1f}-{est_hi/60:.1f} minutes")

    seen_ids = set()
    seen_order = []
    first_run = True

    while True:
        try:
            for group in SUB_GROUPS:
                posts = fetch_posts_from_group(group)

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
                        log.info(f"'{matched}' found in r/{post['subreddit']}: {post['title'][:60]}")
                        send_telegram(build_message(post, matched))
                        time.sleep(2)

                # Respect Reddit's ~1 request/minute limit.
                time.sleep(random.randint(*MIN_GAP_BETWEEN_FETCHES))

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
