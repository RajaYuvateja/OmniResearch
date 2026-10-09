"""
Database persistence layer for OmniResearch.
Supports hosted PostgreSQL (Render, Neon, Supabase) via psycopg2 with connection pooling,
and gracefully falls back to thread-local SQLite for local development.
"""
import os
import json
import sqlite3
import threading
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from contextlib import contextmanager

logger = logging.getLogger("omniresearch.db")

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
DB_PATH = os.getenv("OMNI_DB_PATH", os.path.join(os.path.dirname(os.path.dirname(__file__)), "omniresearch.db"))

_local = threading.local()
_pg_pool = None
IS_POSTGRES = False

def _normalize_database_url(url: str) -> str:
    """Normalize postgres:// to postgresql:// and enforce sslmode for remote hosts."""
    if not url:
        return ""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    
    # Enforce sslmode=require for non-local hosted Postgres instances if not specified
    if "localhost" not in url and "127.0.0.1" not in url and "sslmode" not in url:
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}sslmode=require"
    return url

# Initialize PostgreSQL pool if DATABASE_URL is present
if DATABASE_URL:
    try:
        import psycopg2
        import psycopg2.pool
        import psycopg2.extras
        
        normalized_url = _normalize_database_url(DATABASE_URL)
        # Bounded thread-safe pool suitable for cloud deployment
        _pg_pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=10,
            dsn=normalized_url
        )
        IS_POSTGRES = True
        logger.info("OmniResearch database configured for PostgreSQL.")
    except Exception as e:
        logger.warning("Failed to initialize PostgreSQL pool (%s). Falling back to SQLite.", e)
        IS_POSTGRES = False

def get_sqlite_conn() -> sqlite3.Connection:
    """Thread-local SQLite connection to ensure thread safety."""
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
    return _local.conn

@contextmanager
def get_db_cursor():
    """
    Context manager yielding a database cursor (RealDictCursor for PostgreSQL,
    Row-enabled cursor for SQLite) along with a commit context.
    """
    if IS_POSTGRES and _pg_pool is not None:
        import psycopg2.extras
        conn = _pg_pool.getconn()
        try:
            with conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    yield cur, "postgres"
        finally:
            _pg_pool.putconn(conn)
    else:
        conn = get_sqlite_conn()
        with conn:
            cur = conn.cursor()
            yield cur, "sqlite"

