#!/usr/bin/env python3
"""
AutoCommit Generator — Indian Calendar & Mood Engine
======================================================
Determines today's "mood" based on:
  - Indian public holidays (Calendarific API with local cache, hardcoded fallback)
  - Exam seasons (JEE/NEET/GATE/RTU — hardcoded)
  - College break periods (Summer, Winter, Diwali break — hardcoded)
  - Day-of-week personality (Monday motivation, Friday wind-down, weekend)

Entry point: get_today_mood() → dict

Tech: Python 3.12 · requests · stdlib only (no new pip packages)
"""

import json
import os
import sys
import datetime
import random
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
HOLIDAYS_CACHE_FILE = "holidays_cache.json"
CACHE_TTL_DAYS = 7

# Mood names
MOOD_FESTIVAL_MAJOR   = "festival_major"
MOOD_FESTIVAL_MINOR   = "festival_minor"
MOOD_EXAM_SEASON      = "exam_season"
MOOD_EXAM_WEEK        = "exam_week"
MOOD_COLLEGE_HOLIDAY  = "college_holiday"
MOOD_MONDAY           = "monday_motivation"
MOOD_FRIDAY           = "friday_winddown"
MOOD_WEEKEND          = "weekend"
MOOD_NORMAL           = "normal"

# Priority order (lower index = higher priority)
MOOD_PRIORITY = [
    MOOD_FESTIVAL_MAJOR,
    MOOD_EXAM_SEASON,
    MOOD_FESTIVAL_MINOR,
    MOOD_EXAM_WEEK,
    MOOD_COLLEGE_HOLIDAY,
    MOOD_MONDAY,
    MOOD_FRIDAY,
    MOOD_WEEKEND,
    MOOD_NORMAL,
]

# Mood rules table
MOOD_RULES = {
    MOOD_FESTIVAL_MAJOR:  {"commit_multiplier": 0.0, "skip_probability": 1.0,  "message_category": "celebration"},
    MOOD_FESTIVAL_MINOR:  {"commit_multiplier": 0.3, "skip_probability": 0.5,  "message_category": "celebration"},
    MOOD_EXAM_SEASON:     {"commit_multiplier": 0.0, "skip_probability": 0.9,  "message_category": "exam_mode"},
    MOOD_EXAM_WEEK:       {"commit_multiplier": 0.4, "skip_probability": 0.6,  "message_category": "exam_mode"},
    MOOD_COLLEGE_HOLIDAY: {"commit_multiplier": 1.5, "skip_probability": 0.1,  "message_category": "college_holiday_burst"},
    MOOD_MONDAY:          {"commit_multiplier": 1.4, "skip_probability": 0.05, "message_category": "monday_energy"},
    MOOD_FRIDAY:          {"commit_multiplier": 0.6, "skip_probability": 0.2,  "message_category": "friday_relax"},
    MOOD_WEEKEND:         {"commit_multiplier": 0.7, "skip_probability": 0.3,  "message_category": "weekend_light"},
    MOOD_NORMAL:          {"commit_multiplier": 1.0, "skip_probability": 0.15, "message_category": None},
}

# Major festivals (skip_probability=1.0): names must match Calendarific responses
# (case-insensitive substring match used)
MAJOR_FESTIVAL_KEYWORDS = [
    "diwali", "deepawali", "holi", "eid ul-fitr", "eid-ul-fitr", "eid al-fitr",
    "eid ul-adha", "eid-ul-adha", "eid al-adha", "christmas", "new year",
]

