
"""
Debug script to test LinkedIn login and search flow.
Tests login with li_at cookie and saves page source for inspection.
"""
import time
import sys
import traceback
from src.browser_stealth import StealthBrowser
from config import config

def debug_search():
    print("Initializing browser...")
    browser = None
    try:
        browser = StealthBrowser(headless=False)
        print("Starting browser...")
        browser.start()
        
        print("Logging in with li_at cookie...")
        if not browser.login_with_cookie(config.LINKEDIN_LI_AT):
            print("Login failed! Check your li_at cookie value in .env. Exiting.")
            return
            
        print("Logged in. Saving feed page source...")
        try:
            with open("debug_feed.html", "w", encoding="utf-8") as f:
                f.write(browser.driver.page_source)
            print("Done. Saved to debug_feed.html")
        except Exception as ignored:
            print(f"Failed to save source: {ignored}")

    except Exception as e:
        print(f"Error: {e}")
        traceback.print_exc()
    finally:
        if browser:
            print("Closing browser...")
            try:
                browser.close()
            except Exception as e:
                print(f"Error closing browser: {e}")

if __name__ == "__main__":
    debug_search()
