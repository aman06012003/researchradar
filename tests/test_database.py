"""
Tests for app.core.database — SQLite wrapper.
"""

import sqlite3
from datetime import date, datetime
from unittest.mock import patch

import pytest

from app.core import database
from app.core.models import Digest, Paper


class TestInitialize:
    def test_creates_tables(self, tmp_db):
        conn = database.get_connection(tmp_db)
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        names = {r['name'] for r in tables}
        assert 'papers' in names
        assert 'digests' in names
        assert 'digest_papers' in names
        assert 'meta' in names
        conn.close()

    def test_sets_db_version(self, tmp_db):
        conn = database.get_connection(tmp_db)
        row = conn.execute(
            "SELECT value FROM meta WHERE key = 'db_version'"
        ).fetchone()
        assert row is not None
        assert int(row['value']) == 1
        conn.close()


class TestSaveAndLoadDigest:
    def test_round_trip(self, tmp_db, sample_digest):
        database.save_digest(tmp_db, sample_digest)
        loaded = database.get_latest_digest(tmp_db)

        assert loaded is not None
        assert loaded.digest_id == sample_digest.digest_id
        assert loaded.week_start == sample_digest.week_start
        assert loaded.total_fetched == 1
        assert 'ml' in loaded.papers
        assert len(loaded.papers['ml']) == 1
        assert loaded.papers['ml'][0].title == 'Attention Is All You Need (Again)'

    def test_load_empty_db(self, tmp_db):
        result = database.get_latest_digest(tmp_db)
        assert result is None


class TestBookmark:
    def test_toggle_bookmark(self, tmp_db, sample_digest):
        database.save_digest(tmp_db, sample_digest)
        paper_id = 'arxiv:2401.12345'

        # Initially False
        state = database.toggle_bookmark(tmp_db, paper_id)
        assert state is True

        # Toggle back
        state = database.toggle_bookmark(tmp_db, paper_id)
        assert state is False


class TestMarkRead:
    def test_mark_read(self, tmp_db, sample_digest):
        database.save_digest(tmp_db, sample_digest)
        database.mark_read(tmp_db, 'arxiv:2401.12345')

        papers = database.get_papers(tmp_db, 'ml', limit=10)
        assert len(papers) == 1
        assert papers[0].is_read is True


class TestGetPapers:
    def test_get_by_category(self, tmp_db, sample_digest):
        database.save_digest(tmp_db, sample_digest)
        papers = database.get_papers(tmp_db, 'ml')
        assert len(papers) == 1
        assert papers[0].app_category == 'ml'

    def test_get_nonexistent_category(self, tmp_db, sample_digest):
        database.save_digest(tmp_db, sample_digest)
        papers = database.get_papers(tmp_db, 'nonexistent')
        assert papers == []
