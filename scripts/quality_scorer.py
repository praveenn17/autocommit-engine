#!/usr/bin/env python3
"""
AutoCommit Generator — Quality Scorer
=======================================
Analyses the last 30 days of commit history and computes a naturalness score
from 0–100 across 5 weighted signals (PRD Section 6.3).

Signals and weights:
  1. Commit time variance      25% — penalise if commits cluster in same 30-min window
  2. Daily count variance      25% — penalise if exactly N commits every day
  3. Rest day presence         20% — penalise if zero rest days in 30-day period
  4. Message category diversity 15% — penalise if same category used 3+ consecutive days
  5. Weekend reduction          15% — penalise if weekend rate ≈ weekday rate

Score ≥ 75: Safe (green)
Score 60–74: Watch out (amber)
Score < 60: Robotic pattern detected (red)

Output: quality_score.json with score, signal breakdown, and status.
"""

import json
import datetime
import re
import sys
from pathlib import Path
from collections import defaultdict, Counter
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
IST_OFFSET      = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
HISTORY_FILE    = "commit_history.json"
COMMIT_PLAN     = "commit_plan.json"
QUALITY_OUT     = "quality_score.json"
STREAK_FILE     = "streak_stats.json"

ANALYSIS_DAYS   = 30
WARN_THRESHOLD  = 60
SAFE_THRESHOLD  = 75

# Signal weights (must sum to 100)
W_TIME_VAR   = 25
W_COUNT_VAR  = 25
W_REST_DAY   = 20
W_MSG_DIV    = 15
W_WEEKEND    = 15

