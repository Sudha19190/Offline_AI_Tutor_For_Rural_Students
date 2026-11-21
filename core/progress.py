"""Progress tracking in SQLite: students, quiz attempts, per-question results."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from core.config import SQLITE_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS quiz_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES students(id),
    subject TEXT NOT NULL,
    chapter TEXT NOT NULL,
    score INTEGER NOT NULL,
    total INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS question_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    attempt_id INTEGER NOT NULL REFERENCES quiz_attempts(id),
    question TEXT NOT NULL,
    correct INTEGER NOT NULL
);
"""


@contextmanager
def _db() -> Iterator[sqlite3.Connection]:
    """Open a connection, commit on success, roll back on error, always close."""
    conn = sqlite3.connect(str(SQLITE_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Create the tables if they don't exist yet."""
    with _db() as conn:
        conn.executescript(SCHEMA)


def get_or_create_student(name: str) -> int:
    """Return the student's id, creating the student on first use (name is case-insensitive)."""
    name = name.strip()
    if not name:
        raise ValueError("Student name cannot be empty.")
    with _db() as conn:
        conn.execute("INSERT OR IGNORE INTO students (name) VALUES (?)", (name,))
        row = conn.execute("SELECT id FROM students WHERE name = ?", (name,)).fetchone()
        return row["id"]


def save_attempt(student_id: int, subject: str, chapter: str, results: list[dict]) -> int:
    """Save one quiz attempt. `results` is a list of {'question': str, 'correct': bool}."""
    score = sum(1 for r in results if r["correct"])
    with _db() as conn:
        cur = conn.execute(
            "INSERT INTO quiz_attempts (student_id, subject, chapter, score, total) "
            "VALUES (?, ?, ?, ?, ?)",
            (student_id, subject, chapter, score, len(results)),
        )
        attempt_id = cur.lastrowid
        conn.executemany(
            "INSERT INTO question_results (attempt_id, question, correct) VALUES (?, ?, ?)",
            [(attempt_id, r["question"], int(r["correct"])) for r in results],
        )
    return attempt_id


def get_history(student_id: int, limit: int = 20) -> list[dict]:
    """Most recent quiz attempts first."""
    with _db() as conn:
        rows = conn.execute(
            "SELECT id, subject, chapter, score, total, created_at FROM quiz_attempts "
            "WHERE student_id = ? ORDER BY id DESC LIMIT ?",
            (student_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def get_chapter_accuracy(student_id: int) -> list[dict]:
    """Accuracy per chapter across all attempts (feeds the progress chart)."""
    with _db() as conn:
        rows = conn.execute(
            "SELECT subject, chapter, COUNT(*) AS attempts, SUM(score) AS score, SUM(total) AS total "
            "FROM quiz_attempts WHERE student_id = ? "
            "GROUP BY subject, chapter ORDER BY subject, chapter",
            (student_id,),
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["accuracy"] = round(100 * d["score"] / d["total"], 1) if d["total"] else 0.0
        out.append(d)
    return out


def get_progress(student_id: int) -> dict:
    """Everything the Progress page needs in one call."""
    with _db() as conn:
        row = conn.execute("SELECT name FROM students WHERE id = ?", (student_id,)).fetchone()
    return {
        "student_id": student_id,
        "student_name": row["name"] if row else None,
        "chapters": get_chapter_accuracy(student_id),
        "history": get_history(student_id),
    }


init_db()  # make sure app.db and its tables exist on import