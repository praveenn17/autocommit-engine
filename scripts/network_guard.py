#!/usr/bin/env python3
"""
AutoCommit Generator — Network Guard
======================================
Provides VPN-aware scheduling with exponential backoff retry logic.
Wraps the commit execution callable so the workflow never crashes on
network issues — instead it logs a miss, notifies via Telegram, and
exits cleanly with code 0.

Requires: requests (already in requirements.txt)
All times: IST (UTC+5:30)
"""

import json
import os
import sys
import datetime
import time
import base64
from pathlib import Path

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    print("[NetworkGuard] ⚠️  requests not installed — network guard disabled.", file=sys.stderr)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
GITHUB_API      = "https://api.github.com"
STREAK_FILE     = "streak_stats.json"
PENDING_NOTIF   = "pending_notifications.json"
SLOW_THRESHOLD_MS = 2000   # ms above which connection is considered slow
CONNECT_TIMEOUT   = 10     # seconds

# Backoff schedule in minutes (attempt 0 → 4)
BACKOFF_MINUTES = [5, 15, 30, 60]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_ist() -> datetime.datetime:
    return datetime.datetime.now(IST)


def _load_json(path: str) -> dict:
    p = Path(path)
    if p.exists():
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_json(path: str, data: dict) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[NetworkGuard] ⚠️  Could not save {path}: {e}", file=sys.stderr)


def _push_to_github(filename: str, data: dict) -> bool:
    """Push a JSON file to the commit-archive repo via GitHub Contents API."""
    try:
        username = os.environ.get("GH_USERNAME", "").strip()
        pat      = os.environ.get("ARCHIVE_REPO_PAT", "").strip()
        repo     = os.environ.get("ARCHIVE_REPO", "commit-archive").strip()

        if not username or not pat:
            print("[NetworkGuard] ⚠️  GH_USERNAME or ARCHIVE_REPO_PAT not set — skip push.", file=sys.stderr)
            return False

        url = f"{GITHUB_API}/repos/{username}/{repo}/contents/{filename}"
        headers = {
            "Authorization": f"token {pat}",
            "Accept": "application/vnd.github.v3+json",
        }

        # Fetch current SHA (file may not exist yet)
        sha = None
        resp = requests.get(url, headers=headers, timeout=CONNECT_TIMEOUT)
        if resp.ok:
            sha = resp.json().get("sha")

        body: dict = {
            "message": f"chore: network_guard update {filename} [skip ci]",
            "content": base64.b64encode(
                json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
            ).decode("utf-8"),
        }
        if sha:
            body["sha"] = sha

        put_resp = requests.put(url, headers=headers, json=body, timeout=CONNECT_TIMEOUT)
        if put_resp.ok:
            print(f"[NetworkGuard] ✅ Pushed {filename} to commit-archive.")
            return True
        else:
            print(f"[NetworkGuard] ⚠️  Push failed ({put_resp.status_code}): {put_resp.text[:200]}", file=sys.stderr)
            return False
    except Exception as e:
        print(f"[NetworkGuard] ⚠️  Push exception for {filename}: {e}", file=sys.stderr)
        return False


# ---------------------------------------------------------------------------
# Function 1: check_github_connectivity
# ---------------------------------------------------------------------------

def check_github_connectivity() -> dict:
    """
    Ping https://api.github.com and return connectivity status.

    Returns:
        {
            "reachable": bool,
            "response_ms": int,
            "slow": bool,          # True if response > 2000ms
            "rate_limited": bool,  # True if 429 returned
            "status_code": int
        }
    """
    default = {
        "reachable": False, "response_ms": 0,
        "slow": False, "rate_limited": False, "status_code": 0
    }

    if not REQUESTS_AVAILABLE:
        return default

    try:
        t0 = time.monotonic()
        resp = requests.get(
            GITHUB_API,
            timeout=CONNECT_TIMEOUT,
            headers={"Accept": "application/vnd.github.v3+json"},
        )
        ms = int((time.monotonic() - t0) * 1000)
        return {
            "reachable":    resp.status_code not in (0, 429),
            "response_ms":  ms,
            "slow":         ms > SLOW_THRESHOLD_MS,
            "rate_limited": resp.status_code == 429,
            "status_code":  resp.status_code,
        }
    except Exception as e:
        print(f"[NetworkGuard] 🌐 Connectivity check exception: {e}", file=sys.stderr)
        return default


# ---------------------------------------------------------------------------
# Function 2: wait_with_backoff
# ---------------------------------------------------------------------------

def wait_with_backoff(attempt: int) -> None:
    """
    Sleep for BACKOFF_MINUTES[attempt] minutes with per-minute countdown logs.
    attempt is 0-indexed. Clamps to last entry if attempt >= len(BACKOFF_MINUTES).
    """
    idx = min(attempt, len(BACKOFF_MINUTES) - 1)
    total_minutes = BACKOFF_MINUTES[idx]
    total_attempts = len(BACKOFF_MINUTES)

    print(f"[NetworkGuard] ⏳ Retry attempt {attempt + 1}/{total_attempts} — "
          f"waiting {total_minutes}min before next check.")

    for minute_remaining in range(total_minutes, 0, -1):
        print(f"[NetworkGuard] ⏳ Retry attempt {attempt + 1}/{total_attempts} — "
              f"waiting {total_minutes}min. Next check in {minute_remaining} min...")
        sys.stdout.flush()
        time.sleep(60)

    print(f"[NetworkGuard] 🔄 Backoff complete — checking connectivity again.")


