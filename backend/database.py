"""Database access and repository initialization using SQLite.
Implements the UML Domain Model and schema requirements for the English-only edition.
"""
import os
import json
import hashlib
import sqlite3
import aiosqlite
from datetime import datetime
from typing import Optional, List, Dict, Any
from backend.config import settings

DB_PATH = settings.DATABASE_PATH


def hash_token(token: str) -> str:
    """Returns SHA256 hex digest for sensitive tokens and keys."""
    return hashlib.sha256(token.strip().encode("utf-8")).hexdigest()


CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS patients (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    device_token_hash TEXT NOT NULL,
    preferred_script TEXT DEFAULT 'en',
    email TEXT,
    doctor_name TEXT,
    doctor_email TEXT,
    doctor_specialty TEXT,
    doctor_phone TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pairing_keys (
    key_hash TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    used_at TIMESTAMP,
    FOREIGN KEY(patient_id) REFERENCES patients(id)
);

CREATE TABLE IF NOT EXISTS caregiver_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id TEXT NOT NULL,
    caregiver_name TEXT NOT NULL,
    token_hash TEXT,
    status TEXT NOT NULL, -- 'pending', 'active', 'declined', 'revoked'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    revoked_at TIMESTAMP,
    FOREIGN KEY(patient_id) REFERENCES patients(id)
);

CREATE TABLE IF NOT EXISTS discharge_summaries (
    id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL,
    title TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(patient_id) REFERENCES patients(id)
);

CREATE TABLE IF NOT EXISTS summary_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    summary_id TEXT NOT NULL,
    line_id TEXT NOT NULL,
    text TEXT NOT NULL,
    FOREIGN KEY(summary_id) REFERENCES discharge_summaries(id)
);

CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id TEXT NOT NULL,
    medicine_name TEXT NOT NULL,
    dose_text TEXT NOT NULL,
    timing_text TEXT NOT NULL,
    status TEXT DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(patient_id) REFERENCES patients(id)
);

CREATE TABLE IF NOT EXISTS reminder_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reminder_id INTEGER NOT NULL,
    patient_id TEXT NOT NULL,
    scheduled_time TIMESTAMP NOT NULL,
    action TEXT NOT NULL, -- 'taken', 'snoozed', 'missed'
    actual_intake_time TIMESTAMP,
    intake_notes TEXT,
    logged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(reminder_id) REFERENCES reminders(id),
    FOREIGN KEY(patient_id) REFERENCES patients(id)
);

CREATE TABLE IF NOT EXISTS conversation_memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id TEXT NOT NULL,
    user_query TEXT NOT NULL,
    assistant_response TEXT NOT NULL,
    intent TEXT,
    metadata TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(patient_id) REFERENCES patients(id)
);

CREATE TABLE IF NOT EXISTS prescriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id TEXT NOT NULL,
    added_by TEXT NOT NULL, -- 'caregiver' or 'patient'
    author_name TEXT NOT NULL,
    medicine_name TEXT NOT NULL,
    dose_text TEXT NOT NULL,
    timing_text TEXT NOT NULL,
    instructions TEXT,
    status TEXT DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(patient_id) REFERENCES patients(id)
);

CREATE TABLE IF NOT EXISTS appointments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id TEXT NOT NULL,
    slot_start TEXT NOT NULL,
    status TEXT DEFAULT 'booked',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(patient_id) REFERENCES patients(id)
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id TEXT NOT NULL,
    type TEXT NOT NULL,
    priority TEXT NOT NULL,
    transcript_excerpt TEXT,
    action_taken TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    handled_at TIMESTAMP,
    FOREIGN KEY(patient_id) REFERENCES patients(id)
);

CREATE TABLE IF NOT EXISTS review_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id TEXT NOT NULL,
    question TEXT NOT NULL,
    attempted_answer TEXT,
    cited_line_ids TEXT,
    reason TEXT,
    clinician_note TEXT,
    status TEXT DEFAULT 'pending', -- 'pending', 'reviewed'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(patient_id) REFERENCES patients(id)
);

CREATE TABLE IF NOT EXISTS turn_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    transcript TEXT,
    intent TEXT,
    red_flag INTEGER,
    cited_line_ids TEXT,
    confidence REAL,
    action_taken TEXT,
    stage_latencies TEXT,
    provider_name_internal TEXT
);

