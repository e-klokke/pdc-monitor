import requests
import feedparser
import json
import os
import urllib.parse
from datetime import datetime, timedelta

# --- CONFIGURATION: KEYWORD LISTS ---

# 1. Industry/Coaching Keywords (Finding Jobs & Openings)
COACHING_KEYWORDS = [
    "Player Development", "Mental Performance", "Life Skills", 
    "Head Coach", "Assistant Coach", "Director of Operations", 
    "Basketball", "Athlete Development"
]

# 2. Parent Pain Points (Finding "Emotional" Clients)
PAIN_KEYWORDS = [
    "quit", "confidence", "anxiety", "scared", "nervous", "toxic coach",
    "unfair", "politics", "bench", "playing time", "struggling", "lost passion"
]

# 3. High-Net-Worth/Advisory (Finding "Investment" Clients)
WEALTH_KEYWORDS = [
    "prep school", "tuition", "private school", "boarding school",
    "consultant", "recruiting service", "showcase", "ivy league",
    "financial aid", "investment", "is it worth it", "advisor"
]

# Get Webhook from Environment Variable
SLACK_WEBHOOK_URL = os.environ.get('SLACK_WEBHOOK_URL')

# Master list to store all findings
found_opps = []

# --- HELPER FUNCTIONS ---

def is_relevant(text, keyword_list):
    """Returns True if any keyword from the list is in the text."""
    if not text:
        return False
    text = text.lower()
    return any(keyword.lower() in text for keyword in keyword_list)

def get_hoopdirt_news():
    """Fetches coaching news from HoopDirt (Industry Standard)"""
    print("Checking HoopDirt...")
    try:
        feed = feedparser.parse("https://hoopdirt.com/feed/")
        for entry in feed.entries:
            published = datetime.strptime(entry.published, "%a, %d %b %Y %H:%M:%S %z")
            if datetime.now(published.tzinfo) - published > timedelta(hours=24):
                continue
            
            found_opps.append({
                "source": "HoopDirt",
                "title": entry.title,
                "url": entry.link,
                "summary": "🏀 Coaching Move / Industry Rumor",
                "type": "industry"
            })
    except Exception as e:
        print(f"Error fetching HoopDirt: {e}")

def get_google_alerts():
    """Fetches Google News for Vacancies and Wealth Partners"""
    print("Checking Google News...")
    
    # 1. Vacancy Search
    job_query = "Basketball Coach (Hiring OR Wanted OR Vacancy OR 'Player Development')"
    
    # 2. Wealth Partner Search (Financial Advisors talking about athletes)
    partner_query = "(Wealth Management OR Financial Advisor) AND (NIL OR Student Athletes)"
    
    queries = [
        (job_query, "📰 Job Vacancy", "industry"),
        (partner_query, "🤝 Potential Wealth Partner", "partner")
    ]

    for q, summary, type_ in queries:
        encoded = urllib.parse.quote(q)
        rss_url = f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en"
        try:
            feed = feedparser.parse(rss_url)
            for entry in feed.entries[:5]: # Top 5 only
                found_opps.append({
                    "source": "Google News",
                    "title": entry.title,
                    "url": entry.link,
                    "summary": summary,
                    "type": type_
                })
        except Exception as e:
            print(f"Error google search '{q}': {e}")

def get_ncaa_market():
    """Fetches official NCAA job postings"""
    print("Checking NCAA Market...")
    try:
        feed = feedparser.parse("https://ncaamarket.ncaa.org/jobs/?display=rss")
        for entry in feed.entries:
            if "basketball" in entry.title.lower() or "development" in entry.title.lower():
                 found_opps.append({
                    "source": "NCAA Market",
                    "title": entry.title,
                    "url": entry.link,
                    "summary": "🎓 Collegiate Role",
                    "type": "industry"
                })
    except Exception as e:
        print(f"Error fetching NCAA: {e}")

def get_college_confidential():
    """Fetches High-Net-Worth parent discussions"""
    print("Checking College Confidential...")
    try:
        rss_url = "https://talk.collegeconfidential.com/c/athletic-recruits.rss"
        feed = feedparser.parse(rss_url)
        for entry in feed.entries[:10]:
            category = "💰 High-Net-Worth Discussion"
            # Simple logic: If it's in this forum, it's likely a wealthy parent
            found_opps.append({
                "source": "College Confidential",
                "title": entry.title,
                "url": entry.link,
                "summary": category,
                "type": "wealth"
            })
    except Exception as e:
        print(f"Error fetching College Confidential: {e}")

def get_reddit_monitor():
    """Scans Reddit for Parents (Pain Points & Advisory Needs)"""
    print("Checking Reddit...")
    subreddits = ["BasketballTips", "YouthSports", "Parenting", "basketballcoach"]
    headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}
    
    for sub in subreddits:
        try:
            url = f"https://www.reddit.com/r/{sub}/new.json?limit=25"
            r = requests.get(url, headers=headers)
            data = r.json()
            
            for post in data['data']['children']:
                p = post['data']
                full_text = f"{p['title']} {p.get('selftext', '')}".lower()
                
                # Context: Is this a parent talking about a child?
                is_parent = any(k in full_text for k in ["son", "daughter", "kid", "child", "12yo", "13yo", "14yo", "hs", "my boy"])
                
                if is_parent:
                    if is_relevant(full_text, WEALTH_KEYWORDS):
                        found_opps.append({
                            "source": f"Reddit (r/{sub})",
                            "title": p['title'],
                            "url": f"https://www.reddit.com{p['permalink']}",
                            "summary": "💰 Investment/Advisory Question",
                            "type": "wealth"
                        })
                    elif is_relevant(full_text, PAIN_KEYWORDS):
                        found_opps.append({
                            "source": f"Reddit (r/{sub})",
                            "title": p['title'],
                            "url": f"https://www.reddit.com{p['permalink']}",
                            "summary": "❤️ Parent Pain Point (Confidence/Politics)",
                            "type": "pain"
                        })
        except Exception as e:
            print(f"Error fetching r/{sub}: {e}")

def send_slack_alert():
    if not found_opps:
        print("No opportunities found today.")
        return

    # Deduplicate by URL
    unique_opps = {opp['url']: opp for opp in found_opps}.values()
    print(f"Found {len(unique_opps)} opportunities.")
    
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"🚀 PDC Daily Monitor: {len(unique_opps)} Leads"}
        },
        {"type": "divider"}
    ]

    # Limit to top 15 to prevent Slack errors
    for opp in list(unique_opps)[:15]:
        # Dynamic Emoji based on type
        emoji = "🏀" # default
        if opp['type'] == "wealth": emoji = "💰"
        elif opp['type'] == "pain": emoji = "❤️"
        elif opp['type'] == "partner": emoji = "🤝"
        elif opp['type'] == "industry": emoji = "📰"

        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"{emoji} *{opp['source']}*: <{opp['url']}|{opp['title']}>\n_{opp['summary']}_"
            }
        })

    payload = {"blocks": blocks}
    
    if SLACK_WEBHOOK_URL:
        requests.post(SLACK_WEBHOOK_URL, json=payload)
    else:
        print("No Webhook set. JSON Output:")
        print(json.dumps(payload, indent=2))

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    get_hoopdirt_news()
    get_google_alerts()
    get_ncaa_market()
    get_college_confidential()
    get_reddit_monitor()
    send_slack_alert()
