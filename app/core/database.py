"""
ResearchRadar — SQLite wrapper with migrations.

All write operations use parameterised queries exclusively.
Never format SQL strings with user or API data.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from datetime import date, datetime
from typing import List, Optional

from app.core.config import DB_VERSION
from app.core.models import Digest, Paper

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema DDL (Version 1)
# ---------------------------------------------------------------------------

_SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS papers (
    paper_id        TEXT PRIMARY KEY,
    source          TEXT NOT NULL,
    title           TEXT NOT NULL,
    abstract        TEXT NOT NULL,
    summary_llm     TEXT,
    authors         TEXT NOT NULL,
    published_date  TEXT NOT NULL,
    categories      TEXT NOT NULL,
    app_category    TEXT NOT NULL,
    pdf_url         TEXT,
    abstract_url    TEXT NOT NULL,
    citation_count  INTEGER DEFAULT 0,
    relevance_score REAL    DEFAULT 0.0,
    composite_score REAL    DEFAULT 0.0,
    fetched_at      TEXT NOT NULL,
    is_bookmarked   INTEGER DEFAULT 0,
    is_read         INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS digests (
    digest_id     TEXT PRIMARY KEY,
    week_start    TEXT NOT NULL,
    generated_at  TEXT NOT NULL,
    total_fetched INTEGER,
    total_ranked  INTEGER,
    fetch_errors  TEXT,
    videos_json   TEXT
);

CREATE TABLE IF NOT EXISTS digest_papers (
    digest_id  TEXT NOT NULL,
    paper_id   TEXT NOT NULL,
    rank_order INTEGER NOT NULL,
    PRIMARY KEY (digest_id, paper_id),
    FOREIGN KEY (digest_id) REFERENCES digests(digest_id),
    FOREIGN KEY (paper_id)  REFERENCES papers(paper_id)
);

CREATE TABLE IF NOT EXISTS subscribers (
    chat_id TEXT PRIMARY KEY,
    joined_at TEXT NOT NULL
);
"""

# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

_DB_RETRY_MAX = 3
_DB_RETRY_SLEEP = 0.5


def get_connection(db_path: str) -> sqlite3.Connection:
    """Return a connection with row_factory and WAL mode enabled."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA foreign_keys=ON')
    return conn


def _retry_on_locked(func):
    """Decorator: retry up to _DB_RETRY_MAX times on 'database is locked'."""
    def wrapper(*args, **kwargs):
        for attempt in range(_DB_RETRY_MAX):
            try:
                return func(*args, **kwargs)
            except sqlite3.OperationalError as exc:
                if 'database is locked' in str(exc) and attempt < _DB_RETRY_MAX - 1:
                    logger.warning('DB locked — retrying (%d/%d)', attempt + 1, _DB_RETRY_MAX)
                    time.sleep(_DB_RETRY_SLEEP)
                else:
                    raise
    return wrapper


# ---------------------------------------------------------------------------
# Initialisation & Migrations
# ---------------------------------------------------------------------------

def initialize(db_path: str) -> None:
    """Create tables and run any pending migrations."""
    conn = get_connection(db_path)
    try:
        conn.executescript(_SCHEMA_V1)
        # Set version if not present
        row = conn.execute(
            "SELECT value FROM meta WHERE key = 'db_version'"
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO meta (key, value) VALUES ('db_version', ?)",
                (str(DB_VERSION),),
            )
        else:
            current = int(row['value'])
            if current < DB_VERSION:
                run_migrations(conn, current, DB_VERSION)
        
        # Recovery: Ensure 'subscribers' exists even if migrations were skipped 
        # (Fixes a rare race condition where DB_VERSION was updated before table creation)
        try:
            conn.execute("SELECT 1 FROM subscribers LIMIT 1")
        except sqlite3.OperationalError:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS subscribers (
                    chat_id TEXT PRIMARY KEY,
                    joined_at TEXT NOT NULL
                )
            """)
            logger.info('Recovery: Created missing subscribers table.')

        conn.commit()
    finally:
        conn.close()


