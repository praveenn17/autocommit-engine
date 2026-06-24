#!/usr/bin/env python3
"""
AutoCommit Generator — Hybrid Mood Engine
======================================================
Determines today's "mood" based on 3 sources:
  1. Festivals (Calendarific API + Cache)
  2. Exam Dates (User-controlled via Telegram prompt & monthly config)
  3. Commit Intensity (One-time setup: HIGH/MEDIUM/LOW)

Entry point: get_today_mood() → dict

Tech: Python 3.12 · requests · stdlib only
"""

import json
import os
import sys
import datetime
import random
import base64
from pathlib import Path

try:
    import requests
    _REQUESTS_OK = True
except ImportError:
    _REQUESTS_OK = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

CALENDARIFIC_API = "https://calendarific.com/api/v2/holidays"
GITHUB_API = "https://api.github.com"
HOLIDAYS_CACHE_FILE = "holidays_cache.json"
MONTHLY_CONFIG_FILE = "monthly_config.json"
USER_PREFS_FILE = "user_preferences.json"
CACHE_TTL_DAYS = 7

# Major festivals (always 0 commits)
MAJOR_FESTIVAL_KEYWORDS = [
    "diwali", "deepawali", "holi", "eid ul-fitr", "eid-ul-fitr", "eid al-fitr",
    "eid ul-adha", "eid-ul-adha", "eid al-adha"
]

HARDCODED_HOLIDAYS = [
    {"name": "Republic Day",        "date": "01-26", "major": False},
    {"name": "Independence Day",    "date": "08-15", "major": False},
    {"name": "Gandhi Jayanti",      "date": "10-02", "major": False},
    {"name": "Christmas",           "date": "12-25", "major": False},
    {"name": "New Year",            "date": "01-01", "major": False},
    # Approximate floating holidays
    {"name": "Holi",                "date": "2025-03-14", "major": True},
    {"name": "Diwali",              "date": "2025-10-20", "major": True},
    {"name": "Eid ul-Fitr",         "date": "2025-03-31", "major": True},
    {"name": "Eid ul-Adha",         "date": "2025-06-07", "major": True},
    {"name": "Holi",                "date": "2026-03-04", "major": True},
    {"name": "Diwali",              "date": "2026-11-08", "major": True},
]



# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def today_ist() -> datetime.date:
    return datetime.datetime.now(IST).date()


def load_json_safe(path: str) -> dict:
    try:
        p = Path(path)
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def save_json_safe(path: str, data: dict) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[IndianCalendar] ⚠️  Could not save {path}: {e}", file=sys.stderr)


def fetch_from_github(filename: str) -> dict:
    """Fetch a JSON file from the commit-archive repo via GitHub Contents API."""
    try:
        username = os.environ.get("GH_USERNAME", "").strip()
        pat = os.environ.get("ARCHIVE_REPO_PAT", "").strip() or os.environ.get("GH_PAT", "").strip()
        repo = os.environ.get("ARCHIVE_REPO", "commit-archive").strip()

        if not pat:
            print("[IndianCalendar] ⚠️ GitHub API credentials missing — using fallback", file=sys.stderr)
            return {}
        if not username:
            print(f"[IndianCalendar] ⚠️ GitHub username missing for {filename}.", file=sys.stderr)
            return {}

        url = f"{GITHUB_API}/repos/{username}/{repo}/contents/{filename}"
        headers = {
            "Authorization": f"token {pat}",
            "Accept": "application/vnd.github.v3+json",
        }
        
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.ok:
            data = resp.json()
            if "content" in data:
                decoded = base64.b64decode(data["content"]).decode("utf-8")
                return json.loads(decoded)
        else:
            print(f"[IndianCalendar] ⚠️ Failed to fetch {filename} from API: {resp.status_code}", file=sys.stderr)
    except Exception as e:
        print(f"[IndianCalendar] ⚠️ Error fetching {filename} from GitHub API: {e}", file=sys.stderr)
    return {}


def parse_holiday_date(date_str: str, year: int) -> datetime.date | None:
    try:
        if len(date_str) == 5:  # MM-DD
            return datetime.date(year, int(date_str[:2]), int(date_str[3:]))
        else:
            return datetime.date.fromisoformat(date_str)
    except (ValueError, AttributeError):
        return None


def _is_major_festival(name: str) -> bool:
    n = name.lower()
    return any(kw in n for kw in MAJOR_FESTIVAL_KEYWORDS)


# ---------------------------------------------------------------------------
# Source 1: Festivals
# ---------------------------------------------------------------------------

