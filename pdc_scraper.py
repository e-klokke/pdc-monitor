import requests
import feedparser
import json
import os
import urllib.parse
from datetime import datetime, timedelta

# --- CONFIGURATION ---

# 1. Industry/Coaching (Jobs)
COACHING_KEYWORDS = [
    "Player Development", "Mental Performance", "Life Skills", 
    "Head Coach", "Assistant Coach", "Director of Operations", 
    "Basketball", "Athlete Development"
]

# 2. Parent/Advisory (Clients)
# We look for these words in the Google/Reddit results
CLIENT_KEYWORDS = [
    "son", "daughter", "kid", "child", "quit", "confidence", "anxiety", 
    "toxic coach", "politics", "playing time", "recruiting", "prep school", 
    "tuition", "financial aid", "boarding school", "is it worth it"
]

SLACK_WEBHOOK_URL = os.environ.get('SLACK_WEBHOOK_URL')

found_opps = []

# --- HELPER FUNCTIONS ---

def is_recent(published_str):
    """Checks if a date string is within the last 48 hours"""
    try:
        # Handling multiple date formats is tricky, so we do a "generous" check
        # If parsing fails, we assume it's recent enough to show.
        dt = datetime.strptime(published_str, "%a, %d %b %Y %H:%M:%S %z")
        if datetime.now(dt.tzinfo) - dt > timedelta(hours=48):
            return False
    except:
        return True # Default to showing it if we can't parse date
    return True

def get_hoopdirt():
    """Fetches Coaching News"""
    print("Checking HoopDirt...")
    try:
        feed = feedparser.parse("https://hoopdirt.com/feed/")
        for entry in feed.entries[:10]:
            if is_recent(entry.published):
                found_opps.append({
                    "source": "HoopDirt",
                    "title": entry.title,
                    "url": entry.link,
                    "summary": "🏀 Industry News",
                    "type": "industry"
                })
    except Exception as e:
        print(f"Error HoopDirt: {e}")

def get_google_smart_search():
    """
    The Master Search: Queries Google News for both Jobs AND Parent Discussions.
    This bypasses Reddit's anti-bot blocking by letting Google do the work.
    """
    print("Checking Google Smart Search...")
    
    searches = [
        # 1. Finding Jobs
        ("Basketball Coach (Hiring OR Vacancy OR 'Player Development')", "📰 Job Vacancy", "industry"),
        
        # 2. Finding Wealth Partners (Financial Advisors)
        ("(Wealth Management OR Financial Advisor) AND (NIL OR Student Athletes)", "🤝 Potential Partner", "partner"),
        
        # 3. Finding Parents (The "Backdoor" Reddit Search)
        # This asks Google to find Reddit threads about basketball parents
        ("site:reddit.com (basketball OR youth sports) AND (son OR daughter) AND (quit OR confidence OR coach)", "❤️ Parent Discussion", "pain"),
        
        # 4. Finding High-Net-Worth Parents (Prep Schools)
        ("site:collegeconfidential.com OR site:reddit.com (prep school OR tuition OR boarding school) basketball", "💰 HNW Lead", "wealth")
    ]

    for query, label, type_ in searches:
        try:
            encoded = urllib.parse.quote(query)
            rss_url = f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en"
            feed = feedparser.parse(rss_url)
            
            for entry in feed.entries[:4]: # Top 4 per category to avoid spam
                found_opps.append({
                    "source": "Google Alert",
                    "title": entry.title,
                    "url": entry.link,
                    "summary": label,
                    "type": type_
                })
        except Exception as e:
            print(f"Error Google Search '{query}': {e}")

def get_ncaa_market():
    """Fetches NCAA Jobs (Filtering out Fundraising)"""
    print("Checking NCAA Market...")
    IGNORE = ["fundraising", "donor", "gift", "advancement", "annual fund"]
    try:
        feed = feedparser.parse("https://ncaamarket.ncaa.org/jobs/?display=rss")
        for entry in feed.entries:
            title = entry.title.lower()
            if "basketball" in title or "player development" in title:
                if not any(x in title for x in IGNORE):
                    found_opps.append({
                        "source": "NCAA Market",
                        "title": entry.title,
                        "url": entry.link,
                        "summary": "🎓 Collegiate Role",
                        "type": "industry"
                    })
    except Exception as e:
        print(f"Error NCAA: {e}")

def send_slack_alert():
    # DEDUPLICATE: Remove results with the same URL
    unique_opps = {opp['url']: opp for opp in found_opps}.values()
    count = len(unique_opps)
    
    print(f"Total Unique Opps Found: {count}")

    if count == 0:
        # DEBUG MESSAGE: If nothing found, send a "Heartbeat" so we know it ran.
        payload = {
            "blocks": [{
                "type": "section",
                "text": {"type": "mrkdwn", "text": "✅ *PDC Monitor Ran:* No new matches found this cycle."}
            }]
        }
    else:
        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"🚀 PDC Monitor: {count} Leads"}
            },
            {"type": "divider"}
        ]

        # Sort: Wealth/Pain first, then Jobs
        sorted_opps = sorted(unique_opps, key=lambda x: 0 if x['type'] in ['wealth', 'pain'] else 1)

        for opp in list(sorted_opps)[:15]: # Max 15 to fit in Slack
            emoji = "🏀"
            if opp['type'] == "wealth": emoji = "💰"
            elif opp['type'] == "pain": emoji = "❤️"
            elif opp['type'] == "partner": emoji = "🤝"
            
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{emoji} *{opp['summary']}*: <{opp['url']}|{opp['title']}>"
                }
            })
            
        payload = {"blocks": blocks}

    if SLACK_WEBHOOK_URL:
        requests.post(SLACK_WEBHOOK_URL, json=payload)
    else:
        print("No Webhook set. Outputting JSON locally.")
        print(json.dumps(payload, indent=2))

if __name__ == "__main__":
    get_hoopdirt()
    get_google_smart_search()
    get_ncaa_market()
    send_slack_alert()
