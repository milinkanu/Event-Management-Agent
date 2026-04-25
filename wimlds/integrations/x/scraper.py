"""X scraping and lightweight audience analytics."""
from __future__ import annotations

import re
import time
import urllib.parse
from collections import Counter

from wimlds.config.settings import settings
from wimlds.integrations.x.ai_rewriter import generate_qa_insights


def _create_driver(headless: bool = False):
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager

    chrome_options = Options()
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument(f"user-data-dir={settings.x_selenium_profile_dir}")
    if headless:
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--no-sandbox")
    else:
        chrome_options.add_argument("--start-maximized")
    return webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=chrome_options,
    )


def _login_check(driver, headless: bool = False):
    driver.get("https://x.com/home")
    time.sleep(5)
    if "login" in driver.current_url:
        if headless:
            raise RuntimeError("Not logged in. Run the scraper once in non-headless mode to authenticate first.")
        input("Log into X in the opened browser, then press ENTER here...")


def _extract_posts(driver, max_posts: int = 20):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    try:
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, "article")))
    except Exception:
        return []

    posts = []
    elements = driver.find_elements(By.CSS_SELECTOR, "article")
    for el in elements:
        text = el.text
        if not text or len(text) <= 20:
            continue
        url = "Unknown"
        try:
            time_el = el.find_element(By.XPATH, ".//time/..")
            href = time_el.get_attribute("href")
            if href:
                url = href
        except Exception:
            pass
        analytics = {"replies": 0, "reposts": 0, "likes": 0, "views": 0}
        try:
            group_el = el.find_element(By.CSS_SELECTOR, "div[role='group']")
            aria_label = group_el.get_attribute("aria-label")
            if aria_label:
                patterns = [
                    ("replies", r"([\d,]+)\s+repl"),
                    ("reposts", r"([\d,]+)\s+repost"),
                    ("likes", r"([\d,]+)\s+like"),
                    ("views", r"([\d,]+)\s+view"),
                ]
                for key, pattern in patterns:
                    match = re.search(pattern, aria_label)
                    if match:
                        analytics[key] = int(match.group(1).replace(",", ""))
        except Exception:
            pass
        posts.append({"text": text, "url": url, "analytics": analytics})
        if len(posts) >= max_posts:
            break
    return posts


def scrape_hashtag_posts(hashtag: str, max_posts: int = 20, headless: bool = False):
    driver = _create_driver(headless)
    try:
        _login_check(driver, headless)
        clean = hashtag.strip().lstrip("#")
        encoded = urllib.parse.quote(clean)
        driver.get(f"https://x.com/search?q=%23{encoded}&src=typed_query&f=live")
        return _extract_posts(driver, max_posts)
    finally:
        driver.quit()


def scrape_account_mentions(username: str, max_posts: int = 20, headless: bool = False):
    driver = _create_driver(headless)
    try:
        _login_check(driver, headless)
        clean = username.strip().lstrip("@")
        encoded = urllib.parse.quote(clean)
        driver.get(f"https://x.com/search?q=%40{encoded}&src=typed_query&f=live")
        return _extract_posts(driver, max_posts)
    finally:
        driver.quit()


def event_buzz_tracker(posts, query):
    unique_users = {p["text"].split("\n")[0] for p in posts if p["text"].split("\n")}
    return {"title": "Event Buzz Summary", "total_posts": len(posts), "unique_contributors": len(unique_users)}


def identify_potential_attendees(posts):
    keywords = ["attending", "looking forward", "excited for", "anyone attending", "joining"]
    attendees = []
    for p in posts:
        lower = p["text"].lower()
        if any(k in lower for k in keywords):
            attendees.append({"text": p["text"][:150].replace("\n", " "), "url": p["url"]})
    return {"title": "Potential Attendees", "count": len(attendees), "items": attendees}


def topic_trend_analysis(posts):
    words = []
    for p in posts:
        words.extend(re.findall(r"\b[A-Za-z]{4,}\b", p["text"].lower()))
    counter = Counter(words)
    return {"title": "Trending Topics", "items": [{"word": w, "count": c} for w, c in counter.most_common(10)]}


def best_tweets(posts):
    ranked = sorted(posts, key=lambda x: len(x["text"]), reverse=True)[:5]
    return {"title": "Longest Event Tweets", "items": [{"text": t["text"][:150].replace("\n", " "), "url": t["url"]} for t in ranked]}


