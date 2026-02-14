"""
Telegram-Interactive LinkedIn Login & Cookie Refresher.

When the li_at cookie expires, this script:
1. Opens a visible browser to LinkedIn login
2. Enters email/password (from .env or user enters manually)
3. If LinkedIn requires OTP/verification, asks the user via Telegram
4. User replies with OTP on Telegram
5. Bot enters OTP, completes login
6. Extracts fresh li_at cookie from the browser session
7. Updates .env file automatically
8. Sends confirmation via Telegram

Usage:
    python telegram_login.py
    (or double-click telegram_login.bat)
"""
import asyncio
import sys
import time
import traceback

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from telegram import Bot

from config import config
from src.browser_stealth import StealthBrowser
from src.cookie_refresher import update_env_file


# LinkedIn login page
LOGIN_URL = "https://www.linkedin.com/login"


class TelegramLoginAssistant:
    """Interactive assistant that communicates with the user via Telegram.
    
    Handles sending messages and waiting for replies using the Telegram Bot API.
    Each async call creates a fresh Bot instance to avoid event-loop issues
    (same pattern as TelegramNotifier).
    """

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self._last_update_id = 0

    def send(self, message: str) -> bool:
        """Send a message to the user via Telegram (sync wrapper)."""
        try:
            async def _send():
                bot = Bot(token=self.bot_token)
                async with bot:
                    await bot.send_message(
                        chat_id=self.chat_id,
                        text=message,
                        parse_mode="HTML",
                    )
                return True

            return asyncio.run(_send())
        except Exception as e:
            print(f"  [Telegram] Send failed: {e}")
            return False

    def ask(self, question: str, timeout: int = 300) -> str | None:
        """Send a question and poll for the user's reply.

        Args:
            question: HTML-formatted question to send.
            timeout:  Max seconds to wait for a reply (default 5 min).

        Returns:
            The user's reply text, or None on timeout.
        """
        try:
            async def _ask():
                bot = Bot(token=self.bot_token)
                async with bot:
                    # Flush old updates so we only see fresh replies
                    updates = await bot.get_updates(timeout=1)
                    if updates:
                        self._last_update_id = updates[-1].update_id + 1

                    # Send the question
                    await bot.send_message(
                        chat_id=self.chat_id,
                        text=question,
                        parse_mode="HTML",
                    )

                    # Poll for reply
                    deadline = time.time() + timeout
                    while time.time() < deadline:
                        try:
                            updates = await bot.get_updates(
                                offset=self._last_update_id,
                                timeout=10,
                            )
                        except Exception:
                            await asyncio.sleep(3)
                            continue

                        for update in updates:
                            self._last_update_id = update.update_id + 1

                            if (
                                update.message
                                and str(update.message.chat_id) == str(self.chat_id)
                                and update.message.text
                            ):
                                return update.message.text.strip()

                        await asyncio.sleep(2)

                    return None  # timed out

            return asyncio.run(_ask())
        except Exception as e:
            print(f"  [Telegram] Ask failed: {e}")
            return None


# ---------------------------------------------------------------------------
# Login flow
# ---------------------------------------------------------------------------

def _enter_credentials(browser: StealthBrowser, email: str, password: str) -> bool:
    """Type email & password into the LinkedIn login form and click Sign In."""
    try:
        email_field = WebDriverWait(browser.driver, 10).until(
            EC.presence_of_element_located((By.ID, "username"))
        )
        email_field.clear()
        browser.human_type(email_field, email)
        browser.random_delay(0.5, 1)

        password_field = browser.driver.find_element(By.ID, "password")
        password_field.clear()
        browser.human_type(password_field, password)
        browser.random_delay(0.5, 1)

        sign_in_btn = browser.driver.find_element(
            By.CSS_SELECTOR, "button[type='submit']"
        )
        sign_in_btn.click()
        print("  Clicked 'Sign In'")
        browser.random_delay(3, 5)
        return True
    except Exception as e:
        print(f"  Auto-fill failed: {e}")
        return False


def _detect_otp_challenge(browser: StealthBrowser) -> bool:
    """Return True if the current page is an OTP / verification challenge."""
    current_url = browser.driver.current_url.lower()
    page_source = browser._get_page_source_safe().lower()[:5000]

    indicators = [
        "checkpoint/challenge",
        "checkpoint/lg",
        "two-step-verification",
        "enter the code",
        "security verification",
        "we sent a code",
        "enter code",
        "verify your identity",
        "verification code",
        "two-factor",
    ]
    return any(ind in current_url or ind in page_source for ind in indicators)


