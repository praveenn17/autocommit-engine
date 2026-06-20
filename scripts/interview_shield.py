#!/usr/bin/env python3
"""
AutoCommit Generator — Interview Shield
=========================================
Backs up and destroys the autocommit-engine files before an interview,
and coordinates the restore flow via interviews.json in commit-archive.

Uses only: requests, datetime, json, uuid (stdlib)
All times: IST (UTC+5:30)
Every external call wrapped in try/except — never crashes the workflow.
"""

import json
import os
import sys
import uuid
import datetime
import base64
from pathlib import Path

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    print("[Shield] ❌ requests not installed.", file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
IST         = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
GITHUB_API  = "https://api.github.com"
INTERVIEWS_FILE = "interviews.json"
TG_API_BASE = "https://api.telegram.org/bot{token}/{method}"

# Files to back up from engine repo (relative paths)
ENGINE_WORKFLOW = ".github/workflows/autocommit.yml"
SCRIPTS_DIR     = "scripts"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_ist() -> datetime.datetime:
    return datetime.datetime.now(IST)


def _today_str() -> str:
    return _now_ist().date().isoformat()


def _gh_headers(pat: str) -> dict:
    return {
        "Authorization": f"token {pat}",
        "Accept":        "application/vnd.github.v3+json",
        "Content-Type":  "application/json",
    }


def _get_file(pat: str, repo: str, path: str) -> tuple[str | None, str | None]:
    """Return (base64_content, sha) or (None, None) on failure."""
    try:
        url  = f"{GITHUB_API}/repos/{repo}/contents/{path}"
        resp = requests.get(url, headers=_gh_headers(pat), timeout=15)
        if resp.status_code == 404:
            return None, None
        resp.raise_for_status()
        data = resp.json()
        return data.get("content", ""), data.get("sha")
    except Exception as e:
        print(f"[Shield] ⚠️  GET {path} failed: {e}", file=sys.stderr)
        return None, None


def _put_file(pat: str, repo: str, path: str, content_b64: str,
              sha: str | None, message: str) -> bool:
    """Create or update a file in a GitHub repo. content_b64 must be base64-encoded."""
    try:
        url  = f"{GITHUB_API}/repos/{repo}/contents/{path}"
        body: dict = {"message": message, "content": content_b64}
        if sha:
            body["sha"] = sha
        resp = requests.put(url, headers=_gh_headers(pat), json=body, timeout=15)
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"[Shield] ⚠️  PUT {path} failed: {e}", file=sys.stderr)
        return False


def _delete_file(pat: str, repo: str, path: str, sha: str, message: str) -> bool:
    """Delete a file from a GitHub repo by sha."""
    try:
        url  = f"{GITHUB_API}/repos/{repo}/contents/{path}"
        body = {"message": message, "sha": sha}
        resp = requests.delete(url, headers=_gh_headers(pat), json=body, timeout=15)
        if resp.status_code == 404:
            print(f"[Shield] ⚠️  {path} already missing — skipping delete.", file=sys.stderr)
            return True   # idempotent
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"[Shield] ⚠️  DELETE {path} failed: {e}", file=sys.stderr)
        return False


def _list_dir(pat: str, repo: str, path: str) -> list[dict]:
    """Return list of file objects [{name, path, sha, ...}] or [] on failure."""
    try:
        url  = f"{GITHUB_API}/repos/{repo}/contents/{path}"
        resp = requests.get(url, headers=_gh_headers(pat), timeout=15)
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        return [item for item in resp.json() if item.get("type") == "file"]
    except Exception as e:
        print(f"[Shield] ⚠️  LIST {path} failed: {e}", file=sys.stderr)
        return []


def _send_telegram(token: str, chat_id: str, message: str) -> bool:
    try:
        url  = TG_API_BASE.format(token=token, method="sendMessage")
        resp = requests.post(url, json={
            "chat_id": chat_id, "text": message, "parse_mode": "Markdown"
        }, timeout=15)
        return resp.ok
    except Exception as e:
        print(f"[Shield] ⚠️  Telegram send failed: {e}", file=sys.stderr)
        return False


def _load_interviews(pat: str, archive_repo: str) -> tuple[dict, str | None]:
    """Read interviews.json from commit-archive. Returns (data, sha)."""
    content_b64, sha = _get_file(pat, archive_repo, INTERVIEWS_FILE)
    if content_b64 is None:
        return {"interviews": [], "system_status": "active"}, None
    try:
        decoded = base64.b64decode(content_b64.replace("\n", "")).decode("utf-8")
        return json.loads(decoded), sha
    except Exception as e:
        print(f"[Shield] ⚠️  Could not decode interviews.json: {e}", file=sys.stderr)
        return {"interviews": [], "system_status": "active"}, sha