# ---------------------------------------------------------------------------
# Hardcoded holidays fallback (name → "MM-DD" or "YYYY-MM-DD")
# Approximate dates — good enough for mood detection
# ---------------------------------------------------------------------------
HARDCODED_HOLIDAYS: list[dict] = [
    # Fixed-date national holidays
    {"name": "Republic Day",        "date": "01-26", "major": False},
    {"name": "Independence Day",    "date": "08-15", "major": False},
    {"name": "Gandhi Jayanti",      "date": "10-02", "major": False},
    {"name": "Christmas",           "date": "12-25", "major": True},
    {"name": "New Year",            "date": "01-01", "major": True},
    # Floating festivals — approximate 2025/2026 dates
    # 2025
    {"name": "Holi",                "date": "2025-03-14", "major": True},
    {"name": "Diwali",              "date": "2025-10-20", "major": True},
    {"name": "Ganesh Chaturthi",    "date": "2025-08-27", "major": False},
    {"name": "Janmashtami",         "date": "2025-08-16", "major": False},
    {"name": "Navratri",            "date": "2025-10-02", "major": False},
    {"name": "Dussehra",            "date": "2025-10-12", "major": False},
    {"name": "Raksha Bandhan",      "date": "2025-08-09", "major": False},
    {"name": "Eid ul-Fitr",         "date": "2025-03-31", "major": True},
    {"name": "Eid ul-Adha",         "date": "2025-06-07", "major": True},
    # 2026
    {"name": "Holi",                "date": "2026-03-04", "major": True},
    {"name": "Diwali",              "date": "2026-11-08", "major": True},
    {"name": "Ganesh Chaturthi",    "date": "2026-08-19", "major": False},
    {"name": "Janmashtami",         "date": "2026-08-05", "major": False},
    {"name": "Navratri",            "date": "2026-10-12", "major": False},
    {"name": "Dussehra",            "date": "2026-10-21", "major": False},
    {"name": "Raksha Bandhan",      "date": "2026-08-29", "major": False},
    {"name": "Eid ul-Fitr",         "date": "2026-03-20", "major": True},
    {"name": "Eid ul-Adha",         "date": "2026-05-27", "major": True},
]

# ---------------------------------------------------------------------------
# Exam season ranges — (month, day) tuples, inclusive
# ---------------------------------------------------------------------------
# Format: (name, [(start_month, start_day, end_month, end_day), ...])
EXAM_SEASONS: list[tuple[str, list[tuple[int,int,int,int]]]] = [
    ("JEE Mains Session 1",   [(1, 15, 1, 30)]),
    ("JEE Mains Session 2",   [(4, 1,  4, 15)]),
    ("JEE Advanced",          [(5, 25, 6, 5)]),
    ("NEET",                  [(5, 1,  5, 10)]),
    ("GATE",                  [(2, 1,  2, 15)]),
    ("RTU Exams (Semester)",  [(11, 10, 12, 5), (4, 20, 5, 15)]),
]

# One week before any exam start date is "exam_week" mood
PRE_EXAM_DAYS = 7

# ---------------------------------------------------------------------------
# College break periods — (month, day) inclusive ranges
# ---------------------------------------------------------------------------
COLLEGE_BREAKS: list[tuple[str, int, int, int, int]] = [
    ("Summer Break",  5, 20, 7, 10),
    ("Winter Break", 12, 20, 1,  5),
    # Diwali break is computed dynamically from Diwali date ±2 days
]
DIWALI_BREAK_BEFORE = 3
DIWALI_BREAK_AFTER  = 2


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


def date_in_range(today: datetime.date, sm: int, sd: int, em: int, ed: int) -> bool:
    """
    Returns True if today falls within the range (sm/sd .. em/ed), wrapping
    correctly across year boundaries (e.g. Dec 20 – Jan 5).
    """
    year = today.year
    start = datetime.date(year, sm, sd)
    # Handle year-wrap (e.g. Dec 20 → Jan 5 next year)
    if em < sm or (em == sm and ed < sd):
        end = datetime.date(year + 1, em, ed)
        if today < start:
            # We might be in the second half (Jan side) of a wrap from prev year
            start = datetime.date(year - 1, sm, sd)
            end   = datetime.date(year, em, ed)
    else:
        end = datetime.date(year, em, ed)
    return start <= today <= end


def parse_holiday_date(date_str: str, year: int) -> datetime.date | None:
    """Parse 'MM-DD' or 'YYYY-MM-DD' into a date."""
    try:
        if len(date_str) == 5:  # MM-DD
            return datetime.date(year, int(date_str[:2]), int(date_str[3:]))
        else:
            return datetime.date.fromisoformat(date_str)
    except (ValueError, AttributeError):
        return None


