"""
ResearchRadar — Telegram Bot notification system.

Sends formatted paper digests to the user's Telegram chat.
Replaces plyer notifications for phone delivery.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Dict, List, Optional

import requests

from app.core.models import Digest, Paper
from app.core.config import CATEGORY_LABELS

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_CONFIG_KEYS = ('telegram_bot_token', 'telegram_chat_id')


def _load_telegram_config(data_dir: str) -> dict:
    """Load Telegram config from settings.json."""
    path = os.path.join(data_dir, 'settings.json')
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _get_credentials(data_dir: str) -> tuple:
    """
    Get bot token and chat ID from settings or environment variables.

    Priority: env vars > settings.json
    """
    config = _load_telegram_config(data_dir)

    token = (
        os.getenv('TELEGRAM_BOT_TOKEN')
        or config.get('telegram_bot_token', '')
    )
    chat_id = (
        os.getenv('TELEGRAM_CHAT_ID')
        or config.get('telegram_chat_id', '')
    )
    return token, chat_id


# ---------------------------------------------------------------------------
# Message formatting
# ---------------------------------------------------------------------------

def _format_paper(rank: int, paper: Paper) -> str:
    """Format a single paper as a Telegram message block."""
    # Authors (first author + et al.)
    if paper.authors:
        if len(paper.authors) > 2:
            authors = f"{paper.authors[0]} et al."
        else:
            authors = ", ".join(paper.authors)
    else:
        authors = "Unknown"

    # Score badge
    score = f"{paper.composite_score:.2f}"

    lines = [
        f"*{rank}.* [{paper.title}]({paper.abstract_url})",
        f"   👤 _{authors}_",
        f"   📅 {paper.published_date.isoformat()}  •  📊 Score: {score}  •  📝 Citations: {paper.citation_count}",
    ]

    # LLM Summary (Structured)
    if paper.summary_llm:
        lines.append("")
        lines.append(f"🤖 *AI Summary:*")
        # Indent the summary for readability
        for slink in paper.summary_llm.split('\n'):
            if slink.strip():
                lines.append(f"   _{slink.strip()}_")

    if paper.pdf_url:
        lines.append("")
        lines.append(f"   📄 [PDF]({paper.pdf_url})")

    return "\n".join(lines)


def format_digest_message(digest: Digest) -> str:
    """Format a full digest as a Telegram-ready Markdown message."""
    lines = [
        "📡 *ResearchRadar — Daily Paper Digest*",
        f"📅 Week of {digest.week_start.isoformat()}",
        f"🕐 Generated: {digest.generated_at.strftime('%Y-%m-%d %H:%M UTC')}",
        "",
    ]

    total_papers = 0

    for cat_slug, papers in digest.papers.items():
        if not papers:
            continue

        cat_name = CATEGORY_LABELS.get(cat_slug, cat_slug.title())
        total_papers += len(papers)

        lines.append(f"━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"🔬 *{cat_name}* ({len(papers)} papers)")
        lines.append("")

        for i, paper in enumerate(papers, 1):
            lines.append(_format_paper(i, paper))
            lines.append("")

    if total_papers == 0:
        lines.append("_No new papers found this cycle. Check back tomorrow!_")

    if digest.videos:
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append("🎬 *While You Eat: AI Video Updates*")
        lines.append("")
        for vid in digest.videos:
            lines.append(f"• [{vid['title']}]({vid['url']})")
        lines.append("")

    # Summary footer
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append(
        f"📊 *Summary:* {digest.total_fetched} fetched → "
        f"{digest.total_ranked} ranked → {total_papers} delivered"
    )

    if digest.fetch_errors:
        lines.append(f"⚠️ {len(digest.fetch_errors)} non-fatal errors logged")

    return "\n".join(lines)


def format_short_notification(digest: Digest) -> str:
    """Format a short notification summary."""
    counts = []
    for cat_slug, papers in digest.papers.items():
        if papers:
            label = CATEGORY_LABELS.get(cat_slug, cat_slug.title())
            counts.append(f"{label}: {len(papers)}")

    if not counts:
        return "📡 ResearchRadar: No new papers found today."

    summary = " | ".join(counts)
    total = sum(len(p) for p in digest.papers.values())
    return f"📡 *ResearchRadar* — {total} new papers!\n{summary}"


# ---------------------------------------------------------------------------
# Sending
# ---------------------------------------------------------------------------

def send_message(
    token: str,
    chat_id: str,
    text: str,
    parse_mode: str = 'Markdown',
    disable_preview: bool = True,
) -> bool:
    """
    Send a message via Telegram Bot API.

    Returns True on success, False on failure (never raises).
    """
    url = f"https://api.telegram.org/bot{token}/sendMessage"

    # Telegram has a 4096 char limit per message
    if len(text) > 4000:
        return _send_chunked(token, chat_id, text, parse_mode, disable_preview)

    try:
        resp = requests.post(
            url,
            json={
                'chat_id': chat_id,
                'text': text,
                'parse_mode': parse_mode,
                'disable_web_page_preview': disable_preview,
            },
            timeout=15,
        )

        if resp.status_code == 200:
            data = resp.json()
            if data.get('ok'):
                logger.info('Telegram message sent to chat %s', chat_id)
                return True
            else:
                logger.error('Telegram API error: %s', data.get('description'))
                return False
        else:
            logger.error('Telegram HTTP %d: %s', resp.status_code, resp.text[:200])
            return False

    except requests.exceptions.RequestException as exc:
        logger.error('Telegram send failed: %s', exc)
        return False


def _send_chunked(
    token: str,
    chat_id: str,
    text: str,
    parse_mode: str,
    disable_preview: bool,
) -> bool:
    """Split long messages at section boundaries and send sequentially."""
    chunks = []
    current = ""

    for line in text.split("\n"):
        if len(current) + len(line) + 1 > 3800 and current:
            chunks.append(current)
            current = line
        else:
            current = current + "\n" + line if current else line

    if current:
        chunks.append(current)

    success = True
    for i, chunk in enumerate(chunks):
        if i > 0:
            import time
            time.sleep(0.5)  # Rate limiting courtesy

        ok = send_message(token, chat_id, chunk, parse_mode, disable_preview)
        if not ok:
            success = False

    return success


# ---------------------------------------------------------------------------
# High-level API
# ---------------------------------------------------------------------------

def send_digest_notification(digest: Digest, data_dir: str) -> bool:
    """
    Send the full digest to Telegram.

    Reads credentials from env vars or settings.json.
    Returns True on success, False on failure (never raises).
    """
    token, chat_id = _get_credentials(data_dir)

    if not token or not chat_id:
        logger.warning(
            'Telegram not configured — set TELEGRAM_BOT_TOKEN and '
            'TELEGRAM_CHAT_ID in environment or settings.json'
        )
        return False

    # Send short notification first
    short = format_short_notification(digest)
    send_message(token, chat_id, short)

    # Then send the full digest
    full = format_digest_message(digest)
    return send_message(token, chat_id, full)


def send_test_message(data_dir: str) -> bool:
    """Send a test message to verify Telegram setup."""
    token, chat_id = _get_credentials(data_dir)

    if not token or not chat_id:
        print("❌ Telegram not configured!")
        print("   Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in settings.json")
        print("   or as environment variables.")
        return False

    text = (
        "✅ *ResearchRadar — Test Message*\n\n"
        "Your Telegram notifications are working!\n"
        "You'll receive daily paper digests at your configured time."
    )
    success = send_message(token, chat_id, text)

    if success:
        print("✅ Test message sent! Check your Telegram.")
    else:
        print("❌ Failed to send test message. Check your bot token and chat ID.")

    return success
