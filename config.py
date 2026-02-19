"""
Configuration loader for LinkedIn Recruiter Outreach Automation.
Loads all settings from environment variables.
"""
import os
import json
import re
import warnings
from pathlib import Path

# Suppress warnings
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

class Config:
    """Central configuration class."""
    
    # LinkedIn - Simple li_at cookie value (matching first project's approach)
    LINKEDIN_LI_AT: str = ""
    
    # Telegram
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""
    
    # AI
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.0-flash"
    
    # Automation
    DAILY_INVITE_LIMIT: int = 14
    SCHEDULE_TIME: str = "09:30"
    PRIORITY_LOCATIONS: list = ["United States", "Canada", "Australia"]
    
    # Browser
    HEADLESS: bool = True
    MIN_DELAY: int = 3
    MAX_DELAY: int = 8
    
    # Paths
    BASE_DIR: Path = Path(__file__).parent
    DATA_DIR: Path = BASE_DIR / "data"
    DB_PATH: Path = DATA_DIR / "agent_state.db"
    
    @classmethod
    def load(cls) -> "Config":
        """Load configuration from environment."""
        config = cls()
        
        # Load .env manually
        env_vars = cls._load_env_robust(cls.BASE_DIR / ".env")
        
        # LinkedIn li_at cookie - simple string value (just like first project)
        config.LINKEDIN_LI_AT = env_vars.get("LINKEDIN_LI_AT", "").strip()
        
        # Remove quotes if present (common when pasting)
        if config.LINKEDIN_LI_AT:
            if (config.LINKEDIN_LI_AT.startswith('"') and config.LINKEDIN_LI_AT.endswith('"')) or \
               (config.LINKEDIN_LI_AT.startswith("'") and config.LINKEDIN_LI_AT.endswith("'")):
                config.LINKEDIN_LI_AT = config.LINKEDIN_LI_AT[1:-1]
        
        # Telegram
        config.TELEGRAM_BOT_TOKEN = env_vars.get("TELEGRAM_BOT_TOKEN", "")
        config.TELEGRAM_CHAT_ID = env_vars.get("TELEGRAM_CHAT_ID", "")
        
        # AI
        config.GEMINI_API_KEY = env_vars.get("GEMINI_API_KEY", "")
        # Updated to current stable model
        config.GEMINI_MODEL = env_vars.get("GEMINI_MODEL", "gemini-1.5-flash").strip() or "gemini-1.5-flash"
        
        # Automation
        config.DAILY_INVITE_LIMIT = int(env_vars.get("DAILY_INVITE_LIMIT", "14"))
        config.SCHEDULE_TIME = env_vars.get("SCHEDULE_TIME", "09:30")
        
        # Priority locations
        locations_str = env_vars.get("PRIORITY_LOCATIONS", "United States,Canada,Australia")
        config.PRIORITY_LOCATIONS = [loc.strip() for loc in locations_str.split(",")]
        
        # Browser
        config.HEADLESS = env_vars.get("HEADLESS", "true").lower() == "true"
        config.MIN_DELAY = int(env_vars.get("MIN_DELAY", "3"))
        config.MAX_DELAY = int(env_vars.get("MAX_DELAY", "8"))
        
        return config
    
    @staticmethod
    def _load_env_robust(env_path: Path) -> dict:
        """Robustly load .env file handling multi-line strings."""
        env_vars = {}
        if not env_path.exists():
            return env_vars
            
        try:
            with open(env_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # Iterate through lines
            lines = content.splitlines()
            current_key = None
            current_value = []
            
            for line in lines:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                # Check for key=value
                if '=' in line:
                    # If we were building a value, save it
                    if current_key:
                        env_vars[current_key] = "".join(current_value)
                    
                    key, value = line.split('=', 1)
                    key = key.strip()
                    current_key = key
                    current_value = [value]
                else:
                    # Continuation of previous value
                    if current_key:
                        current_value.append(line)
            
            # Save last value
            if current_key:
                env_vars[current_key] = "".join(current_value)
                
        except Exception as e:
            print(f"Error reading .env file: {e}")
            
        return env_vars

    def validate(self) -> list[str]:
        """Validate required configuration. Returns list of errors."""
        errors = []
        
        if not self.LINKEDIN_LI_AT:
            errors.append("LINKEDIN_LI_AT is not set in .env")
        
        if not self.TELEGRAM_BOT_TOKEN:
            errors.append("TELEGRAM_BOT_TOKEN is not set")
        
        if not self.TELEGRAM_CHAT_ID:
            errors.append("TELEGRAM_CHAT_ID is not set")
        
        return errors


# Global config instance
config = Config.load()
