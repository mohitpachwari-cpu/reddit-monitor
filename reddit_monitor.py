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

# Keywords to monitor (case-insensitive, add more anytime)
KEYWORDS = [
    "BUY",
    # "SELL",
    # "DEAL",
    # "DISCOUNT",
]

WHATSAPP_CONFIG = {
    "phone":   "919758800885",       # Your number with country code, no +
    "api_key": "Ys7qCVcJhKFA", # From CallMeBot WhatsApp setup
}

POLL_INTERVAL = 60  # seconds between checks

# ─────────────────────────────────────────────
#  LOGGING SETUP
# ─────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("monitor.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────
#  REDDIT FETCHER (no API key needed)
# ─────────────────────────────────────────────

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
}

RSS_NS = "{http://www.w3.org/2005/Atom}"

def fetch_new_posts(limit=25):
    """Fetch posts via RSS feed — more reliable from cloud servers than JSON API."""
    url = f"https://www.reddit.com/r/{SUBREDDIT_NAME}/new/.rss?limit={limit}"
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code == 200:
            root = ET.fromstring(response.content)
            posts = []
            for entry in root.findall(f"{RSS_NS}entry"):
                post = {
                    "id":               (entry.findtext(f"{RSS_NS}id") or "").split("_")[-1],
                    "title":            entry.findtext(f"{RSS_NS}title") or "",
                    "selftext":         entry.findtext(f"{RSS_NS}content") or "",
                    "permalink":        "",
                    "author":           "",
                    "link_flair_text":  "",
                    "author_flair_text":"",
                    "created_utc":      0,
                }
                # Extract link
                link = entry.find(f"{RSS_NS}link")
                if link is not None:
                    post["permalink"] = link.get("href", "")

                # Extract author
                author = entry.find(f"{RSS_NS}author")
                if author is not None:
                    post["author"] = (author.findtext(f"{RSS_NS}name") or "").replace("/u/", "")

                # Extract timestamp
                updated = entry.findtext(f"{RSS_NS}updated") or ""
                if updated:
                    try:
                        dt = datetime.strptime(updated, "%Y-%m-%dT%H:%M:%S+00:00")
                        post["created_utc"] = dt.timestamp()
                    except:
                        pass

                posts.append({"data": post})
            return posts

        elif response.status_code == 429:
            log.warning("⚠️ Rate limited. Waiting 90 seconds...")
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

def contains_keyword(post_data):
    """Check title, body, flair for any keyword. Returns matched keyword or None."""
    fields = [
        post_data.get("title", ""),
        post_data.get("selftext", ""),
        post_data.get("link_flair_text", "") or "",
        post_data.get("author_flair_text", "") or "",
    ]
    combined = " ".join(fields).upper()

    for keyword in KEYWORDS:
        if keyword.upper() in combined:
            return keyword
    return None

# ─────────────────────────────────────────────
#  WHATSAPP SENDER
# ─────────────────────────────────────────────

def send_whatsapp(message: str):
    tryurl = (
    f"https://api.textmebot.com/send.php"
    f"?recipient={WHATSAPP_CONFIG['phone']}"
    f"&apikey={WHATSAPP_CONFIG['api_key']}"
    f"&text={quote(message)}"
)
    response = requests.get(url, timeout=10)
        if response.status_code == 200:
            log.info("✅ WhatsApp alert sent!")
        else:
            log.warning(f"WhatsApp API status: {response.status_code}")
    except Exception as e:
        log.error(f"WhatsApp send failed: {e}")

# ─────────────────────────────────────────────
#  MESSAGE BUILDER
# ─────────────────────────────────────────────

def build_message(post_data, matched_keyword):
    flair   = post_data.get("link_flair_text") or "None"
    author  = post_data.get("author", "[deleted]")
    title   = post_data.get("title", "No title")
    permalink = post_data.get("permalink", "")
    link    = permalink if permalink.startswith("http") else "https://reddit.com" + permalink
    ts      = datetime.utcfromtimestamp(post_data.get("created_utc", 0)).strftime("%d %b %Y, %H:%M UTC")

    return (
        f"🚨 Keyword Alert: *{matched_keyword}*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📌 {title}\n"
        f"👤 u/{author}\n"
        f"🏷️ Flair: {flair}\n"
        f"🕒 {ts}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🔗 {link}"
    )

# ─────────────────────────────────────────────
#  MAIN LOOP
# ─────────────────────────────────────────────

def main():
    log.info(f"🚀 Monitoring r/{SUBREDDIT_NAME}")
    log.info(f"👁️  Keywords: {', '.join(KEYWORDS)}")
    log.info(f"⏱️  Polling every {POLL_INTERVAL} seconds\n")

    seen_ids = set()
    first_run = True

    while True:
        posts = fetch_new_posts(limit=25)

        for post in posts:
            post_data = post["data"]
            post_id   = post_data["id"]

            if post_id in seen_ids:
                continue

            seen_ids.add(post_id)

            # On first run, just index existing posts — don't alert
            if first_run:
                continue

            matched = contains_keyword(post_data)
            if matched:
                log.info(f"🎯 '{matched}' found: {post_data['title'][:60]}...")
                message = build_message(post_data, matched)
                send_whatsapp(message)
                time.sleep(2)

        if first_run:
            log.info(f"✅ Indexed {len(seen_ids)} existing posts. Now watching for new ones...")
            first_run = False

        # Keep memory lean
        if len(seen_ids) > 5000:
            seen_ids = set(list(seen_ids)[-2000:])

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
