#!/usr/bin/env python3
"""
AutoCommit Generator — Telegram Notifier
==========================================
Runs every Tuesday via GitHub Actions. Generates a weekly PDF report using
ReportLab and sends it to Telegram via the Bot API with a rich summary message.

Features:
  - Reads streak_stats.json, commit_history.json, quality_score.json
  - Generates in-memory PDF with ReportLab (no disk I/O)
  - Sends formatted Markdown message via sendMessage
  - Attaches PDF via sendDocument
  - Supports streak break warning (if no commit by 8pm IST today)

Secrets required (GitHub Actions secrets):
  TELEGRAM_BOT_TOKEN  — from @BotFather
  TELEGRAM_CHAT_ID    — your personal chat ID
  DASHBOARD_URL       — optional, link to your Vercel dashboard

Tech: Python 3.12 · requests · reportlab 4.x
"""

import json
import os
import io
import datetime
import sys
from pathlib import Path
from typing import Optional

try:
    import requests
except ImportError:
    print("[ERROR] requests not installed. Run: pip install requests", file=sys.stderr)
    sys.exit(1)

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    )
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False
    print("[WARN] ReportLab not installed. PDF report will be skipped.", file=sys.stderr)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
IST_OFFSET   = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
HISTORY_FILE = "commit_history.json"
STREAK_FILE  = "streak_stats.json"
QUALITY_FILE = "quality_score.json"
CONFIG_FILE  = "config.json"

# Telegram API base
TG_API_BASE  = "https://api.telegram.org/bot{token}/{method}"


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


def tg_url(token: str, method: str) -> str:
    return TG_API_BASE.format(token=token, method=method)


def get_week_range() -> tuple[datetime.date, datetime.date]:
    """Return Monday–Sunday of the previous week."""
    today = now_ist().date()
    monday = today - datetime.timedelta(days=today.weekday() + 7)
    sunday = monday + datetime.timedelta(days=6)
    return monday, sunday


def get_week_history(history: dict, monday: datetime.date, sunday: datetime.date) -> dict:
    """Extract history entries for a specific week."""
    result = {}
    current = monday
    while current <= sunday:
        date_str = current.isoformat()
        result[date_str] = history.get(date_str, [])
        current += datetime.timedelta(days=1)
    return result


def commit_mode_for_day(msgs: list[str]) -> str:
    count = len(msgs)
    if count == 0:
        return "Rest"
    elif count == 1:
        return "Quiet"
    elif count <= 3:
        return "Normal"
    else:
        return "Burst"


def get_next_sick_days(config: dict, n: int = 3) -> list[str]:
    """Get next N upcoming sick days."""
    sick_days = config.get("sick_days_this_month", [])
    today = now_ist().date()
    future = sorted([d for d in sick_days if d >= today.isoformat()])
    return future[:n]


# ---------------------------------------------------------------------------
# PDF Report Generator (ReportLab)
# ---------------------------------------------------------------------------