# Category prefixes for detection
CATEGORY_PREFIXES = {
    "refactor": "refactor",
    "feat":     "feat",
    "fix":      "fix",
    "perf":     "perf",
    "docs":     "docs",
    "test":     "test",
    "style":    "style",
    "security": "security",
    "chore":    "chore",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def now_ist() -> datetime.datetime:
    return datetime.datetime.now(IST_OFFSET)


def load_json(path: str) -> dict:
    p = Path(path)
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_json(path: str, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def detect_category(message: str) -> str:
    """Extract commit category from conventional commit prefix."""
    lower = message.lower().strip()
    for cat, prefix in CATEGORY_PREFIXES.items():
        if lower.startswith(prefix + ":") or lower.startswith(prefix + "("):
            return cat
    return "other"


def get_last_n_days(history: dict, n: int) -> dict[str, list[str]]:
    """Return history entries for last n days."""
    today = now_ist().date()
    result = {}
    for i in range(n):
        date = (today - datetime.timedelta(days=i)).isoformat()
        result[date] = history.get(date, [])
    return result


# ---------------------------------------------------------------------------
# Signal 1: Commit Time Variance (25%)
# PRD: Penalty if all commits fall within same 30-min window for 5+ days
# ---------------------------------------------------------------------------

def score_time_variance(recent_history: dict) -> tuple[int, str]:
    """
    Analyse commit timestamps from commit_plan.json history.
    Since we don't store exact times in commit_history.json, we compute
    variance from the mode distribution pattern.
    
    Heuristic: if >60% of active days had single-burst commits (mode=Quiet),
    the time variance is too low.
    """
    # Approximate: count active days and their commit counts
    active_days = {d: msgs for d, msgs in recent_history.items() if msgs}
    if len(active_days) < 5:
        return W_TIME_VAR, "Insufficient data — full score awarded"

    # Count days with exactly 1 commit (minimal variance signal)
    single_commit_days = sum(1 for msgs in active_days.values() if len(msgs) == 1)
    ratio = single_commit_days / len(active_days)

    if ratio > 0.75:
        deduction = int(W_TIME_VAR * 0.7)
        return W_TIME_VAR - deduction, f"High single-commit ratio ({ratio:.0%}) — low time variance"
    elif ratio > 0.5:
        deduction = int(W_TIME_VAR * 0.3)
        return W_TIME_VAR - deduction, f"Moderate single-commit ratio ({ratio:.0%})"
    else:
        return W_TIME_VAR, f"Good time variance (single-commit ratio: {ratio:.0%})"


# ---------------------------------------------------------------------------
# Signal 2: Daily Count Variance (25%)
# PRD: Penalty if exactly N commits every single day for 7+ days
# ---------------------------------------------------------------------------

def score_count_variance(recent_history: dict) -> tuple[int, str]:
    """Check for suspiciously uniform commit counts over 7+ consecutive days."""
    active_days = sorted(
        [(d, len(msgs)) for d, msgs in recent_history.items() if msgs],
        key=lambda x: x[0]
    )
    if len(active_days) < 7:
        return W_COUNT_VAR, "Insufficient data — full score awarded"

    counts = [c for _, c in active_days]
    count_freq = Counter(counts)
    most_common_count, freq = count_freq.most_common(1)[0]

    # Check for 7+ consecutive days with same count
    max_consecutive = 0
    current_consecutive = 0
    for _, count in active_days:
        if count == most_common_count:
            current_consecutive += 1
            max_consecutive = max(max_consecutive, current_consecutive)
        else:
            current_consecutive = 0

    if max_consecutive >= 10:
        return 0, f"CRITICAL: {max_consecutive} consecutive days with exactly {most_common_count} commits"
    elif max_consecutive >= 7:
        deduction = int(W_COUNT_VAR * 0.8)
        return W_COUNT_VAR - deduction, f"Warning: {max_consecutive} consecutive days with {most_common_count} commits"
    elif max_consecutive >= 5:
        deduction = int(W_COUNT_VAR * 0.4)
        return W_COUNT_VAR - deduction, f"Slight pattern: {max_consecutive} days with {most_common_count} commits"
    else:
        return W_COUNT_VAR, f"Good variance (max streak of same count: {max_consecutive} days)"


# ---------------------------------------------------------------------------
# Signal 3: Rest Day Presence (20%)
# PRD: Penalty if zero rest days in any 30-day period
# ---------------------------------------------------------------------------

def score_rest_day_presence(recent_history: dict) -> tuple[int, str]:
    """Check that rest days exist in the 30-day window."""
    rest_days = sum(1 for msgs in recent_history.values() if not msgs)
    total_days = len(recent_history)
    expected_rest = total_days * 0.117  # PRD: ~11.7% rest days

    if rest_days == 0:
        return 0, f"CRITICAL: Zero rest days in {total_days}-day period"
    elif rest_days < max(1, expected_rest * 0.5):
        deduction = int(W_REST_DAY * 0.6)
        return W_REST_DAY - deduction, f"Too few rest days ({rest_days}/{total_days}) — expected ~{expected_rest:.1f}"
    elif rest_days > expected_rest * 2:
        deduction = int(W_REST_DAY * 0.2)
        return W_REST_DAY - deduction, f"Slightly too many rest days ({rest_days}/{total_days})"
    else:
        return W_REST_DAY, f"Healthy rest days ({rest_days}/{total_days} = {rest_days/total_days:.0%})"


# ---------------------------------------------------------------------------
# Signal 4: Message Category Diversity (15%)
# PRD: Penalty if same category used for 3+ consecutive days
# ---------------------------------------------------------------------------

def score_message_diversity(recent_history: dict) -> tuple[int, str]:
    """Check that commit categories rotate and don't repeat 3+ days in a row."""
    sorted_days = sorted(
        [(d, msgs) for d, msgs in recent_history.items() if msgs],
        key=lambda x: x[0]
    )
    if len(sorted_days) < 3:
        return W_MSG_DIV, "Insufficient data"

    # Get dominant category per day
    day_categories = []
    for _, msgs in sorted_days:
        cats = [detect_category(m) for m in msgs]
        dominant = Counter(cats).most_common(1)[0][0]
        day_categories.append(dominant)

    # Find max consecutive same-category streak
    max_streak = 1
    current_streak = 1
    for i in range(1, len(day_categories)):
        if day_categories[i] == day_categories[i - 1]:
            current_streak += 1
            max_streak = max(max_streak, current_streak)
        else:
            current_streak = 1

    if max_streak >= 5:
        return 0, f"CRITICAL: Same category for {max_streak} consecutive days"
    elif max_streak >= 3:
        deduction = int(W_MSG_DIV * 0.7)
        return W_MSG_DIV - deduction, f"Category repeated {max_streak} consecutive days"
    elif max_streak >= 2:
        deduction = int(W_MSG_DIV * 0.2)
        return W_MSG_DIV - deduction, f"Slight repetition ({max_streak} days same category)"
    else:
        return W_MSG_DIV, f"Excellent category diversity (max streak: {max_streak})"


# ---------------------------------------------------------------------------
# Signal 5: Weekend Reduction (15%)
# PRD: Penalty if weekend commit rate ≈ weekday rate
# ---------------------------------------------------------------------------

def score_weekend_reduction(recent_history: dict) -> tuple[int, str]:
    """Check that weekends have fewer commits than weekdays."""
    weekday_counts = []
    weekend_counts = []

    for date_str, msgs in recent_history.items():
        try:
            d = datetime.date.fromisoformat(date_str)
        except ValueError:
            continue
        count = len(msgs)
        if d.weekday() < 5:  # Mon-Fri
            weekday_counts.append(count)
        else:  # Sat-Sun
            weekend_counts.append(count)

    if not weekday_counts or not weekend_counts:
        return W_WEEKEND, "Insufficient weekend/weekday data"

    avg_weekday = sum(weekday_counts) / len(weekday_counts)
    avg_weekend = sum(weekend_counts) / len(weekend_counts)

    if avg_weekday == 0:
        return W_WEEKEND, "No weekday commits to compare"

    ratio = avg_weekend / avg_weekday  # Should be < 0.8 for natural pattern

    if ratio > 0.95:
        deduction = int(W_WEEKEND * 0.9)
        return W_WEEKEND - deduction, f"Weekend rate = weekday rate ({ratio:.0%}) — looks robotic"
    elif ratio > 0.8:
        deduction = int(W_WEEKEND * 0.5)
        return W_WEEKEND - deduction, f"Weekend barely reduced ({ratio:.0%} of weekday rate)"
    else:
        return W_WEEKEND, f"Good weekend reduction ({ratio:.0%} of weekday rate)"


# ---------------------------------------------------------------------------
# Main Quality Scorer
# ---------------------------------------------------------------------------

def compute_quality_score() -> dict:
    """Run all 5 signals and compute composite quality score."""
    history = load_json(HISTORY_FILE)
    recent = get_last_n_days(history, ANALYSIS_DAYS)

    # Run signals
    s1_score, s1_note = score_time_variance(recent)
    s2_score, s2_note = score_count_variance(recent)
    s3_score, s3_note = score_rest_day_presence(recent)
    s4_score, s4_note = score_message_diversity(recent)
    s5_score, s5_note = score_weekend_reduction(recent)

    total = s1_score + s2_score + s3_score + s4_score + s5_score

    if total >= SAFE_THRESHOLD:
        status = "safe"
        status_label = "Safe"
        status_emoji = "green"
    elif total >= WARN_THRESHOLD:
        status = "warning"
        status_label = "Watch Out"
        status_emoji = "amber"
    else:
        status = "danger"
        status_label = "Robotic Pattern"
        status_emoji = "red"

    result = {
        "score": total,
        "max_score": 100,
        "status": status,
        "status_label": status_label,
        "computed_at": now_ist().isoformat(),
        "analysis_days": ANALYSIS_DAYS,
        "signals": {
            "time_variance": {
                "score": s1_score,
                "max": W_TIME_VAR,
                "weight": f"{W_TIME_VAR}%",
                "note": s1_note,
                "passed": s1_score >= W_TIME_VAR * 0.5,
            },
            "count_variance": {
                "score": s2_score,
                "max": W_COUNT_VAR,
                "weight": f"{W_COUNT_VAR}%",
                "note": s2_note,
                "passed": s2_score >= W_COUNT_VAR * 0.5,
            },
            "rest_day_presence": {
                "score": s3_score,
                "max": W_REST_DAY,
                "weight": f"{W_REST_DAY}%",
                "note": s3_note,
                "passed": s3_score >= W_REST_DAY * 0.5,
            },
            "message_diversity": {
                "score": s4_score,
                "max": W_MSG_DIV,
                "weight": f"{W_MSG_DIV}%",
                "note": s4_note,
                "passed": s4_score >= W_MSG_DIV * 0.5,
            },
            "weekend_reduction": {
                "score": s5_score,
                "max": W_WEEKEND,
                "weight": f"{W_WEEKEND}%",
                "note": s5_note,
                "passed": s5_score >= W_WEEKEND * 0.5,
            },
        },
    }

    return result


def main() -> None:
    print("[QualityScorer] Analysing commit pattern naturalness...")
    result = compute_quality_score()

    save_json(QUALITY_OUT, result)
    print(f"[QualityScorer] Score: {result['score']}/100 — {result['status_label']}")
    for sig_name, sig_data in result["signals"].items():
        icon = "✓" if sig_data["passed"] else "✗"
        print(f"  {icon} {sig_name}: {sig_data['score']}/{sig_data['max']} — {sig_data['note']}")


if __name__ == "__main__":
    main()
