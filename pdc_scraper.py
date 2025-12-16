import requests
import feedparser
import json
import os
import urllib.parse
from datetime import datetime, timedelta

# --- CONFIGURATION: TARGETED KEYWORDS ---

# 1. The "Product" (What you sell) - Used to find parents searching for this.
SERVICE_KEYWORDS = [
    "Mindset Coach", "Emotional Intelligence", "Life Skills", 
    "Habit Building", "Discipline Coaching", "Mental Performance", 
    "Competitive Edge", "Resilience Training", "Athlete Mentorship"
]

# 2. The "Target" (Who has the money/need) - Used to find investment discussions.
HNW_KEYWORDS = [
    "High Net Worth", "Affluent", "Prep School", "Boarding School", 
    "Private School", "Sports Academy", "Tuition", "Financial Aid", 
    "Ivy League", "Showcase", "Recruiting Service", "Family Office"
]

# 3. Global Opportunities (Job/Contract Hunters)
OPPORTUNITY_KEYWORDS = [
    "Hiring", "Vacancy", "Job Opening", "Director of Athletics", 
    "Head of Player Development", "Basketball Coach", "Sports Director"
]

SLACK_WEBHOOK_URL = os.environ.get('SLACK_WEBHOOK_URL')
found_opps = []

# --- HELPER FUNCTIONS ---

def is_recent(published_str):
    """Checks if a date string is within the last 48 hours"""
    try:
        # Generic date parser - if it fails, we assume it's fresh enough to check
        dt = datetime.strptime(published_str, "%a, %d %b %Y %H:%M:%S %z")
        if datetime.now(dt.tzinfo) - dt > timedelta(hours=48):
            return False
    except:
        return True 
    return True

def get_global_academies():
    """
    Scours Google News for 'Hiring' signals at Prep Schools & Academies Globally.
    Targeting: USA, Europe, Asia (International Schools)
    """
    print("Checking Global Academies...")
    
    queries = [
        # 1. The "Prep School" Vacancy Search
        ('("Prep School" OR "Boarding School") ("hiring" OR "vacancy" OR "seeking") "basketball coach"', "🏫 Prep School Job"),
        
        # 2. The "International Academy" Search (Europe/Global)
        ('("Sports Academy" OR "International School") ("Director of Athletics" OR "Head Coach") vacancy', "🌍 Global Academy Job"),
        
        # 3. The "Player Development" Specific Search
        ('"Director of Player Development" ("hiring" OR "job") basketball', "🏀 Development Director Role")
    ]

    for q, label in queries:
        try:
            encoded = urllib.parse.quote(q)
            # using &gl=US for English results, but the query terms catch global entities
            rss_url = f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en"
            feed = feedparser.parse(rss_url)
            
            for entry in feed.entries[:3]: # Top 3 per category
                found_opps.append({
                    "source": "Global Academy Monitor",
                    "title": entry.title,
                    "url": entry.link,
                    "summary": label,
                    "type": "opportunity"
                })
        except Exception as e:
            print(f"Error Global Search '{q}': {e}")

def get_hnw_parent_needs():
    """
    Finds HNW Parents searching for YOUR specific keywords (Mindset, Discipline, EQ).
    Looks for pain points in forums (Reddit, College Confidential) via Google.
    """
    print("Checking HNW Parent Needs...")
    
    # We construct queries that combine a "Pain Point" with a "Service Solution"
    queries = [
        # 1. The "Soft Skills" Search (Discipline/Mindset)
        ('site:reddit.com OR site:talk.collegeconfidential.com ("son" OR "daughter") ("mindset" OR "discipline" OR "lazy" OR "motivation") basketball', "🧠 Mindset/Discipline Need"),
        
        # 2. The "Competitive Edge" Search
        ('site:reddit.com ("competitive edge" OR "mental toughness") athlete "help"', "🔥 Competitive Edge Lead"),
        
        # 3. The "Investment" Search (Is Prep School Worth it?)
        ('("is it worth it" OR "investment") ("prep school" OR "IMG Academy" OR "Montverde") basketball', "💰 HNW Investment Question")
    ]

    for q, label in queries:
        try:
            encoded = urllib.parse.quote(q)
            rss_url = f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en"
            feed = feedparser.parse(rss_url)
            
            for entry in feed.entries[:4]:
                found_opps.append({
                    "source": "Parent Radar",
                    "title": entry.title,
                    "url": entry.link,
                    "summary": label,
                    "type": "lead"
                })
        except Exception as e:
            print(f"Error Parent Search '{q}': {e}")

def get_wealth_partners():
    """
    Finds Family Offices/Wealth Managers talking about Athletes.
    These are your Referral Partners.
    """
    print("Checking Wealth Partners...")
    query = '(Wealth Management OR "Family Office") AND ("Student Athlete" OR "NIL" OR "Next Gen")', 
    
    try:
        encoded = urllib.parse.quote(query[0])
        rss_url = f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en"
        feed = feedparser.parse(rss_url)
        for entry in feed.entries[:3]:
            found_opps.append({
                "source": "Wealth Partner",
                "title": entry.title,
                "url": entry.link,
                "summary": "🤝 Potential Partner",
                "type": "partner"
            })
    except Exception as e:
        print(f"Error Wealth Partner: {e}")

def send_slack_alert():
    unique_opps = {opp['url']: opp for opp in found_opps}.values()
    count = len(unique_opps)
    print(f"Total Unique Opps: {count}")

    if count == 0:
        # Heartbeat so you know it ran
        payload = {"blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": "✅ *Global Monitor Ran:* No new high-quality matches found."}}]}
    else:
        blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": f"🌍 Global PDC Monitor: {count} Leads"}},
            {"type": "divider"}
        ]

        # Sort: Leads (Money) First, then Opportunities (Jobs), then Partners
        sorted_opps = sorted(unique_opps, key=lambda x: 0 if x['type'] == 'lead' else (1 if x['type'] == 'opportunity' else 2))

        for opp in list(sorted_opps)[:15]:
            emoji = "🧠" # Default (Mindset)
            if opp['type'] == "opportunity": emoji = "🏫" # Prep School/Job
            elif opp['type'] == "partner": emoji = "🤝" # Wealth Partner
            elif "Money" in opp['summary'] or "HNW" in opp['summary']: emoji = "💰"
            
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
    get_global_academies()    # Finds Jobs/Contracts globally
    get_hnw_parent_needs()    # Finds Parents needing Mindset/Discipline
    get_wealth_partners()     # Finds Referral Partners
    send_slack_alert()
