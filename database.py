import sqlite3
import hashlib
import time
from contextlib import contextmanager

DB_PATH = "agent_local.db"

def init_db():
    """Initialize SQLite database with required tables"""
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS jobs_local (
                job_id TEXT PRIMARY KEY,
                job_input TEXT NOT NULL,
                job_input_hash TEXT NOT NULL,
                sender_address TEXT NOT NULL,
                group_txid TEXT NOT NULL,
                txn_ids TEXT,
                status TEXT NOT NULL,
                created_at INTEGER DEFAULT (unixepoch()),
                started_at INTEGER,
                completed_at INTEGER,
                error_message TEXT,
                output TEXT
            );

            CREATE TABLE IF NOT EXISTS receipts_local (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                group_txid TEXT NOT NULL,
                verified_at INTEGER DEFAULT (unixepoch())
            );

            CREATE TABLE IF NOT EXISTS logs_local (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                message TEXT NOT NULL,
                level TEXT DEFAULT 'info',
                timestamp INTEGER DEFAULT (unixepoch())
            );
        """)

@contextmanager
def get_db():
    """Database connection context manager"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def create_job(job_input, sender_address):
    """Create new job and return job_id and hash"""
    job_input_hash = hashlib.sha256(job_input.encode()).hexdigest()
    job_id = f"J{int(time.time())}"
    
    with get_db() as conn:
        conn.execute("""
            INSERT INTO jobs_local (job_id, job_input, job_input_hash, sender_address, group_txid, status)
            VALUES (?, ?, ?, ?, '', 'queued')
        """, (job_id, job_input, job_input_hash, sender_address))
        conn.commit()
    
    return job_id, job_input_hash

def update_job_payment_processing(job_id, txn_ids):
    """Update job status to payment_processing and store txn_ids"""
    with get_db() as conn:
        conn.execute("""
            UPDATE jobs_local 
            SET status = 'payment_processing', txn_ids = ?
            WHERE job_id = ?
        """, (','.join(txn_ids), job_id))
        conn.commit()

def get_job(job_id):
    """Get job by ID"""
    with get_db() as conn:
        return conn.execute("SELECT * FROM jobs_local WHERE job_id = ?", (job_id,)).fetchone()