def _enter_otp(browser: StealthBrowser, otp: str) -> bool:
    """Find the OTP input field and type the code."""
    selectors = [
        "input[name='pin']",
        "input#input__email_verification_pin",
        "input#input__phone_verification_pin",
        "input[name='verification_code']",
        "input[name='code']",
        "input[type='tel']",
        "input[type='number']",
        # Last resort: first visible text input
        "input[type='text']",
    ]

    for selector in selectors:
        try:
            fields = browser.driver.find_elements(By.CSS_SELECTOR, selector)
            for field in fields:
                if field.is_displayed():
                    field.clear()
                    browser.human_type(field, otp)
                    print(f"  Entered OTP via selector: {selector}")
                    return True
        except Exception:
            continue

    return False


def _click_submit(browser: StealthBrowser) -> bool:
    """Click the submit / verify button after entering OTP."""
    selectors = [
        "button#two-step-submit-button",
        "button[type='submit']",
        "input[type='submit']",
        "button[data-litms-control-urn*='submit']",
    ]

    for selector in selectors:
        try:
            btns = browser.driver.find_elements(By.CSS_SELECTOR, selector)
            for btn in btns:
                if btn.is_displayed():
                    btn.click()
                    print(f"  Clicked submit via: {selector}")
                    return True
        except Exception:
            continue

    return False


def _is_on_login_page(browser: StealthBrowser) -> bool:
    """Check if the browser is still on the login page (wrong password etc.)."""
    url = browser.driver.current_url.lower()
    return "/login" in url or "/uas/login" in url


def _is_logged_in_url(browser: StealthBrowser) -> bool:
    """Quick check — are we on a page that implies the session is active?"""
    url = browser.driver.current_url.lower()
    return any(p in url for p in ["/feed", "/mynetwork", "/in/", "/messaging"])


