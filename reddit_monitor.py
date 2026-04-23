import re
import requests
import time
import logging
import xml.etree.ElementTree as ET
from urllib.parse import quote
from datetime import datetime
import random

# ─────────────────────────────────────────────
#  CONFIGURATION
# ─────────────────────────────────────────────

SUBREDDIT_NAME = "IndiaDealsExchange"

KEYWORDS = [
    "AI Coupon",
    "Air India",
    "Ai Points",
    "Maharaja",
    "Blinkit",
    "Taj"
    # "DEAL",
    # "DISCOUNT",
]

WHATSAPP_CONFIG = {
    "phone":   "919758800885",
    "api_key": "Ys7qCVcJhKFA",
}

POLL_INTERVAL = 120  # seconds between checks (2 min = less likely to get blocked)

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
#  ROTATING USER AGENTS (looks more human)
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
#  FETCH POSTS
# ─────────────────────────────────────────────

def fetch_new_posts():
    global consecutive_403s

    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
    }

    url = f"https://www.reddit.com/r/{SUBREDDIT_NAME}/new/.rss?limit=25"

    try:
        response = requests.get(url, headers=headers, timeout=15)

        if response.status_code == 200:
            consecutive_403s = 0  # reset on success
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
                        created_utc = dt.timestamp()
                    except Exception:
                        pass
                posts.append({
                    "id": post_id,
                    "title": title,
                    "selftext": content,
                    "permalink": permalink,
                    "author": author,
                    "created_utc": created_utc,
                })
            return posts

        elif response.status_code == 403:
            consecutive_403s += 1
            wait = min(300, 60 * consecutive_403s)  # wait longer each time, max 5 min
            log.warning(f"403 blocked (#{consecutive_403s}). Waiting {wait}s before retry...")
            time.sleep(wait)
            return []

        elif response.status_code == 429:
            log.warning("Rate limited. Waiting 3 minutes...")
            time.sleep(180)
            return []

        else:
            log.warning(f"Reddit returned status {response.status_code}. Retrying next cycle.")
            return []

    except Exception as e:
        log.error(f"Fetch error: {e}. Retrying next cycle.")
        return []

# ─────────────────────────────────────────────
#  KEYWORD CHECKER
# ─────────────────────────────────────────────

def contains_keyword(post):
    combined = (post["title"] + " " + post["selftext"]).upper()
    for keyword in KEYWORDS:
        # Use word boundaries to match whole words only
        if re.search(r'\b' + re.escape(keyword.upper()) + r'\b', combined):
            return keyword
    return None


# ─────────────────────────────────────────────
#  WHATSAPP SENDER
# ─────────────────────────────────────────────

def send_whatsapp(message):
    try:
        url = (
            f"https://api.textmebot.com/send.php"
    f"?recipient={WHATSAPP_CONFIG['phone']}"
    f"&apikey={WHATSAPP_CONFIG['api_key']}"
    f"&text={quote(message)}"
        )
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            log.info("WhatsApp alert sent!")
        else:
            log.warning(f"WhatsApp API status: {response.status_code}")
    except Exception as e:
        log.error(f"WhatsApp send failed: {e}")

# ─────────────────────────────────────────────
#  MESSAGE BUILDER
# ─────────────────────────────────────────────

def build_message(post, matched_keyword):
    ts = datetime.utcfromtimestamp(post["created_utc"]).strftime("%d %b %Y, %H:%M UTC") if post["created_utc"] else "Unknown"
    return (
        f"Keyword Alert: {matched_keyword}\n"
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
    log.info(f"Monitoring r/{SUBREDDIT_NAME}")
    log.info(f"Keywords: {', '.join(KEYWORDS)}")
    log.info(f"Polling every {POLL_INTERVAL} seconds")

    seen_ids = set()
    first_run = True

    while True:
        try:
            posts = fetch_new_posts()

            for post in posts:
                post_id = post["id"]
                if post_id in seen_ids:
                    continue
                seen_ids.add(post_id)
                if first_run:
                    continue
                matched = contains_keyword(post)
                if matched:
                    log.info(f"Keyword '{matched}' found: {post['title'][:60]}")
                    message = build_message(post, matched)
                    send_whatsapp(message)
                    time.sleep(2)

            if first_run and posts:
                log.info(f"Indexed {len(seen_ids)} existing posts. Now watching for new ones...")
                first_run = False

            if len(seen_ids) > 5000:
                seen_ids = set(list(seen_ids)[-2000:])

            # Add small random jitter to polling (looks more human)
            jitter = random.randint(0, 30)
            time.sleep(POLL_INTERVAL + jitter)

        except Exception as e:
            log.error(f"Unexpected error: {e}. Continuing in 60s...")
            time.sleep(60)


if __name__ == "__main__":
    main()
