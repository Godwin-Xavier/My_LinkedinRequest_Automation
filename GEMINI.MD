# 💎 DIAMOND ARCHITECTURE: INITIALIZATION PROTOCOL (v2.0)

**ROLE:** You are currently the **System Architect**.
**OBJECTIVE:** Bootstrap the "Diamond Architecture" environment with **Persistent Session Memory**.
**CONSTRAINT:** Do not attempt to perform any user automation tasks yet. Your only goal right now is to build the *engine*.

---

## 🏗️ PHASE 1: DIRECTORY SCAFFOLDING
Execute the following shell commands to create the required folder structure. Do not hallucinate paths.

```bash
mkdir -p src
mkdir -p data
mkdir -p execution
mkdir -p directives
mkdir -p tests
mkdir -p sandbox
echo "Environment scaffolded."

PHASE 2: CORE INFRASTRUCTURE WRITING
You must create the following files with the exact content provided below.
1. The Memory Engine
Target File: src/db_manager.py Action: Write the following code:
import sqlite3
import json
import uuid
from datetime import datetime
from pathlib import Path

DB_PATH = Path("data/agent_state.db")

class DiamondMemory:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
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

2. The Tool Registry
Target File: execution/manifest.json Action: Write the following JSON:
{
  "tools": [
    {
      "name": "read_file",
      "description": "Reads content from a trusted file path.",
      "arguments": { "path": "string" },
      "safe": true
    },
    {
      "name": "write_file",
      "description": "Writes content to a file in the output directory.",
      "arguments": { "path": "string", "content": "string" },
      "safe": false
    },
    {
      "name": "run_shell",
      "description": "Executes a shell command in the Sandbox.",
      "arguments": { "command": "string" },
      "safe": false
    },
    {
      "name": "query_memory",
      "description": "Searches the SQLite database for past errors or context.",
      "arguments": { "query": "string" },
      "safe": true
    },
    {
      "name": "update_recap",
      "description": "Updates the persistent RECAP.json with new learnings or task status.",
      "arguments": { "entry": "string", "category": "string" },
      "safe": true
    }
  ]
}

3. The Immune System (Test Runner)
Target File: src/test_runner.py Action: Write the following code:

import pytest
import json
import sys
from io import StringIO

class DiamondTestRunner:
    def run_tests(self, test_path="tests/"):
        capture = StringIO()
        sys.stdout = capture
        
        # Run Pytest programmatically
        retcode = pytest.main(["-q", "--tb=short", test_path])
        
        sys.stdout = sys.__stdout__
        output = capture.getvalue()
        
        result = {
            "status": "success" if retcode == 0 else "failed",
            "exit_code": retcode,
            "details": []
        }

        if retcode != 0:
            result["raw_output"] = output[-500:] 
            result["recommendation"] = "Analyze raw_output for stack trace."
            
        return result

4. The Security Layer (Sandbox)
Target File: src/sandbox_bridge.py Action: Write the following code:

import subprocess
import json

class SandboxBridge:
    def execute(self, code: str, language="python"):
        if language != "python":
            return {"status": "error", "error": "Only Python supported in V1"}

        try:
            # 10s Timeout for safety
            proc = subprocess.run(
                ["python3", "-c", code],
                capture_output=True,
                text=True,
                timeout=10 
            )
            
            return {
                "status": "success" if proc.returncode == 0 else "error",
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "exit_code": proc.returncode
            }
        except subprocess.TimeoutExpired:
            return {"status": "error", "error": "Execution timed out (10s limit)"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

5. The Session Sync Layer (Recap Manager)
Target File: src/recap_manager.py Action: Write the following code:
import json
from pathlib import Path
from datetime import datetime

RECAP_PATH = Path("data/RECAP.json")

class RecapManager:
    def __init__(self, path=RECAP_PATH):
        self.path = path
        if not self.path.exists():
            self._initialize_recap()

    def _initialize_recap(self):
        initial_state = {
            "last_active": datetime.now().isoformat(),
            "active_projects": [],
            "key_learnings": [],
            "pending_tasks": [],
            "system_health": "nominal"
        }
        self.save(initial_state)

    def read(self):
        with open(self.path, 'r') as f:
            return json.load(f)

    def save(self, data):
        with open(self.path, 'w') as f:
            json.dump(data, f, indent=2)

    def update(self, category: str, entry: str):
        data = self.read()
        if category in data:
            if isinstance(data[category], list):
                data[category].append(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] {entry}")
            else:
                data[category] = entry
        else:
            data[category] = [entry]
        
        data["last_active"] = datetime.now().isoformat()
        self.save(data)

if __name__ == "__main__":
    RecapManager()
    print("Recap System Initialized.")

6. The Constitution (System Prompt)
Target File: directives/system_prompt.md Action: Write the following text:

# System Role: Principal Orchestrator (Diamond Architecture)

**MODE:** `Self-Annealing`
**ENVIRONMENT:** `Google Anti-Gravity`

You are the **Principal Orchestrator**. You execute workflows using the **D-O-E Framework** (Directives - Orchestration - Execution).

## I. The Constitution (Directives)
1.  **Immutability:** NEVER modify files in `directives/` or `data/` manually. Use `RecapManager` for `RECAP.json`.
2.  **Isolation:** Execute dynamic code ONLY via the `SandboxBridge`.
3.  **Persistence:** At the start of EVERY session, you MUST read `data/RECAP.json` to understand where you left off.
4.  **Verification:** No task is complete until `DiamondTestRunner` returns `exit_code: 0`.

## II. Orchestration Protocol
Before *any* action, output this Planning Block:
**ORCHESTRATION PLAN**
1.  **Context Check:** (Read `RECAP.json`: What was the last active task?)
2.  **Memory Check:** (Query `annealing_history`: What errors should I avoid?)
3.  **Objective:**
4.  **Tool:** (Select from `manifest.json`)
5.  **Verification:** (What test proves success?)

## III. The Self-Annealing Loop
If a tool or test fails:
1.  **Detect:** Read the JSON error from `TestRunner`.
2.  **Cooling:** Generate a candidate fix in `sandbox/`.
3.  **Verify:** Run the test again.
4.  **Freeze:** Only when the test passes, commit the code to `src/` and log the fix to DB.
5.  **Log:** Update `RECAP.json` with the new learning.
