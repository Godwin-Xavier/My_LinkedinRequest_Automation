
import subprocess
import json

class SandboxBridge:
    def execute(self, code: str, language="python"):
        if language != "python":
            return {"status": "error", "error": "Only Python supported in V1"}

        try:
            # 10s Timeout for safety
            proc = subprocess.run(
                ["python", "-c", code],
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
