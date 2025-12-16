import requests
import feedparser
import json
import os
import urllib.parse
from datetime import datetime, timedelta
import time

# --- CONFIGURATION ---

# 1. Product Keywords (What you sell)
SERVICE_KEYWORDS = [
    "Mindset Coach", "Emotional Intelligence", "Life Skills", 
    "Habit Building", "Discipline Coaching", "Mental Performance", 
    "Competitive Edge", "Resilience Training", "Athlete Mentorship"
]

# 2. Target Keywords (Who has the money)
HNW_KEYWORDS = [
    "Prep School", "Boarding School", "Private School", "Tuition", 
    "Financial Aid", "Ivy League", "Showcase", "Recruiting Service", 
    "Family Office", "Wealth Management", "NIL", "High Net Worth"
]

# 3. Global Job/Contract Keywords
OPPORTUNITY_KEYWORDS = [
    "Hiring", "Vacancy", "Job Opening", "Director of Athletics", 
    "Head of Player Development", "Basketball Coach", "Sports Director",
    "Head of Performance", "Dean of Students"
]

SLACK_WEBHOOK_URL = os.environ.get('SLACK_WEBHOOK_URL')
found_opps = []

# --- HELPER FUNCTIONS ---

def is_within_30_days(published_entry):
    """
    Returns True if the post is less than 30 days old.
    Handles multiple date formats from different RSS feeds.
    """
    # 1. Try standard 'published_parsed' (struct_time)
    if hasattr(published_entry, 'published_parsed') and published_entry.published_parsed:
        pub_date = datetime.fromtimestamp(time.mktime(published_entry.published_parsed))
        return datetime.now() - pub_date < timedelta(days=30)
    
    # 2. Try 'updated_parsed'
    if hasattr(published_entry, 'updated_parsed') and published_entry.updated_parsed:
        pub_date = datetime.fromtimestamp(time.mktime(published_entry.updated_parsed))
        return datetime.now() - pub_date < timedelta(days=30)
        
    # 3. If no date is found, we assume it's fresh (better to see it than miss it)
    return True

def get_google_smart_search():
    """
    Uses Google News RSS with the 'when:14d' operator to enforce freshness.
    """
    print("Checking Google Smart Search (Last 14 Days)...")
    
    queries = [
        # A. Global Academy Jobs (The "Big Money" Contracts)
        # Query: Jobs at Prep Schools or International Academies
        ('("Prep School" OR "Boarding School" OR "International School") ("hiring" OR "vacancy") basketball when:14d', "🏫 Academy Job"),
        
        # B. HNW Parent Pain Points (The "Client" Leads)
        # Query: Parents discussing tuition, mindset, or problems on forums
        ('site:reddit.com OR site:collegeconfidential.com ("son" OR "daughter") ("mindset" OR "discipline" OR "tuition" OR "prep school") basketball when:14d', "🧠 Parent/Client Lead"),
        
        # C. Wealth Management Partners (The "Referral" Network)
        # Query: Financial Advisors writing about Athletes/NIL
        ('(Wealth Management OR "Family Office") ("Student Athlete" OR "NIL") when:14d', "🤝 Wealth Partner"),
        
        # D. New Source: Youth/AAU Forums (The "Politics" Leads)
        ('("AAU" OR "Travel Basketball") ("politics" OR "toxic" OR "advice") parent when:14d', "🏀 AAU/Travel Parent")
    ]

    for q, label in queries:
        try:
            encoded = urllib.parse.quote(q)
            # &gl=US ensures English results, but broadly searches global sources
            rss_url = f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en"
            feed = feedparser.parse(rss_url)
            
            for entry in feed.entries[:5]: # Top 5 per category
                if is_within_30_days(entry):
                    found_opps.append({
                        "source": "Google Monitor",
                        "title": entry.title,
                        "url": entry.link,
                        "summary": label,
                        "type": "opportunity" if "Job" in label else ("lead" if "Parent" in label else "partner")
                    })
        except Exception as e:
            print(f"Error Google Search '{q}': {e}")

def get_college_confidential_prep():
    """
    Directly checks College Confidential 'Prep School Admissions' Forum.
    This is where parents discuss $60k+ tuition schools.
    """
    print("Checking College Confidential (Prep School)...")
    try:
        # Specific RSS for the Prep School Admissions board
        feed = feedparser.parse("https://talk.collegeconfidential.com/c/prep-school-admissions/750.rss")
        
        for entry in feed.entries[:10]:
            if is_within_30_days(entry):
                found_opps.append({
                    "source": "College Confidential",
                    "title": entry.title,
                    "url": entry.link,
                    "summary": "💰 Prep School Discussion",
                    "type": "lead"
                })
    except Exception as e:
        print(f"Error CC Prep: {e}")

def get_ncaa_market():
    """Fetches NCAA Jobs (Filtering out Fundraising)"""
    print("Checking NCAA Market...")
    IGNORE = ["fundraising", "donor", "gift", "advancement", "annual fund"]
    try:
        feed = feedparser.parse("https://ncaamarket.ncaa.org/jobs/?display=rss")
        for entry in feed.entries:
            if is_within_30_days(entry):
                title = entry.title.lower()
                if "basketball" in title or "player development" in title:
                    if not any(x in title for x in IGNORE):
                        found_opps.append({
                            "source": "NCAA Market",
                            "title": entry.title,
                            "url": entry.link,
                            "summary": "🎓 Collegiate Role",
                            "type": "opportunity"
                        })
    except Exception as e:
        print(f"Error NCAA: {e}")

def send_slack_alert():
    # Deduplicate results by URL
    unique_opps = {opp['url']: opp for opp in found_opps}.values()
    count = len(unique_opps)
    print(f"Total Unique Opps (Last 30 Days): {count}")

    if count == 0:
        # Heartbeat message
        payload = {"blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": "✅ *PDC Global Monitor Ran:* No new matches found (Last 30 Days)."}}]}
    else:
        blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": f"🌍 Global PDC Monitor: {count} Fresh Leads"}},
            {"type": "divider"}
        ]

        # Sort: Leads (Money) -> Partners -> Jobs
        sorted_opps = sorted(unique_opps, key=lambda x: 0 if x['type'] == 'lead' else (1 if x['type'] == 'partner' else 2))

        for opp in list(sorted_opps)[:15]: # Max 15 for Slack
            emoji = "🧠"
            if opp['type'] == "opportunity": emoji = "🏫" 
            elif opp['type'] == "partner": emoji = "🤝"
            elif "Prep School" in opp['summary']: emoji = "💰"
            
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{emoji} *{opp['summary']}*: <{opp['url']}|{opp['title']}>\n_{opp['source']}_"
                }
            })
            
        payload = {"blocks": blocks}

    if SLACK_WEBHOOK_URL:
        requests.post(SLACK_WEBHOOK_URL, json=payload)
    else:
        print(json.dumps(payload, indent=2))

if __name__ == "__main__":
    get_google_smart_search()       # Freshness enforced via 'when:14d'
    get_college_confidential_prep() # New High-Net-Worth source
    get_ncaa_market()               # Standard Job source
    send_slack_alert()
