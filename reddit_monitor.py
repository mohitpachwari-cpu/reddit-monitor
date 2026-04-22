import requests
import time
import logging
import xml.etree.ElementTree as ET
from urllib.parse import quote
from datetime import datetime

# ─────────────────────────────────────────────
#  CONFIGURATION — Edit these before running
# ─────────────────────────────────────────────

SUBREDDIT_NAME = "IndiaDealsExchange"

KEYWORDS = [
    "BUY",
    # "SELL",
    # "DEAL",
    # "DISCOUNT",
]

WHATSAPP_CONFIG = {
    "phone":   "917017007171",       # Your number with country code, no +
    "api_key": "Ys7qCVcJhKFA",       # From TextMeBot/CallMeBot
}

POLL_INTERVAL = 60  # seconds between checks

# ─────────────────────────────────────────────
#  LOGGING SETUP
# ─────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────
#  HEADERS
# ─────────────────────────────────────────────

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

RSS_NS = "{http://www.w3.org/2005/Atom}"

# ─────────────────────────────────────────────
#  FETCH POSTS VIA RSS
# ─────────────────────────────────────────────

def fetch_new_posts():
    url = f"https://www.reddit.com/r/{SUBREDDIT_NAME}/new/.rss?limit=25"
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code == 200:
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
        elif response.status_code == 429:
            log.warning("Rate limited. Waiting 90 seconds...")
            time.sleep(90)
            return []
        else:
            log.warning(f"Reddit returned status {response.status_code}")
            return []
    except Exception as e:
        log.error(f"Failed to fetch posts: {e}")
        return []

# ─────────────────────────────────────────────
#  KEYWORD CHECKER
# ─────────────────────────────────────────────

def contains_keyword(post):
    combined = (post["title"] + " " + post["selftext"]).upper()
    for keyword in KEYWORDS:
        if keyword.upper() in combined:
            return keyword
    return None

# ─────────────────────────────────────────────
#  WHATSAPP SENDER
# ─────────────────────────────────────────────

def send_whatsapp(message):
    try:
        url = (
            "https://api.textmebot.com/send.php"
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

        if first_run:
            log.info(f"Indexed {len(seen_ids)} existing posts. Now watching for new ones...")
            first_run = False

        if len(seen_ids) > 5000:
            seen_ids = set(list(seen_ids)[-2000:])

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
