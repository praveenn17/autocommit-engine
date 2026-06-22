#!/usr/bin/env python3
"""
AutoCommit Generator — File Mutator
=====================================
Applies one of three variable mutations to activity_log.txt on each commit.
This ensures every commit has a real, non-empty diff — making it completely
indistinguishable from a real code commit at the git log level.

Mutation types (rotated randomly):
  A: Append timestamped log line     → "[ YYYY-MM-DD HH:MM:SS IST] session active"
  B: Increment session counter        → updates counter in last line
  C: Update 'last_active' timestamp   → overwrites last_active field

Tech: Python 3.12 stdlib only — no extra dependencies.
"""

import datetime
import os
import random
import re
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
IST_OFFSET   = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
LOG_FILE     = "activity_log.txt"
MAX_LINES    = 500       # Trim file to last 500 lines automatically
MUTATION_A   = "append"
MUTATION_B   = "counter"
MUTATION_C   = "last_active"

# Rotation state file (persists between runs to avoid consecutive same mutations)
MUTATION_STATE_FILE = ".mutation_state"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def now_ist() -> datetime.datetime:
    return datetime.datetime.now(IST_OFFSET)


def ist_timestamp() -> str:
    return now_ist().strftime("%Y-%m-%d %H:%M:%S")


def load_log_lines() -> list[str]:
    p = Path(LOG_FILE)
    if not p.exists():
        # Bootstrap the file
        return [
            "# AutoCommit Activity Log\n",
            f"# Created: {ist_timestamp()} IST\n",
            "session_counter=0\n",
            f"last_active={ist_timestamp()} IST\n",
        ]
    with open(p, "r", encoding="utf-8") as f:
        return f.readlines()


def save_log_lines(lines: list[str]) -> None:
    # Trim to last MAX_LINES lines
    if len(lines) > MAX_LINES:
        lines = lines[-MAX_LINES:]
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.writelines(lines)


def load_mutation_state() -> int:
    """Return last mutation index (0, 1, or 2)."""
    p = Path(MUTATION_STATE_FILE)
    if p.exists():
        try:
            return int(p.read_text().strip()) % 3
        except ValueError:
            pass
    return -1


def save_mutation_state(idx: int) -> None:
    Path(MUTATION_STATE_FILE).write_text(str(idx % 3))


def pick_mutation() -> str:
    """
    Rotate through mutations avoiding same mutation twice in a row.
    Adds random shuffle to prevent detectable pattern.
    """
    last = load_mutation_state()
    options = [0, 1, 2]
    if last in options:
        options.remove(last)
    chosen_idx = random.choice(options)
    save_mutation_state(chosen_idx)
    return [MUTATION_A, MUTATION_B, MUTATION_C][chosen_idx]


# ---------------------------------------------------------------------------
# Mutation A — Append Timestamped Log Line
# ---------------------------------------------------------------------------

def mutation_append(lines: list[str]) -> list[str]:
    """
    Appends: [2025-06-01 10:23:47 IST] session active
    Diff size: ~45 bytes
    """
    ts = ist_timestamp()
    # Add small random variation to make each line slightly different
    session_type = random.choice([
        "session active",
        "heartbeat ok",
        "sync complete",
        "activity logged",
        "status: running",
        "checkpoint reached",
        "routine check passed",
    ])
    new_line = f"[{ts} IST] {session_type}\n"
    lines.append(new_line)
    return lines


# ---------------------------------------------------------------------------
# Mutation B — Increment Session Counter
# ---------------------------------------------------------------------------

def mutation_counter(lines: list[str]) -> list[str]:
    """
    Finds and increments the session_counter line.
    Diff size: 8-20 bytes depending on counter value.
    """
    counter_pattern = re.compile(r"^session_counter=(\d+)", re.MULTILINE)
    found = False
    for i, line in enumerate(lines):
        m = counter_pattern.match(line.strip())
        if m:
            old_val = int(m.group(1))
            new_val = old_val + 1
            lines[i] = f"session_counter={new_val}\n"
            found = True
            break

    if not found:
        # No counter line exists — add one
        lines.append(f"session_counter=1\n")

    return lines


# ---------------------------------------------------------------------------
# Mutation C — Update last_active Field
# ---------------------------------------------------------------------------

def mutation_last_active(lines: list[str]) -> list[str]:
    """
    Finds and updates the last_active timestamp line.
    Diff size: ~36 bytes.
    """
    ts = ist_timestamp()
    active_pattern = re.compile(r"^last_active=", re.MULTILINE)
    found = False
    for i, line in enumerate(lines):
        if active_pattern.match(line.strip()):
            lines[i] = f"last_active={ts} IST\n"
            found = True
            break

    if not found:
        lines.append(f"last_active={ts} IST\n")

    return lines


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------

def apply_mutation(mutation_type: str | None = None) -> str:
    """
    Apply a single mutation to activity_log.txt.
    If mutation_type is None, auto-select via rotation.
    Returns the mutation type applied.
    """
    lines = load_log_lines()

    if mutation_type is None:
        mutation_type = pick_mutation()

    print(f"[FileMutator] Applying mutation: {mutation_type}")

    if mutation_type == MUTATION_A:
        lines = mutation_append(lines)
    elif mutation_type == MUTATION_B:
        lines = mutation_counter(lines)
    elif mutation_type == MUTATION_C:
        lines = mutation_last_active(lines)
    else:
        print(f"[ERROR] Unknown mutation type: {mutation_type}", file=sys.stderr)
        sys.exit(1)

    save_log_lines(lines)
    print(f"[FileMutator] {LOG_FILE} updated ({len(lines)} lines).")

    # Stage the file immediately so git diff --staged is populated
    # when ai_commit_generator.get_staged_diff() is called next.
    try:
        result = subprocess.run(
            ["git", "add", LOG_FILE],
            capture_output=True, text=True, check=False
        )
        if result.returncode == 0:
            print(f"[FileMutator] git add {LOG_FILE} ✔")
        else:
            print(f"[FileMutator] ⚠️  git add returned code {result.returncode}: {result.stderr.strip()}",
                  file=sys.stderr)
    except FileNotFoundError:
        print("[FileMutator] ⚠️  git not found — skipping git add (non-git environment).",
              file=sys.stderr)
    except Exception as e:
        print(f"[FileMutator] ⚠️  git add failed: {e}", file=sys.stderr)

    return mutation_type


def main() -> None:
    """
    Entry point called per-commit by the GitHub Actions workflow.
    Accepts optional --mutation A/B/C argument for testing.
    """
    mutation_type = None
    if len(sys.argv) >= 3 and sys.argv[1] == "--mutation":
        arg = sys.argv[2].lower()
        mutation_map = {"a": MUTATION_A, "b": MUTATION_B, "c": MUTATION_C}
        mutation_type = mutation_map.get(arg)
        if mutation_type is None:
            print(f"[ERROR] Invalid mutation: {sys.argv[2]}. Use A, B, or C.", file=sys.stderr)
            sys.exit(1)

    applied = apply_mutation(mutation_type)
    print(f"[FileMutator] Done. Mutation '{applied}' applied to {LOG_FILE}.")


if __name__ == "__main__":
    main()