CREATE TABLE IF NOT EXISTS pending_actions (
    id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL,
    action_type TEXT NOT NULL, -- 'reminder', 'appointment'
    action_data TEXT NOT NULL,
    echo_back_text TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'pending' -- 'pending', 'confirmed', 'rejected'
);

CREATE TABLE IF NOT EXISTS rate_limit_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_ip TEXT NOT NULL,
    timestamp REAL NOT NULL,
    action TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS doctors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id TEXT NOT NULL,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    specialty TEXT,
    phone TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(patient_id) REFERENCES patients(id)
);

CREATE TABLE IF NOT EXISTS doctor_emails (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id TEXT NOT NULL,
    doctor_name TEXT NOT NULL,
    doctor_email TEXT NOT NULL,
    patient_email TEXT,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    health_issue TEXT NOT NULL,
    prescriptions_summary TEXT,
    status TEXT DEFAULT 'draft', -- 'draft', 'approved', 'sent', 'declined'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sent_at TIMESTAMP,
    FOREIGN KEY(patient_id) REFERENCES patients(id)
);
"""


def init_db_sync():
    """Synchronous initialization of the SQLite database tables and seed data."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.executescript(CREATE_TABLES_SQL)

    # Migrate columns if patients table existed previously
    cursor.execute("PRAGMA table_info(patients)")
    existing_cols = [row[1] for row in cursor.fetchall()]
    new_cols = [
        ("email", "TEXT"),
        ("doctor_name", "TEXT"),
        ("doctor_email", "TEXT"),
        ("doctor_specialty", "TEXT"),
        ("doctor_phone", "TEXT")
    ]
    for col_name, col_type in new_cols:
        if col_name not in existing_cols:
            try:
                cursor.execute(f"ALTER TABLE patients ADD COLUMN {col_name} {col_type}")
            except sqlite3.OperationalError:
                pass

    # Migrate columns if reminder_logs table existed previously
    cursor.execute("PRAGMA table_info(reminder_logs)")
    existing_r_cols = [row[1] for row in cursor.fetchall()]
    new_r_cols = [
        ("actual_intake_time", "TIMESTAMP"),
        ("intake_notes", "TEXT")
    ]
    for col_name, col_type in new_r_cols:
        if col_name not in existing_r_cols:
            try:
                cursor.execute(f"ALTER TABLE reminder_logs ADD COLUMN {col_name} {col_type}")
            except sqlite3.OperationalError:
                pass

    # Seed synthetic summary data if not present
    cursor.execute("SELECT COUNT(*) FROM discharge_summaries")
    count = cursor.fetchone()[0]
    if count == 0:
        seed_path = os.path.join(os.path.dirname(__file__), "data", "synthetic_summary.json")
        if os.path.exists(seed_path):
            with open(seed_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for summary in data.get("summaries", []):
                    cursor.execute(
                        "INSERT INTO discharge_summaries (id, patient_id, title) VALUES (?, ?, ?)",
                        (summary["id"], summary["patient_id"], summary["title"])
                    )
                    for line in summary.get("lines", []):
                        cursor.execute(
                            "INSERT INTO summary_lines (summary_id, line_id, text) VALUES (?, ?, ?)",
                            (summary["id"], line["line_id"], line["text"])
                        )

    # Seed default patient if not present
    cursor.execute("SELECT COUNT(*) FROM patients WHERE id = 'default-patient'")
    if cursor.fetchone()[0] == 0:
        # Default patient device token for demo/testing: "demo-patient-token-12345"
        token_hash = hash_token("demo-patient-token-12345")
        cursor.execute(
            "INSERT INTO patients (id, display_name, device_token_hash, preferred_script) VALUES (?, ?, ?, ?)",
            ("default-patient", "Robert Jenkins", token_hash, "en")
        )

    conn.commit()
    conn.close()


async def get_db_connection() -> aiosqlite.Connection:
    """Async connection provider for FastAPI request handlers."""
    conn = await aiosqlite.connect(DB_PATH)
    conn.row_factory = aiosqlite.Row
    return conn
