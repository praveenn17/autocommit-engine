#!/usr/bin/env python3
"""
AutoCommit Generator — AI Commit Generator
============================================
Uses the Gemini API (gemini-2.0-flash) to generate context-aware commit
messages tailored to the project's actual tech stack AND real git diffs.

New in v2: diff-first generation
  1. Reads the staged git diff from the archive repo working directory
  2. Sends the real diff to Gemini for a single, contextually accurate message
  3. Falls back to extension-based batch generation if diff is unavailable
  4. Falls back to message_pool.json if Gemini fails entirely

Environment variable required:
  GEMINI_API_KEY  — your Google AI Studio API key

Tech: Python 3.12 · requests · subprocess · stdlib only (no SDK needed)
"""

import json
import os
import sys
import random
import difflib
import argparse
import subprocess
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
GEMINI_MODEL    = "gemini-2.0-flash"
GEMINI_API_BASE = (
    "https://generativelanguage.googleapis.com/v1beta/models"
    "/{model}:generateContent?key={key}"
)
MSG_POOL_FILE   = "message_pool.json"
HISTORY_FILE    = "commit_history.json"
TARGET_COUNT    = 10
DIFF_MAX_CHARS  = 3000    # Truncation limit for Gemini context safety
GEMINI_TIMEOUT  = 15     # seconds

# Words that must NOT appear in any diff-generated commit message
BANNED_WORDS = {
    "activity_log", "activity log", "log entry", "counter",
    "timestamp", "automation", "autocommit", "auto-commit",
}

# Conventional commit prefixes — must appear in every generated message
COMMIT_PREFIXES = ["feat", "fix", "refactor", "perf", "docs", "test", "chore", "style", "security"]

# Extension → tech description mapping for richer prompts
EXT_DESCRIPTIONS = {
    ".py":    "Python backend",
    ".js":    "JavaScript",
    ".jsx":   "React (JSX)",
    ".ts":    "TypeScript",
    ".tsx":   "React TypeScript",
    ".json":  "JSON config/data",
    ".yml":   "YAML / CI config",
    ".yaml":  "YAML / CI config",
    ".sh":    "Bash scripting",
    ".html":  "HTML templates",
    ".css":   "CSS styling",
    ".sql":   "SQL / database",
    ".go":    "Go backend",
    ".rs":    "Rust",
    ".java":  "Java backend",
    ".kt":    "Kotlin / Android",
    ".swift": "Swift / iOS",
    ".rb":    "Ruby / Rails",
    ".php":   "PHP backend",
    ".md":    "Markdown docs",
    ".tf":    "Terraform / IaC",
    ".dart":  "Flutter / Dart",
}

SIMILARITY_THRESHOLD = 0.72  # Slightly looser than pool engine; AI varies more


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_json(path: str) -> dict:
    p = Path(path)
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def parse_extensions(raw: str) -> list[str]:
    """Normalise comma-separated extensions, ensuring leading dot."""
    exts = []
    for e in raw.split(","):
        e = e.strip().lower()
        if e and not e.startswith("."):
            e = "." + e
        if e:
            exts.append(e)
    return list(dict.fromkeys(exts))  # deduplicate while preserving order


def describe_stack(extensions: list[str]) -> str:
    """Convert extension list into a readable stack description for the prompt."""
    parts = []
    seen = set()
    for ext in extensions:
        desc = EXT_DESCRIPTIONS.get(ext)
        if desc and desc not in seen:
            parts.append(desc)
            seen.add(desc)
    return ", ".join(parts) if parts else "general software project"


def strip_prefix(message: str) -> str:
    parts = message.split(":", 1)
    return parts[1].strip().lower() if len(parts) == 2 else message.lower().strip()


def is_too_similar(candidate: str, existing: list[str], threshold: float = SIMILARITY_THRESHOLD) -> bool:
    c = strip_prefix(candidate)
    for msg in existing:
        ratio = difflib.SequenceMatcher(None, c, strip_prefix(msg)).ratio()
        if ratio >= threshold:
            return True
    return False


def deduplicate(messages: list[str], threshold: float = SIMILARITY_THRESHOLD) -> list[str]:
    """Remove semantically similar entries from a list, keeping the first occurrence."""
    unique = []
    for msg in messages:
        if not is_too_similar(msg, unique, threshold):
            unique.append(msg)
    return unique


