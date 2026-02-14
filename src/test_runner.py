
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