def generate_pdf_report(
    stats: dict,
    week_history: dict,
    quality: dict,
    config: dict,
    monday: datetime.date,
    sunday: datetime.date,
) -> bytes:
    """Generate weekly PDF report in memory and return as bytes."""
    if not REPORTLAB_AVAILABLE:
        return b""

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    styles = getSampleStyleSheet()
    # Custom styles
    title_style = ParagraphStyle(
        "Title", parent=styles["Title"],
        fontSize=22, textColor=colors.HexColor("#39d353"),
        spaceAfter=6,
    )
    subtitle_style = ParagraphStyle(
        "Subtitle", parent=styles["Normal"],
        fontSize=11, textColor=colors.HexColor("#8b949e"),
        spaceAfter=20,
    )
    heading_style = ParagraphStyle(
        "Heading", parent=styles["Heading2"],
        fontSize=13, textColor=colors.HexColor("#58a6ff"),
        spaceBefore=14, spaceAfter=6,
    )
    normal_style = ParagraphStyle(
        "Body", parent=styles["Normal"],
        fontSize=10, textColor=colors.HexColor("#e6edf3"),
    )
    note_style = ParagraphStyle(
        "Note", parent=styles["Normal"],
        fontSize=9, textColor=colors.HexColor("#8b949e"),
        spaceAfter=4,
    )

    # Background colour workaround: set bg via canvas
    story = []

    week_num = monday.isocalendar()[1]
    date_range = f"{monday.strftime('%b %d')} – {sunday.strftime('%b %d, %Y')}"

    # ── Cover ──────────────────────────────────────────────────────────────
    story.append(Paragraph("AutoCommit Generator", title_style))
    story.append(Paragraph(f"Weekly Report · Week {week_num} · {date_range}", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#30363d")))
    story.append(Spacer(1, 0.4 * cm))

    # ── Streak Summary ──────────────────────────────────────────────────────
    current_streak = stats.get("current_streak", 0)
    longest_streak = stats.get("longest_streak", 0)
    total_commits  = stats.get("total_commits", 0)
    week_commits   = sum(len(v) for v in week_history.values())

    story.append(Paragraph("Streak Summary", heading_style))

    streak_data = [
        ["Metric", "Value"],
        ["Current Streak", f"{current_streak} days"],
        ["Longest Streak", f"{longest_streak} days"],
        ["Total All-Time Commits", f"{total_commits:,}"],
        ["This Week's Commits", f"{week_commits}"],
    ]
    streak_table = Table(streak_data, colWidths=[10 * cm, 6 * cm])
    streak_table.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, 0), colors.HexColor("#161b22")),
        ("TEXTCOLOR",    (0, 0), (-1, 0), colors.HexColor("#39d353")),
        ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, -1), 10),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#0d1117"), colors.HexColor("#161b22")]),
        ("TEXTCOLOR",    (0, 1), (-1, -1), colors.HexColor("#e6edf3")),
        ("GRID",         (0, 0), (-1, -1), 0.5, colors.HexColor("#30363d")),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",   (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 6),
        ("LEFTPADDING",  (0, 0), (-1, -1), 8),
    ]))
    story.append(streak_table)
    story.append(Spacer(1, 0.4 * cm))

    # ── Daily Breakdown ─────────────────────────────────────────────────────
    story.append(Paragraph("Daily Breakdown", heading_style))

    daily_data = [["Date", "Day", "Commits", "Mode", "Messages (preview)"]]
    for date_str, msgs in sorted(week_history.items()):
        d = datetime.date.fromisoformat(date_str)
        mode = commit_mode_for_day(msgs)
        count = len(msgs)
        preview = msgs[0][:35] + "…" if msgs else "—"
        daily_data.append([
            d.strftime("%b %d"),
            d.strftime("%A"),
            str(count),
            mode,
            preview,
        ])

    daily_table = Table(
        daily_data,
        colWidths=[2.5 * cm, 3 * cm, 2 * cm, 2.5 * cm, 7 * cm],
    )
    daily_table.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, 0), colors.HexColor("#161b22")),
        ("TEXTCOLOR",    (0, 0), (-1, 0), colors.HexColor("#58a6ff")),
        ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#0d1117"), colors.HexColor("#161b22")]),
        ("TEXTCOLOR",    (0, 1), (-1, -1), colors.HexColor("#e6edf3")),
        ("GRID",         (0, 0), (-1, -1), 0.5, colors.HexColor("#30363d")),
        ("TOPPADDING",   (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
        ("LEFTPADDING",  (0, 0), (-1, -1), 6),
    ]))
    story.append(daily_table)
    story.append(Spacer(1, 0.4 * cm))

    # ── Quality Score ────────────────────────────────────────────────────────
    story.append(Paragraph("Quality Score", heading_style))

    q_score  = quality.get("score", 0)
    q_status = quality.get("status_label", "Unknown")
    signals  = quality.get("signals", {})

    story.append(Paragraph(
        f"<b>Overall Score: {q_score}/100 — {q_status}</b>",
        ParagraphStyle("QScore", parent=normal_style, fontSize=12,
                       textColor=colors.HexColor("#39d353" if q_score >= 75
                                                 else "#f0883e" if q_score >= 60
                                                 else "#ff7b72"))
    ))
    story.append(Spacer(1, 0.2 * cm))

    q_data = [["Signal", "Score", "Max", "Status", "Note"]]
    for sig_name, sig_data in signals.items():
        passed_icon = "PASS" if sig_data.get("passed") else "FAIL"
        q_data.append([
            sig_name.replace("_", " ").title(),
            str(sig_data.get("score", 0)),
            str(sig_data.get("max", 0)),
            passed_icon,
            sig_data.get("note", "")[:45],
        ])

    q_table = Table(
        q_data,
        colWidths=[4 * cm, 1.5 * cm, 1.5 * cm, 1.5 * cm, 8.5 * cm],
    )
    q_table.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, 0), colors.HexColor("#161b22")),
        ("TEXTCOLOR",    (0, 0), (-1, 0), colors.HexColor("#58a6ff")),
        ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#0d1117"), colors.HexColor("#161b22")]),
        ("TEXTCOLOR",    (0, 1), (-1, -1), colors.HexColor("#e6edf3")),
        ("GRID",         (0, 0), (-1, -1), 0.5, colors.HexColor("#30363d")),
        ("TOPPADDING",   (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
        ("LEFTPADDING",  (0, 0), (-1, -1), 6),
    ]))
    story.append(q_table)
    story.append(Spacer(1, 0.4 * cm))

    # ── Next Week Preview ────────────────────────────────────────────────────
    story.append(Paragraph("Next Week Preview", heading_style))
    next_sick_days = get_next_sick_days(config)
    if next_sick_days:
        story.append(Paragraph(
            f"Scheduled rest days: {', '.join(next_sick_days)}",
            note_style
        ))
    else:
        story.append(Paragraph("No rest days scheduled next week.", note_style))
    story.append(Paragraph(
        f"Target commits/day: {config.get('commits_per_day', 3)} "
        f"| Burst mode: {'ON' if config.get('burst_mode') else 'OFF'} "
        f"| Weekday only: {'YES' if config.get('weekday_only') else 'NO'}",
        note_style
    ))

    story.append(Spacer(1, 0.4 * cm))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#30363d")))
    story.append(Paragraph(
        "AutoCommit Generator v1.0 · Confidential · Personal Use Only",
        ParagraphStyle("Footer", parent=normal_style, fontSize=8,
                       textColor=colors.HexColor("#8b949e"), alignment=TA_CENTER)
    ))

    doc.build(story)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Telegram Sender
