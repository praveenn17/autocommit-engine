#!/usr/bin/env python3
"""
AutoCommit Generator — Pattern Learner
========================================
Analyses the user's real GitHub commit history for the last 365 days,
extracts a personal behavioural fingerprint, and saves it as
pattern_profile.json to the archive repo via the GitHub Contents API.

Reads from environment:
  GH_USERNAME        — GitHub login (e.g. "praveenn17")
  ARCHIVE_REPO_PAT   — Personal Access Token with repo scope

Output: pattern_profile.json committed to commit-archive repo root.

Tech: Python 3.12 · requests · stdlib only (no PyGitHub / Octokit)
"""

import json
import os
import sys
import re
import base64
import datetime
import collections
from pathlib import Path

try:
    import requests
except ImportError:
    print("[PatternLearner] ERROR: 'requests' not installed. Run: pip install requests", file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
GITHUB_API     = "https://api.github.com"
SEARCH_COMMITS = GITHUB_API + "/search/commits"
PROFILE_FILE   = "pattern_profile.json"
LOOKBACK_DAYS  = 365

CONVENTIONAL_PREFIXES = [
    "feat", "fix", "refactor", "perf", "docs",
    "test", "chore", "style", "security", "build", "ci",
]

WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


# ---------------------------------------------------------------------------
# GitHub REST API helpers
# ---------------------------------------------------------------------------

def github_headers(pat: str) -> dict:
    return {
        "Authorization": f"token {pat}",
        "Accept":        "application/vnd.github.cloak-preview",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def fetch_commits_page(username: str, pat: str, page: int, since: str) -> dict:
    """Fetch one page of commits from GitHub Search API."""
    params = {
        "q":        f"author:{username} author-date:>={since}",
        "sort":     "author-date",
        "order":    "desc",
        "per_page": 100,
        "page":     page,
    }
    resp = requests.get(
        SEARCH_COMMITS,
        headers=github_headers(pat),
        params=params,
        timeout=30,
    )

    if resp.status_code == 422:
        print(f"[PatternLearner] Search API error 422: {resp.json().get('message', '')}",
              file=sys.stderr)
        return {"items": [], "total_count": 0}

    if resp.status_code == 403:
        remaining = resp.headers.get("X-RateLimit-Remaining", "?")
        reset_ts   = resp.headers.get("X-RateLimit-Reset", "?")
        print(f"[PatternLearner] Rate limited (403). Remaining={remaining}, Reset={reset_ts}",
              file=sys.stderr)
        return {"items": [], "total_count": 0}

    resp.raise_for_status()
    return resp.json()


def fetch_all_commits(username: str, pat: str) -> list[dict]:
    """
    Page through GitHub Search API to collect up to 1000 commits
    (API hard limit) from the last 365 days.
    """
    since = (datetime.date.today() - datetime.timedelta(days=LOOKBACK_DAYS)).isoformat()
    print(f"[PatternLearner] Fetching commits for '{username}' since {since}...")

    all_items = []
    page = 1

    while True:
        data = fetch_commits_page(username, pat, page, since)
        items = data.get("items", [])
        total = data.get("total_count", 0)

        if page == 1:
            print(f"[PatternLearner] Total commits found by API: {total} (fetching up to 1000)")

        all_items.extend(items)
        print(f"[PatternLearner]   Page {page}: +{len(items)} commits (total so far: {len(all_items)})")

        if len(items) < 100 or len(all_items) >= 1000:
            break

        page += 1

    print(f"[PatternLearner] Collected {len(all_items)} commits total.")
    return all_items


# ---------------------------------------------------------------------------
# Fingerprint extraction
# ---------------------------------------------------------------------------

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))


def parse_commit_dt(item: dict) -> datetime.datetime | None:
    """Extract author date from GitHub search result and convert to IST."""
    try:
        date_str = item["commit"]["author"]["date"]   # ISO 8601 UTC
        dt_utc = datetime.datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt_utc.astimezone(IST)
    except (KeyError, ValueError):
        return None


def extract_prefix(message: str) -> str | None:
    """Extract conventional commit prefix from a message like 'feat: ...'"""
    if not message:
        return None
    m = re.match(r"^([a-z]+)(?:\([^)]+\))?!", message.strip().lower())
    if m:
        return m.group(1)
    m = re.match(r"^([a-z]+)(?:\([^)]+\))?:", message.strip().lower())
    if m:
        prefix = m.group(1)
        if prefix in CONVENTIONAL_PREFIXES:
            return prefix
    return None


