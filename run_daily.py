"""
ResearchRadar — Standalone daily runner.

This script runs as a persistent background process on your PC.
It fetches papers and sends Telegram notifications on a schedule.

Usage:
    # First time: configure your Telegram bot
    python run_daily.py --setup

    # Test your Telegram connection
    python run_daily.py --test

    # Run once immediately (fetch + notify)
    python run_daily.py --now

    # Start the daily scheduler (runs forever, fetches at 5:00 AM)
    python run_daily.py

    # Custom time
    python run_daily.py --hour 8 --minute 30
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta

# Ensure project root on path
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.core.config import logger
from app.core import database
from app.core.models import UserProfile
from app.core.telegram_bot import send_digest_notification, send_test_message
from app.fetcher.fetch_pipeline import run_weekly_fetch

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_DATA_DIR = os.path.join(os.path.expanduser('~'), '.researchradar')
DEFAULT_HOUR = 5
DEFAULT_MINUTE = 0

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(name)s %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
log = logging.getLogger('researchradar.runner')


# ---------------------------------------------------------------------------
# Setup wizard
# ---------------------------------------------------------------------------

def interactive_setup(data_dir: str) -> None:
    """Walk the user through Telegram bot setup."""
    os.makedirs(data_dir, exist_ok=True)
    settings_path = os.path.join(data_dir, 'settings.json')

    print()
    print("=" * 55)
    print("  📡 ResearchRadar — Telegram Setup Wizard")
    print("=" * 55)
    print()
    print("  Follow these steps first:")
    print("  1. Open Telegram → search @BotFather")
    print("  2. Send /newbot → choose a name and username")
    print("  3. Copy the bot TOKEN you receive")
    print("  4. Open your new bot in Telegram and send /start")
    print("  5. Visit this URL in your browser:")
    print("     https://api.telegram.org/bot<TOKEN>/getUpdates")
    print("     (replace <TOKEN> with your actual token)")
    print("  6. Find your chat_id in the JSON response")
    print()

    token = input("  Enter your bot TOKEN: ").strip()
    chat_id = input("  Enter your chat_id:   ").strip()

    if not token or not chat_id:
        print("\n  ❌ Both token and chat_id are required!")
        return

    # Load existing settings or create new
    settings = {}
    if os.path.exists(settings_path):
        try:
            with open(settings_path, 'r', encoding='utf-8') as f:
                settings = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass

    settings['telegram_bot_token'] = token
    settings['telegram_chat_id'] = chat_id

    with open(settings_path, 'w', encoding='utf-8') as f:
        json.dump(settings, f, indent=2)

    print(f"\n  ✅ Settings saved to {settings_path}")
    print("  Run 'python run_daily.py --test' to verify.\n")


# ---------------------------------------------------------------------------
# Fetch + Notify
# ---------------------------------------------------------------------------

def run_fetch_and_notify(data_dir: str) -> None:
    """Run the full pipeline: fetch → rank → save → notify via Telegram."""
    db_path = os.path.join(data_dir, 'researchradar.db')
    database.initialize(db_path)

    # Load user profile from settings
    profile = _load_profile(data_dir)

    log.info("Checking for new subscribers...")
    from app.core.telegram_bot import poll_updates
    poll_updates(data_dir)

    log.info("Starting paper fetch...")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔄 Fetching papers...")

    digest = run_weekly_fetch(db_path, profile)

    total = sum(len(p) for p in digest.papers.values())
    print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Found {digest.total_fetched} papers, ranked {total} for delivery")

    if digest.fetch_errors:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️  {len(digest.fetch_errors)} non-fatal errors")
        for err in digest.fetch_errors[:3]:
            print(f"   → {err}")

    # Send to Telegram
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 📲 Sending to Telegram...")
    success = send_digest_notification(digest, data_dir)

    if success:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Telegram notification sent!")
    else:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️  Telegram send failed (check config)")


def _load_profile(data_dir: str) -> UserProfile:
    """Load user profile from settings.json."""
    path = os.path.join(data_dir, 'settings.json')
    if not os.path.exists(path):
        return UserProfile()
    try:
        with open(path, 'r', encoding='utf-8') as f:
            s = json.load(f)
        return UserProfile(
            interests=s.get('interests', UserProfile().interests),
            weight_relevance=s.get('weight_relevance', 0.60),
            weight_citation=s.get('weight_citation', 0.30),
            weight_recency=s.get('weight_recency', 0.10),
            top_n_per_category=s.get('top_n', 5),
        )
    except Exception:
        return UserProfile()


# ---------------------------------------------------------------------------
# Scheduler loop
# ---------------------------------------------------------------------------

def run_scheduler(data_dir: str, hour: int, minute: int) -> None:
    """
    Simple scheduler that runs forever and triggers fetch+notify
    at the specified time every day.

    No APScheduler dependency — just a sleep loop.
    """
    print()
    print("=" * 55)
    print("  📡 ResearchRadar — Daily Scheduler")
    print("=" * 55)
    print(f"  ⏰ Fetch time: {hour:02d}:{minute:02d} every day")
    print(f"  📂 Data dir:   {data_dir}")
    print(f"  🕐 Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print("  Press Ctrl+C to stop.")
    print("=" * 55)
    print()

    while True:
        now = datetime.now()
        # Calculate next run time
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)

        wait_seconds = (target - now).total_seconds()
        hours_left = wait_seconds / 3600

        print(f"[{now.strftime('%H:%M:%S')}] 💤 Next fetch in {hours_left:.1f} hours "
              f"(at {target.strftime('%Y-%m-%d %H:%M')})")

        try:
            time.sleep(wait_seconds)
        except KeyboardInterrupt:
            print("\n\n  👋 Scheduler stopped. Goodbye!")
            return

        # Time to fetch!
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] ⏰ Time to fetch papers!\n")
        try:
            run_fetch_and_notify(data_dir)
        except Exception:
            log.exception("Fetch cycle failed (will retry tomorrow)")
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Fetch failed — will retry tomorrow")

        print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='ResearchRadar — Daily AI & Neuroscience Paper Notifications',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_daily.py --setup          Set up Telegram bot
  python run_daily.py --test           Test Telegram connection
  python run_daily.py --now            Fetch and notify immediately
  python run_daily.py                  Start daily scheduler (5:00 AM)
  python run_daily.py --hour 8         Start scheduler for 8:00 AM
        """,
    )

    parser.add_argument(
        '--setup', action='store_true',
        help='Interactive Telegram bot setup wizard',
    )
    parser.add_argument(
        '--test', action='store_true',
        help='Send a test message to verify Telegram setup',
    )
    parser.add_argument(
        '--now', action='store_true',
        help='Fetch papers and send notification immediately',
    )
    parser.add_argument(
        '--poll', action='store_true',
        help='Listen for /start commands and exit',
    )
    parser.add_argument(
        '--hour', type=int, default=DEFAULT_HOUR,
        help=f'Hour to fetch (0-23, default: {DEFAULT_HOUR})',
    )
    parser.add_argument(
        '--minute', type=int, default=DEFAULT_MINUTE,
        help=f'Minute to fetch (0-59, default: {DEFAULT_MINUTE})',
    )
    parser.add_argument(
        '--data-dir', type=str, default=DEFAULT_DATA_DIR,
        help=f'Data directory (default: {DEFAULT_DATA_DIR})',
    )

    args = parser.parse_args()
    data_dir = args.data_dir
    os.makedirs(data_dir, exist_ok=True)

    if args.setup:
        interactive_setup(data_dir)
        return

    if args.test:
        send_test_message(data_dir)
        return

    if args.poll:
        from app.core.telegram_bot import poll_updates
        poll_updates(data_dir)
        return

    if args.now:
        run_fetch_and_notify(data_dir)
        return

    # Default: run the daily scheduler
    run_scheduler(data_dir, args.hour, args.minute)


if __name__ == '__main__':
    main()
