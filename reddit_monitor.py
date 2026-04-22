import requests
import time
import logging
from urllib.parse import quote
from datetime import datetime

# ─────────────────────────────────────────────
#  CONFIGURATION — Edit these before running
# ─────────────────────────────────────────────

SUBREDDIT_NAME = "IndiaDealsExchange"

# Keywords to monitor (case-insensitive, add more anytime)
KEYWORDS = [
    "trades",
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
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

def fetch_new_posts(limit=25):
    url = f"https://www.reddit.com/r/{SUBREDDIT_NAME}/new.json?limit={limit}"
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code == 200:
            data = response.json()
            return data["data"]["children"]
        elif response.status_code == 429:
            log.warning("⚠️ Rate limited by Reddit. Waiting 90 seconds...")
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
    try:
        url = (
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
    link    = "https://reddit.com" + post_data.get("permalink", "")
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
