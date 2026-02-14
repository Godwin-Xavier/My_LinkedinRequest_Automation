
"""
Debug script to verify LinkedIn connection flow in the second project.
Tests:
1. Login with new simple li_at cookie
2. Recruiter search (handling rate limits)
3. Connection modal interaction (using new JS button finder)
"""
import time
import sys
from src.browser_stealth import StealthBrowser
from src.linkedin_client import LinkedInClient
from src.recruiter_search import search_generator
from config import config

def debug_connection_flow():
    print("🚀 Starting Debug: LinkedIn Connection Flow")
    
    # 1. Initialize Browser
    print("\n1. Initializing Browser...")
    browser = StealthBrowser(headless=False)
    browser.start()
    
    try:
        # 2. Test Login
        print("\n2. Testing Login...")
        if not browser.login_with_cookie(config.LINKEDIN_LI_AT):
            print("❌ Login Failed! Check cookie value.")
            return
        print("✅ Login Successful")
        
        # 3. Initialize Client
        client = LinkedInClient(browser, search_generator=search_generator)
        
        # 4. Search for a recruiter (using a common term)
        keyword = "Technical Recruiter"
        location = "India"
        print(f"\n3. Searching for '{keyword}' in '{location}'...")
        
        recruiters = client.search_recruiters(keyword, location)
        
        if not recruiters:
            print("❌ No recruiters found. Search failed or rate limited.")
            return
            
        print(f"✅ Found {len(recruiters)} recruiters")
        target = recruiters[0]
        print(f"Targeting: {target['name']} ({target['url']})")
        
        # 5. Navigate to Profile
        print(f"\n4. Navigating to profile: {target['name']}...")
        browser.driver.get(target['url'])
        time.sleep(5)
        
        # 6. Attempt Connection (DRY RUN - will stop before sending if possible, or we just send one)
        # Note: The send_connection_request function sends it immediately.
        # We will wrap it to capture logs.
        
        print("\n5. Attempting Connection Flow...")
        print("   (Watch the browser for 'Connect' click and Modal interaction)")
        
        success = client.send_connection_request(target['url'], target['name'], target['title'])
        
        if success:
            print(f"\n✅ Connection Request Sent Successfully to {target['name']}!")
            print("   The new JS button finder worked!")
        else:
            print(f"\n❌ Failed to send request to {target['name']}")
            
    except Exception as e:
        print(f"\n❌ Error during debug: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        print("\nClosing browser in 10 seconds...")
        time.sleep(10)
        browser.close()

if __name__ == "__main__":
    debug_connection_flow()
