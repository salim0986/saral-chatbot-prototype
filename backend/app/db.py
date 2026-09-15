"""
SQLite database initialization and connection management.
Tables: papers, chunks, sessions, generations.
Uses aiosqlite for async access.
"""

import aiosqlite

from app.config import settings

_DB_PATH = settings.sqlite_db_path

CREATE_PAPERS_TABLE = """
CREATE TABLE IF NOT EXISTS papers (
    paper_id    TEXT PRIMARY KEY,
    filename    TEXT NOT NULL,
    sha256_hash TEXT NOT NULL UNIQUE,
    status      TEXT NOT NULL DEFAULT 'processing',  -- processing | ready | failed
    error_msg   TEXT,
    chunk_count INTEGER DEFAULT 0,
    is_presentation INTEGER DEFAULT 0,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_CHUNKS_TABLE = """
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id      TEXT PRIMARY KEY,
    paper_id      TEXT NOT NULL REFERENCES papers(paper_id),
    page_number   INTEGER NOT NULL,
    section_title TEXT,
    block_index   INTEGER NOT NULL,
    text          TEXT NOT NULL,
    contains_math INTEGER NOT NULL DEFAULT 0,  -- SQLite bool
    has_figure    INTEGER NOT NULL DEFAULT 0,
    figure_caption TEXT,
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_SESSIONS_TABLE = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id  TEXT PRIMARY KEY,
    paper_id    TEXT NOT NULL REFERENCES papers(paper_id),
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_GENERATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS generations (
    generation_id TEXT PRIMARY KEY,
    session_id    TEXT NOT NULL REFERENCES sessions(session_id),
    version       INTEGER NOT NULL DEFAULT 1,
    audience      TEXT NOT NULL,
    length        TEXT NOT NULL,
    style         TEXT NOT NULL,
    output_json   TEXT NOT NULL,  -- full structured JSON as text
    citation_coverage REAL,
    low_confidence    INTEGER DEFAULT 0,
    change_instruction TEXT,
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(session_id, version)
);
"""

CREATE_DELTAS_TABLE = """
CREATE TABLE IF NOT EXISTS deltas (
    delta_id      TEXT PRIMARY KEY,
    session_id    TEXT NOT NULL REFERENCES sessions(session_id),
    version_from  INTEGER NOT NULL,
    version_to    INTEGER NOT NULL,
    slide_number  INTEGER NOT NULL,
    old_text      TEXT NOT NULL,
    new_text      TEXT NOT NULL,
    diff_hunks    TEXT NOT NULL,  -- JSON
    reason        TEXT NOT NULL,
    provenance    TEXT,           -- JSON array of chunk_ids
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

ALL_TABLES = [
    CREATE_PAPERS_TABLE,
    CREATE_CHUNKS_TABLE,
    CREATE_SESSIONS_TABLE,
    CREATE_GENERATIONS_TABLE,
    CREATE_DELTAS_TABLE,
]


async def init_db() -> None:
    """Create all tables if they don't exist. Safe to call on every startup."""
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL;")  # safer for concurrent reads
        await db.execute("PRAGMA foreign_keys=ON;")
        for statement in ALL_TABLES:
            await db.execute(statement)
            
        # Migration: Add is_presentation if it doesn't exist
        try:
            await db.execute("ALTER TABLE papers ADD COLUMN is_presentation INTEGER DEFAULT 0;")
        except aiosqlite.OperationalError:
            pass # Column already exists
            
        await db.commit()


async def get_db() -> aiosqlite.Connection:
    """
    Dependency-injectable DB connection for FastAPI routes.
    Usage: db: aiosqlite.Connection = Depends(get_db)
    """
    async with aiosqlite.connect(_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys=ON;")
        yield db
