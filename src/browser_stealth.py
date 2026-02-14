"""
Stealth Browser Setup for LinkedIn Automation.
Uses undetected-chromedriver and selenium-stealth to avoid bot detection.
"""
import random
import sys
import time
import os
import re
import subprocess
from typing import Optional

import undetected_chromedriver as uc
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium_stealth import stealth

from config import config


def _print(msg: str):
    """Print and flush immediately. Strips non-ASCII chars for Windows CP1252."""
    safe = msg.encode("ascii", errors="replace").decode("ascii")
    print(safe)
    sys.stdout.flush()


class StealthBrowser:
    """Stealth Chrome browser with human-like behavior."""
    
    def __init__(self, headless: Optional[bool] = None):
        self.headless = headless if headless is not None else config.HEADLESS
        self.driver: Optional[WebDriver] = None
    
    def _get_chrome_major_version(self, chrome_path: Optional[str] = None) -> Optional[int]:
        """Detect installed Chrome major version to prevent driver mismatch."""

        # 1) Prefer explicit browser path if available (works in CI/Linux/Windows).
        if chrome_path:
            try:
                output = subprocess.check_output(
                    [chrome_path, "--version"],
                    stderr=subprocess.STDOUT,
                    text=True,
                    timeout=10,
                )
                match = re.search(r"(\d+)\.", output)
                if match:
                    return int(match.group(1))
            except Exception as e:
                _print(f"Warning: Could not detect Chrome version from binary: {e}")

        # 2) Windows registry fallback for local runs without explicit path.
        try:
            import platform
            if platform.system() == "Windows":
                import winreg
                try:
                    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon")
                    version, _ = winreg.QueryValueEx(key, "version")
                    return int(version.split(".")[0])
                except FileNotFoundError:
                    pass

                try:
                    key = winreg.OpenKey(
                        winreg.HKEY_LOCAL_MACHINE,
                        r"SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Google Chrome",
                    )
                    version, _ = winreg.QueryValueEx(key, "DisplayVersion")
                    return int(version.split(".")[0])
                except FileNotFoundError:
                    pass
        except Exception as e:
            _print(f"Warning: Could not detect Chrome version from registry: {e}")

        return None

    def start(self) -> WebDriver:
        """Initialize and return stealth Chrome driver."""
        running_in_github_actions = os.getenv("GITHUB_ACTIONS") == "true"
        options = webdriver.ChromeOptions()

        chrome_path = (
            os.getenv("CHROME_PATH")
            or os.getenv("GOOGLE_CHROME_BIN")
            or os.getenv("CHROME_BIN")
        )
        if chrome_path:
            options.binary_location = chrome_path
            _print(f"Using Chrome binary: {chrome_path}")
        
        if self.headless:
            options.add_argument("--headless=new")
        
        # Anti-detection options
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-infobars")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--start-maximized")
        
        # Realistic user agent
        options.add_argument(
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )
        
        # In GitHub Actions, prefer Selenium Manager directly.
        # UC often lags behind the fast-moving Chrome versions on hosted runners.
        if running_in_github_actions:
            _print("GitHub Actions detected: using Selenium Manager Chrome driver")
            chromedriver_path = os.getenv("CHROMEDRIVER_PATH", "").strip()
            if chromedriver_path:
                _print(f"Using ChromeDriver binary: {chromedriver_path}")
                service = ChromeService(executable_path=chromedriver_path)
            else:
                _print("CHROMEDRIVER_PATH not set; falling back to Selenium Manager resolution")
                service = ChromeService()
            self.driver = webdriver.Chrome(service=service, options=options)
        else:
            version_main = self._get_chrome_major_version(chrome_path)
            if version_main:
                _print(f"Detected Chrome version: {version_main}")
            else:
                _print("Could not detect Chrome version, letting undetected-chromedriver decide.")

            uc_kwargs = {
                "options": options,
                "use_subprocess": True,
            }
            if version_main:
                uc_kwargs["version_main"] = version_main
            if chrome_path:
                uc_kwargs["browser_executable_path"] = chrome_path

            self.driver = uc.Chrome(**uc_kwargs)
        
        # Apply selenium-stealth
        stealth(
            self.driver,
            languages=["en-US", "en"],
            vendor="Google Inc.",
            platform="Win32",
            webgl_vendor="Intel Inc.",
            renderer="Intel Iris OpenGL Engine",
            fix_hairline=True,
        )
        
        return self.driver
    
    def _get_page_source_safe(self) -> str:
        """Safely get page source, returning empty string if None or error."""
        driver = self.driver
        if not driver:
            return ""
        try:
            source = driver.page_source
            return source if source else ""
        except Exception:
            return ""
    
    def safe_navigate(self, url: str, max_retries: int = 3) -> bool:
        """
        Navigate to a URL with built-in rate limit handling (429/Redirects).
        Uses exponential backoff if rate limited.

        IMPORTANT: Only check for rate-limit indicators in the URL or in very
        specific page text patterns.  Generic words like "challenge",
        "verification", "checkpoint" appear in normal LinkedIn JavaScript and
        will cause false positives if matched against the full page source.
        """
        if not self.driver:
            raise RuntimeError("Browser not started")
            
        for attempt in range(max_retries + 1):
            try:
                _print(f"Navigating to: {url[:100]}...")
                self.driver.get(url)
                
                # Small delay to let page render
                time.sleep(random.uniform(2, 4))
                
                current_url = self.driver.current_url.lower()
                
                # --- Check URL for challenge/checkpoint redirect ---
                url_blocked = any(x in current_url for x in [
                    "checkpoint/challenge",
                    "checkpoint/lg",
                    "/checkpoint/",
                    "/authwall",
                ])
                
                # --- Check page text for SPECIFIC rate-limit error strings ---
                # Only check the <title> and the first 2000 chars of visible text,
                # NOT the full page_source (which is 1MB+ of obfuscated JS).
                page_title = (self.driver.title or "").lower()
                body_text = ""
                try:
                    body = self.driver.find_element(By.TAG_NAME, "body")
                    body_text = (body.text or "")[:2000].lower()
                except Exception:
                    pass

                text_blocked = any(indicator in page_title or indicator in body_text
                                   for indicator in [
                                       "http error 429",
                                       "too many requests",
                                       "unusual traffic",
                                       "temporarily restricted",
                                   ])
                
                if url_blocked or text_blocked:
                    reason = "URL redirect" if url_blocked else "page text"
                    if attempt < max_retries:
                        wait_time = 30 * (2 ** attempt)  # 30s, 60s, 120s
                        _print(f"\nRATE LIMIT / CHALLENGE DETECTED ({reason})")
                        _print(f"  URL: {current_url[:80]}")
                        _print(f"  Waiting {wait_time}s before retry {attempt+1}/{max_retries}...")
                        time.sleep(wait_time)
                        
                        _print("  Refreshing page...")
                        try:
                            self.driver.refresh()
                            time.sleep(5)
                        except Exception:
                            pass
                        continue
                    else:
                        _print("Max retries reached for rate limit.")
                        return False
                
                _print(f"  Page loaded OK: {current_url[:80]}")
                return True
                
            except Exception as e:
                _print(f"Navigation error: {e}")
                if attempt < max_retries:
                    time.sleep(random.uniform(5, 10))
                else:
                    return False
        
        return False

    def login_with_cookie(self, li_at_value: str) -> bool:
        """Simple LinkedIn login using just the li_at cookie value."""
        if not self.driver:
            raise RuntimeError("Browser not started. Call start() first.")
        
        if not li_at_value:
            _print("LINKEDIN_LI_AT cookie value is empty!")
            return False
        
        _print("Navigating to neutral page (404) for cookie injection...")
        try:
            self.driver.get("https://www.linkedin.com/404")
            self.random_delay(2, 4)
        except Exception as e:
            _print(f"Failed to navigate to 404 page: {e}")
            return False
        
        _print("Injecting li_at cookie...")
        try:
            self.driver.add_cookie({
                'name': 'li_at',
                'value': li_at_value,
                'domain': '.linkedin.com'
            })
        except Exception as e:
            _print(f"Failed to inject cookie: {e}")
            return False
        
        # Navigate to /feed/ (lighter than /mynetwork/, fewer redirects).
        # If the tab crashes ("target frame detached" on Chrome 144+),
        # try to recover and retry once.
        verification_urls = [
            "https://www.linkedin.com/feed/",
            "https://www.linkedin.com/mynetwork/",
        ]
        
        page_loaded = False
        for verify_url in verification_urls:
            _print(f"Navigating to {verify_url} to verify session...")
            try:
                self.driver.get(verify_url)
                self.random_delay(5, 8)
                page_loaded = True
                break
            except Exception as e:
                error_str = str(e).lower()
                if "target frame detached" in error_str or "target window already closed" in error_str:
                    _print(f"  Chrome tab crashed ({type(e).__name__}). Attempting recovery...")
                    # Try to open a new tab and navigate
                    try:
                        self.driver.execute_script("window.open('');")
                        handles = self.driver.window_handles
                        if handles:
                            self.driver.switch_to.window(handles[-1])
                            # Re-inject cookie (new tab needs it)
                            self.driver.get("https://www.linkedin.com/404")
                            self.random_delay(1, 2)
                            self.driver.add_cookie({
                                'name': 'li_at',
                                'value': li_at_value,
                                'domain': '.linkedin.com'
                            })
                            self.driver.get(verify_url)
                            self.random_delay(5, 8)
                            page_loaded = True
                            break
                    except Exception as recovery_err:
                        _print(f"  Recovery failed: {recovery_err}")
                        continue
                else:
                    _print(f"  Navigation error: {e}")
                    continue
        
        if not page_loaded:
            _print("")
            _print("=" * 70)
            _print("BROWSER CRASH: Chrome tab crashed during navigation")
            _print("=" * 70)
            _print("This is often caused by:")
            _print("  1. Expired / invalid li_at cookie")
            _print("  2. Chrome v144+ compatibility issue with automation driver")
            _print("  3. LinkedIn anti-bot detection")
            _print("")
            _print("Solutions:")
            _print("  1. Run: python telegram_login.py  (login via Telegram)")
            _print("  2. Get a fresh li_at cookie from your browser")
            _print("  3. Try restarting Chrome completely, then retry")
            _print("=" * 70)
            return False
        
        # Check for rate limiting / error pages -- SAFE: handle None page_source
        page_source = self._get_page_source_safe()
        
        if not page_source:
            _print("")
            _print("="*70)
            _print("PAGE LOAD FAILURE: Could not get page content")
            _print("="*70)
            _print("The page did not load. This usually means:")
            _print("  1. The li_at cookie is expired or invalid")
            _print("  2. LinkedIn is rate-limiting your IP (HTTP 429)")
            _print("  3. Network connectivity issue")
            _print("")
            _print("Solutions:")
            _print("  1. Get a fresh li_at cookie from your browser")
            _print("  2. Wait 15-30 minutes, then try again")
            _print("  3. Use a different IP (VPN, mobile hotspot)")
            _print("  4. Run: python telegram_login.py  (auto cookie capture)")
            _print("="*70)
            return False
        
        rate_limit_indicators = [
            "ERR_TOO_MANY_REDIRECTS",
            "This page isn't working",
            "HTTP ERROR 429",
            "Too Many Requests",
            "rate limit",
            "temporarily restricted",
            "Unusual traffic from your computer network"
        ]
        
        page_lower = page_source.lower()
        for indicator in rate_limit_indicators:
            if indicator.lower() in page_lower:
                _print("")
                _print("="*70)
                _print(f"RATE LIMITED: Detected '{indicator}'")
                _print("="*70)
                _print("LinkedIn has temporarily blocked requests.")
                _print("")
                _print("Solutions:")
                _print("  1. Wait 15-30 minutes before trying again")
                _print("  2. Use a different IP (VPN, mobile hotspot)")
                _print("  3. Get a fresh li_at cookie after waiting")
                _print("  4. Run: python telegram_login.py  (auto cookie capture)")
                _print("="*70)
                return False
        
        # Check if we landed on login/authwall page (cookie definitely expired)
        current_url = self.driver.current_url.lower()
        if any(x in current_url for x in ["/login", "/signin", "/authwall", "uas/login"]):
            _print("")
            _print("="*70)
            _print("COOKIE EXPIRED: Redirected to login page")
            _print("="*70)
            _print("Your li_at cookie is no longer valid.")
            _print("")
            _print("Solutions:")
            _print("  1. Run: python telegram_login.py  (recommended)")
            _print("  2. Manually copy fresh cookie from browser (F12 > Application > Cookies)")
            _print("="*70)
            return False
        
        # Validate we're actually logged in
        if self.is_logged_in():
            _print("Login successful! Session is active.")
            return True
        
        _print("")
        _print("="*70)
        _print("LOGIN FAILED - Cookie is not working or Session Timeout")
        _print("="*70)
        _print("")
        _print("Your li_at cookie has expired. To get a fresh one:")
        _print("  Option 1: Run 'python telegram_login.py' (recommended)")
        _print("  Option 2: Manually copy from browser (F12 > Application > Cookies)")
        _print("="*70)
        return False
    
    # Keep inject_cookies as alias for backward compatibility
    def inject_cookies(self, cookies: list) -> bool:
        """Legacy method - extracts li_at from cookie list and uses simple login."""
        li_at_value = None
        for cookie in cookies:
            if cookie.get("name") == "li_at":
                li_at_value = cookie.get("value")
                break
        
        if li_at_value:
            return self.login_with_cookie(li_at_value)
        
        _print("No li_at cookie found in cookie list!")
        return False
    
    def is_logged_in(self) -> bool:
        """Check if currently logged into LinkedIn using multiple fallback methods."""
        if not self.driver:
            return False
        
        try:
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            current_url = self.driver.current_url
            page_title = (self.driver.title or "").lower()
            
            _print(f"Login check - Title: {self.driver.title}")
            _print(f"Login check - URL: {current_url}")
            
            # Check 1: If redirected to login/signin page
            login_indicators = ["/login", "/signin", "/checkpoint", "/authwall", "uas/login"]
            for indicator in login_indicators:
                if indicator in current_url.lower():
                    _print(f"Not logged in: URL contains '{indicator}'")
                    return False
            
            # Check 2: Page title indicators
            if "sign in" in page_title or "log in" in page_title or "join" in page_title:
                _print("Not logged in: Title indicates login page")
                return False
            
            # Check 3: If we're on the feed, we're logged in
            if "/feed" in current_url:
                _print("Logged in: URL is /feed")
                return True
            
            # Check 4: Profile URL pattern
            if "/in/" in current_url:
                _print("Logged in: URL is a profile page")
                return True
            
            # Check 5: Nav elements
            nav_selectors = [
                "nav.global-nav",
                "[data-test-global-nav-link]",
                ".feed-shared-actor",
                ".scaffold-layout__main",
                "[data-control-name='identity_profile_photo']",
                ".global-nav__me",
                "#global-nav",
            ]
            
            for selector in nav_selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        _print(f"Logged in: Found element '{selector}'")
                        return True
                except Exception:
                    continue
            
            # Check 6: Page source check
            try:
                page_source = self._get_page_source_safe()[:5000]
                auth_indicators = [
                    '"isLoggedIn":true',
                    'data-x-logout-url',
                    'ember-application',
                    'voyager-web',
                ]
                for indicator in auth_indicators:
                    if indicator in page_source:
                        _print(f"Logged in: Page source contains '{indicator}'")
                        return True
            except Exception:
                pass
            
            _print("Login status: Could not confirm login")
            return False
            
        except Exception as e:
            _print(f"Error checking login status: {e}")
            return False
    
    def get_li_at_cookie(self) -> Optional[str]:
        """Extract the li_at cookie value from the current browser session."""
        if not self.driver:
            return None
        try:
            cookies = self.driver.get_cookies()
            for cookie in cookies:
                if cookie.get("name") == "li_at":
                    return cookie.get("value")
        except Exception:
            pass
        return None
    
    def random_delay(self, min_sec: Optional[float] = None, max_sec: Optional[float] = None):
        """Human-like random delay between actions."""
        min_sec = min_sec if min_sec is not None else config.MIN_DELAY
        max_sec = max_sec if max_sec is not None else config.MAX_DELAY
        delay = random.uniform(float(min_sec), float(max_sec))
        time.sleep(delay)
    
    def human_scroll(self, scroll_pause: float = 0.5):
        """Simulate human-like scrolling behavior."""
        if not self.driver:
            return
        
        last_height = self.driver.execute_script("return document.body.scrollHeight")
        
        scroll_position = 0
        while scroll_position < last_height:
            scroll_amount = random.randint(200, 500)
            scroll_position += scroll_amount
            
            self.driver.execute_script(f"window.scrollTo(0, {scroll_position});")
            time.sleep(scroll_pause + random.uniform(0, 0.3))
            
            if random.random() < 0.2:
                time.sleep(random.uniform(1, 3))
            
            new_height = self.driver.execute_script("return document.body.scrollHeight")
            if new_height > last_height:
                last_height = new_height
    
    def human_type(self, element, text: str, min_delay: float = 0.05, max_delay: float = 0.15):
        """Type text with human-like delays between keystrokes."""
        for char in text:
            element.send_keys(char)
            time.sleep(random.uniform(min_delay, max_delay))
            
            if random.random() < 0.05:
                time.sleep(random.uniform(0.3, 0.7))
    
    def close(self):
        """Close the browser."""
        if self.driver:
            driver = self.driver
            try:
                driver.quit()
            except OSError:
                pass
            except Exception as e:
                _print(f"Warning during browser shutdown: {e}")
            finally:
                # undetected_chromedriver calls quit() again from __del__.
                # Override instance quit with a no-op to avoid noisy teardown errors.
                try:
                    driver.quit = lambda *args, **kwargs: None
                except Exception:
                    pass
                self.driver = None
    
    def __enter__(self):
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
