#!/usr/bin/env python3
"""
AutoCommit Generator — Setup Wizard
====================================
One-time setup script triggered via workflow_dispatch.
Accepts INTENSITY (HIGH / MEDIUM / LOW) and saves to user_preferences.json
in the commit-archive via GitHub Contents API.

Tech: Python 3.12 · requests
"""

import json
import os
import sys
import base64
import datetime

try:
    import requests
except ImportError:
    print("[ERROR] 'requests' not installed.", file=sys.stderr)
    sys.exit(1)

GITHUB_API = "https://api.github.com"
PREFS_FILE = "user_preferences.json"
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

DEFAULT_TARGETS = {
    "HIGH": {"min": 3, "max": 6, "burst_chance": 0.3},
    "MEDIUM": {"min": 1, "max": 3, "burst_chance": 0.15},
    "LOW": {"min": 0, "max": 2, "burst_chance": 0.05}
}

def github_headers(pat: str) -> dict:
    return {
        "Authorization": f"token {pat}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

def get_file_sha(username: str, pat: str, repo: str, path: str) -> str | None:
    url = f"{GITHUB_API}/repos/{username}/{repo}/contents/{path}"
    resp = requests.get(url, headers=github_headers(pat), timeout=15)
    if resp.status_code == 200:
        return resp.json().get("sha")
    return None

def write_file_to_repo(username: str, pat: str, repo: str, path: str, content: str, message: str, sha: str | None = None) -> None:
    url = f"{GITHUB_API}/repos/{username}/{repo}/contents/{path}"
    body = {
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
    }
    if sha:
        body["sha"] = sha
    resp = requests.put(url, headers=github_headers(pat), json=body, timeout=30)
    resp.raise_for_status()

def send_telegram_message(token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        requests.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}, timeout=15)
    except Exception as e:
        print(f"[Telegram] Warning: Could not send message: {e}", file=sys.stderr)

def main():
    print("🚀 AutoCommit Generator — Setup Wizard")
    
    intensity = os.environ.get("SETUP_INTENSITY", "").strip().upper()
    username = os.environ.get("GH_USERNAME", "").strip()
    pat = os.environ.get("ARCHIVE_REPO_PAT", "").strip()
    archive_repo = os.environ.get("ARCHIVE_REPO", "commit-archive").strip()
    tg_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    tg_chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

    if not intensity or intensity not in ["HIGH", "MEDIUM", "LOW"]:
        print(f"[ERROR] Invalid INTENSITY: '{intensity}'. Must be HIGH, MEDIUM, or LOW.", file=sys.stderr)
        sys.exit(1)

    if not username or not pat:
        print("[ERROR] GH_USERNAME or ARCHIVE_REPO_PAT missing.", file=sys.stderr)
        sys.exit(1)

    # 1. Prepare JSON
    prefs = {
        "intensity": intensity,
        "set_at": datetime.datetime.now(IST).isoformat(),
        "daily_targets": DEFAULT_TARGETS
    }
    content = json.dumps(prefs, indent=2, ensure_ascii=False)

    # 2. Write to GitHub
    print(f"📦 Saving {intensity} intensity to {PREFS_FILE} in {username}/{archive_repo}...")
    try:
        sha = get_file_sha(username, pat, archive_repo, PREFS_FILE)
        write_file_to_repo(username, pat, archive_repo, PREFS_FILE, content, "chore: update user intensity preferences", sha)
        print("✅ Successfully updated user_preferences.json")
    except Exception as e:
        print(f"[ERROR] Failed to save to archive repo: {e}", file=sys.stderr)
        sys.exit(1)

    # 3. Send Telegram Notification
    if tg_token and tg_chat:
        msg = f"✅ *AutoCommit setup complete!*\n\nIntensity set to *{intensity}*.\nYou'll receive exam day prompts on the 1st of each month."
        send_telegram_message(tg_token, tg_chat, msg)
        print("✅ Telegram confirmation sent.")

if __name__ == "__main__":
    main()
