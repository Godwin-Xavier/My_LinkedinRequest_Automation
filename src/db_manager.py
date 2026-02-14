import sqlite3
import json
import uuid
from datetime import datetime
from pathlib import Path

from config import config

# Use absolute path from config instead of relative path
DB_PATH = config.DB_PATH

class DiamondMemory:
    def __init__(self, db_path=None):
        self.db_path = db_path or DB_PATH
        self._init_db()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = self._get_connection()
        try:
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA foreign_keys = ON;")
            
            # 1. RUNS TABLE
            conn.execute("""
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    objective TEXT,
                    status TEXT DEFAULT 'planning',
                    start_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                    end_time DATETIME
                );
            """)
            
            # 2. STEPS TABLE
            conn.execute("""
                CREATE TABLE IF NOT EXISTS run_steps (
                    step_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT,
                    step_number INTEGER,
                    action_type TEXT,
                    thought_process TEXT,
                    tool_output TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(run_id) REFERENCES runs(run_id)
                );
            """)

            # 3. ANNEALING HISTORY
            conn.execute("""
                CREATE TABLE IF NOT EXISTS annealing_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    error_signature TEXT,
                    fix_strategy TEXT,
                    success_rate REAL DEFAULT 0.0,
                    context_hash TEXT
                );
            """)
            conn.commit()
        finally:
            conn.close()

    def start_run(self, objective: str) -> str:
        run_id = str(uuid.uuid4())
        conn = self._get_connection()
        conn.execute(
            "INSERT INTO runs (run_id, objective) VALUES (?, ?)", 
            (run_id, objective)
        )
        conn.commit()
        conn.close()
        return run_id

    def log_step(self, run_id: str, step_num: int, action: str, thought: str, output: dict):
        conn = self._get_connection()
        conn.execute("""
            INSERT INTO run_steps (run_id, step_number, action_type, thought_process, tool_output)
            VALUES (?, ?, ?, ?, ?)
        """, (run_id, step_num, action, thought, json.dumps(output)))
        conn.commit()
        conn.close()

    def recall_errors(self, query_context: str) -> list:
        conn = self._get_connection()
        cursor = conn.execute("""
            SELECT error_signature, fix_strategy 
            FROM annealing_history 
            WHERE error_signature LIKE ? 
            ORDER BY id DESC LIMIT 3
        """, (f"%{query_context}%",))
        results = cursor.fetchall()
        conn.close()
        return [{"error": r[0], "fix": r[1]} for r in results]