def init_db():
    """Initializes schema for jobs persistence and handles non-destructive migrations."""
    with get_db_cursor() as (cur, engine):
        if engine == "postgres":
            cur.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id VARCHAR(64) PRIMARY KEY,
                    objective TEXT NOT NULL,
                    status VARCHAR(32) NOT NULL,
                    stage VARCHAR(32) NOT NULL,
                    plan_json TEXT DEFAULT '[]',
                    duplicates_removed INTEGER DEFAULT 0,
                    sources_json TEXT DEFAULT '[]',
                    claims_json TEXT DEFAULT '[]',
                    analysis_json TEXT DEFAULT '{}',
                    report_md TEXT DEFAULT '',
                    chart_png BYTEA,
                    log_json TEXT DEFAULT '[]',
                    error TEXT,
                    file_name TEXT DEFAULT NULL,
                    file_context TEXT DEFAULT '',
                    chat_json TEXT DEFAULT '[]',
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at DESC);")
            
            # Non-destructive migrations for existing Postgres tables
            cur.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS file_name TEXT DEFAULT NULL;")
            cur.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS file_context TEXT DEFAULT '';")
            cur.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS chat_json TEXT DEFAULT '[]';")
        else:
            cur.execute("""
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
            cur.execute("CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at DESC)")
            
            # Non-destructive migrations for existing SQLite tables
            cur.execute("PRAGMA table_info(jobs)")
            columns = [row["name"] for row in cur.fetchall()]
            if "file_name" not in columns:
                cur.execute("ALTER TABLE jobs ADD COLUMN file_name TEXT DEFAULT NULL")
            if "file_context" not in columns:
                cur.execute("ALTER TABLE jobs ADD COLUMN file_context TEXT DEFAULT ''")
            if "chat_json" not in columns:
                cur.execute("ALTER TABLE jobs ADD COLUMN chat_json TEXT DEFAULT '[]'")

def save_job(job: Dict[str, Any]):
    """Insert or update a job record atomically."""
    with get_db_cursor() as (cur, engine):
        raw_chart = job.get("chart_png")
        if engine == "postgres":
            import psycopg2
            chart_val = psycopg2.Binary(raw_chart) if raw_chart is not None else None
            
            sql = """
                INSERT INTO jobs (
                    id, objective, status, stage, plan_json, duplicates_removed,
                    sources_json, claims_json, analysis_json, report_md, chart_png,
                    log_json, error, file_name, file_context, chat_json, updated_at
                ) VALUES (
                    %(id)s, %(objective)s, %(status)s, %(stage)s, %(plan_json)s, %(duplicates_removed)s,
                    %(sources_json)s, %(claims_json)s, %(analysis_json)s, %(report_md)s, %(chart_png)s,
                    %(log_json)s, %(error)s, %(file_name)s, %(file_context)s, %(chat_json)s, CURRENT_TIMESTAMP
                )
                ON CONFLICT (id) DO UPDATE SET
                    status = EXCLUDED.status,
                    stage = EXCLUDED.stage,
                    plan_json = EXCLUDED.plan_json,
                    duplicates_removed = EXCLUDED.duplicates_removed,
                    sources_json = EXCLUDED.sources_json,
                    claims_json = EXCLUDED.claims_json,
                    analysis_json = EXCLUDED.analysis_json,
                    report_md = EXCLUDED.report_md,
                    chart_png = COALESCE(EXCLUDED.chart_png, jobs.chart_png),
                    log_json = EXCLUDED.log_json,
                    error = EXCLUDED.error,
                    file_name = COALESCE(EXCLUDED.file_name, jobs.file_name),
                    file_context = COALESCE(EXCLUDED.file_context, jobs.file_context),
                    chat_json = EXCLUDED.chat_json,
                    updated_at = CURRENT_TIMESTAMP
            """
        else:
            chart_val = raw_chart
            sql = """
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
            """

        cur.execute(sql, {
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
            "chart_png": chart_val,
            "log_json": json.dumps(job.get("log", [])),
            "error": job.get("error"),
            "file_name": job.get("file_name"),
            "file_context": job.get("file_context", ""),
            "chat_json": json.dumps(job.get("chat", []))
        })

def get_job(jid: str) -> Optional[Dict[str, Any]]:
    """Retrieve full job dictionary by ID."""
    with get_db_cursor() as (cur, engine):
        if engine == "postgres":
            cur.execute("SELECT * FROM jobs WHERE id = %s", (jid,))
        else:
            cur.execute("SELECT * FROM jobs WHERE id = ?", (jid,))
        row = cur.fetchone()
        if not row:
            return None
        return _row_to_dict(row, engine)

def list_recent_jobs(limit: int = 20) -> List[Dict[str, Any]]:
    """List recent research jobs (metadata summary)."""
    with get_db_cursor() as (cur, engine):
        query = """
            SELECT id, objective, status, stage, duplicates_removed,
                   file_name, created_at, updated_at, error
            FROM jobs ORDER BY created_at DESC LIMIT """ + ("%s" if engine == "postgres" else "?")
        cur.execute(query, (limit,))
        rows = cur.fetchall()
        
        results = []
        for r in rows:
            d = dict(r)
            # Ensure timestamps are JSON serializable
            if isinstance(d.get("created_at"), datetime):
                d["created_at"] = d["created_at"].isoformat()
            if isinstance(d.get("updated_at"), datetime):
                d["updated_at"] = d["updated_at"].isoformat()
            results.append(d)
        return results

def append_chat_message(jid: str, role: str, content: str) -> List[Dict[str, str]]:
    """Appends a chat message to the job's conversation and returns full history."""
    with get_db_cursor() as (cur, engine):
        select_sql = "SELECT chat_json FROM jobs WHERE id = " + ("%s" if engine == "postgres" else "?")
        cur.execute(select_sql, (jid,))
        row = cur.fetchone()
        if not row:
            return []
        
        raw_chat = row["chat_json"] if isinstance(row, dict) else row["chat_json"]
        chat_list = json.loads(raw_chat or "[]")
        chat_list.append({"role": role, "content": content})
        
        update_sql = "UPDATE jobs SET chat_json = " + ("%s" if engine == "postgres" else "?") + \
                     ", updated_at = CURRENT_TIMESTAMP WHERE id = " + ("%s" if engine == "postgres" else "?")
        cur.execute(update_sql, (json.dumps(chat_list), jid))
        return chat_list

def get_chat_history(jid: str) -> List[Dict[str, str]]:
    """Fetches chat messages for a job."""
    with get_db_cursor() as (cur, engine):
        sql = "SELECT chat_json FROM jobs WHERE id = " + ("%s" if engine == "postgres" else "?")
        cur.execute(sql, (jid,))
        row = cur.fetchone()
        if not row:
            return []
        raw_chat = row["chat_json"] if isinstance(row, dict) else row["chat_json"]
        return json.loads(raw_chat or "[]")

def check_db_health() -> Dict[str, Any]:
    """Non-leaking database health check for production probes."""
    try:
        with get_db_cursor() as (cur, engine):
            cur.execute("SELECT 1")
            return {
                "healthy": True,
                "engine": engine,
                "status": "connected"
            }
    except Exception as e:
        return {
            "healthy": False,
            "engine": "postgres" if IS_POSTGRES else "sqlite",
            "status": "unhealthy",
            "error": f"{type(e).__name__}: Database check failed"
        }

def _row_to_dict(row: Any, engine: str = "sqlite") -> Dict[str, Any]:
    row_dict = dict(row)
    
    # Handle BYTEA / BLOB chart_png
    chart_val = row_dict.get("chart_png")
    if isinstance(chart_val, memoryview):
        chart_val = bytes(chart_val)

    created_at = row_dict.get("created_at")
    if isinstance(created_at, datetime):
        created_at = created_at.isoformat()

    updated_at = row_dict.get("updated_at")
    if isinstance(updated_at, datetime):
        updated_at = updated_at.isoformat()

    return {
        "id": row_dict["id"],
        "objective": row_dict["objective"],
        "status": row_dict["status"],
        "stage": row_dict["stage"],
        "plan": json.loads(row_dict.get("plan_json") or "[]"),
        "duplicates_removed": row_dict.get("duplicates_removed") or 0,
        "sources": json.loads(row_dict.get("sources_json") or "[]"),
        "claims": json.loads(row_dict.get("claims_json") or "[]"),
        "analysis": json.loads(row_dict.get("analysis_json") or "{}"),
        "report_md": row_dict.get("report_md") or "",
        "chart_png": chart_val,
        "log": json.loads(row_dict.get("log_json") or "[]"),
        "error": row_dict.get("error"),
        "file_name": row_dict.get("file_name"),
        "file_context": row_dict.get("file_context") or "",
        "chat": json.loads(row_dict.get("chat_json") or "[]"),
        "created_at": created_at,
        "updated_at": updated_at
    }
