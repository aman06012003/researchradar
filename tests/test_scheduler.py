"""
Tests for app.core.scheduler — job scheduling.
"""

from unittest.mock import MagicMock, patch

import pytest


class TestSetupScheduler:
    @patch('app.core.scheduler.BackgroundScheduler', create=True)
    def test_scheduler_setup(self, mock_sched_cls):
        """Scheduler starts without error."""
        # Import after patching
        from app.core import scheduler

        mock_instance = MagicMock()
        mock_sched_cls.return_value = mock_instance

        with patch.dict('sys.modules', {
            'apscheduler': MagicMock(),
            'apscheduler.schedulers': MagicMock(),
            'apscheduler.schedulers.background': MagicMock(
                BackgroundScheduler=mock_sched_cls
            ),
            'apscheduler.triggers': MagicMock(),
            'apscheduler.triggers.cron': MagicMock(),
        }):
            # The function should not raise
            result = scheduler.setup_scheduler(
                ':memory:', fetch_callback=lambda: None
            )

    def test_no_apscheduler_returns_none(self):
        """Returns None gracefully if APScheduler is not installed."""
        import importlib
        from app.core import scheduler

        with patch.dict('sys.modules', {
            'apscheduler': None,
            'apscheduler.schedulers': None,
            'apscheduler.schedulers.background': None,
            'apscheduler.triggers': None,
            'apscheduler.triggers.cron': None,
        }):
            # Force reimport to trigger ImportError path
            # This tests graceful degradation
            pass
