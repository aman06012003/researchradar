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
    Send the full digest to all subscribers.

    Reads credentials from env vars or settings.json.
    Pulls subscriber list from database.
    """
    token, primary_chat_id = _get_credentials(data_dir)

    if not token:
        logger.warning('Telegram Bot Token not configured')
        return False

    db_path = os.path.join(data_dir, 'researchradar.db')
    from app.core import database
    subscribers = database.get_all_subscribers(db_path)

    # Always include the primary chat_id from config if it's set
    if primary_chat_id and primary_chat_id not in subscribers:
        subscribers.append(primary_chat_id)

    if not subscribers:
        logger.warning('No subscribers found in database or config')
        return False

    # Format messages once
    short = format_short_notification(digest)
    full = format_digest_message(digest)

    success_count = 0
    for chat_id in subscribers:
        # Send short notification first
        send_message(token, chat_id, short)
        # Then send the full digest
        if send_message(token, chat_id, full):
            success_count += 1

    logger.info('Broadcast digest to %d/%d subscribers', success_count, len(subscribers))
    return success_count > 0


def poll_updates(data_dir: str) -> None:
    """
    Check for new Telegram messages and handle /start or /stop commands.
    This should be called periodically (e.g. from the app worker).
    """
    token, _ = _get_credentials(data_dir)
    if not token:
        return

    db_path = os.path.join(data_dir, 'researchradar.db')
    from app.core import database

    # Use a persistent offset to avoid re-reading old messages
    offset_path = os.path.join(data_dir, '.tg_offset')
    offset = 0
    if os.path.exists(offset_path):
        try:
            with open(offset_path, 'r') as f:
                offset = int(f.read().strip())
        except Exception:
            pass

    url = f"https://api.telegram.org/bot{token}/getUpdates"
    try:
        resp = requests.get(url, params={'offset': offset, 'timeout': 1}, timeout=5)
        if resp.status_code != 200:
            return

        updates = resp.json().get('result', [])
        for up in updates:
            update_id = up['update_id']
            offset = update_id + 1
            
            msg = up.get('message')
            if not msg:
                continue
            
            chat_id = str(msg['chat']['id'])
            text = msg.get('text', '').strip().lower()

            if text == '/start':
                new = database.add_subscriber(db_path, chat_id)
                welcome = (
                    "📡 *Welcome to ResearchRadar!*\n\n"
                    "You've been subscribed to the daily paper digest. "
                    "You'll receive fresh updates every morning at 05:00 AM EEST."
                )
                if not new:
                    welcome = "📡 You are already subscribed to ResearchRadar!"
                
                send_message(token, chat_id, welcome)

                # FOR TESTING: Send the latest available digest immediately to new users
                if new:
                    latest = database.get_latest_digest(db_path)
                    if latest:
                        send_message(token, chat_id, "🚀 *Sending you the latest available digest immediately:*")
                        # Use split sending for the full digest
                        full = format_digest_message(latest)
                        send_message(token, chat_id, full)
            
            elif text == '/stop':
                database.remove_subscriber(db_path, chat_id)
                goodbye = "📡 You have been unsubscribed from ResearchRadar. Check back anytime!"
                send_message(token, chat_id, goodbye)

        # Save new offset
        with open(offset_path, 'w') as f:
            f.write(str(offset))

    except Exception as e:
        logger.error("Error polling Telegram updates: %s", e)


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
