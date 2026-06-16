#!/usr/bin/env python3
"""
AutoCommit Generator — Pattern Engine
======================================
Reads commit_history.json from the archive repo, determines today's commit
mode (Quiet/Normal/Burst/Rest), picks unique commit times using the
Excel-derived human activity model, selects semantically unique messages,
and outputs a JSON plan for the GitHub Actions workflow.

Tech: Python 3.12 · difflib stdlib · pandas 2.x (optional) · datetime
"""

import json
import os
import sys
import random
import datetime
import difflib
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
IST_OFFSET = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
HISTORY_FILE = "commit_history.json"
STREAK_FILE  = "streak_stats.json"
CONFIG_FILE  = "config.json"
MSG_POOL_FILE = "message_pool.json"

SIMILARITY_THRESHOLD = 0.75   # Reject if ≥75% similar to any 180-day msg
HISTORY_DAYS         = 180
ACTIVITY_LOG_MAX     = 500

# Excel-derived active hour distribution (weighted by real data)
# Hours extracted from activity_generator.xlsx reference data
ACTIVE_HOURS_WEIGHTS = {
    7: 3,  8: 8,  9: 12, 10: 14, 11: 12, 12: 10,
    13: 6, 14: 9, 15: 11, 16: 10, 17: 8, 18: 9,
    19: 10, 20: 12, 21: 11, 22: 8, 23: 5
}

# Mode probabilities from PRD Section 3.4
MODE_QUIET  = "Quiet"
MODE_NORMAL = "Normal"
MODE_BURST  = "Burst"
MODE_REST   = "Rest"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def now_ist() -> datetime.datetime:
    return datetime.datetime.now(IST_OFFSET)


def today_str() -> str:
    return now_ist().strftime("%Y-%m-%d")


