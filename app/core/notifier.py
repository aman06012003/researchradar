"""
ResearchRadar — Notification wrapper.

Primary: Telegram Bot notifications (works on any phone).
Fallback: plyer local notifications (desktop / Kivy builds).
"""

from __future__ import annotations

import logging
import os
import platform
from typing import Optional

from app.core.models import Digest

logger = logging.getLogger(__name__)


def send_digest_notification(digest: Digest, data_dir: str = '') -> None:
    """
    Send a notification about the latest digest.

    Tries Telegram first (phone notifications), then falls back to plyer.
    """
    # Try Telegram first
    if data_dir:
        try:
            from app.core.telegram_bot import send_digest_notification as tg_send
            if tg_send(digest, data_dir):
                return  # Telegram succeeded
        except ImportError:
            pass
        except Exception:
            logger.debug('Telegram notification failed', exc_info=True)

    # Fallback: plyer local notification
    _send_plyer_notification(digest)


def _send_plyer_notification(digest: Digest) -> None:
    """Send a local notification via plyer (desktop only)."""
    # Skip on Linux if not desktop (Hugging Face / Docker)
    if platform.system() == 'Linux' and not os.environ.get('DISPLAY'):
        logger.info('Environment is headless Linux — skipping desktop notification')
        return

    try:
        from plyer import notification
    except ImportError:
        logger.info('plyer not installed — skipping notification')
        return

    lines = []
    top_title = ''
    for cat, papers in digest.papers.items():
        count = len(papers)
        label = cat.replace('_', ' ').title()
        lines.append(f'{label}: {count} paper{"s" if count != 1 else ""}')
        if papers and not top_title:
            top_title = papers[0].title

    if not lines:
        lines.append('No new papers this week.')

    message = '\n'.join(lines)
    if top_title:
        if len(top_title) > 80:
            top_title = top_title[:77] + '...'
        message += f'\n\n📄 {top_title}'

    try:
        notification.notify(
            title='ResearchRadar — New Papers!',
            message=message,
            app_name='ResearchRadar',
            timeout=10,
        )
        logger.info('Notification sent for digest %s', digest.digest_id)
    except NotImplementedError:
        logger.warning('Notifications not supported on this platform')
    except Exception:
        logger.warning('Notification failed', exc_info=True)
