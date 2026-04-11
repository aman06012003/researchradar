"""
ResearchRadar — Job scheduling.

Uses APScheduler with CronTrigger for the weekly fetch job.
On Android, uses AlarmManager via pyjnius to wake the app if backgrounded.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from app.core.config import SCHEDULE_DAY, SCHEDULE_HOUR, SCHEDULE_MINUTE

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# APScheduler setup
# ---------------------------------------------------------------------------

def setup_scheduler(
    db_path: str,
    fetch_callback: Optional[Callable] = None,
) -> object:
    """
    Initialise and start the APScheduler BackgroundScheduler.

    - CronTrigger: every Sunday at 08:00 local time.
    - misfire_grace_time: 3600s (fires within 1 hour of missed time).
    - max_instances: 1 (prevent overlapping fetch jobs).
    """
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        logger.warning('APScheduler not installed — scheduler disabled')
        return None

    if fetch_callback is None:
        from app.fetcher.fetch_pipeline import run_weekly_fetch

        def _default_callback():
            run_weekly_fetch(db_path)

        fetch_callback = _default_callback

    scheduler = BackgroundScheduler()

    # Try to use SQLAlchemy job store for persistence
    try:
        from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
        jobstore = SQLAlchemyJobStore(url=f'sqlite:///{db_path}')
        scheduler.add_jobstore(jobstore, 'default')
    except ImportError:
        logger.info('SQLAlchemy not available — using memory job store')

    scheduler.add_job(
        fetch_callback,
        CronTrigger(
            day_of_week=SCHEDULE_DAY,
            hour=SCHEDULE_HOUR,
            minute=SCHEDULE_MINUTE,
        ),
        id='weekly_fetch',
        name='Weekly Paper Fetch',
        misfire_grace_time=3600,
        max_instances=1,
        replace_existing=True,
    )

    try:
        scheduler.start()
        logger.info(
            'Scheduler started — next fetch: %s %02d:%02d',
            SCHEDULE_DAY.upper(), SCHEDULE_HOUR, SCHEDULE_MINUTE,
        )
    except Exception as exc:
        # SchedulerAlreadyRunningError or other — log and continue
        logger.warning('Scheduler start issue (non-fatal): %s', exc)

    return scheduler


# ---------------------------------------------------------------------------
# Android AlarmManager integration (Android-only)
# ---------------------------------------------------------------------------

def setup_android_alarm() -> None:
    """
    Set a repeating alarm via Android's AlarmManager to wake the app
    every Sunday at 08:00.

    Only called on Android. Guarded by platform check in main.py.
    """
    try:
        from jnius import autoclass

        Context = autoclass('android.content.Context')
        Intent = autoclass('android.content.Intent')
        PendingIntent = autoclass('android.app.PendingIntent')
        AlarmManager = autoclass('android.app.AlarmManager')
        Calendar = autoclass('java.util.Calendar')

        from android import mActivity  # type: ignore[import]

        context = mActivity.getApplicationContext()
        alarm_mgr = context.getSystemService(Context.ALARM_SERVICE)

        intent = Intent(context, mActivity.getClass())
        pending = PendingIntent.getActivity(
            context, 0, intent,
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE,
        )

        # Set weekly repeating alarm
        cal = Calendar.getInstance()
        cal.set(Calendar.DAY_OF_WEEK, Calendar.SUNDAY)
        cal.set(Calendar.HOUR_OF_DAY, SCHEDULE_HOUR)
        cal.set(Calendar.MINUTE, SCHEDULE_MINUTE)
        cal.set(Calendar.SECOND, 0)

        interval_week = 7 * 24 * 60 * 60 * 1000  # ms

        alarm_mgr.setExactAndAllowWhileIdle(
            AlarmManager.RTC_WAKEUP,
            cal.getTimeInMillis(),
            pending,
        )
        logger.info('Android AlarmManager set for Sunday %02d:%02d',
                     SCHEDULE_HOUR, SCHEDULE_MINUTE)

    except ImportError:
        logger.debug('pyjnius not available — not on Android')
    except Exception:
        logger.warning('Failed to set Android alarm', exc_info=True)
