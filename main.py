"""
LinkedIn Recruiter Outreach Automation - Main Entry Point.
Handles scheduling and orchestration of daily outreach.
"""
import argparse
import sys
import traceback
from datetime import datetime
from typing import Optional

import pytz
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from config import config
from src.browser_stealth import StealthBrowser
from src.linkedin_client import LinkedInClient
from src.telegram_notifier import notifier
from src.recruiter_search import search_generator


# IST Timezone
IST = pytz.timezone('Asia/Kolkata')


class TeeLogger:
    """Writes to both stdout/stderr and a file."""
    def __init__(self, filename):
        self.terminal = sys.stdout
        self.filename = filename
        self.log_file = open(filename, "w", encoding="utf-8", buffering=1)  # Line buffered

    def write(self, message):
        self.terminal.write(message)
        self.log_file.write(message)

    def flush(self):
        self.terminal.flush()
        self.log_file.flush()

    def close(self):
        self.log_file.close()


def run_outreach(dry_run: bool = False, limit: Optional[int] = None):
    """Execute the daily outreach routine."""
    # Setup file logging
    log_filename = "session_log.txt"
    logger = TeeLogger(log_filename)
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    sys.stdout = logger
    sys.stderr = logger

    print(f"\n{'='*50}")
    print(f"LinkedIn Outreach Started at {datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S')} IST")
    print(f"{'='*50}\n")
    
    results = {
        "success": False,
        "sent": 0,
        "failed": 0,
        "skipped": 0,
        "total_today": 0,
        "recruiters_found": [],
        "errors": [],
        "warnings": [],
        "diagnostics": [],
        "limit_reached": False,
    }
    
    browser = None
    client = None
    initial_today_count = 0
    
    try:
        # Validate configuration
        errors = config.validate()
        if errors:
            for err in errors:
                print(f"Config Error: {err}")
                results["errors"].append(err)

            results["diagnostics"].append("Configuration validation failed before browser startup.")
            
            if "LINKEDIN_LI_AT" in str(errors):
                notifier.send_cookie_warning()
            else:
                notifier.send_error_alert("\n".join(errors), "Configuration Validation")
            
            return results
        
        # Initialize browser
        print("Initializing stealth browser...")
        browser = StealthBrowser(headless=config.HEADLESS)
        browser.start()
        
        # Inject cookies and verify login
        print("Logging in with li_at cookie...")
        if not browser.login_with_cookie(config.LINKEDIN_LI_AT):
            print("Failed to log in with provided cookie!")
            login_issue = (getattr(browser, "last_login_issue", "") or "").strip()
            if login_issue:
                results["errors"].append(login_issue)
            else:
                results["errors"].append("Cookie authentication failed")
            results["diagnostics"].append(
                "Cookie login failed before outreach search started. Refresh LINKEDIN_LI_AT and retry."
            )
            notifier.send_cookie_warning()
            
            # Auto-offer Telegram login
            print("\nWould you like to refresh the cookie now via Telegram?")
            print("Run:  python main.py --refresh-cookie")
            
            return results
        
        print("Successfully logged into LinkedIn")
        
        # Initialize LinkedIn client with AI search generator
        client = LinkedInClient(browser, search_generator=search_generator)
        initial_today_count = client.get_today_invite_count()
        results["total_today"] = initial_today_count
        print(f"Invites already sent today: {initial_today_count}")
        
        # Run outreach
        effective_limit = limit or config.DAILY_INVITE_LIMIT
        print(f"\nStarting outreach (limit: {effective_limit}, dry_run: {dry_run})")
        print(f"Target locations: {', '.join(config.PRIORITY_LOCATIONS)}")
        run_results = client.run_daily_outreach(limit=effective_limit, dry_run=dry_run)
        results.update(run_results)
        results["success"] = True
        
        print(f"\n{'='*50}")
        print(f"Outreach Complete!")
        print(f"Sent: {results['sent']}, Failed: {results['failed']}, Skipped: {results['skipped']}")
        print(f"{'='*50}\n")
        
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        print(f"Error during outreach: {error_msg}")
        traceback.print_exc()

        # Recover sent-count from DB if crash happened mid-run.
        if client:
            try:
                current_total = client.get_today_invite_count()
                recovered_sent = max(0, current_total - initial_today_count)
                if recovered_sent > results.get("sent", 0):
                    print(
                        f"Recovered sent-count after crash: {recovered_sent} "
                        f"(total today: {current_total})"
                    )
                results["sent"] = max(results.get("sent", 0), recovered_sent)
                results["total_today"] = max(results.get("total_today", 0), current_total)
            except Exception as recovery_error:
                print(f"Warning: could not recover sent-count: {recovery_error}")

        results["errors"].append(error_msg)
        notifier.send_error_alert(error_msg, "Daily Outreach Execution")
        
    finally:
        if browser:
            browser.close()

        print("\nSending report to Telegram...")
        notifier.send_daily_summary(results)
        
        # Restore stdout/stderr and close log
        sys.stdout = original_stdout
        sys.stderr = original_stderr
        logger.close()
        
        # Send the log file
        print("Uploading session log to Telegram...")
        notifier.send_log_file(log_filename, caption=f"Log: {datetime.now(IST).strftime('%Y-%m-%d %H:%M')}")
    
    return results


