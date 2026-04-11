"""
ResearchRadar — Kivy Application Entry Point.

Initialises the database, scheduler, and screen manager.
All UI is defined via .kv files in app/ui/kv/.
"""

from __future__ import annotations

import json
import logging
import os
import sys

# ---------------------------------------------------------------------------
# Ensure the project root is on sys.path so 'app.*' imports work
# ---------------------------------------------------------------------------
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, SlideTransition

from app.core import database
from app.core.config import DB_PATH, logger
from app.core.models import Digest, UserProfile
from app.fetcher.fetch_pipeline import run_weekly_fetch

logger_main = logging.getLogger('researchradar.main')


class ResearchRadarApp(App):
    """Main Kivy application."""

    title = 'ResearchRadar'

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._db_path = ''
        self._profile = UserProfile()
        self._cached_digest = None

    @property
    def data_dir(self) -> str:
        """Writable data directory (platform-aware)."""
        if self._db_path:
            return os.path.dirname(self._db_path)
        try:
            from kivy.utils import platform as kv_platform
            if kv_platform == 'android':
                from android.storage import app_storage_path  # type: ignore
                d = app_storage_path()
            else:
                d = self.user_data_dir
        except Exception:
            d = os.path.join(os.path.expanduser('~'), '.researchradar')
        os.makedirs(d, exist_ok=True)
        return d

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def build(self):
        """Initialise DB, load settings, create screens."""

        # Database
        self._db_path = DB_PATH or os.path.join(self.data_dir, 'researchradar.db')
        database.initialize(self._db_path)
        logger_main.info('Database initialised at %s', self._db_path)

        # Load user settings
        self._load_settings()

        # Screen manager
        sm = ScreenManager(transition=SlideTransition())

        from app.ui.home_screen import HomeScreen
        from app.ui.detail_screen import DetailScreen
        from app.ui.settings_screen import SettingsScreen

        sm.add_widget(HomeScreen(name='home'))
        sm.add_widget(DetailScreen(name='detail'))
        sm.add_widget(SettingsScreen(name='settings'))

        # Start scheduler (non-blocking)
        self._start_scheduler()

        return sm

    def _start_scheduler(self):
        """Start the background fetch scheduler."""
        try:
            from app.core.scheduler import setup_scheduler, setup_android_alarm
            setup_scheduler(self._db_path)
            # Android alarm
            try:
                from kivy.utils import platform as kv_platform
                if kv_platform == 'android':
                    setup_android_alarm()
            except Exception:
                pass
        except Exception:
            logger_main.warning('Scheduler setup failed', exc_info=True)

    def _load_settings(self):
        """Load user settings from JSON file."""
        path = os.path.join(self.data_dir, 'settings.json')
        if not os.path.exists(path):
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                s = json.load(f)
            self._profile = UserProfile(
                interests=s.get('interests', self._profile.interests),
                weight_relevance=s.get('weight_relevance', 0.60),
                weight_citation=s.get('weight_citation', 0.30),
                weight_recency=s.get('weight_recency', 0.10),
                top_n_per_category=s.get('top_n', 5),
            )
        except Exception:
            logger_main.warning('Could not load settings', exc_info=True)

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def show_detail(self, category_slug: str):
        detail_screen = self.root.get_screen('detail')
        detail_screen.load_papers(category_slug)
        self.root.current = 'detail'

    def show_settings(self):
        self.root.current = 'settings'

    def go_home(self):
        self.root.current = 'home'

    # ------------------------------------------------------------------
    # Data access
    # ------------------------------------------------------------------

    def get_latest_digest(self):
        if self._cached_digest is None:
            self._cached_digest = database.get_latest_digest(self._db_path)
        return self._cached_digest

    def run_fetch(self):
        """Run the weekly fetch pipeline (call from background thread)."""
        self._cached_digest = None
        digest = run_weekly_fetch(self._db_path, self._profile)
        self._cached_digest = digest
        return digest

    def toggle_bookmark(self, paper_id: str) -> bool:
        result = database.toggle_bookmark(self._db_path, paper_id)
        self._cached_digest = None  # invalidate cache
        return result

    def apply_settings(self, settings: dict):
        """Apply settings from SettingsScreen."""
        self._profile = UserProfile(
            interests=settings.get('interests', self._profile.interests),
            weight_relevance=settings.get('weight_relevance', 0.60),
            weight_citation=settings.get('weight_citation', 0.30),
            weight_recency=settings.get('weight_recency', 0.10),
            top_n_per_category=settings.get('top_n', 5),
        )
        logger_main.info('Settings applied')


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    ResearchRadarApp().run()


if __name__ == '__main__':
    main()