def deduplicate_against_history(
    message: str,
    history_file_path: str = HISTORY_FILE,
    lookback: int = 30,
    threshold: float = SIMILARITY_THRESHOLD,
) -> bool:
    """
    Check whether `message` is unique against recent commit history.

    Args:
        message:           The candidate commit message.
        history_file_path: Path to commit_history.json on disk.
        lookback:          Number of recent days to compare against.
        threshold:         Similarity ratio above which message is rejected.

    Returns:
        True  — message is unique enough, accept it.
        False — too similar to a recent message, reject it.
    """
    try:
        history = load_json(history_file_path)
        recent_msgs: list[str] = []
        # Sort dates descending, take last `lookback` days
        for date_key in sorted(history.keys(), reverse=True)[:lookback]:
            recent_msgs.extend(history.get(date_key, []))
        return not is_too_similar(message, recent_msgs, threshold)
    except Exception as e:
        print(f"[AIGenerator] ⚠️  History dedup check failed: {e} — accepting message.",
              file=sys.stderr)
        return True  # Accept on failure (safe default)


# ---------------------------------------------------------------------------
# Diff helpers (new in v2)
# ---------------------------------------------------------------------------

def get_staged_diff(repo_dir: str | None = None) -> str:
    """
    Return the staged git diff from `repo_dir` (defaults to cwd).
    If staged diff is empty, falls back to git diff HEAD~1.
    Truncates to DIFF_MAX_CHARS for Gemini context safety.

    Returns:
        Diff string, or empty string on any failure.
    """
    cwd = repo_dir or os.getcwd()
    try:
        result = subprocess.run(
            ["git", "diff", "--staged"],
            capture_output=True, text=True, cwd=cwd, timeout=10
        )
        diff = result.stdout.strip()

        if not diff:
            # Fall back to last commit diff
            result2 = subprocess.run(
                ["git", "diff", "HEAD~1"],
                capture_output=True, text=True, cwd=cwd, timeout=10
            )
            diff = result2.stdout.strip()

        if diff:
            diff = diff[:DIFF_MAX_CHARS]
            if len(result.stdout.strip()) > DIFF_MAX_CHARS:
                diff += "\n... [truncated]"

        return diff
    except Exception as e:
        print(f"[AIGenerator] ⚠️  get_staged_diff failed: {e}", file=sys.stderr)
        return ""


def _validate_diff_message(message: str) -> tuple[bool, str]:
    """
    Validate a single diff-generated commit message.

    Returns:
        (True, "") if valid.
        (False, reason) if invalid.
    """
    msg = message.strip()

    # Must start with a valid conventional commit type
    if not any(msg.startswith(p + ":") or msg.startswith(p + "(") for p in COMMIT_PREFIXES):
        return False, f"No valid type prefix (got: {msg[:20]!r})"

    # Must be under 72 characters
    if len(msg) > 72:
        return False, f"Too long ({len(msg)} chars, max 72)"

    # Must not contain banned words
    msg_lower = msg.lower()
    for word in BANNED_WORDS:
        if word in msg_lower:
            return False, f"Contains banned word: {word!r}"

    return True, ""