def top_engaged_tweets(posts):
    ranked = sorted(posts, key=lambda x: x["analytics"]["likes"] + x["analytics"]["reposts"] + x["analytics"]["replies"], reverse=True)[:5]
    items = []
    for t in ranked:
        a = t["analytics"]
        items.append({"text": t["text"][:100].replace("\n", " "), "url": t["url"], "likes": a["likes"], "reposts": a["reposts"], "replies": a["replies"]})
    return {"title": "Top Engaged Tweets", "items": items}


def question_mining(posts):
    questions = [{"text": p["text"][:150].replace("\n", " "), "url": p["url"]} for p in posts if "?" in p["text"]]
    return {"title": "Questions From Audience", "count": len(questions), "items": questions}


def sentiment_analysis(posts):
    positive_words = ["great", "amazing", "love", "awesome", "excited", "stellar", "fantastic", "good", "impressed", "wow", "helpful", "learning", "innovation", "future", "cool", "fire", "recommend", "thanks", "thank", "best", "perfect", "win", "success"]
    negative_words = ["bad", "boring", "crowded", "disappointing", "awful", "terrible", "slow", "fail", "worst", "hate", "unhappy", "broke", "broken", "issue", "bug", "scam", "trash"]
    pos = neg = 0
    for p in posts:
        lower = p["text"].lower()
        if any(w in lower for w in positive_words):
            pos += 1
        elif any(w in lower for w in negative_words):
            neg += 1
    total = len(posts) or 1
    return {"title": "Sentiment Summary", "positive": round(pos / total * 100, 2), "negative": round(neg / total * 100, 2), "neutral": round((total - pos - neg) / total * 100, 2)}


def photo_detector(posts):
    photos = [{"text": p["text"][:150].replace("\n", " "), "url": p["url"]} for p in posts if "pic.twitter.com" in p["text"]]
    return {"title": "Posts With Photos", "count": len(photos), "items": photos}


def event_feedback(posts):
    categories = {"content": ["great session", "amazing talk"], "venue": ["crowded", "venue", "hall"], "speaker": ["speaker", "talk"], "networking": ["meet", "network"]}
    result = {}
    for cat, words in categories.items():
        result[cat] = sum(1 for p in posts if any(w in p["text"].lower() for w in words))
    return {"title": "Event Feedback Summary", "categories": result}


def event_advocates(posts):
    user_counts = Counter()
    for p in posts:
        lines = p["text"].split("\n")
        if lines:
            user_counts[lines[0]] += 1
    return {"title": "Event Advocates", "items": [{"user": u, "count": c} for u, c in user_counts.most_common(5)]}


def event_impact_report(posts):
    users = {p["text"].split("\n")[0] for p in posts if p["text"].split("\n")}
    return {"title": "Event Impact Report", "total_tweets": len(posts), "unique_contributors": len(users)}


def run_scraper_api(query: str, headless: bool = True):
    query = query.strip()
    max_posts = settings.x_scrape_max_posts
    posts = scrape_account_mentions(query, max_posts, headless=headless) if query.startswith("@") else scrape_hashtag_posts(query, max_posts, headless=headless)
    analytics = {
        "buzz": {"title": "Event Buzz Summary", "total_posts": 0, "unique_contributors": 0},
        "attendees": {"title": "Potential Attendees", "count": 0, "items": []},
        "trending": {"title": "Trending Topics", "items": []},
        "best_tweets": {"title": "Longest Event Tweets", "items": []},
        "top_engaged": {"title": "Top Engaged Tweets", "items": []},
        "questions": {"title": "Questions From Audience", "count": 0, "items": []},
        "sentiment": {"title": "Sentiment Summary", "positive": 0, "negative": 0, "neutral": 100},
        "photos": {"title": "Posts With Photos", "count": 0, "items": []},
        "feedback": {"title": "Event Feedback Summary", "categories": {}},
        "advocates": {"title": "Event Advocates", "items": []},
        "impact": {"title": "Event Impact Report", "total_tweets": 0, "unique_contributors": 0},
    }
    if not posts:
        return {"posts": [], "analytics": analytics, "ai_insights": "No posts found to analyze."}
    analytics = {
        "buzz": event_buzz_tracker(posts, query),
        "attendees": identify_potential_attendees(posts),
        "trending": topic_trend_analysis(posts),
        "best_tweets": best_tweets(posts),
        "top_engaged": top_engaged_tweets(posts),
        "questions": question_mining(posts),
        "sentiment": sentiment_analysis(posts),
        "photos": photo_detector(posts),
        "feedback": event_feedback(posts),
        "advocates": event_advocates(posts),
        "impact": event_impact_report(posts),
    }
    return {"posts": posts, "analytics": analytics, "ai_insights": generate_qa_insights(posts)}
