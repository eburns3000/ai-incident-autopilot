"""SQLite database operations."""

import sqlite3
import json
import os
from datetime import datetime, timedelta
from typing import Optional
from contextlib import contextmanager

from app.config import get_settings
from app.models import AuditEvent, NormalizedIncident


class Database:
    """SQLite database wrapper for audit events and correlation."""

    def __init__(self, db_path: Optional[str] = None):
        """Initialize database connection."""
        if db_path is None:
            settings = get_settings()
            # Extract path from sqlite:/// URL
            db_path = settings.database_url.replace("sqlite:///", "")

        # Ensure directory exists
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self.db_path = db_path
        self._init_tables()

    @contextmanager
    def _get_connection(self):
        """Get a database connection with context management."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_tables(self):
        """Initialize database tables."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Audit events table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    jira_key TEXT,
                    component TEXT,
                    severity TEXT,
                    action TEXT NOT NULL,
                    status TEXT NOT NULL,
                    details TEXT,
                    dry_run INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Incidents table for correlation
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS incidents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    jira_key TEXT UNIQUE NOT NULL,
                    summary TEXT NOT NULL,
                    component TEXT,
                    environment TEXT,
                    created_at TEXT NOT NULL,
                    processed_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create indexes
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_incidents_component_created
                ON incidents(component, created_at)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_jira_key
                ON audit_events(jira_key)
            """)

    def insert_audit_event(self, event: AuditEvent) -> int:
        """Insert an audit event and return its ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO audit_events
                (timestamp, event_type, jira_key, component, severity, action, status, details, dry_run)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.timestamp.isoformat(),
                    event.event_type,
                    event.jira_key,
                    event.component,
                    event.severity,
                    event.action,
                    event.status,
                    json.dumps(event.details),
                    1 if event.dry_run else 0,
                ),
            )
            return cursor.lastrowid

    def insert_incident(self, incident: NormalizedIncident) -> int:
        """Insert or update an incident for correlation tracking."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO incidents
                (jira_key, summary, component, environment, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    incident.jira_key,
                    incident.summary,
                    incident.component,
                    incident.environment.value,
                    incident.created_at.isoformat(),
                ),
            )
            return cursor.lastrowid

    def find_correlated_incidents(
        self,
        component: str,
        summary: str,
        window_minutes: int = 30,
        exclude_key: Optional[str] = None,
    ) -> list[dict]:
        """Find potentially correlated incidents within time window."""
        cutoff = datetime.utcnow() - timedelta(minutes=window_minutes)

        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Simple correlation: same component within time window
            query = """
                SELECT jira_key, summary, component, environment, created_at
                FROM incidents
                WHERE component = ?
                AND created_at > ?
            """
            params = [component, cutoff.isoformat()]

            if exclude_key:
                query += " AND jira_key != ?"
                params.append(exclude_key)

            cursor.execute(query, params)
            rows = cursor.fetchall()

            return [dict(row) for row in rows]

    def get_recent_audit_events(self, limit: int = 100) -> list[dict]:
        """Get recent audit events."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM audit_events
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (limit,),
            )
            return [dict(row) for row in cursor.fetchall()]


# Singleton instance
_database: Optional[Database] = None


def get_database() -> Database:
    """Get or create database singleton."""
    global _database
    if _database is None:
        _database = Database()
    return _database
