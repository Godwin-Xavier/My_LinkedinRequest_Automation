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