def load_json(path: str) -> dict:
    p = Path(path)
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_json(path: str, data: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def prune_history(history: dict) -> dict:
    """Remove entries older than HISTORY_DAYS days."""
    cutoff = now_ist().date() - datetime.timedelta(days=HISTORY_DAYS)
    return {
        date_str: msgs
        for date_str, msgs in history.items()
        if datetime.date.fromisoformat(date_str) >= cutoff
    }


# ---------------------------------------------------------------------------
# Sick Day Logic (PRD Section 3.3)
# ---------------------------------------------------------------------------

def load_config() -> dict:
    cfg = load_json(CONFIG_FILE)
    defaults = {
        "active": True,
        "commits_per_day": 3,
        "weekday_only": False,
        "burst_mode": True,
        "sick_days_this_month": [],
        "similarity_threshold": SIMILARITY_THRESHOLD,
    }
    for k, v in defaults.items():
        cfg.setdefault(k, v)
    return cfg


def is_sick_day(config: dict) -> bool:
    today = today_str()
    return today in config.get("sick_days_this_month", [])


def is_weekend() -> bool:
    return now_ist().weekday() >= 5  # Saturday=5, Sunday=6


# ---------------------------------------------------------------------------
# Mode Selection (PRD Section 3.4)
# ---------------------------------------------------------------------------

def select_mode(config: dict, history: dict) -> str:
    """Determine today's commit mode using PRD probability weights."""
    if not config.get("active", True):
        return MODE_REST
    if is_sick_day(config):
        return MODE_REST
    if config.get("weekday_only", False) and is_weekend():
        return MODE_REST

    today = today_str()
    yesterday = (now_ist().date() - datetime.timedelta(days=1)).isoformat()

    # After rest day → Quiet mode
    yesterday_msgs = history.get(yesterday, [])
    if not yesterday_msgs:
        return MODE_QUIET

    # Burst mode disabled → cap at Normal
    if not config.get("burst_mode", True):
        r = random.random()
        return MODE_QUIET if r < 0.25 else MODE_NORMAL

    # Full probability draw
    r = random.random()
    if r < 0.12:
        return MODE_REST
    elif r < 0.12 + 0.25:
        return MODE_QUIET
    elif r < 0.12 + 0.25 + 0.60:
        return MODE_NORMAL
    else:
        return MODE_BURST


def commit_count_for_mode(mode: str, config: dict) -> int:
    """Return number of commits for the selected mode."""
    if mode == MODE_REST:
        return 0
    elif mode == MODE_QUIET:
        return 1
    elif mode == MODE_NORMAL:
        cap = min(config.get("commits_per_day", 3), 3)
        return random.randint(2, cap) if cap >= 2 else 1
    elif mode == MODE_BURST:
        cap = min(config.get("commits_per_day", 7), 7)
        return random.randint(4, max(4, cap))
    return 1


# ---------------------------------------------------------------------------
# Timing Engine (PRD Section 3.2)
# ---------------------------------------------------------------------------

def sample_hour() -> int:
    """Sample an active hour weighted by real Excel distribution."""
    hours = list(ACTIVE_HOURS_WEIGHTS.keys())
    weights = list(ACTIVE_HOURS_WEIGHTS.values())
    # Weekend: skew toward afternoon (12-20)
    if is_weekend():
        weights = [
            w * 2 if 12 <= h <= 20 else max(1, w // 2)
            for h, w in zip(hours, weights)
        ]
    return random.choices(hours, weights=weights, k=1)[0]


def generate_commit_times(count: int, mode: str) -> list[str]:
    """
    Generate `count` commit times in IST as HH:MM:SS strings.
    Rules:
      - Never before 07:00 or after 23:30
      - Minimum 45-minute gap between commits
      - Burst mode: cluster in 2 sessions with 2-4 hour gap
      - Never exactly HH:MM:00 (random seconds 1-59)
    """
    if count == 0:
        return []

    times = []
    used_minutes: list[int] = []  # minutes from midnight

    def minutes_ok(m: int) -> bool:
        if m < 7 * 60 or m > 23 * 60 + 30:
            return False
        for used in used_minutes:
            if abs(m - used) < 45:
                return False
        return True

    if mode == MODE_BURST and count >= 4:
        # Two sessions separated by 2-4 hours
        session1_count = count // 2
        session2_count = count - session1_count
        session1_start = sample_hour() * 60 + random.randint(0, 30)
        session1_start = max(7 * 60, min(session1_start, 20 * 60))
        gap = random.randint(120, 240)  # 2-4 hours gap
        session2_start = session1_start + gap

        for i in range(session1_count):
            m = session1_start + i * random.randint(5, 25)
            while not minutes_ok(m):
                m += 1
                if m > 23 * 60 + 30:
                    m = 7 * 60
            used_minutes.append(m)
            times.append(m)

        for i in range(session2_count):
            m = session2_start + i * random.randint(5, 25)
            while not minutes_ok(m):
                m += 1
                if m > 23 * 60 + 30:
                    break
            if minutes_ok(m):
                used_minutes.append(m)
                times.append(m)
    else:
        for _ in range(count):
            for _attempt in range(50):
                h = sample_hour()
                m_offset = random.randint(-23, 23)
                m = h * 60 + m_offset
                if minutes_ok(m):
                    used_minutes.append(m)
                    times.append(m)
                    break

    times.sort()
    result = []
    for m in times:
        h = m // 60
        mn = m % 60
        sec = random.randint(1, 59)  # Never exactly :00
        result.append(f"{h:02d}:{mn:02d}:{sec:02d}")
    return result


# ---------------------------------------------------------------------------
# Message Uniqueness Engine (PRD Section 4)
# ---------------------------------------------------------------------------

def load_all_history_messages(history: dict) -> list[str]:
    """Flatten all messages from history dict into a single list."""
    msgs = []
    for date_str, day_msgs in history.items():
        if isinstance(day_msgs, list):
            msgs.extend(day_msgs)
        elif isinstance(day_msgs, str):
            msgs.append(day_msgs)
    return [m.lower().strip() for m in msgs]


def strip_prefix(message: str) -> str:
    """Remove conventional commit prefix for similarity comparison."""
    parts = message.split(":", 1)
    return parts[1].strip().lower() if len(parts) == 2 else message.lower().strip()


def is_too_similar(candidate: str, history_msgs: list[str], threshold: float) -> bool:
    """
    Returns True if candidate is >= threshold similar to any history message.
    Uses difflib.SequenceMatcher (Levenshtein-based ratio).
    """
    candidate_stripped = strip_prefix(candidate)
    for hist_msg in history_msgs:
        hist_stripped = strip_prefix(hist_msg)
        ratio = difflib.SequenceMatcher(
            None, candidate_stripped, hist_stripped
        ).ratio()
        if ratio >= threshold:
            return True
    return False


def pick_unique_messages(
    count: int,
    history_msgs: list[str],
    message_pool: dict,
    threshold: float = SIMILARITY_THRESHOLD,
) -> list[str]:
    """
    Pick `count` unique messages from the pool that pass semantic check.
    Categories are rotated to ensure diversity (PRD 6.3 signal 4).
    """
    categories = list(message_pool.get("categories", {}).keys())
    if not categories:
        raise ValueError("message_pool.json has no categories")

    selected = []
    used_in_this_run: list[str] = []
    session_msgs = history_msgs + []
    random.shuffle(categories)

    attempts = 0
    cat_index = 0

    while len(selected) < count and attempts < 500:
        attempts += 1
        cat = categories[cat_index % len(categories)]
        cat_index += 1
        pool = message_pool["categories"].get(cat, [])
        if not pool:
            continue

        candidate = random.choice(pool)
        if candidate in used_in_this_run:
            continue
        if is_too_similar(candidate, session_msgs, threshold):
            continue

        selected.append(candidate)
        used_in_this_run.append(candidate)
        session_msgs.append(candidate)

    if len(selected) < count:
        print(
            f"[WARN] Only found {len(selected)}/{count} unique messages. "
            "Consider expanding the message pool.",
            file=sys.stderr,
        )

    return selected


# ---------------------------------------------------------------------------
# Streak Tracker (PRD Section 6.1)
# ---------------------------------------------------------------------------

def update_streak_stats(history: dict, stats: dict, today_count: int) -> dict:
    """Recompute current streak, update longest streak and total commits."""
    stats.setdefault("current_streak", 0)
    stats.setdefault("longest_streak", 0)
    stats.setdefault("total_commits", 0)
    stats.setdefault("weekly_summaries", [])

    if today_count > 0:
        stats["total_commits"] += today_count

    # Recompute current streak from history
    streak = 0
    check_date = now_ist().date()
    while True:
        date_str = check_date.isoformat()
        day_msgs = history.get(date_str, [])
        has_commit = bool(day_msgs)
        if check_date == now_ist().date() and today_count > 0:
            has_commit = True
        if not has_commit:
            break
        streak += 1
        check_date -= datetime.timedelta(days=1)

    stats["current_streak"] = streak
    if streak > stats["longest_streak"]:
        stats["longest_streak"] = streak

    stats["last_updated"] = today_str()
    return stats


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------

def main() -> None:
    print("[AutoCommit] Pattern Engine v1.0 starting...")

    config        = load_config()
    history       = load_json(HISTORY_FILE)
    streak_stats  = load_json(STREAK_FILE)
    message_pool  = load_json(MSG_POOL_FILE)

    # Prune old history entries
    history = prune_history(history)

    # Determine today's mode
    mode = select_mode(config, history)
    count = commit_count_for_mode(mode, config)

    print(f"[AutoCommit] Mode: {mode} | Commits planned: {count}")

    if mode == MODE_REST or count == 0:
        # Write empty plan — workflow will skip committing
        plan = {
            "date": today_str(),
            "mode": MODE_REST,
            "commits": [],
        }
        save_json("commit_plan.json", plan)
        print("[AutoCommit] Rest day — no commits scheduled.")
        # Still update streak (break)
        streak_stats = update_streak_stats(history, streak_stats, 0)
        save_json(STREAK_FILE, streak_stats)
        return

    # Load existing messages for uniqueness check
    history_msgs = load_all_history_messages(history)
    threshold = config.get("similarity_threshold", SIMILARITY_THRESHOLD)

    # Select messages
    messages = pick_unique_messages(count, history_msgs, message_pool, threshold)
    if not messages:
        print("[ERROR] No unique messages available. Exiting.", file=sys.stderr)
        sys.exit(1)

    # Generate commit times
    times = generate_commit_times(len(messages), mode)

    # Build commit plan
    commits = [
        {"time": t, "message": m}
        for t, m in zip(times, messages)
    ]

    plan = {
        "date": today_str(),
        "mode": mode,
        "commits": commits,
    }
    save_json("commit_plan.json", plan)

    # Update history with today's messages
    today = today_str()
    history.setdefault(today, [])
    for c in commits:
        history[today].append(c["message"])

    save_json(HISTORY_FILE, history)

    # Update streak stats
    streak_stats = update_streak_stats(history, streak_stats, len(commits))
    save_json(STREAK_FILE, streak_stats)

    print(f"[AutoCommit] Plan saved: {len(commits)} commits scheduled.")
    for c in commits:
        print(f"  [{c['time']} IST] {c['message']}")


if __name__ == "__main__":
    main()
