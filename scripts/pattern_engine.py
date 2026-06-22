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

# AI commit generator — imported lazily so the engine still works without it
try:
    from ai_commit_generator import generate_ai_messages, parse_extensions
    AI_GENERATOR_AVAILABLE = True
except ImportError:
    AI_GENERATOR_AVAILABLE = False

# Indian calendar mood engine — imported lazily, defaults to normal mood on failure
try:
    from indian_calendar import get_today_mood
    MOOD_ENGINE_AVAILABLE = True
except ImportError:
    MOOD_ENGINE_AVAILABLE = False

# Network guard — imported lazily, pattern engine runs normally without it
try:
    from network_guard import run_with_network_guard
    NETWORK_GUARD_AVAILABLE = True
except ImportError:
    NETWORK_GUARD_AVAILABLE = False
    print("[AutoCommit] ⚠️  network_guard not available — commits will run without retry logic.")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
IST_OFFSET = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
HISTORY_FILE = "commit_history.json"
STREAK_FILE  = "streak_stats.json"
CONFIG_FILE  = "config.json"
MSG_POOL_FILE = "message_pool.json"
MOOD_MSG_FILE = "mood_messages.json"

SIMILARITY_THRESHOLD = 0.75   # Reject if ≥75% similar to any 180-day msg
HISTORY_DAYS         = 180
ACTIVITY_LOG_MAX     = 500
PROFILE_FILE         = "pattern_profile.json"

# Excel-derived active hour distribution (weighted by real data)
# Hours extracted from activity_generator.xlsx reference data
ACTIVE_HOURS_WEIGHTS = {
    7: 3,  8: 8,  9: 12, 10: 14, 11: 12, 12: 10,
    13: 6, 14: 9, 15: 11, 16: 10, 17: 8, 18: 9,
    19: 10, 20: 12, 21: 11, 22: 8, 23: 5
}

def load_profile() -> dict:
    """
    Load pattern_profile.json from the archive repo working directory.
    Returns {} if not found — all callers must handle missing keys gracefully.
    """
    return load_json(PROFILE_FILE)


def profile_hour_weights(profile: dict) -> dict[int, int]:
    """
    Build an hour→weight dict from the profile's commits_by_hour.
    Falls back to the Excel-derived ACTIVE_HOURS_WEIGHTS if the profile
    is missing or has all-zero counts.
    """
    raw = profile.get("commits_by_hour", {})
    weights = {int(h): max(1, int(v)) for h, v in raw.items() if int(v) > 0}
    if not weights:
        return ACTIVE_HOURS_WEIGHTS
    return weights


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
# Timing Engine (PRD Section 3.2)
# ---------------------------------------------------------------------------