# ---------------------------------------------------------------------------
# Function 3: run_with_network_guard
# ---------------------------------------------------------------------------

def run_with_network_guard(commit_function, max_retries: int = 4) -> dict:
    """
    Wraps commit_function() with connectivity checks and exponential backoff.

    Args:
        commit_function: A zero-argument callable that performs the actual commits.
        max_retries: How many attempts to make before giving up.

    Returns:
        {"success": bool, "attempts": int, "reason": str | None}
    """
    for attempt in range(max_retries):
        status = check_github_connectivity()

        print(f"[NetworkGuard] 🌐 Connectivity check — "
              f"reachable={status['reachable']}, "
              f"response_ms={status['response_ms']}, "
              f"slow={status['slow']}, "
              f"rate_limited={status['rate_limited']}")

        if status["rate_limited"]:
            print(f"[NetworkGuard] 🚫 Rate limited by GitHub. "
                  f"Attempt {attempt + 1}/{max_retries}. Waiting before retry...")
            wait_with_backoff(attempt)
            continue

        if not status["reachable"] or status["slow"]:
            print(f"[NetworkGuard] 🌐 GitHub unreachable/slow ({status['response_ms']}ms). "
                  f"Attempt {attempt + 1}/{max_retries}...")
            wait_with_backoff(attempt)
            continue

        # Network is good — run the actual commits
        print(f"[NetworkGuard] ✅ Network OK ({status['response_ms']}ms). "
              f"Proceeding with commit function (attempt {attempt + 1}/{max_retries}).")
        try:
            commit_function()
            return {"success": True, "attempts": attempt + 1, "reason": None}
        except Exception as e:
            print(f"[NetworkGuard] ❌ commit_function raised an exception: {e}", file=sys.stderr)
            return {"success": False, "attempts": attempt + 1, "reason": str(e)}

    # All retries exhausted
    print(f"[NetworkGuard] ❌ All {max_retries} retry attempts exhausted.")
    handle_network_failure(max_retries)
    return {"success": False, "attempts": max_retries, "reason": "network_failure"}


# ---------------------------------------------------------------------------
# Function 4: handle_network_failure
# ---------------------------------------------------------------------------

def handle_network_failure(attempts: int = 4) -> None:
    """
    Log a network_miss entry to streak_stats.json in commit-archive and
    trigger Telegram notifications.
    """
    print("[NetworkGuard] ❌ All retry attempts exhausted. Logging network miss.")

    now         = _now_ist()
    today_str   = now.date().isoformat()
    expires_str = (now + datetime.timedelta(hours=24)).isoformat()

    miss_entry = {
        "date":             today_str,
        "attempts":         attempts,
        "logged_at":        now.isoformat(),
        "warning_expires":  expires_str,
        "notified":         False,
    }

    # Read existing streak stats (from local working dir — archive checkout)
    streak = _load_json(STREAK_FILE)
    misses = streak.get("network_misses", [])
    misses.append(miss_entry)
    # Keep only the most recent 30
    misses = misses[-30:]
    streak["network_misses"] = misses

    # Save locally first
    _save_json(STREAK_FILE, streak)
    print(f"[NetworkGuard] 📝 Network miss logged locally to {STREAK_FILE}.")

    # Push to commit-archive via API
    _push_to_github(STREAK_FILE, streak)

    # Now trigger Telegram notifications
    schedule_telegram_notifications(today_str, attempts, now)


# ---------------------------------------------------------------------------
# Function 5: schedule_telegram_notifications
# ---------------------------------------------------------------------------

def schedule_telegram_notifications(
    miss_date: str,
    attempts: int,
    now: datetime.datetime,
) -> None:
    """
    Write pending_notifications.json and send the FIRST Telegram alert immediately.
    Subsequent alerts (2/3 and 3/3) are handled by the network_miss_followup workflow job.
    """
    notify_times = [
        now.isoformat(),                                      # immediately
        (now + datetime.timedelta(hours=8)).isoformat(),      # 8h later
        (now + datetime.timedelta(hours=16)).isoformat(),     # 16h later
    ]

    pending = {
        "active":               True,
        "miss_date":            miss_date,
        "notify_times":         notify_times,
        "notifications_sent":   0,
        "attempts":             attempts,
    }

    _save_json(PENDING_NOTIF, pending)
    _push_to_github(PENDING_NOTIF, pending)
    print("[NetworkGuard] 📋 pending_notifications.json written and pushed.")

    # Send first notification immediately
    try:
        from telegram_notifier import send_network_miss_alert
        send_network_miss_alert(miss_date, attempts)
        # Update sent count
        pending["notifications_sent"] = 1
        _save_json(PENDING_NOTIF, pending)
        _push_to_github(PENDING_NOTIF, pending)
    except Exception as e:
        print(f"[NetworkGuard] ⚠️  Could not send immediate Telegram alert: {e}", file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI entry point (for manual testing)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Network Guard — VPN-aware scheduling")
    parser.add_argument("--check",   action="store_true", help="Check GitHub connectivity only")
    parser.add_argument("--dry-run", action="store_true", help="Simulate a network failure flow")
    args = parser.parse_args()

    if args.check:
        s = check_github_connectivity()
        print(json.dumps(s, indent=2))
    elif args.dry_run:
        print("[NetworkGuard] DRY RUN — simulating network failure handling")
        handle_network_failure(attempts=4)
    else:
        parser.print_help()