def _call_gemini_single(prompt: str, api_key: str) -> str:
    """
    Call Gemini and extract a single plain-text response (not JSON array).
    Used by generate_message_from_diff().
    Returns raw response text (stripped), or raises on failure.
    """
    try:
        import requests as _req
    except ImportError:
        raise RuntimeError("requests not installed")

    url = GEMINI_API_BASE.format(model=GEMINI_MODEL, key=api_key)
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.4,   # Lower temp for precise single-message output
            "topP":        0.9,
            "maxOutputTokens": 128,
        },
        "safetySettings": [
            {"category": "HARM_CATEGORY_HARASSMENT",        "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH",       "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ],
    }
    import time
    resp = _req.post(url, json=payload, timeout=GEMINI_TIMEOUT)
    if resp.status_code == 429:
        print("[AIGenerator] ⚠️  429 Rate limit hit, waiting 5 seconds before retry...", file=sys.stderr)
        time.sleep(5)
        resp = _req.post(url, json=payload, timeout=GEMINI_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
    # Strip markdown fences or quotes the model might add
    text = text.strip('`"\' \n')
    # If model returned multiple lines, take the first non-empty one
    for line in text.splitlines():
        line = line.strip().strip('`"\' ')
        if line:
            return line
    return text


def generate_message_from_diff(
    diff_text: str,
    extensions: list[str] | None = None,
    api_key: str | None = None,
) -> str | None:
    """
    Send a real git diff to Gemini and get back ONE validated commit message.

    Validation rules:
      • Must start with valid conventional commit type
      • Must be ≤ 72 characters
      • Must not contain banned words

    Retries once with a stricter prompt on validation failure.
    Returns None if both attempts fail (caller should fall back).
    """
    if not diff_text:
        return None

    key = api_key or os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        return None

    ext_str = ", ".join(extensions or [".py", ".yml", ".json"])

    def _build_prompt(strict: bool = False) -> str:
        extra = (
            "\nBe especially careful: the message must be under 72 characters "
            "and must NOT mention logs, counters, timestamps, or automation."
        ) if strict else ""
        return (
            "You are an expert developer writing git commit messages.\n"
            "Analyze this git diff and write ONE commit message that:\n\n"
            "- Follows conventional commits format: <type>(<scope>): <description>\n"
            "  or <type>: <description>\n"
            "- Types allowed: feat, fix, docs, chore, refactor, perf, test, style\n"
            "- Is specific to what actually changed in the diff\n"
            "- Is under 72 characters total\n"
            "- Sounds natural, written by a human developer\n"
            "- Does NOT mention: activity_log, log entry, counter, timestamp, "
            "or automation — these are internal implementation details\n"
            f"{extra}\n"
            f"Git diff:\n{diff_text}\n\n"
            f"Project tech stack (for context): {ext_str}\n\n"
            "Respond with ONLY the commit message. No explanation. No markdown. "
            "No quotes. Just the commit message itself."
        )

    for attempt in range(2):
        try:
            raw = _call_gemini_single(_build_prompt(strict=attempt > 0), key)
            valid, reason = _validate_diff_message(raw)
            if valid:
                return raw
            print(
                f"[AIGenerator] ⚠️  Diff message attempt {attempt+1} failed validation: {reason}",
                file=sys.stderr,
            )
        except Exception as e:
            print(f"[AIGenerator] ⚠️  Diff Gemini call attempt {attempt+1} failed: {e}",
                  file=sys.stderr)

    return None  # Both attempts failed — caller falls back


# ---------------------------------------------------------------------------
# Prompt builder (extension-based batch generation — unchanged)
# ---------------------------------------------------------------------------

def build_prompt(stack_desc: str, style_examples: list[str]) -> str:
    """Build the Gemini prompt for commit message generation."""
    examples_block = "\n".join(f"- {e}" for e in style_examples[:12])

    return f"""You are a senior software engineer writing git commit messages for a real project.

Tech stack: {stack_desc}

Here are examples of commit messages already used in this project (match the style and vocabulary exactly):
{examples_block}

Generate exactly 10 NEW commit messages for this project. Rules:
1. Every message MUST start with one of: feat:, fix:, refactor:, perf:, docs:, test:, chore:, style:, security:
2. Messages must be specific and realistic for the tech stack above — not generic.
3. No two messages may be semantically similar (no paraphrases).
4. No message should repeat or closely resemble any example shown above.
5. Keep each message between 40 and 90 characters total (including prefix).
6. Use lowercase after the colon, no period at the end.
7. Vary the prefixes — do not use the same prefix more than 3 times.
8. Write in the imperative mood (e.g. "implement", "add", "resolve", not "implemented").

Return ONLY a valid JSON array of exactly 10 strings. No explanation, no markdown fences, no extra text.
Example format: ["feat: add user authentication", "fix: resolve memory leak in parser"]"""


# ---------------------------------------------------------------------------
# Gemini API call
# ---------------------------------------------------------------------------

def call_gemini(prompt: str, api_key: str) -> list[str]:
    """
    Call Gemini API via raw HTTP POST using requests.
    Returns a list of commit message strings.
    Raises on network/API errors.
    """
    try:
        import requests
    except ImportError:
        raise RuntimeError("requests library not available. Install it with: pip install requests")

    url = GEMINI_API_BASE.format(model=GEMINI_MODEL, key=api_key)
    payload = {
        "contents": [
            {
                "parts": [{"text": prompt}]
            }
        ],
        "generationConfig": {
            "temperature": 0.85,
            "topP": 0.95,
            "maxOutputTokens": 1024,
            "responseMimeType": "application/json",
        },
        "safetySettings": [
            {"category": "HARM_CATEGORY_HARASSMENT",        "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH",       "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ],
    }

    import time
    resp = requests.post(url, json=payload, timeout=30)
    if resp.status_code == 429:
        print("[AIGenerator] ⚠️  429 Rate limit hit, waiting 5 seconds before retry...", file=sys.stderr)
        time.sleep(5)
        resp = requests.post(url, json=payload, timeout=30)
    resp.raise_for_status()

    data = resp.json()

    # Extract text from Gemini response structure
    try:
        raw_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"Unexpected Gemini response structure: {e}\nResponse: {data}")

    # Parse the JSON array
    try:
        messages = json.loads(raw_text)
        if not isinstance(messages, list):
            raise ValueError("Response is not a JSON array")
    except (json.JSONDecodeError, ValueError) as e:
        # Try to extract JSON array from text if model added surrounding text
        import re
        match = re.search(r'\[.*?\]', raw_text, re.DOTALL)
        if match:
            messages = json.loads(match.group(0))
        else:
            raise RuntimeError(f"Could not parse Gemini response as JSON array: {e}\nRaw: {raw_text[:500]}")

    # Validate each message has a conventional commit prefix
    valid = []
    for msg in messages:
        if isinstance(msg, str) and any(msg.startswith(p + ":") for p in COMMIT_PREFIXES):
            valid.append(msg.strip())

    if not valid:
        raise RuntimeError(f"No valid conventional commit messages in Gemini response: {messages}")

    return valid


# ---------------------------------------------------------------------------
# Fallback: pull messages from message_pool.json
# ---------------------------------------------------------------------------

def fallback_from_pool(count: int, pool: dict, existing: list[str]) -> list[str]:
    """
    Sample `count` messages from message_pool.json that pass the similarity check.
    Rotates through categories for diversity.
    """
    categories = list(pool.get("categories", {}).keys())
    if not categories:
        return []

    random.shuffle(categories)
    selected = []
    session = list(existing)
    cat_index = 0
    attempts = 0

    while len(selected) < count and attempts < 300:
        attempts += 1
        cat = categories[cat_index % len(categories)]
        cat_index += 1
        pool_msgs = pool["categories"].get(cat, [])
        if not pool_msgs:
            continue
        candidate = random.choice(pool_msgs)
        if candidate not in selected and not is_too_similar(candidate, session):
            selected.append(candidate)
            session.append(candidate)

    return selected


# ---------------------------------------------------------------------------
# Style examples extractor
# ---------------------------------------------------------------------------

def extract_style_examples(pool: dict, n: int = 12) -> list[str]:
    """Pick n diverse example messages from the pool to show Gemini our style."""
    categories = list(pool.get("categories", {}).keys())
    examples = []
    for cat in categories:
        msgs = pool["categories"].get(cat, [])
        if msgs:
            examples.append(random.choice(msgs))
        if len(examples) >= n:
            break
    random.shuffle(examples)
    return examples[:n]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def generate_ai_messages(
    extensions: list[str],
    existing_history: list[str] | None = None,
    repo_dir: str | None = None,
) -> list[str]:
    """
    Primary entry point for external callers (e.g. pattern_engine.py).

    v2 flow:
      1. Try diff-based single-message generation (most accurate)
      2. If that fails, try extension-based batch generation
      3. If Gemini unavailable/fails, fall back to message_pool.json

    Args:
        extensions:       List of file extensions from the project repo.
        existing_history: List of messages already used (for similarity check).
        repo_dir:         Path to the archive repo clone (for git diff). Defaults to cwd.

    Returns:
        List of unique commit message strings.
    """
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    pool    = load_json(MSG_POOL_FILE)
    history = existing_history or []
    results: list[str] = []

    # ── Path A: Diff-based single message (highest quality) ──────────────────
    if api_key:
        try:
            diff = get_staged_diff(repo_dir)
            if diff:
                msg = generate_message_from_diff(diff, extensions, api_key)
                if msg:
                    is_unique = deduplicate_against_history(
                        msg,
                        history_file_path=str(Path(repo_dir or ".") / HISTORY_FILE),
                    )
                    if is_unique and not is_too_similar(msg, history):
                        results.append(msg)
                        print(
                            f"[AIGenerator] 🧠 AI: Generated from real diff ({len(msg)} chars)",
                            file=sys.stderr,
                        )
                    else:
                        # Regenerate once if duplicate
                        msg2 = generate_message_from_diff(diff, extensions, api_key)
                        if msg2 and not is_too_similar(msg2, history):
                            results.append(msg2)
                            print(
                                f"[AIGenerator] 🧠 AI: Generated from real diff after regen ({len(msg2)} chars)",
                                file=sys.stderr,
                            )
                        else:
                            print(
                                "[AIGenerator] ⚠️  Diff message rejected (duplicate) — falling through.",
                                file=sys.stderr,
                            )
            else:
                print("[AIGenerator] 🔍 No staged diff available — using extension fallback.",
                      file=sys.stderr)
        except Exception as e:
            if "429" in str(e):
                api_key = None
            print(f"[AIGenerator] ⚠️  Diff path error: {e}", file=sys.stderr)

    # ── Path B: Extension-based batch generation (fills remaining slots) ──────
    # Always run if we still need more messages (or if diff path skipped)
    remaining = max(TARGET_COUNT - len(results), 0)
    if remaining > 0 and api_key:
        import time
        if results:
            time.sleep(2)  # delay between sequential Gemini calls
        try:
            stack_desc     = describe_stack(extensions)
            style_examples = extract_style_examples(pool)
            prompt         = build_prompt(stack_desc, style_examples)

            print(f"[AIGenerator] Calling Gemini ({GEMINI_MODEL}) for stack: {stack_desc}",
                  file=sys.stderr)
            raw_messages = call_gemini(prompt, api_key)
            raw_messages = deduplicate(raw_messages)
            filtered = [m for m in raw_messages if not is_too_similar(m, history + results)]

            if filtered:
                results.extend(filtered)
                print(
                    f"[AIGenerator] 🧠 AI: Generated from extensions (fallback) — "
                    f"{len(filtered)} messages",
                    file=sys.stderr,
                )
            else:
                print("[AIGenerator] All extension messages failed history check.",
                      file=sys.stderr)

        except Exception as e:
            print(f"[AIGenerator] Gemini extension call error: {e}", file=sys.stderr)

    elif remaining > 0 and not api_key:
        print("[AIGenerator] GEMINI_API_KEY not set — using message_pool.json fallback.",
              file=sys.stderr)

    # ── Path C: Static message pool fallback ─────────────────────────────────
    if not results:
        print("[AIGenerator] 🧠 AI: API failed, using message pool", file=sys.stderr)
        results = fallback_from_pool(TARGET_COUNT, pool, history)
        print(f"[AIGenerator] Fallback pool returned {len(results)} messages.", file=sys.stderr)
    elif len(results) < TARGET_COUNT:
        # Top up with pool messages if we have fewer than needed
        top_up = fallback_from_pool(TARGET_COUNT - len(results), pool, history + results)
        results.extend(top_up)

    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate AI-powered commit messages using Gemini API."
    )
    parser.add_argument(
        "--extensions",
        default=".py,.js,.jsx,.json,.yml",
        help='Comma-separated file extensions (e.g. ".py,.js,.jsx"). Default: .py,.js,.jsx,.json,.yml',
    )
    parser.add_argument(
        "--history",
        default="",
        help="Comma-separated existing commit messages to avoid repeating (optional).",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=TARGET_COUNT,
        help=f"Number of messages to generate (default: {TARGET_COUNT}).",
    )
    args = parser.parse_args()

    extensions = parse_extensions(args.extensions)
    history    = [m.strip() for m in args.history.split(",") if m.strip()] if args.history else []

    messages = generate_ai_messages(extensions, history)

    # Output as JSON array to stdout (consumed by pattern_engine.py)
    print(json.dumps(messages[:args.count], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