def build_fingerprint(commits: list[dict]) -> dict:
    """
    Build the complete behavioural fingerprint from raw commit items.
    Returns a dict that becomes pattern_profile.json.
    """
    if not commits:
        return {}

    # ── Raw counters ──────────────────────────────────────────────────────────
    hour_counts:    dict[int, int] = collections.defaultdict(int)   # 0..23
    weekday_counts: dict[int, int] = collections.defaultdict(int)   # 0=Mon..6=Sun
    prefix_counts:  dict[str, int] = collections.defaultdict(int)
    day_commit_map: dict[str, int] = collections.defaultdict(int)   # "YYYY-MM-DD" → count

    parsed = 0
    for item in commits:
        dt = parse_commit_dt(item)
        if dt is None:
            continue

        hour_counts[dt.hour]       += 1
        weekday_counts[dt.weekday()] += 1

        date_key = dt.strftime("%Y-%m-%d")
        day_commit_map[date_key] += 1

        msg = item.get("commit", {}).get("message", "")
        prefix = extract_prefix(msg)
        if prefix:
            prefix_counts[prefix] += 1

        parsed += 1

    print(f"[PatternLearner] Successfully parsed {parsed}/{len(commits)} commits.")

    # ── Derived statistics ────────────────────────────────────────────────────

    # commits_by_hour: fill all 24 hours (zero if no activity)
    commits_by_hour = {str(h): hour_counts.get(h, 0) for h in range(24)}

    # commits_by_weekday: fill all 7 days
    commits_by_weekday = {str(d): weekday_counts.get(d, 0) for d in range(7)}

    # active_hours: top 6 hours by commit count (must have > 0)
    active_hours = sorted(
        [h for h in range(24) if hour_counts.get(h, 0) > 0],
        key=lambda h: hour_counts.get(h, 0),
        reverse=True
    )[:6]

    # peak_weekday: 0=Mon..6=Sun
    peak_weekday = max(range(7), key=lambda d: weekday_counts.get(d, 0))

    # rest_day_ratio: fraction of days in the window with 0 commits
    total_window_days = LOOKBACK_DAYS
    active_days = len(day_commit_map)
    rest_day_ratio = round(max(0, total_window_days - active_days) / total_window_days, 3)

    # commits_per_active_day distribution
    if day_commit_map:
        commit_counts_list = list(day_commit_map.values())
        total_active = len(commit_counts_list)

        def _pct(n_list):
            return round(len(n_list) / total_active, 3) if total_active else 0.0

        counts_1  = [c for c in commit_counts_list if c == 1]
        counts_2  = [c for c in commit_counts_list if c == 2]
        counts_3  = [c for c in commit_counts_list if c == 3]
        counts_4p = [c for c in commit_counts_list if c >= 4]

        commits_per_active_day = {
            "1":   _pct(counts_1),
            "2":   _pct(counts_2),
            "3":   _pct(counts_3),
            "4+":  _pct(counts_4p),
        }
        avg_per_active_day = round(sum(commit_counts_list) / total_active, 2)
    else:
        commits_per_active_day = {"1": 0.5, "2": 0.3, "3": 0.15, "4+": 0.05}
        avg_per_active_day     = 1.5

    # prefix_ratios: normalise to fractions
    total_prefixed = sum(prefix_counts.values())
    if total_prefixed > 0:
        prefix_ratios = {
            k: round(v / total_prefixed, 3)
            for k, v in sorted(prefix_counts.items(), key=lambda x: -x[1])
        }
    else:
        # sensible defaults when no conventional commits found
        prefix_ratios = {"feat": 0.35, "fix": 0.30, "refactor": 0.15,
                         "chore": 0.10, "docs": 0.05, "perf": 0.05}

    return {
        "generated_at":         datetime.datetime.now(IST).isoformat(),
        "lookback_days":         LOOKBACK_DAYS,
        "commits_analysed":     parsed,
        "active_days":          active_days,
        "rest_day_ratio":       rest_day_ratio,
        "avg_per_active_day":   avg_per_active_day,
        "peak_weekday":         peak_weekday,
        "active_hours":         active_hours,
        "commits_by_hour":      commits_by_hour,
        "commits_by_weekday":   commits_by_weekday,
        "commits_per_active_day": commits_per_active_day,
        "prefix_ratios":        prefix_ratios,
    }


# ---------------------------------------------------------------------------
# GitHub Contents API — read/write file in archive repo
# ---------------------------------------------------------------------------

def get_file_sha(username: str, pat: str, repo: str, path: str) -> str | None:
    """Get the SHA of an existing file (needed for updates)."""
    url  = f"{GITHUB_API}/repos/{username}/{repo}/contents/{path}"
    resp = requests.get(url, headers=github_headers(pat), timeout=15)
    if resp.status_code == 200:
        return resp.json().get("sha")
    return None


def write_file_to_repo(
    username: str,
    pat: str,
    repo: str,
    path: str,
    content: str,
    message: str,
    sha: str | None = None,
) -> None:
    """Create or update a file in the archive repo via Contents API."""
    url  = f"{GITHUB_API}/repos/{username}/{repo}/contents/{path}"
    body: dict = {
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
    }
    if sha:
        body["sha"] = sha

    resp = requests.put(url, headers=github_headers(pat), json=body, timeout=30)
    resp.raise_for_status()


# ---------------------------------------------------------------------------
# Human-readable summary
# ---------------------------------------------------------------------------