# ---------------------------------------------------------------------------

def send_telegram_message(token: str, chat_id: str, text: str) -> bool:
    """Send a text message via Telegram Bot API."""
    resp = requests.post(
        tg_url(token, "sendMessage"),
        json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        },
        timeout=30,
    )
    if not resp.ok:
        print(f"[TG ERROR] sendMessage: {resp.status_code} {resp.text}", file=sys.stderr)
        return False
    return True


def send_telegram_document(
    token: str, chat_id: str, pdf_bytes: bytes, caption: str, filename: str
) -> bool:
    """Send a PDF document via Telegram Bot API (sendDocument)."""
    resp = requests.post(
        tg_url(token, "sendDocument"),
        data={
            "chat_id": chat_id,
            "caption": caption,
            "parse_mode": "Markdown",
        },
        files={"document": (filename, pdf_bytes, "application/pdf")},
        timeout=60,
    )
    if not resp.ok:
        print(f"[TG ERROR] sendDocument: {resp.status_code} {resp.text}", file=sys.stderr)
        return False
    return True


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------

def build_weekly_message(
    stats: dict,
    quality: dict,
    week_commits: int,
    week_rest_days: int,
    monday: datetime.date,
    sunday: datetime.date,
    dashboard_url: str,
    next_sick_days: list[str],
) -> str:
    """Build the Telegram markdown summary message."""
    q_score  = quality.get("score", 0)
    q_status = quality.get("status_label", "Unknown")
    q_emoji  = "🟢" if q_score >= 75 else "🟡" if q_score >= 60 else "🔴"

    current_streak = stats.get("current_streak", 0)
    longest_streak = stats.get("longest_streak", 0)
    total_commits  = stats.get("total_commits", 0)

    week_range = f"{monday.strftime('%b %d')} – {sunday.strftime('%b %d')}"

    sick_preview = ", ".join(next_sick_days) if next_sick_days else "None scheduled"

    msg = f"""🤖 *AutoCommit Generator — Weekly Report*
📅 Week ending {sunday.strftime('%b %d, %Y')} · {week_range}

━━━━━━━━━━━━━━━━━
🔥 *Streak*
• Current streak: *{current_streak} days*
• Longest streak: *{longest_streak} days*

📊 *This Week*
• Commits fired: *{week_commits}*
• Rest days taken: *{week_rest_days}*
• Total all-time: *{total_commits:,}*

{q_emoji} *Quality Score: {q_score}/100 — {q_status}*

📆 *Next Week Rest Days*
{sick_preview}

🔗 [Open Dashboard]({dashboard_url})

_AutoCommit Generator v1.0 · Personal Use Only_"""

    return msg