# ---------------------------------------------------------------------------
# Calendarific API + Cache
# ---------------------------------------------------------------------------

def _cache_is_fresh(cache: dict, year: int) -> bool:
    try:
        fetched = datetime.date.fromisoformat(cache.get("fetched_at", "2000-01-01"))
        age = (today_ist() - fetched).days
        return cache.get("year") == year and age < CACHE_TTL_DAYS
    except Exception:
        return False


def _fetch_from_calendarific(api_key: str, year: int) -> list[dict]:
    """Call Calendarific API and return simplified holiday list."""
    if not _REQUESTS_OK:
        return []
    try:
        resp = requests.get(
            CALENDARIFIC_API,
            params={"api_key": api_key, "country": "IN", "year": year, "type": "national"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        holidays = data.get("response", {}).get("holidays", [])
        return [
            {
                "name": h["name"],
                "date": h["date"]["iso"][:10],  # YYYY-MM-DD
            }
            for h in holidays
            if h.get("name") and h.get("date", {}).get("iso")
        ]
    except Exception as e:
        print(f"[IndianCalendar] ⚠️  Calendarific API error: {e}", file=sys.stderr)
        return []


def load_holidays(year: int) -> tuple[list[dict], str]:
    """
    Return (holidays_list, source_label).
    Priority: fresh cache → Calendarific API → hardcoded fallback.
    holidays_list format: [{"name": str, "date": "YYYY-MM-DD"}, ...]
    """
    api_key = os.environ.get("CALENDARIFIC_API_KEY", "").strip()

    # 1. Try cache
    cache = load_json_safe(HOLIDAYS_CACHE_FILE)
    if _cache_is_fresh(cache, year):
        print(f"[IndianCalendar] 📅 Using cached holidays ({len(cache.get('holidays', []))} entries)")
        return cache.get("holidays", []), "cache"

    # 2. Try API
    if api_key:
        print(f"[IndianCalendar] 🌐 Fetching holidays from Calendarific for {year}...")
        holidays = _fetch_from_calendarific(api_key, year)
        if holidays:
            new_cache = {
                "fetched_at": today_ist().isoformat(),
                "year": year,
                "holidays": holidays,
            }
            save_json_safe(HOLIDAYS_CACHE_FILE, new_cache)
            print(f"[IndianCalendar] ✅ Calendarific: {len(holidays)} holidays cached.")
            return holidays, "api"
        print("[IndianCalendar] ⚠️  Calendarific returned empty — using hardcoded fallback.")
    else:
        print("[IndianCalendar] ℹ️  CALENDARIFIC_API_KEY not set — using hardcoded fallback.")

    # 3. Hardcoded fallback
    resolved = []
    for h in HARDCODED_HOLIDAYS:
        d = parse_holiday_date(h["date"], year)
        if d:
            resolved.append({"name": h["name"], "date": d.isoformat(), "_major": h.get("major", False)})
    return resolved, "hardcoded"


# ---------------------------------------------------------------------------
# Holiday mood detection
# ---------------------------------------------------------------------------

def _is_major_festival(name: str) -> bool:
    n = name.lower()
    return any(kw in n for kw in MAJOR_FESTIVAL_KEYWORDS)


def check_holiday_mood(today: datetime.date, holidays: list[dict]) -> tuple[str | None, str]:
    """Return (mood, occasion_name) or (None, '') if not a holiday."""
    today_str = today.isoformat()
    for h in holidays:
        if h.get("date", "") == today_str:
            name = h.get("name", "Holiday")
            is_major = h.get("_major", _is_major_festival(name))
            mood = MOOD_FESTIVAL_MAJOR if is_major else MOOD_FESTIVAL_MINOR
            return mood, name
    return None, ""


# ---------------------------------------------------------------------------
# Exam season detection
# ---------------------------------------------------------------------------

def check_exam_mood(today: datetime.date) -> tuple[str | None, str]:
    """Return (MOOD_EXAM_SEASON | MOOD_EXAM_WEEK | None, label)."""
    year = today.year

    for exam_name, ranges in EXAM_SEASONS:
        for (sm, sd, em, ed) in ranges:
            # Compute actual start/end dates for this year
            start = datetime.date(year, sm, sd)
            if em < sm or (em == sm and ed < sd):
                end = datetime.date(year + 1, em, ed)
            else:
                end = datetime.date(year, em, ed)

            if start <= today <= end:
                return MOOD_EXAM_SEASON, exam_name

            # Pre-exam week
            pre_start = start - datetime.timedelta(days=PRE_EXAM_DAYS)
            if pre_start <= today < start:
                return MOOD_EXAM_WEEK, f"Pre-{exam_name}"

    return None, ""


# ---------------------------------------------------------------------------
# College break detection
# ---------------------------------------------------------------------------

def _find_diwali_date(holidays: list[dict], year: int) -> datetime.date | None:
    for h in holidays:
        if "diwali" in h.get("name", "").lower() or "deepawali" in h.get("name", "").lower():
            try:
                return datetime.date.fromisoformat(h["date"])
            except ValueError:
                pass
    # Fallback hardcoded
    for h in HARDCODED_HOLIDAYS:
        if "diwali" in h["name"].lower():
            d = parse_holiday_date(h["date"], year)
            if d and d.year == year:
                return d
    return None


def check_college_break(today: datetime.date, holidays: list[dict]) -> tuple[bool, str]:
    """Return (is_break, label)."""
    # Fixed breaks
    for (label, sm, sd, em, ed) in COLLEGE_BREAKS:
        if date_in_range(today, sm, sd, em, ed):
            return True, label

    # Diwali break (dynamic)
    diwali = _find_diwali_date(holidays, today.year)
    if diwali:
        break_start = diwali - datetime.timedelta(days=DIWALI_BREAK_BEFORE)
        break_end   = diwali + datetime.timedelta(days=DIWALI_BREAK_AFTER)
        if break_start <= today <= break_end:
            return True, "Diwali Break"

    return False, ""


# ---------------------------------------------------------------------------
# Day-of-week mood
# ---------------------------------------------------------------------------

def check_weekday_mood(today: datetime.date) -> tuple[str | None, str]:
    wd = today.weekday()  # 0=Mon, 4=Fri, 5=Sat, 6=Sun
    if wd == 0:
        return MOOD_MONDAY, "Monday"
    if wd == 4:
        return MOOD_FRIDAY, "Friday"
    if wd >= 5:
        return MOOD_WEEKEND, today.strftime("%A")
    return None, ""


# ---------------------------------------------------------------------------
# Main public API
# ---------------------------------------------------------------------------

def get_today_mood(override: str | None = None) -> dict:
    """
    Determine today's mood. Returns a dict:
    {
        "mood": str,
        "occasion": str,
        "commit_multiplier": float,
        "message_category": str | None,
        "skip_probability": float,
        "log": str,
    }

    Args:
        override: If set (e.g. from config.json mood_override), uses that mood
                  directly without any date checks. Pass None for auto-detect.
    """
    try:
        today = today_ist()
        year  = today.year

        # Manual override from config
        if override and override in MOOD_RULES:
            rules = MOOD_RULES[override]
            return {
                "mood": override,
                "occasion": "Manual Override",
                "commit_multiplier": rules["commit_multiplier"],
                "message_category":  rules["message_category"],
                "skip_probability":  rules["skip_probability"],
                "log": f"🎛️  Mood manually overridden to '{override}'",
            }

        # Load holidays (cached or fresh)
        holidays, source = load_holidays(year)

        # Evaluate candidate moods in priority order
        candidates: list[tuple[str, str]] = []  # (mood, occasion)

        # Festival check
        h_mood, h_name = check_holiday_mood(today, holidays)
        if h_mood:
            candidates.append((h_mood, h_name))

        # Exam check
        e_mood, e_name = check_exam_mood(today)
        if e_mood:
            candidates.append((e_mood, e_name))

        # College break check
        is_break, break_label = check_college_break(today, holidays)
        if is_break:
            candidates.append((MOOD_COLLEGE_HOLIDAY, break_label))

        # Day-of-week check
        w_mood, w_name = check_weekday_mood(today)
        if w_mood:
            candidates.append((w_mood, w_name))

        # Always append normal as lowest priority
        candidates.append((MOOD_NORMAL, "Regular day"))

        # Pick highest-priority mood
        for priority_mood in MOOD_PRIORITY:
            for mood, occasion in candidates:
                if mood == priority_mood:
                    rules = MOOD_RULES[mood]
                    emoji = _mood_emoji(mood)
                    log   = _mood_log(mood, occasion, rules, today)
                    result = {
                        "mood": mood,
                        "occasion": occasion,
                        "commit_multiplier": rules["commit_multiplier"],
                        "message_category":  rules["message_category"],
                        "skip_probability":  rules["skip_probability"],
                        "log": log,
                    }
                    print(f"[IndianCalendar] {emoji} {log}")
                    return result

        # Unreachable but safe
        return _default_mood()

    except Exception as e:
        print(f"[IndianCalendar] ⚠️  Error in get_today_mood: {e} — defaulting to normal.",
              file=sys.stderr)
        return _default_mood()


def _default_mood() -> dict:
    rules = MOOD_RULES[MOOD_NORMAL]
    return {
        "mood": MOOD_NORMAL,
        "occasion": "Regular day",
        "commit_multiplier": rules["commit_multiplier"],
        "message_category":  rules["message_category"],
        "skip_probability":  rules["skip_probability"],
        "log": "📅 Normal day — standard commit behaviour",
    }


def _mood_emoji(mood: str) -> str:
    return {
        MOOD_FESTIVAL_MAJOR:  "🎆",
        MOOD_FESTIVAL_MINOR:  "🎉",
        MOOD_EXAM_SEASON:     "📚",
        MOOD_EXAM_WEEK:       "📖",
        MOOD_COLLEGE_HOLIDAY: "🏖️",
        MOOD_MONDAY:          "💪",
        MOOD_FRIDAY:          "🎶",
        MOOD_WEEKEND:         "😴",
        MOOD_NORMAL:          "📅",
    }.get(mood, "📅")


def _mood_log(mood: str, occasion: str, rules: dict, today: datetime.date) -> str:
    m = rules["commit_multiplier"]
    s = rules["skip_probability"]
    templates = {
        MOOD_FESTIVAL_MAJOR:  f"{occasion} — zero commits today, enjoying the break (skip={s})",
        MOOD_FESTIVAL_MINOR:  f"{occasion} — reduced commits (×{m}, skip={s})",
        MOOD_EXAM_SEASON:     f"{occasion} exam season — minimal commits (×{m}, skip={s})",
        MOOD_EXAM_WEEK:       f"Pre-exam week ({occasion}) — scaling back (×{m}, skip={s})",
        MOOD_COLLEGE_HOLIDAY: f"{occasion} — burst mode, finally free to code! (×{m}, skip={s})",
        MOOD_MONDAY:          f"Monday motivation — starting the week strong (×{m}, skip={s})",
        MOOD_FRIDAY:          f"Friday wind-down — wrapping up the week (×{m}, skip={s})",
        MOOD_WEEKEND:         f"{occasion} — weekend mode (×{m}, skip={s})",
        MOOD_NORMAL:          f"Standard day ({today.strftime('%A')}) — normal commit behaviour",
    }
    return templates.get(mood, f"{mood}: {occasion}")


# ---------------------------------------------------------------------------
# CLI for testing
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Indian Calendar mood detector")
    parser.add_argument("--date", help="Test a specific date YYYY-MM-DD (default: today IST)")
    parser.add_argument("--override", help="Force a mood (e.g. festival_major)")
    args = parser.parse_args()

    if args.date:
        # Monkey-patch today for testing
        _test_date = datetime.date.fromisoformat(args.date)
        original_today = today_ist
        today_ist = lambda: _test_date  # noqa: E731

    mood = get_today_mood(override=args.override)
    print("\n--- Mood Result ---")
    print(json.dumps(mood, indent=2, ensure_ascii=False))