def sample_hour(profile: dict | None = None) -> int:
    """
    Sample an active hour.
    When a pattern profile is available, uses the user's real commits_by_hour
    weights. Falls back to the Excel-derived static distribution otherwise.
    """
    if profile:
        weights_dict = profile_hour_weights(profile)
    else:
        weights_dict = ACTIVE_HOURS_WEIGHTS

    hours   = list(weights_dict.keys())
    weights = list(weights_dict.values())

    # Weekend: skew toward afternoon (12-20) regardless of profile source
    if is_weekend():
        weights = [
            w * 2 if 12 <= h <= 20 else max(1, w // 2)
            for h, w in zip(hours, weights)
        ]
    return random.choices(hours, weights=weights, k=1)[0]


def generate_commit_times(count: int, mode: str, profile: dict | None = None) -> list[str]:
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
        session1_start = sample_hour(profile) * 60 + random.randint(0, 30)
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
                h = sample_hour(profile)
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
    profile: dict | None = None,
) -> list[str]:
    """
    Pick `count` unique messages from the pool that pass semantic check.
    When a pattern profile is available, categories are weighted by the user's
    real prefix_ratios so the generated messages match their natural style.
    Falls back to uniform rotation when profile is absent.
    """
    categories = list(message_pool.get("categories", {}).keys())
    if not categories:
        raise ValueError("message_pool.json has no categories")

    # Build category weights from profile prefix_ratios
    if profile and profile.get("prefix_ratios"):
        ratios = profile["prefix_ratios"]
        cat_weights = []
        for cat in categories:
            # ai_generated gets the highest weight; others match their prefix ratio
            if cat == "ai_generated":
                cat_weights.append(10.0)
            else:
                cat_weights.append(float(ratios.get(cat, 0.05)) * 100 + 1)
        use_weighted = True
    else:
        cat_weights = [1.0] * len(categories)
        use_weighted = False

    selected = []
    used_in_this_run: list[str] = []
    session_msgs = history_msgs + []

    if not use_weighted:
        random.shuffle(categories)

    attempts = 0
    cat_index = 0

    while len(selected) < count and attempts < 500:
        attempts += 1
        if use_weighted:
            cat = random.choices(categories, weights=cat_weights, k=1)[0]
        else:
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
    print("[AutoCommit] Pattern Engine v1.1 starting...")

    config        = load_config()
    history       = load_json(HISTORY_FILE)
    streak_stats  = load_json(STREAK_FILE)
    message_pool  = load_json(MSG_POOL_FILE)
    profile       = load_profile()   # may be {} if pattern_profile.json not yet generated

    if profile:
        print(f"[AutoCommit] Pattern profile loaded — "
              f"{profile.get('commits_analysed', 0)} commits analysed, "
              f"peak day: {['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][profile.get('peak_weekday', 1)]}")
    else:
        print("[AutoCommit] No pattern_profile.json found — using defaults.")

    # ── Step 0: Evaluate today's mood (Indian Calendar) ──────────────────────
    # Must run BEFORE mode selection so multiplier can adjust the commit count.
    mood_result = {"mood": "normal",
                   "skip_probability": 0.15, "message_category": None,
                   "occasion": "", "commits_range": [1, 3], "log": ""}
    try:
        if MOOD_ENGINE_AVAILABLE:
            mood_override = config.get("mood_override", None)
            mood_result = get_today_mood(override=mood_override)
        else:
            print("[AutoCommit] 📅 indian_calendar not available — using normal mood.")
    except Exception as _me:
        print(f"[AutoCommit] ⚠️  Mood engine error: {_me} — defaulting to normal.",
              file=sys.stderr)

    # Apply skip probability (hard skip of the entire day)
    skip_p = mood_result.get("skip_probability", 0.15)
    if random.random() < skip_p:
        plan = {
            "date": today_str(),
            "mode": MODE_REST,
            "mood": mood_result.get("mood", "normal"),
            "occasion": mood_result.get("occasion", ""),
            "commits": [],
        }
        save_json("commit_plan.json", plan)
        print(f"[AutoCommit] 🎭 Mood skip triggered ({mood_result['mood']}, "
              f"skip_p={skip_p:.2f}) — no commits today.")
        streak_stats = update_streak_stats(history, streak_stats, 0)
        save_json(STREAK_FILE, streak_stats)
        return

    # Prune old history entries
    history = prune_history(history)

    # Apply mood range to get today's count
    c_range = mood_result.get("commits_range", [1, 3])
    count = random.randint(c_range[0], c_range[1])

    # Assign a mode string based on count (for timing spacing logic)
    if count == 0:
        mode = MODE_REST
    elif count == 1:
        mode = MODE_QUIET
    elif count >= 4:
        mode = MODE_BURST
    else:
        mode = MODE_NORMAL

    print(f"[AutoCommit] Mode: {mode} | Commits planned: {count} (from range {c_range})")

    if mode == MODE_REST or count == 0:
        # Write empty plan — workflow will skip committing
        plan = {
            "date": today_str(),
            "mode": MODE_REST,
            "mood": mood_result.get("mood", "normal"),
            "occasion": mood_result.get("occasion", ""),
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

    # ── Step 1: Try AI-generated messages (Gemini) ───────────────────────────
    # Detect project file extensions from environment (set by workflow)
    # Falls back to message_pool.json automatically if API key absent / fails
    ai_messages: list[str] = []
    if AI_GENERATOR_AVAILABLE:
        raw_exts = os.environ.get("PROJECT_EXTENSIONS", ".py,.js,.jsx,.json,.yml")
        extensions = parse_extensions(raw_exts)
        print(f"[AutoCommit] Requesting AI messages for extensions: {', '.join(extensions)}")
        ai_messages = generate_ai_messages(
            extensions,
            history_msgs,
            repo_dir=os.path.abspath(os.getcwd()),  # archive repo working dir for git diff
        )
    else:
        print("[AutoCommit] ai_commit_generator not available — using static pool only.")

    # ── Step 1b: Inject mood-specific messages at highest priority ───────────
    mood_messages: list[str] = []
    mood_category = mood_result.get("message_category")
    if mood_category:
        try:
            mood_pool = load_json(MOOD_MSG_FILE)
            mood_messages = mood_pool.get(mood_category, [])
            if mood_messages:
                print(f"[AutoCommit] 🎭 Mood messages: {len(mood_messages)} '{mood_category}' "
                      f"messages loaded from mood_messages.json")
        except Exception as _mme:
            print(f"[AutoCommit] ⚠️  Could not load mood_messages.json: {_mme}",
                  file=sys.stderr)

    # ── Step 2: Build a merged pool for pick_unique_messages ─────────────────
    # Priority order: mood-specific → AI-generated → static pool
    merged_categories: dict = {}
    if mood_messages:
        merged_categories["mood_" + (mood_category or "misc")] = mood_messages
    if ai_messages:
        merged_categories["ai_generated"] = ai_messages
    merged_categories.update(message_pool.get("categories", {}))

    merged_pool = {"categories": merged_categories}
    total_static = sum(len(v) for v in message_pool.get("categories", {}).values())
    print(f"[AutoCommit] Pool sizes — mood: {len(mood_messages)} | "
          f"AI: {len(ai_messages)} | static: {total_static}")

    # ── Step 3: Pick unique messages with 180-day semantic check ─────────────
    messages = pick_unique_messages(count, history_msgs, merged_pool, threshold, profile)
    if not messages:
        print("[ERROR] No unique messages available. Exiting.", file=sys.stderr)
        sys.exit(1)

    # Generate commit times (profile-aware)
    times = generate_commit_times(len(messages), mode, profile)

    # Build commit plan
    commits = [
        {"time": t, "message": m}
        for t, m in zip(times, messages)
    ]

    plan = {
        "date": today_str(),
        "mode": mode,
        "mood": mood_result.get("mood", "normal"),
        "occasion": mood_result.get("occasion", ""),
        "commits": commits,
    }

    def _save_plan_and_history() -> None:
        """Callable passed to run_with_network_guard — saves plan + history atomically."""
        save_json("commit_plan.json", plan)

        # Update history with today's messages
        today = today_str()
        history.setdefault(today, [])
        for c in commits:
            history[today].append(c["message"])

        save_json(HISTORY_FILE, history)

        # Update streak stats
        updated_streak = update_streak_stats(history, streak_stats, len(commits))
        save_json(STREAK_FILE, updated_streak)

        print(f"[AutoCommit] Plan saved: {len(commits)} commits scheduled.")
        for c in commits:
            print(f"  [{c['time']} IST] {c['message']}")

    # ── Step 4: Execute via network guard (with retry logic) ─────────────────
    if NETWORK_GUARD_AVAILABLE:
        result = run_with_network_guard(_save_plan_and_history, max_retries=4)
        if result["success"]:
            print(f"[AutoCommit] ✅ Network guard: success after {result['attempts']} attempt(s).")
        else:
            print(f"[AutoCommit] ❌ Network guard: failed after {result['attempts']} attempt(s) "
                  f"— see streak_stats.json for the network_miss entry.")
            sys.exit(0)  # Exit cleanly — handle_network_failure() already ran
    else:
        # No network guard — run directly
        _save_plan_and_history()


if __name__ == "__main__":
    main()