def get_festivals_today(date: datetime.date, api_key: str = None) -> dict:
    """Returns {"is_holiday": bool, "name": str, "is_major": bool}"""
    year = date.year
    date_str = date.isoformat()

    # 1. Try Cache
    cache = load_json_safe(HOLIDAYS_CACHE_FILE)
    try:
        fetched = datetime.date.fromisoformat(cache.get("fetched_at", "2000-01-01"))
        age = (today_ist() - fetched).days
        is_fresh = (cache.get("year") == year and age < CACHE_TTL_DAYS)
    except Exception:
        is_fresh = False

    holidays = []
    if is_fresh:
        holidays = cache.get("holidays", [])
    elif api_key and _REQUESTS_OK:
        print(f"[IndianCalendar] 🌐 Fetching Calendarific API for {year}...")
        try:
            resp = requests.get(
                CALENDARIFIC_API,
                params={"api_key": api_key, "country": "IN", "year": year, "type": "national"},
                timeout=15,
            )
            if resp.ok:
                data = resp.json()
                items = data.get("response", {}).get("holidays", [])
                holidays = [
                    {"name": h["name"], "date": h["date"]["iso"][:10]}
                    for h in items if h.get("name") and h.get("date", {}).get("iso")
                ]
                save_json_safe(HOLIDAYS_CACHE_FILE, {
                    "fetched_at": today_ist().isoformat(),
                    "year": year,
                    "holidays": holidays
                })
        except Exception as e:
            print(f"[IndianCalendar] ⚠️ Calendarific API error: {e}", file=sys.stderr)

    if not holidays:
        # Fallback to hardcoded
        for h in HARDCODED_HOLIDAYS:
            d = parse_holiday_date(h["date"], year)
            if d:
                holidays.append({"name": h["name"], "date": d.isoformat(), "_major": h.get("major", False)})

    # Check if today is in holidays
    for h in holidays:
        if h.get("date") == date_str:
            name = h.get("name", "Holiday")
            is_major = h.get("_major", _is_major_festival(name))
            return {"is_holiday": True, "name": name, "is_major": is_major}

    return {"is_holiday": False, "name": "", "is_major": False}


# ---------------------------------------------------------------------------
# Source 2: Exams (from monthly_config.json)
# ---------------------------------------------------------------------------

def get_exam_status_today(date: datetime.date) -> dict:
    """Returns {"is_exam_day": bool, "is_exam_week": bool}"""
    date_str = date.isoformat()
    current_month = date.strftime("%Y-%m")
    
    config = fetch_from_github(MONTHLY_CONFIG_FILE)
    
    if config.get("month") != current_month:
        # Missing or outdated config -> 0 exam days
        return {"is_exam_day": False, "is_exam_week": False}
        
    exam_dates_str = config.get("exam_dates", [])

    exam_dates = []
    for ed_str in exam_dates_str:
        try:
            exam_dates.append(datetime.date.fromisoformat(ed_str))
        except ValueError:
            pass

    if date_str in exam_dates_str:
        return {"is_exam_day": True, "is_exam_week": False}

    # Check if we are in the 7 days before the FIRST exam of the month
    if exam_dates:
        exam_dates.sort()
        first_exam = exam_dates[0]
        # Only consider exam_week if the first exam is in the future relative to today
        if date < first_exam and (first_exam - date).days <= 7:
            return {"is_exam_day": False, "is_exam_week": True}

    return {"is_exam_day": False, "is_exam_week": False}




# ---------------------------------------------------------------------------
# Core Mood Resolver
# ---------------------------------------------------------------------------

def get_today_mood() -> dict:
    try:
        today = today_ist()
        api_key = os.environ.get("CALENDARIFIC_API_KEY", "").strip()

        # Gather sources
        festivals = get_festivals_today(today, api_key)
        exams = get_exam_status_today(today)

        # Resolution Priority
        # 1. Major Festival
        if festivals["is_holiday"] and festivals["is_major"]:
            return {
                "mood": "festival_major",
                "occasion": festivals["name"],
                "message_category": "celebration",
                "skip_probability": 1.0,
                "log": f"🎆 {festivals['name']} — major festival, zero commits today"
            }

        # 2. Exam Day
        if exams["is_exam_day"]:
            return {
                "mood": "exam_season",
                "occasion": "Exam Day",
                "message_category": "exam_mode",
                "skip_probability": 1.0,
                "log": "📚 Exam day today — zero commits, skipping entirely"
            }

        # 3. Minor Festival
        if festivals["is_holiday"]:
            return {
                "mood": "festival_minor",
                "occasion": festivals["name"],
                "message_category": "celebration",
                "skip_probability": 0.5,
                "log": f"🎉 {festivals['name']} — minor holiday (50/50 chance of 1 commit)"
            }

        # 4. Exam Week (Pre-exam)
        if exams["is_exam_week"]:
            return {
                "mood": "exam_week",
                "occasion": "Pre-exam week",
                "message_category": "exam_mode",
                "skip_probability": 0.6,
                "log": f"📖 Pre-exam week — reducing commits"
            }

        # 5. Normal Day
        return {
            "mood": "normal",
            "occasion": "Regular Day",
            "message_category": None,
            "skip_probability": 0.0, 
            "log": f"📅 Normal day"
        }

    except Exception as e:
        print(f"[IndianCalendar] ⚠️ Error in get_today_mood: {e}", file=sys.stderr)
        return {
            "mood": "normal",
            "occasion": "Fallback",
            "message_category": None,
            "skip_probability": 0.0,
            "log": "📅 Fallback to normal day"
        }

if __name__ == "__main__":
    mood = get_today_mood()
    print(json.dumps(mood, indent=2, ensure_ascii=False))
