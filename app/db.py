"""Database persistence layer for OmniResearch using standard library SQLite."""
import sqlite3
import json
import os
import threading
from typing import Optional, Dict, Any, List

DB_PATH = os.getenv("OMNI_DB_PATH", os.path.join(os.path.dirname(os.path.dirname(__file__)), "omniresearch.db"))
_local = threading.local()

def get_connection() -> sqlite3.Connection:
    """Thread-local SQLite connection to ensure thread safety."""
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
    return _local.conn

def init_db():
    """Initializes SQLite schema for jobs persistence and migrates new columns."""
    conn = get_connection()
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                objective TEXT NOT NULL,
                status TEXT NOT NULL,
                stage TEXT NOT NULL,
                plan_json TEXT DEFAULT '[]',
                duplicates_removed INTEGER DEFAULT 0,
                sources_json TEXT DEFAULT '[]',
                claims_json TEXT DEFAULT '[]',
                analysis_json TEXT DEFAULT '{}',
                report_md TEXT DEFAULT '',
                chart_png BLOB,
                log_json TEXT DEFAULT '[]',
                error TEXT,
                file_name TEXT DEFAULT NULL,
                file_context TEXT DEFAULT '',
                chat_json TEXT DEFAULT '[]',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at DESC)")

        # Migration: ensure file_name, file_context, chat_json exist if table pre-existed
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(jobs)")
        columns = [row["name"] for row in cur.fetchall()]
        if "file_name" not in columns:
            conn.execute("ALTER TABLE jobs ADD COLUMN file_name TEXT DEFAULT NULL")
        if "file_context" not in columns:
            conn.execute("ALTER TABLE jobs ADD COLUMN file_context TEXT DEFAULT ''")
        if "chat_json" not in columns:
            conn.execute("ALTER TABLE jobs ADD COLUMN chat_json TEXT DEFAULT '[]'")

def save_job(job: Dict[str, Any]):
    """Insert or replace a job record."""
    conn = get_connection()
    with conn:
        conn.execute("""
            INSERT INTO jobs (
                id, objective, status, stage, plan_json, duplicates_removed,
                sources_json, claims_json, analysis_json, report_md, chart_png,
                log_json, error, file_name, file_context, chat_json, updated_at
            ) VALUES (
                :id, :objective, :status, :stage, :plan_json, :duplicates_removed,
                :sources_json, :claims_json, :analysis_json, :report_md, :chart_png,
                :log_json, :error, :file_name, :file_context, :chat_json, CURRENT_TIMESTAMP
            )
            ON CONFLICT(id) DO UPDATE SET
                status = excluded.status,
                stage = excluded.stage,
                plan_json = excluded.plan_json,
                duplicates_removed = excluded.duplicates_removed,
                sources_json = excluded.sources_json,
                claims_json = excluded.claims_json,
                analysis_json = excluded.analysis_json,
                report_md = excluded.report_md,
                chart_png = coalesce(excluded.chart_png, jobs.chart_png),
                log_json = excluded.log_json,
                error = excluded.error,
                file_name = coalesce(excluded.file_name, jobs.file_name),
                file_context = coalesce(excluded.file_context, jobs.file_context),
                chat_json = excluded.chat_json,
                updated_at = CURRENT_TIMESTAMP
        """, {
            "id": job["id"],
            "objective": job.get("objective", ""),
            "status": job.get("status", "queued"),
            "stage": job.get("stage", "queued"),
            "plan_json": json.dumps(job.get("plan", [])),
            "duplicates_removed": job.get("duplicates_removed", 0),
            "sources_json": json.dumps(job.get("sources", [])),
            "claims_json": json.dumps(job.get("claims", [])),
            "analysis_json": json.dumps(job.get("analysis", {})),
            "report_md": job.get("report_md", ""),
            "chart_png": job.get("chart_png"),
            "log_json": json.dumps(job.get("log", [])),
            "error": job.get("error"),
            "file_name": job.get("file_name"),
            "file_context": job.get("file_context", ""),
            "chat_json": json.dumps(job.get("chat", []))
        })

def get_job(jid: str) -> Optional[Dict[str, Any]]:
    """Retrieve full job dictionary by ID."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM jobs WHERE id = ?", (jid,))
    row = cur.fetchone()
    if not row:
        return None
    return _row_to_dict(row)

def list_recent_jobs(limit: int = 20) -> List[Dict[str, Any]]:
    """List recent research jobs (metadata summary)."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, objective, status, stage, duplicates_removed,
               file_name, created_at, updated_at, error
        FROM jobs ORDER BY created_at DESC LIMIT ?
    """, (limit,))
    rows = cur.fetchall()
    return [dict(r) for r in rows]

def append_chat_message(jid: str, role: str, content: str) -> List[Dict[str, str]]:
    """Appends a chat message to the job's conversation and returns full history."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT chat_json FROM jobs WHERE id = ?", (jid,))
    row = cur.fetchone()
    if not row:
        return []
    
    chat_list = json.loads(row["chat_json"] or "[]")
    chat_list.append({"role": role, "content": content})
    with conn:
        conn.execute("UPDATE jobs SET chat_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                     (json.dumps(chat_list), jid))
    return chat_list

def get_chat_history(jid: str) -> List[Dict[str, str]]:
    """Fetches chat messages for a job."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT chat_json FROM jobs WHERE id = ?", (jid,))
    row = cur.fetchone()
    if not row:
        return []
    return json.loads(row["chat_json"] or "[]")

def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "objective": row["objective"],
        "status": row["status"],
        "stage": row["stage"],
        "plan": json.loads(row["plan_json"] or "[]"),
        "duplicates_removed": row["duplicates_removed"] or 0,
        "sources": json.loads(row["sources_json"] or "[]"),
        "claims": json.loads(row["claims_json"] or "[]"),
        "analysis": json.loads(row["analysis_json"] or "{}"),
        "report_md": row["report_md"] or "",
        "chart_png": row["chart_png"],
        "log": json.loads(row["log_json"] or "[]"),
        "error": row["error"],
        "file_name": row["file_name"] if "file_name" in row.keys() else None,
        "file_context": row["file_context"] if "file_context" in row.keys() else "",
        "chat": json.loads(row["chat_json"] or "[]") if "chat_json" in row.keys() else [],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"]
    }