def print_summary(username: str, fp: dict) -> None:
    peak_wd   = fp.get("peak_weekday", 1)
    peak_day  = WEEKDAY_NAMES[peak_wd]
    avg       = fp.get("avg_per_active_day", 0)
    rest_pct  = round(fp.get("rest_day_ratio", 0) * 100)

    # Top hour
    hours_raw = fp.get("commits_by_hour", {})
    if hours_raw:
        peak_hour = max(hours_raw, key=lambda h: hours_raw[h])
        ph = int(peak_hour)
        period = "am" if ph < 12 else "pm"
        peak_label = f"{ph % 12 or 12}{period}"
    else:
        peak_label = "unknown"

    # Top prefix
    prefix_ratios = fp.get("prefix_ratios", {})
    if prefix_ratios:
        top_prefix, top_ratio = next(iter(prefix_ratios.items()))
        prefix_label = f"{top_prefix}: {int(top_ratio * 100)}%"
    else:
        prefix_label = "unknown"

    active_hrs = fp.get("active_hours", [])
    active_hrs_str = ", ".join(
        f"{h % 12 or 12}{'am' if h < 12 else 'pm'}" for h in active_hrs[:3]
    )

    print("")
    print("╔══════════════════════════════════════════════════════════╗")
    print("║           Pattern Learner — Profile Summary              ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print("")
    print(f"  {username}'s commit pattern ({fp.get('lookback_days', 365)} days):")
    print(f"  ├─ Most active day:    {peak_day}")
    print(f"  ├─ Peak commit hour:   {peak_label} IST")
    print(f"  ├─ Top active hours:   {active_hrs_str}")
    print(f"  ├─ Top prefix:         {prefix_label}")
    print(f"  ├─ Avg commits/day:    {avg}× on active days")
    print(f"  ├─ Rest day ratio:     {rest_pct}% of days have no commits")
    print(f"  └─ Commits analysed:   {fp.get('commits_analysed', 0)}")
    print("")
    print(f"  ✓ pattern_profile.json saved to commit-archive")
    print("")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("[PatternLearner] Starting pattern analysis...")

    username = os.environ.get("GH_USERNAME", "").strip()
    pat      = os.environ.get("ARCHIVE_REPO_PAT", "").strip()
    repo     = os.environ.get("ARCHIVE_REPO", "commit-archive").strip()

    if not username:
        print("[PatternLearner] ERROR: GH_USERNAME environment variable not set.", file=sys.stderr)
        sys.exit(1)
    if not pat:
        print("[PatternLearner] ERROR: ARCHIVE_REPO_PAT environment variable not set.", file=sys.stderr)
        sys.exit(1)

    print(f"[PatternLearner] Analysing: {username} → archive: {username}/{repo}")

    # 1. Fetch commits from GitHub Search API
    commits = fetch_all_commits(username, pat)
    if not commits:
        print("[PatternLearner] No commits found — writing empty profile with defaults.", file=sys.stderr)

    # 2. Extract fingerprint
    fingerprint = build_fingerprint(commits)
    if not fingerprint:
        # Write minimal defaults so the engine never breaks
        fingerprint = {
            "generated_at": datetime.datetime.now(IST).isoformat(),
            "lookback_days": LOOKBACK_DAYS,
            "commits_analysed": 0,
            "active_days": 0,
            "rest_day_ratio": 0.15,
            "avg_per_active_day": 2.0,
            "peak_weekday": 1,
            "active_hours": [10, 11, 14, 15, 20, 21],
            "commits_by_hour":    {str(h): 0 for h in range(24)},
            "commits_by_weekday": {str(d): 0 for d in range(7)},
            "commits_per_active_day": {"1": 0.4, "2": 0.35, "3": 0.20, "4+": 0.05},
            "prefix_ratios": {"feat": 0.35, "fix": 0.30, "refactor": 0.15,
                               "chore": 0.10, "docs": 0.05, "perf": 0.05},
        }

    content = json.dumps(fingerprint, indent=2, ensure_ascii=False)

    # 3. Write to archive repo via Contents API
    print(f"[PatternLearner] Writing {PROFILE_FILE} to {username}/{repo}...")
    try:
        existing_sha = get_file_sha(username, pat, repo, PROFILE_FILE)
        write_file_to_repo(
            username=username,
            pat=pat,
            repo=repo,
            path=PROFILE_FILE,
            content=content,
            message="chore: update pattern profile from learner [skip ci]",
            sha=existing_sha,
        )
        print(f"[PatternLearner] ✓ {PROFILE_FILE} written to {username}/{repo}")
    except Exception as e:
        print(f"[PatternLearner] WARNING: Could not write to archive repo: {e}", file=sys.stderr)
        # Still save locally so it can be used in the same run
        Path(PROFILE_FILE).write_text(content, encoding="utf-8")
        print(f"[PatternLearner] ✓ {PROFILE_FILE} saved locally as fallback.")

    # 4. Print human-readable summary
    print_summary(username, fingerprint)


if __name__ == "__main__":
    main()