def main() -> None:
    """Main entry point — called by GitHub Actions on Tuesdays."""
    is_test = "--test" in sys.argv
    is_streak_warning = "--streak-warning" in sys.argv

    # Load secrets from environment
    token    = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id  = os.environ.get("TELEGRAM_CHAT_ID", "")
    dash_url = os.environ.get("DASHBOARD_URL", "https://your-dashboard.vercel.app")

    if not token or not chat_id:
        print("[ERROR] TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set.", file=sys.stderr)
        if not is_test:
            sys.exit(1)
        token   = "TEST_TOKEN"
        chat_id = "TEST_CHAT"

    # Load data
    history = load_json(HISTORY_FILE)
    stats   = load_json(STREAK_FILE)
    quality = load_json(QUALITY_FILE)
    config  = load_json(CONFIG_FILE)

    # ── Streak Break Warning ────────────────────────────────────────────────
    if is_streak_warning:
        today_str = now_ist().date().isoformat()
        today_msgs = history.get(today_str, [])
        if not today_msgs:
            warning_msg = (
                "⚠️ *AutoCommit Warning*\n\n"
                f"No commit yet today ({today_str}) and it's past 8pm IST!\n"
                f"Current streak: *{stats.get('current_streak', 0)} days*\n"
                "Run a manual commit from the dashboard NOW to protect your streak."
            )
            send_telegram_message(token, chat_id, warning_msg)
            print("[TG] Streak warning sent.")
        else:
            print("[TG] Commit already made today — no warning needed.")
        return

    # ── Weekly Report ────────────────────────────────────────────────────────
    monday, sunday = get_week_range()
    week_history = get_week_history(history, monday, sunday)
    week_commits  = sum(len(v) for v in week_history.values())
    week_rest     = sum(1 for v in week_history.values() if not v)
    next_sick     = get_next_sick_days(config)

    print(f"[TGNotifier] Generating weekly report for {monday} – {sunday}")
    print(f"[TGNotifier] Week commits: {week_commits} | Rest days: {week_rest}")

    # Build message
    message = build_weekly_message(
        stats, quality, week_commits, week_rest,
        monday, sunday, dash_url, next_sick
    )

    # Send text message first
    if not is_test:
        ok = send_telegram_message(token, chat_id, message)
        print(f"[TG] Message sent: {ok}")
    else:
        print(f"[TEST MODE] Message preview:\n{message}")

    # Generate and send PDF
    if REPORTLAB_AVAILABLE:
        pdf_bytes = generate_pdf_report(
            stats, week_history, quality, config, monday, sunday
        )
        if pdf_bytes:
            filename = f"autocommit_report_week{monday.isocalendar()[1]}.pdf"
            caption  = f"📊 AutoCommit Weekly Report · Week {monday.isocalendar()[1]}"
            if not is_test:
                ok = send_telegram_document(token, chat_id, pdf_bytes, caption, filename)
                print(f"[TG] PDF sent ({len(pdf_bytes):,} bytes): {ok}")
            else:
                print(f"[TEST MODE] PDF generated ({len(pdf_bytes):,} bytes) — not sent in test mode")
    else:
        print("[TGNotifier] ReportLab not available — skipping PDF attachment")

    print("[TGNotifier] Done.")


if __name__ == "__main__":
    main()