def _save_interviews(pat: str, archive_repo: str,
                     data: dict, sha: str | None) -> bool:
    encoded = base64.b64encode(
        json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
    ).decode("utf-8")
    return _put_file(pat, archive_repo, INTERVIEWS_FILE, encoded, sha,
                     "chore: update interviews.json [skip ci]")


# ---------------------------------------------------------------------------
# Function 1: backup_engine_files
# ---------------------------------------------------------------------------

def backup_engine_files(pat: str, engine_repo: str, archive_repo: str) -> bool:
    """
    Read all critical engine files and write them to commit-archive/backup/.
    Maintains folder structure (e.g. backup/scripts/pattern_engine.py).

    Returns True if all files were backed up successfully.
    """
    print("[Shield] 📦 Starting engine backup...")
    success = True

    # 1. Backup the workflow file
    content, sha = _get_file(pat, engine_repo, ENGINE_WORKFLOW)
    if content:
        dest_path = f"backup/{ENGINE_WORKFLOW}"
        _, existing_sha = _get_file(pat, archive_repo, dest_path)
        ok = _put_file(pat, archive_repo, dest_path, content.replace("\n", ""),
                       existing_sha, f"backup: {ENGINE_WORKFLOW} [skip ci]")
        if ok:
            print(f"[Shield] 📦 Backed up: {ENGINE_WORKFLOW}")
        else:
            print(f"[Shield] ❌ Failed to back up: {ENGINE_WORKFLOW}", file=sys.stderr)
            success = False
    else:
        print(f"[Shield] ⚠️  {ENGINE_WORKFLOW} not found in engine — skipping.", file=sys.stderr)

    # 2. Backup all scripts/
    script_files = _list_dir(pat, engine_repo, SCRIPTS_DIR)
    for item in script_files:
        file_path = item["path"]  # e.g. "scripts/pattern_engine.py"
        content, _ = _get_file(pat, engine_repo, file_path)
        if content is None:
            print(f"[Shield] ⚠️  Could not read {file_path}", file=sys.stderr)
            success = False
            continue

        dest_path = f"backup/{file_path}"
        _, existing_sha = _get_file(pat, archive_repo, dest_path)
        ok = _put_file(pat, archive_repo, dest_path, content.replace("\n", ""),
                       existing_sha, f"backup: {file_path} [skip ci]")
        if ok:
            print(f"[Shield] 📦 Backed up: {file_path}")
        else:
            print(f"[Shield] ❌ Failed to back up: {file_path}", file=sys.stderr)
            success = False

    status = "✅ complete" if success else "⚠️  partial"
    print(f"[Shield] 📦 Backup {status}.")
    return success


# ---------------------------------------------------------------------------
# Function 2: destroy_engine
# ---------------------------------------------------------------------------