def run_telegram_login() -> bool:
    """Main interactive login flow."""

    # ------------------------------------------------------------------
    # Pre-flight checks
    # ------------------------------------------------------------------
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        print("ERROR: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set in .env")
        return False

    assistant = TelegramLoginAssistant(config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID)
    browser = None

    # Read optional email/password from .env
    env_vars = config._load_env_robust(config.BASE_DIR / ".env")
    email = env_vars.get("LINKEDIN_EMAIL", "").strip()
    password = env_vars.get("LINKEDIN_PASSWORD", "").strip()

    try:
        # ------------------------------------------------------------------
        # Step 1: Notify user
        # ------------------------------------------------------------------
        assistant.send(
            "<b>LinkedIn Cookie Refresh Started</b>\n\n"
            "Opening browser to LinkedIn login page.\n"
            "I'll guide you through the process and ask for the OTP "
            "if LinkedIn requires verification."
        )
        print("\n  Starting browser (visible mode)...")

        # ------------------------------------------------------------------
        # Step 2: Launch browser & navigate to login
        # ------------------------------------------------------------------
        browser = StealthBrowser(headless=False)
        browser.start()

        print("  Navigating to LinkedIn login...")
        browser.driver.get(LOGIN_URL)
        browser.random_delay(3, 5)

        # ------------------------------------------------------------------
        # Step 3: Enter credentials
        # ------------------------------------------------------------------
        if email and password:
            print(f"  Entering email: {email[:3]}***")
            if not _enter_credentials(browser, email, password):
                assistant.send(
                    "<b>Auto-fill failed</b>\n\n"
                    "Please enter your credentials manually in the browser window "
                    "and reply <b>done</b> after clicking Sign In."
                )
                assistant.ask("Reply <b>done</b> after submitting the login form.", timeout=300)
        else:
            assistant.send(
                "<b>Credentials needed</b>\n\n"
                "LINKEDIN_EMAIL / LINKEDIN_PASSWORD are not in .env.\n\n"
                "Please type your credentials in the browser window that just "
                "opened, click Sign In, and reply <b>done</b> here."
            )
            print("  Waiting for user to enter credentials in browser...")
            assistant.ask("Reply <b>done</b> after clicking Sign In.", timeout=300)

        # ------------------------------------------------------------------
        # Step 4: Handle OTP / verification challenges
        # ------------------------------------------------------------------
        browser.random_delay(3, 5)

        MAX_OTP_ATTEMPTS = 3
        for otp_attempt in range(1, MAX_OTP_ATTEMPTS + 1):
            # Already logged in?
            if _is_logged_in_url(browser):
                print("  Logged in - no OTP needed.")
                break

            # OTP challenge?
            if _detect_otp_challenge(browser):
                print(f"  OTP/verification required (attempt {otp_attempt}/{MAX_OTP_ATTEMPTS})")

                otp = assistant.ask(
                    "<b>OTP / Verification Required</b>\n\n"
                    "LinkedIn is asking for a verification code.\n"
                    "Check your email or phone and reply with the code.\n\n"
                    f"<i>Attempt {otp_attempt}/{MAX_OTP_ATTEMPTS}</i>",
                    timeout=300,
                )

                if not otp:
                    assistant.send("Timed out waiting for OTP. Aborting.")
                    print("  Timed out waiting for OTP.")
                    return False

                print(f"  Received OTP: {otp[:2]}****")

                if _enter_otp(browser, otp):
                    browser.random_delay(0.5, 1)
                    _click_submit(browser)
                else:
                    assistant.send(
                        "Could not find the OTP input field automatically.\n"
                        "Please enter the code manually in the browser and "
                        "click submit, then reply <b>done</b>."
                    )
                    assistant.ask("Reply <b>done</b> after submitting.", timeout=300)

                browser.random_delay(3, 5)

            elif _is_on_login_page(browser):
                # Still on login — credentials may be wrong
                assistant.send(
                    "<b>Still on login page</b>\n\n"
                    "Login may have failed (wrong password?).\n"
                    "Please fix credentials in the browser and reply <b>done</b> "
                    "after clicking Sign In."
                )
                assistant.ask("Reply <b>done</b> after re-submitting.", timeout=300)
                browser.random_delay(3, 5)
            else:
                # Unknown page — could be a CAPTCHA, app-download prompt, etc.
                # Just break and try to verify login below.
                break

        # ------------------------------------------------------------------
        # Step 5: Verify login
        # ------------------------------------------------------------------
        print("  Verifying login...")
        browser.driver.get("https://www.linkedin.com/feed/")
        browser.random_delay(5, 8)

        if not browser.is_logged_in():
            print("  Login verification failed.")
            assistant.send(
                "<b>Login Failed</b>\n\n"
                "Could not verify that you are logged in.\n"
                "The cookie was NOT updated.\n\n"
                "Please try again or update the cookie manually."
            )
            return False

        # ------------------------------------------------------------------
        # Step 6: Extract li_at cookie
        # ------------------------------------------------------------------
        print("  Login verified! Extracting li_at cookie...")
        li_at = browser.get_li_at_cookie()

        if not li_at:
            print("  Could not extract li_at cookie!")
            assistant.send(
                "<b>Cookie Extraction Failed</b>\n\n"
                "Logged in successfully but could not read the li_at cookie.\n"
                "Please copy it manually:\n"
                "  F12 > Application > Cookies > linkedin.com > li_at"
            )
            return False

        print(f"  Extracted li_at: {li_at[:12]}...{li_at[-8:]}")

        # ------------------------------------------------------------------
        # Step 7: Update .env
        # ------------------------------------------------------------------
        if update_env_file(li_at):
            print("  .env file updated successfully!")
            assistant.send(
                "<b>Cookie Refreshed Successfully!</b>\n\n"
                f"New li_at: <code>{li_at[:15]}...{li_at[-8:]}</code>\n\n"
                "The .env file has been updated.\n"
                "You can now run:\n"
                "<code>python main.py --run-now</code>"
            )
            return True
        else:
            print("  Failed to update .env file!")
            assistant.send(
                "<b>Cookie extracted but .env update failed</b>\n\n"
                f"Cookie: <code>{li_at}</code>\n\n"
                "Please paste this into your .env file manually as LINKEDIN_LI_AT."
            )
            return False

    except KeyboardInterrupt:
        print("\n  Cancelled by user.")
        assistant.send("Cookie refresh cancelled by user.")
        return False

    except Exception as e:
        print(f"  Error: {e}")
        traceback.print_exc()
        try:
            assistant.send(f"<b>Error during login:</b>\n<code>{str(e)[:300]}</code>")
        except Exception:
            pass
        return False

    finally:
        if browser:
            print("\n  Closing browser in 5 seconds...")
            time.sleep(5)
            browser.close()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    print()
    print("=" * 60)
    print("  LinkedIn Cookie Refresher (Telegram-Interactive)")
    print("=" * 60)

    success = run_telegram_login()

    if success:
        print("\n  Cookie refreshed successfully!")
        print("  Run:  python main.py --run-now")
    else:
        print("\n  Cookie refresh failed.")
        print("  Try again or update .env manually.")

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
