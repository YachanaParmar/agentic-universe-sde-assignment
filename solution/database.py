
import sqlite3
from pathlib import Path


DEFAULT_DB = Path("solution/ledger.db")


def connect(db_path=DEFAULT_DB):
    """Open the SQLite database and initialize its schema."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workflow_id TEXT NOT NULL,
            phone_hash TEXT NOT NULL,
            phone_last4 TEXT NOT NULL,
            batch_id TEXT NOT NULL,
            external_ref TEXT NOT NULL,
            fields_json TEXT NOT NULL DEFAULT '{}',
            UNIQUE(workflow_id, phone_hash)
        );

        CREATE TABLE IF NOT EXISTS lead_rows (
            source_file TEXT NOT NULL,
            row_number INTEGER NOT NULL,
            PRIMARY KEY(source_file, row_number)
        );

        CREATE TABLE IF NOT EXISTS rejections (
            source_file TEXT NOT NULL,
            workflow_id TEXT NOT NULL,
            batch_id TEXT NOT NULL,
            row_number INTEGER NOT NULL,
            reason TEXT NOT NULL,
            PRIMARY KEY(source_file, row_number)
        );

        CREATE TABLE IF NOT EXISTS events (
            event_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            workflow_id TEXT,
            call_id TEXT,
            occurred_at TEXT,
            phone_hash TEXT,
            payload_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS event_lines (
            source_file TEXT NOT NULL,
            line_number INTEGER NOT NULL,
            event_id TEXT,
            status TEXT NOT NULL,
            PRIMARY KEY(source_file, line_number)
        );

        CREATE INDEX IF NOT EXISTS idx_events_call
        ON events(workflow_id, call_id);

        CREATE INDEX IF NOT EXISTS idx_events_phone
        ON events(workflow_id, phone_hash);

        CREATE TABLE IF NOT EXISTS field_warnings (
            source_file TEXT NOT NULL,
            row_number INTEGER NOT NULL,
            field_name TEXT NOT NULL,
            PRIMARY KEY(source_file, row_number, field_name)
        );
        
CREATE TABLE IF NOT EXISTS duplicate_leads (
    source_file TEXT NOT NULL,
    row_number INTEGER NOT NULL,
    workflow_id TEXT NOT NULL,
    PRIMARY KEY (source_file, row_number)
);

    """)

    conn.commit()
    return conn