def run_migrations(conn: sqlite3.Connection, current: int, target: int) -> None:
    """Apply sequential migrations from *current* to *target* version."""
    logger.info('Migrating DB from v%d to v%d', current, target)
    
    if current < 2:
        try:
            conn.execute("ALTER TABLE papers ADD COLUMN summary_llm TEXT")
            logger.info('V2 Migration: Added summary_llm column to papers table.')
        except sqlite3.OperationalError as e:
            if 'duplicate column name' in str(e).lower():
                pass # Already exists
            else:
                raise

    if current < 3:
        try:
            conn.execute("ALTER TABLE digests ADD COLUMN videos_json TEXT")
            logger.info('V3 Migration: Added videos_json column to digests table.')
        except sqlite3.OperationalError as e:
            if 'duplicate column name' in str(e).lower():
                pass # Already exists
            else:
                raise

    if current < 4:
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS subscribers (
                    chat_id TEXT PRIMARY KEY,
                    joined_at TEXT NOT NULL
                )
            """)
            logger.info('V4 Migration: Created subscribers table.')
        except sqlite3.OperationalError:
            raise

    conn.execute(
        "UPDATE meta SET value = ? WHERE key = 'db_version'",
        (str(target),),
    )


# ---------------------------------------------------------------------------
# Paper helpers
# ---------------------------------------------------------------------------

def _paper_to_row(paper: Paper) -> tuple:
    return (
        paper.paper_id,
        paper.source,
        paper.title,
        paper.abstract,
        paper.summary_llm,
        json.dumps(paper.authors),
        paper.published_date.isoformat(),
        json.dumps(paper.categories),
        paper.app_category,
        paper.pdf_url,
        paper.abstract_url,
        paper.citation_count,
        paper.relevance_score,
        paper.composite_score,
        paper.fetched_at.isoformat(),
        int(paper.is_bookmarked),
        int(paper.is_read),
    )


def _row_to_paper(row: sqlite3.Row) -> Paper:
    return Paper(
        paper_id=row['paper_id'],
        source=row['source'],
        title=row['title'],
        abstract=row['abstract'],
        summary_llm=row['summary_llm'],
        authors=json.loads(row['authors']),
        published_date=date.fromisoformat(row['published_date']),
        categories=json.loads(row['categories']),
        app_category=row['app_category'],
        pdf_url=row['pdf_url'],
        abstract_url=row['abstract_url'],
        citation_count=row['citation_count'],
        relevance_score=row['relevance_score'],
        composite_score=row['composite_score'],
        fetched_at=datetime.fromisoformat(row['fetched_at']),
        is_bookmarked=bool(row['is_bookmarked']),
        is_read=bool(row['is_read']),
    )


# ---------------------------------------------------------------------------
# CRUD Operations
# ---------------------------------------------------------------------------

@_retry_on_locked
def save_digest(db_path: str, digest: Digest) -> None:
    """Transactional insert of a digest + all its papers."""
    conn = get_connection(db_path)
    try:
        conn.execute('BEGIN')

        # Insert digest record
        conn.execute(
            """INSERT OR REPLACE INTO digests
               (digest_id, week_start, generated_at, total_fetched,
                total_ranked, fetch_errors, videos_json)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                digest.digest_id,
                digest.week_start.isoformat(),
                digest.generated_at.isoformat(),
                digest.total_fetched,
                digest.total_ranked,
                json.dumps(digest.fetch_errors),
                json.dumps(digest.videos),
            ),
        )

        # Insert papers and link to digest
        rank = 0
        for category, papers in digest.papers.items():
            for paper in papers:
                conn.execute(
                    """INSERT OR REPLACE INTO papers
                       (paper_id, source, title, abstract, summary_llm, authors,
                        published_date, categories, app_category, pdf_url,
                        abstract_url, citation_count, relevance_score,
                        composite_score, fetched_at, is_bookmarked, is_read)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    _paper_to_row(paper),
                )
                rank += 1
                conn.execute(
                    """INSERT OR REPLACE INTO digest_papers
                       (digest_id, paper_id, rank_order) VALUES (?, ?, ?)""",
                    (digest.digest_id, paper.paper_id, rank),
                )

        conn.commit()
        logger.info('Saved digest %s with %d papers', digest.digest_id, rank)
    except Exception:
        conn.rollback()
        logger.exception('Failed to save digest — rolled back')
        raise
    finally:
        conn.close()


@_retry_on_locked
def get_latest_digest(db_path: str) -> Optional[Digest]:
    """Load the most recent digest."""
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            'SELECT * FROM digests ORDER BY generated_at DESC LIMIT 1'
        ).fetchone()
        if row is None:
            return None

        digest = Digest(
            digest_id=row['digest_id'],
            week_start=date.fromisoformat(row['week_start']),
            generated_at=datetime.fromisoformat(row['generated_at']),
            total_fetched=row['total_fetched'],
            total_ranked=row['total_ranked'],
            fetch_errors=json.loads(row['fetch_errors'] or '[]'),
            videos=json.loads(row.get('videos_json', '[]')),
        )

        # Load papers linked to this digest
        paper_rows = conn.execute(
            """SELECT p.* FROM papers p
               INNER JOIN digest_papers dp ON p.paper_id = dp.paper_id
               WHERE dp.digest_id = ?
               ORDER BY dp.rank_order""",
            (digest.digest_id,),
        ).fetchall()

        papers_by_cat: dict = {}
        for pr in paper_rows:
            paper = _row_to_paper(pr)
            papers_by_cat.setdefault(paper.app_category, []).append(paper)
        digest.papers = papers_by_cat
        return digest
    finally:
        conn.close()


@_retry_on_locked
def get_papers(db_path: str, category: str, limit: int = 10) -> List[Paper]:
    """Get papers for a category, ordered by composite score."""
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """SELECT * FROM papers
               WHERE app_category = ?
               ORDER BY composite_score DESC
               LIMIT ?""",
            (category, limit),
        ).fetchall()
        return [_row_to_paper(r) for r in rows]
    finally:
        conn.close()


@_retry_on_locked
def toggle_bookmark(db_path: str, paper_id: str) -> bool:
    """Toggle bookmark state; returns the new state."""
    conn = get_connection(db_path)
    try:
        conn.execute(
            """UPDATE papers
               SET is_bookmarked = CASE WHEN is_bookmarked = 0 THEN 1 ELSE 0 END
               WHERE paper_id = ?""",
            (paper_id,),
        )
        conn.commit()
        row = conn.execute(
            'SELECT is_bookmarked FROM papers WHERE paper_id = ?',
            (paper_id,),
        ).fetchone()
        return bool(row['is_bookmarked']) if row else False
    finally:
        conn.close()


@_retry_on_locked
def mark_read(db_path: str, paper_id: str) -> None:
    """Mark a paper as read."""
    conn = get_connection(db_path)
    try:
        conn.execute(
            'UPDATE papers SET is_read = 1 WHERE paper_id = ?',
            (paper_id,),
        )
        conn.commit()
    finally:
        conn.close()


@_retry_on_locked
def get_bookmarked_papers(db_path: str) -> List[Paper]:
    """Return all bookmarked papers ordered by composite score."""
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """SELECT * FROM papers
               WHERE is_bookmarked = 1
               ORDER BY composite_score DESC"""
        ).fetchall()
        return [_row_to_paper(r) for r in rows]
    finally:
        conn.close()

# ---------------------------------------------------------------------------
# Subscriber Management
# ---------------------------------------------------------------------------

@_retry_on_locked
def add_subscriber(db_path: str, chat_id: str) -> bool:
    """Add a new subscriber if they don't exist. Returns True if new."""
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            'SELECT chat_id FROM subscribers WHERE chat_id = ?',
            (chat_id,)
        ).fetchone()
        if row:
            return False
        
        conn.execute(
            'INSERT INTO subscribers (chat_id, joined_at) VALUES (?, ?)',
            (chat_id, datetime.now().isoformat())
        )
        conn.commit()
        return True
    finally:
        conn.close()


@_retry_on_locked
def get_all_subscribers(db_path: str) -> List[str]:
    """Get all registered Telegram chat IDs."""
    conn = get_connection(db_path)
    try:
        rows = conn.execute('SELECT chat_id FROM subscribers').fetchall()
        return [str(r['chat_id']) for r in rows]
    finally:
        conn.close()


@_retry_on_locked
def remove_subscriber(db_path: str, chat_id: str) -> None:
    """Remove a subscriber ($stop)."""
    conn = get_connection(db_path)
    try:
        conn.execute('DELETE FROM subscribers WHERE chat_id = ?', (chat_id,))
        conn.commit()
    finally:
        conn.close()