def destroy_engine(pat: str, engine_repo: str, archive_repo: str,
                   interview: dict) -> bool:
    """
    Delete scripts/ and .github/workflows/autocommit.yml from engine repo.
    Updates interviews.json status. Sends Telegram alert.

    Returns True if destroy succeeded.
    """
    print("[Shield] 💥 Starting engine destroy...")
    success = True

    # 1. Delete all scripts/
    script_files = _list_dir(pat, engine_repo, SCRIPTS_DIR)
    for item in script_files:
        ok = _delete_file(pat, engine_repo, item["path"], item["sha"],
                          f"shield: remove {item['path']} before interview [skip ci]")
        if ok:
            print(f"[Shield] 💥 Destroyed: {item['path']}")
        else:
            success = False

    # 2. Delete the workflow file
    _, wf_sha = _get_file(pat, engine_repo, ENGINE_WORKFLOW)
    if wf_sha:
        ok = _delete_file(pat, engine_repo, ENGINE_WORKFLOW, wf_sha,
                          "shield: remove workflow before interview [skip ci]")
        if ok:
            print(f"[Shield] 💥 Destroyed: {ENGINE_WORKFLOW}")
        else:
            success = False
    else:
        print(f"[Shield] ⚠️  {ENGINE_WORKFLOW} already missing.", file=sys.stderr)

    # 3. Update interviews.json
    data, sha = _load_interviews(pat, archive_repo)
    for iv in data.get("interviews", []):
        if iv.get("id") == interview.get("id"):
            iv["status"] = "destroyed"
            iv["destroyed_at"] = _now_ist().isoformat()
    data["system_status"] = "destroyed"
    _save_interviews(pat, archive_repo, data, sha)
    print("[Shield] 📝 interviews.json updated → status: destroyed")

    # 4. Telegram alert
    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if token and chat_id:
        company     = interview.get("company", "Unknown")
        iv_date_str = interview.get("date", "")
        restore_on  = interview.get("restore_on", "")
        try:
            iv_display  = datetime.date.fromisoformat(iv_date_str).strftime("%-d %B, %Y")
            restore_disp = datetime.date.fromisoformat(restore_on).strftime("%-d %B, %Y")
        except Exception:
            iv_display   = iv_date_str
            restore_disp = restore_on

        msg = (
            "🔴 *AutoCommit Shield Activated*\n\n"
            f"Interview: *{company}* — {iv_display}\n"
            "System hidden 2 days before your interview.\n\n"
            "All workflow files removed from autocommit\\-engine.\n\n"
            "Repo looks clean and innocent. ✅\n"
            f"Auto\\-restore scheduled: {restore_disp}"
        )
        _send_telegram(token, chat_id, msg)
        print("[Shield] 📨 Telegram alert sent.")

    return success


# ---------------------------------------------------------------------------
# CLI entry point — called by workflow
# ---------------------------------------------------------------------------

def main() -> None:
    pat          = os.environ.get("ARCHIVE_REPO_PAT", "").strip()
    engine_owner = os.environ.get("GH_USERNAME", "").strip()
    archive_repo_name = os.environ.get("ARCHIVE_REPO", "commit-archive").strip()
    engine_repo_name  = os.environ.get("ENGINE_REPO", "autocommit-engine").strip()

    if not pat or not engine_owner:
        print("[Shield] ❌ GH_USERNAME and ARCHIVE_REPO_PAT must be set.", file=sys.stderr)
        sys.exit(1)

    archive_repo = f"{engine_owner}/{archive_repo_name}"
    engine_repo  = f"{engine_owner}/{engine_repo_name}"
    today        = _today_str()

    print(f"[Shield] 🛡️  Interview Shield Check — {today}")
    print(f"[Shield] Engine: {engine_repo} | Archive: {archive_repo}")

    data, sha = _load_interviews(pat, archive_repo)
    interviews = data.get("interviews", [])

    if not interviews:
        print("[Shield] No interviews scheduled — nothing to do.")
        return

    changed = False
    for iv in interviews:
        status     = iv.get("status", "scheduled")
        destroy_on = iv.get("destroy_on", "")
        restore_on = iv.get("restore_on", "")
        company    = iv.get("company", "Unknown")

        if not destroy_on:
            continue

        try:
            destroy_date = datetime.date.fromisoformat(destroy_on)
            today_date   = datetime.date.fromisoformat(today)
        except Exception as e:
            print(f"[Shield] ⚠️  Bad date in interview {iv.get('id')}: {e}", file=sys.stderr)
            continue

        days_to_destroy = (destroy_date - today_date).days

        # Update to "destroying_soon" 3 days before destroy
        if 0 < days_to_destroy <= 3 and status == "scheduled":
            iv["status"] = "destroying_soon"
            changed = True
            print(f"[Shield] 🟡 {company}: destroying_soon (in {days_to_destroy}d)")

        # Execute destroy on or after destroy_on date
        elif today_date >= destroy_date and status in ("scheduled", "destroying_soon"):
            print(f"[Shield] 💥 {company}: destroy day! Backing up and destroying...")
            backed_up = backup_engine_files(pat, engine_repo, archive_repo)
            if backed_up:
                destroy_engine(pat, engine_repo, archive_repo, iv)
            else:
                print(f"[Shield] ⚠️  Backup incomplete — ABORTING destroy for safety.", file=sys.stderr)
            changed = True   # interviews.json already updated inside destroy_engine

    if changed:
        # Re-read with updated sha after possible writes inside destroy_engine
        data, sha = _load_interviews(pat, archive_repo)
        _save_interviews(pat, archive_repo, data, sha)
        print("[Shield] 📝 interviews.json saved.")
    else:
        print("[Shield] ✅ No actions required today.")


if __name__ == "__main__":
    main()
