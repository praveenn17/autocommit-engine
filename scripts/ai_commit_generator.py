#!/usr/bin/env python3
"""
AutoCommit Generator — AI Commit Generator
============================================
Uses the Gemini API (gemini-2.0-flash) to generate context-aware commit
messages tailored to the project's actual tech stack.

Inputs (via CLI args or environment):
  --extensions  Comma-separated file extensions found in the project repo
                e.g. ".py,.js,.jsx,.json,.yml"
                Defaults to a generic full-stack set if not provided.

Outputs:
  JSON array of 10 unique commit messages printed to stdout.
  Falls back to message_pool.json if the Gemini API call fails.

Environment variable required:
  GEMINI_API_KEY  — your Google AI Studio API key

Tech: Python 3.12 · requests · stdlib only (no google-generativeai SDK needed)
"""

import json
import os
import sys
import random
import difflib
import argparse
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
TARGET_COUNT    = 10

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


# ---------------------------------------------------------------------------
# Prompt builder
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

def generate_ai_messages(extensions: list[str], existing_history: list[str] | None = None) -> list[str]:
    """
    Primary entry point for external callers (e.g. pattern_engine.py).

    Args:
        extensions:       List of file extensions from the project repo.
        existing_history: List of messages already used (for similarity check).

    Returns:
        List of unique commit message strings.
        Falls back to message_pool.json if Gemini fails.
    """
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    pool    = load_json(MSG_POOL_FILE)
    history = existing_history or []

    # --- Try Gemini first ---
    if api_key:
        try:
            stack_desc     = describe_stack(extensions)
            style_examples = extract_style_examples(pool)
            prompt         = build_prompt(stack_desc, style_examples)

            print(f"[AIGenerator] Calling Gemini ({GEMINI_MODEL}) for stack: {stack_desc}", file=sys.stderr)
            raw_messages = call_gemini(prompt, api_key)

            # Deduplicate within this batch
            raw_messages = deduplicate(raw_messages)

            # Filter against 180-day history
            filtered = [
                m for m in raw_messages
                if not is_too_similar(m, history)
            ]

            if filtered:
                print(f"[AIGenerator] Gemini returned {len(raw_messages)} messages, "
                      f"{len(filtered)} passed history check.", file=sys.stderr)
                return filtered

            print("[AIGenerator] All Gemini messages failed history check — using fallback.",
                  file=sys.stderr)

        except Exception as e:
            print(f"[AIGenerator] Gemini API error: {e} — falling back to message_pool.json",
                  file=sys.stderr)
    else:
        print("[AIGenerator] GEMINI_API_KEY not set — using message_pool.json fallback.",
              file=sys.stderr)

    # --- Fallback: message_pool.json ---
    fallback = fallback_from_pool(TARGET_COUNT, pool, history)
    print(f"[AIGenerator] Fallback pool returned {len(fallback)} messages.", file=sys.stderr)
    return fallback


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