def test_login():
    """Test LinkedIn login with cookies."""
    print("Testing LinkedIn cookie authentication...")
    
    errors = config.validate()
    if errors:
        print("Configuration errors:")
        for err in errors:
            print(f"  - {err}")
        return False
    
    browser = StealthBrowser(headless=False)  # Non-headless for visual verification
    try:
        browser.start()
        if browser.login_with_cookie(config.LINKEDIN_LI_AT):
            print("Login successful! Check the browser window.")
            print("Press Enter to close...")
            input()
            return True
        else:
            print("Login failed. Cookie may be expired.")
            return False
    finally:
        browser.close()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="LinkedIn Recruiter Outreach Automation")
    parser.add_argument("--run-now", action="store_true", help="Run outreach immediately")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without sending invites")
    parser.add_argument("--limit", type=int, default=None, help="Override daily invite limit")
    parser.add_argument("--test-login", action="store_true", help="Test LinkedIn login")
    parser.add_argument("--no-schedule", action="store_true", help="Run once without scheduling")
    parser.add_argument("--refresh-cookie", action="store_true", help="Launch Telegram-interactive cookie refresh")
    
    args = parser.parse_args()
    
    print(f"""
============================================================
  LinkedIn Recruiter Outreach Automation
  Schedule: {config.SCHEDULE_TIME} IST Daily
  Limit: {config.DAILY_INVITE_LIMIT} invites/day
============================================================
    """)
    
    # Refresh cookie mode
    if args.refresh_cookie:
        try:
            from telegram_login import run_telegram_login
            success = run_telegram_login()
            if success:
                # Reload config with fresh cookie
                from importlib import reload
                import config as config_module
                reload(config_module)
            sys.exit(0 if success else 1)
        except ImportError:
            print("ERROR: telegram_login.py not found.")
            sys.exit(1)
    
    # Test login mode
    if args.test_login:
        success = test_login()
        sys.exit(0 if success else 1)
    
    # Immediate run mode
    if args.run_now:
        results = run_outreach(dry_run=args.dry_run, limit=args.limit)
        sys.exit(0 if results.get("success") else 1)
    
    # One-time run without scheduling
    if args.no_schedule:
        results = run_outreach(dry_run=args.dry_run, limit=args.limit)
        sys.exit(0 if results.get("success") else 1)
    
    # Scheduled mode (default)
    print("Starting scheduler...")
    notifier.send_startup_message()
    
    # Parse schedule time
    hour, minute = map(int, config.SCHEDULE_TIME.split(":"))
    
    scheduler = BlockingScheduler(timezone=IST)
    scheduler.add_job(
        run_outreach,
        CronTrigger(hour=hour, minute=minute, timezone=IST),
        id="daily_outreach",
        name="Daily LinkedIn Outreach",
        replace_existing=True
    )
    
    print(f"Scheduler started. Next run at {config.SCHEDULE_TIME} IST")
    print("Press Ctrl+C to exit.\n")
    
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("\nShutting down...")
        scheduler.shutdown()


if __name__ == "__main__":
    main()
