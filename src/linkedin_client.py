"""
LinkedIn Client for connection request automation.
Handles recruiter search and sending connection invites.

NEW APPROACH (v2): Click Connect directly from search results page.
- No navigation to individual profiles (faster, less suspicious)
- Paginate through search results using Next button
- Skip profiles with Follow button (no Connect option)
- Skip profiles where 'Send without a note' doesn't appear in modal
- 10-14 invites per day limit

Selector notes (LinkedIn DOM as of Feb 2026):
- Card selector: [data-chameleon-result-urn]  (10 per page, exact match)
- Connect button: aria-label="Invite {Name} to connect" (lowercase c)
- Follow button:  aria-label="Follow {Name}"
- Old selectors like .entity-result, .reusable-search__result-container are DEAD
"""
import random
import sys
import time
import json
from datetime import datetime, date
from typing import Optional, List, Dict
from urllib.parse import quote

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    ElementClickInterceptedException,
    StaleElementReferenceException
)

from config import config
from src.browser_stealth import StealthBrowser
from src.db_manager import DiamondMemory


def _print(msg: str):
    """Print and flush immediately. Strips non-ASCII chars for Windows CP1252."""
    safe = msg.encode("ascii", errors="replace").decode("ascii")
    print(safe)
    sys.stdout.flush()


class LinkedInClient:
    """LinkedIn automation client for recruiter outreach."""

    # Recruiter-related keywords for search (fallback when Gemini unavailable)
    RECRUITER_KEYWORDS = [
        "Recruiter",
        "Senior Recruiter",
        "Technical Recruiter",
        "Talent Acquisition Recruiter",
        "Staffing Consultant",
        "Recruitment Consultant",
        "Hiring Specialist",
    ]

    def __init__(self, browser: StealthBrowser, search_generator=None):
        self.browser = browser
        self.driver = browser.driver
        self.db = DiamondMemory()
        self.search_generator = search_generator
        self._ensure_tables()

    @staticmethod
    def _append_unique(items: List[str], value: str):
        """Append a message only when non-empty and not already present."""
        if value and value not in items:
            items.append(value)

    # ------------------------------------------------------------------
    # Database helpers
    # ------------------------------------------------------------------

    def _ensure_tables(self):
        """Ensure required database tables exist."""
        conn = self.db._get_connection()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sent_invites (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile_url TEXT UNIQUE,
                    profile_name TEXT,
                    profile_title TEXT,
                    sent_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'sent'
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS daily_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT,
                    invites_sent INTEGER DEFAULT 0,
                    invites_failed INTEGER DEFAULT 0,
                    search_queries_used TEXT
                );
            """)
            conn.commit()
        finally:
            conn.close()

    def get_today_invite_count(self) -> int:
        """Get number of invites sent today."""
        conn = self.db._get_connection()
        try:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM sent_invites WHERE DATE(sent_at) = DATE('now')"
            )
            return cursor.fetchone()[0]
        finally:
            conn.close()

    def is_already_invited(self, profile_url: str) -> bool:
        """Check if profile was already invited."""
        conn = self.db._get_connection()
        try:
            cursor = conn.execute(
                "SELECT id FROM sent_invites WHERE profile_url = ?",
                (profile_url,)
            )
            return cursor.fetchone() is not None
        finally:
            conn.close()

    def record_invite(self, profile_url: str, name: str, title: str, status: str = "sent"):
        """Record a sent invite."""
        conn = self.db._get_connection()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO sent_invites
                   (profile_url, profile_name, profile_title, sent_at, status)
                   VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?)""",
                (profile_url, name, title, status)
            )
            conn.commit()
        finally:
            conn.close()

    def _record_daily_stats(self, sent: int, failed: int, queries_used: List[str]):
        """Record daily statistics to the database."""
        conn = self.db._get_connection()
        try:
            today = date.today().isoformat()
            queries_json = json.dumps(queries_used)
            cursor = conn.execute(
                "SELECT id FROM daily_stats WHERE date = ?", (today,)
            )
            existing = cursor.fetchone()
            if existing:
                conn.execute(
                    """UPDATE daily_stats
                       SET invites_sent = invites_sent + ?,
                           invites_failed = invites_failed + ?,
                           search_queries_used = ?
                       WHERE date = ?""",
                    (sent, failed, queries_json, today)
                )
            else:
                conn.execute(
                    """INSERT INTO daily_stats (date, invites_sent, invites_failed, search_queries_used)
                       VALUES (?, ?, ?, ?)""",
                    (today, sent, failed, queries_json)
                )
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Geo URN mapping
    # ------------------------------------------------------------------

    def _get_geo_urn(self, location: str) -> str:
        """Get LinkedIn geo URN for location filtering."""
        geo_urns = {
            "United States": "103644278",
            "Canada": "101174742",
            "Australia": "101452733",
            "United Kingdom": "101165590",
            "UK": "101165590",
            "India": "102713980",
            "Germany": "101282230",
            "Singapore": "102454443",
            "Netherlands": "102890719",
            "Ireland": "104738515",
            "New Zealand": "105490917",
        }
        return geo_urns.get(location, "")

    # ------------------------------------------------------------------
    # Search query generation
    # ------------------------------------------------------------------

    def _get_search_queries(self, max_queries: int = 9) -> List[tuple]:
        """Get role-focused search queries with a capped query count."""
        if self.search_generator:
            try:
                queries = self.search_generator.generate_queries(count=max_queries)
                if queries:
                    _print(f"Generated {len(queries)} search queries")
                    return queries
            except Exception as e:
                _print(f"AI query generation failed: {e}")

        # Fallback: build keyword+location pairs from static lists
        queries = []
        keywords = self.RECRUITER_KEYWORDS.copy()
        locations = config.PRIORITY_LOCATIONS.copy()
        random.shuffle(keywords)
        random.shuffle(locations)
        for keyword in keywords:
            for location in locations:
                queries.append((keyword, location))
        random.shuffle(queries)
        return queries[:max_queries]

    # ------------------------------------------------------------------
    # Core v2: Search-page-based connect flow
    # ------------------------------------------------------------------

    def _build_search_url(self, keyword: str, location: Optional[str] = None) -> str:
        """
        Build LinkedIn people search URL.
        Only uses 'keywords' to reduce tracking parameter overhead.
        """
        import urllib.parse
        
        # Combine keyword and location into a single query for simpler URL
        # "Technical Recruiter United States" works better than separate filters
        query = keyword
        if location and location.lower() != "worldwide":
            query = f"{keyword} {location}"
            
        params = [
            f"keywords={urllib.parse.quote(query)}",
        ]
        
        return "https://www.linkedin.com/search/results/people/?" + "&".join(params)

    def _navigate_to_search(self, keyword: str, location: Optional[str] = None) -> bool:
        """Navigate to a people search results page."""
        url = self._build_search_url(keyword, location)
        _print(f"  Navigating to search: '{keyword}' in '{location or 'Global'}'")
        if not self.browser.safe_navigate(url):
            _print(f"  Failed to load search results (Rate Limited?)")
            return False
        self.browser.random_delay(3, 5)

        # Rate limit check
        page_source = self.browser._get_page_source_safe()
        if "HTTP ERROR 429" in page_source:
            _print("  Rate limit detected (429). Stopping.")
            return False

        _print(f"  Search page loaded: {self.driver.current_url[:80]}...")
        return True

    def _inspect_search_page_state(self) -> Dict:
        """Collect high-value diagnostics from the current search page."""
        state = {
            "diagnostics": [],
            "empty_results": False,
            "session_lost": False,
            "rate_limited": False,
        }

        if not self.driver:
            self._append_unique(state["diagnostics"], "Browser driver is unavailable during search inspection.")
            state["session_lost"] = True
            return state

        current_url = ""
        page_title = ""
        try:
            current_url = (self.driver.current_url or "").lower()
        except Exception:
            pass

        try:
            page_title = (self.driver.title or "").lower()
        except Exception:
            pass

        if any(x in current_url for x in ["/login", "/signin", "/checkpoint", "/authwall", "uas/login"]):
            state["session_lost"] = True
            self._append_unique(
                state["diagnostics"],
                "LinkedIn redirected search to login/checkpoint page; cookie session likely expired.",
            )

        if any(x in page_title for x in ["sign in", "log in", "challenge", "checkpoint"]):
            state["session_lost"] = True
            self._append_unique(
                state["diagnostics"],
                "LinkedIn page title indicates authentication or challenge flow during search.",
            )

        body_text = ""
        try:
            body = self.driver.find_element(By.TAG_NAME, "body")
            body_text = (body.text or "").lower()[:5000]
        except Exception:
            pass

        empty_indicators = [
            "no results found",
            "we couldn't find any results",
            "try removing a filter",
            "expand your search",
            "no matching people",
        ]
        if any(indicator in body_text for indicator in empty_indicators):
            state["empty_results"] = True
            self._append_unique(
                state["diagnostics"],
                "LinkedIn search returned no matching profiles for the current query/filter.",
            )

        rate_indicators = [
            "too many requests",
            "temporarily restricted",
            "unusual traffic",
            "http error 429",
            "protect our members",
        ]
        if any(indicator in body_text for indicator in rate_indicators):
            state["rate_limited"] = True
            self._append_unique(
                state["diagnostics"],
                "LinkedIn displayed a temporary restriction or rate-limit message on search.",
            )

        challenge_indicators = [
            "verify your identity",
            "let us know you're human",
            "security verification",
        ]
        if any(indicator in body_text for indicator in challenge_indicators):
            state["session_lost"] = True
            self._append_unique(
                state["diagnostics"],
                "LinkedIn requested identity/challenge verification during search.",
            )

        return state

    def _get_result_cards(self) -> list:
        """Get all search result card elements on the current page.

        LinkedIn obfuscates class names but keeps data attributes stable.
        Tested selectors (Feb 2026):
          [data-chameleon-result-urn]                              -> 10 (exact)
          div[data-view-name='search-entity-result-universal-template'] -> 10
          .search-results-container li                             -> 21 (includes extras)
        Dead selectors (return 0):
          li.reusable-search__result-container
          .reusable-search__result-container
          div.entity-result
          .scaffold-layout__list-container li
        """
        # Try working selectors first (fastest match)
        selectors = [
            "[data-chameleon-result-urn]",
            "div[data-view-name='search-entity-result-universal-template']",
            # Legacy fallbacks (in case LinkedIn reverts)
            "li.reusable-search__result-container",
            "div.entity-result",
        ]
        for selector in selectors:
            try:
                _print(f"    Trying card selector: {selector}")
                WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                cards = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if cards:
                    _print(f"    -> Found {len(cards)} cards with: {selector}")
                    return cards
            except TimeoutException:
                _print(f"    -> Timeout (no match)")
                continue
        return []

    def _extract_person_from_card(self, card) -> Optional[Dict]:
        """Extract name, title, and profile URL from a search result card.

        Uses multiple fallback strategies since LinkedIn obfuscates class names.
        The most reliable signals are:
          - a[href*='/in/'] for profile URL
          - span[aria-hidden='true'] for display name
          - button aria-label "Invite {Name} to connect" for name backup
        """
        try:
            # --- Profile URL ---
            profile_url = None
            for sel in ["a[href*='/in/']",
                        ".app-aware-link[href*='/in/']",
                        ".entity-result__title-text a"]:
                try:
                    link = card.find_element(By.CSS_SELECTOR, sel)
                    href = link.get_attribute("href")
                    if href and "/in/" in href:
                        profile_url = href.split("?")[0]
                        break
                except NoSuchElementException:
                    continue

            # --- Name ---
            name = "Unknown"
            # Method 1: span with aria-hidden (the display name text)
            for sel in ["span[aria-hidden='true']",
                        "a[href*='/in/'] span[aria-hidden='true']",
                        ".entity-result__title-text a span[aria-hidden='true']"]:
                try:
                    elem = card.find_element(By.CSS_SELECTOR, sel)
                    txt = elem.text.strip()
                    if txt and len(txt) > 1 and txt != "LinkedIn":
                        name = txt
                        break
                except NoSuchElementException:
                    continue

            # Method 2: if name still unknown, try button aria-label
            if name == "Unknown":
                try:
                    btns = card.find_elements(By.TAG_NAME, "button")
                    for btn in btns:
                        aria = btn.get_attribute("aria-label") or ""
                        # "Invite John Doe to connect"
                        if aria.startswith("Invite ") and " to connect" in aria:
                            name = aria.replace("Invite ", "").replace(" to connect", "")
                            break
                except Exception:
                    pass

            # --- Title / headline ---
            title = ""
            # Try to get the text of the card and parse headline from it
            for sel in [".entity-result__primary-subtitle",
                        ".entity-result__summary",
                        ".subline-level-1"]:
                try:
                    elem = card.find_element(By.CSS_SELECTOR, sel)
                    title = elem.text.strip()
                    if title:
                        break
                except NoSuchElementException:
                    continue

            # Fallback: parse title from card text (second non-empty line after name)
            if not title:
                try:
                    card_text = card.text or ""
                    lines = [l.strip() for l in card_text.split("\n") if l.strip()]
                    # lines[0] = name, lines[1] = "View ... profile", lines[2] = degree,
                    # lines[3] = title/headline (usually)
                    for line in lines:
                        if line == name or "View " in line or "degree" in line.lower():
                            continue
                        if line in ("Connect", "Follow", "Message"):
                            continue
                        if len(line) > 5:
                            title = line
                            break
                except Exception:
                    pass

            return {
                "url": profile_url or "",
                "name": name,
                "title": title,
            }
        except Exception as e:
            _print(f"    [extract error] {e}")
            return None

    def _find_connect_button_in_card(self, card) -> Optional[object]:
        """Find the Connect button inside a search result card.

        Returns the button element, or None if the card has Follow or no Connect.

        Detection strategy (Feb 2026 LinkedIn DOM):
        1. Primary: button whose aria-label contains 'Invite' and 'connect'
        2. Fallback: button whose visible text is exactly 'Connect'
        3. Skip cards where the ONLY action button is 'Follow'
        """
        try:
            buttons = card.find_elements(By.TAG_NAME, "button")
            has_follow = False
            connect_btn = None

            for btn in buttons:
                try:
                    # Check aria-label first (most reliable)
                    aria = (btn.get_attribute("aria-label") or "").lower()
                    if "invite" in aria and "connect" in aria:
                        if btn.is_displayed() and btn.is_enabled():
                            connect_btn = btn
                            break

                    # Check visible text
                    btn_text = btn.text.strip()
                    if btn_text == "Follow":
                        has_follow = True
                        # Do NOT return None here - keep checking other buttons
                        continue
                    if btn_text == "Connect" and btn.is_displayed() and btn.is_enabled():
                        connect_btn = btn
                        break
                except StaleElementReferenceException:
                    continue

            if connect_btn:
                return connect_btn
            if has_follow:
                return None  # Card only has Follow, no Connect
            return None  # No Connect or Follow found
        except Exception:
            pass
        return None

    def _card_has_follow_action(self, card) -> bool:
        """Return True when a card appears to offer Follow but no Connect."""
        try:
            buttons = card.find_elements(By.TAG_NAME, "button")
            has_follow = False
            for btn in buttons:
                try:
                    aria = (btn.get_attribute("aria-label") or "").lower()
                    txt = (btn.text or "").strip().lower()

                    if "invite" in aria and "connect" in aria:
                        return False
                    if txt == "connect":
                        return False

                    if txt == "follow" or ("follow" in aria and "connect" not in aria):
                        has_follow = True
                except StaleElementReferenceException:
                    continue
            return has_follow
        except Exception:
            return False

    def _wait_for_modal(self, timeout: int = 10):
        """Wait for LinkedIn's invitation modal to fully appear and stabilize."""
        modal = None
        modal_selectors = [
            (By.CSS_SELECTOR, ".artdeco-modal"),
            (By.CSS_SELECTOR, "[role='dialog']"),
            (By.CSS_SELECTOR, ".send-invite"),
        ]
        for by, selector in modal_selectors:
            try:
                modal = WebDriverWait(self.driver, timeout).until(
                    EC.visibility_of_element_located((by, selector))
                )
                if modal:
                    break
            except TimeoutException:
                continue

        if not modal:
            return None

        # Wait for modal animation to finish (poll position stability)
        last_rect = None
        stable_count = 0
        for _ in range(20):
            try:
                rect = modal.rect
                if last_rect and rect == last_rect:
                    stable_count += 1
                    if stable_count >= 3:
                        break
                else:
                    stable_count = 0
                last_rect = rect
            except StaleElementReferenceException:
                break
            time.sleep(0.1)

        return modal

    def _has_send_without_note(self, modal) -> bool:
        """Check if the modal contains a 'Send without a note' button."""
        try:
            buttons = modal.find_elements(By.TAG_NAME, "button")
            for btn in buttons:
                try:
                    txt = btn.text.strip().lower()
                    if "send without a note" in txt and btn.is_displayed():
                        return True
                except StaleElementReferenceException:
                    continue
        except Exception:
            pass
        return False

    def _click_send_without_note(self, modal) -> bool:
        """Click the 'Send without a note' button inside the modal.

        Scoped to the modal element. Uses ActionChains for coordinate accuracy.
        Verifies the modal closes after clicking.
        """
        MAX_ATTEMPTS = 3

        for attempt in range(1, MAX_ATTEMPTS + 1):
            send_btn = None

            # --- Method A: button by aria-label ---
            for label in ["Send without a note", "Send now", "Send invitation"]:
                try:
                    candidates = modal.find_elements(
                        By.XPATH, f".//button[@aria-label='{label}']"
                    )
                    for btn in candidates:
                        if btn.is_displayed() and btn.is_enabled():
                            send_btn = btn
                            break
                    if send_btn:
                        break
                except (NoSuchElementException, StaleElementReferenceException):
                    continue

            # --- Method B: button by visible text ---
            if not send_btn:
                for pattern in ["Send without a note", "Send now"]:
                    try:
                        candidates = modal.find_elements(
                            By.XPATH,
                            f".//button[contains(normalize-space(.), '{pattern}')]"
                        )
                        for btn in candidates:
                            if btn.is_displayed() and btn.is_enabled():
                                send_btn = btn
                                break
                        if send_btn:
                            break
                    except (NoSuchElementException, StaleElementReferenceException):
                        continue

            # --- Method C: primary button with 'send' text ---
            if not send_btn:
                try:
                    candidates = modal.find_elements(
                        By.CSS_SELECTOR, "button.artdeco-button--primary"
                    )
                    for btn in candidates:
                        if btn.is_displayed() and btn.is_enabled() and "send" in btn.text.strip().lower():
                            send_btn = btn
                            break
                except (NoSuchElementException, StaleElementReferenceException):
                    pass

            if not send_btn:
                if attempt < MAX_ATTEMPTS:
                    self.browser.random_delay(1, 2)
                    modal = self._wait_for_modal(timeout=5)
                    if not modal:
                        return False
                continue

            # --- Click it ---
            try:
                self.driver.execute_script(
                    "arguments[0].scrollIntoView({block:'center',behavior:'instant'});",
                    send_btn
                )
                self.browser.random_delay(0.3, 0.5)

                actions = ActionChains(self.driver)
                actions.move_to_element(send_btn)
                actions.pause(0.2)
                actions.click(send_btn)
                actions.perform()
            except (ElementClickInterceptedException, StaleElementReferenceException):
                try:
                    self.driver.execute_script("arguments[0].click();", send_btn)
                except Exception:
                    if attempt < MAX_ATTEMPTS:
                        self.browser.random_delay(1, 2)
                        modal = self._wait_for_modal(timeout=5)
                        if not modal:
                            return False
                    continue
            except Exception:
                if attempt < MAX_ATTEMPTS:
                    self.browser.random_delay(1, 2)
                    modal = self._wait_for_modal(timeout=5)
                    if not modal:
                        return False
                continue

            # --- Verify modal closed ---
            self.browser.random_delay(1.5, 2.5)
            modal_still_open = False
            try:
                for m in self.driver.find_elements(By.CSS_SELECTOR, ".artdeco-modal"):
                    try:
                        if m.is_displayed():
                            modal_still_open = True
                            break
                    except StaleElementReferenceException:
                        pass
            except Exception:
                pass

            if modal_still_open:
                if attempt < MAX_ATTEMPTS:
                    modal = self._wait_for_modal(timeout=5)
                    if not modal:
                        return False
                continue
            else:
                return True

        return False

    def _dismiss_modal(self):
        """Dismiss any open modal (click X or press Escape)."""
        try:
            dismiss_btn = self.driver.find_element(
                By.CSS_SELECTOR, ".artdeco-modal__dismiss"
            )
            if dismiss_btn.is_displayed():
                dismiss_btn.click()
                self.browser.random_delay(0.5, 1)
                return
        except (NoSuchElementException, StaleElementReferenceException):
            pass
        # Fallback: press Escape
        try:
            ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
            self.browser.random_delay(0.5, 1)
        except Exception:
            pass

    def _go_to_next_page(self) -> bool:
        """Click the 'Next' pagination button. Returns False if no next page."""
        try:
            # Scroll to bottom to make pagination visible
            self.driver.execute_script(
                "window.scrollTo(0, document.body.scrollHeight);"
            )
            self.browser.random_delay(1, 2)

            # Find the Next button
            next_selectors = [
                "button[aria-label='Next']",
                "a[aria-label='Next']",
                "button.artdeco-pagination__button--next",
                ".artdeco-pagination__button--next",
            ]
            for selector in next_selectors:
                try:
                    next_btn = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if next_btn.is_displayed() and next_btn.is_enabled():
                        # Check it's not disabled
                        disabled = next_btn.get_attribute("disabled")
                        if disabled:
                            _print("  Next button is disabled - last page reached")
                            return False
                        next_btn.click()
                        _print("  Clicked Next - loading next page...")
                        self.browser.random_delay(3, 5)
                        return True
                except NoSuchElementException:
                    continue

            _print("  No Next button found - last page or pagination missing")
            return False
        except Exception as e:
            _print(f"  Pagination error: {e}")
            return False

    def search_and_connect(self, keyword: str, location: Optional[str], remaining: int) -> Dict:
        """Search for recruiters and send invites directly from search results.

        This is the v2 approach: stay on the search results page,
        click Connect buttons, handle modals, paginate through pages.

        Args:
            keyword:   Search keyword (e.g. "Technical Recruiter")
            location:  Country name (e.g. "Canada")
            remaining: Max invites to send in this search

        Returns:
            Dict with sent/failed/skipped counts
        """
        result = {
            "sent": 0,
            "failed": 0,
            "skipped": 0,
            "recruiters": [],
            "follow_only_detected": False,
            "throttled": False,
            "throttle_reason": "",
            "diagnostics": [],
            "navigation_failed": False,
            "empty_results_detected": False,
            "session_lost": False,
            "pages_scanned": 0,
            "cards_seen": 0,
        }

        def add_diagnostic(message: str):
            self._append_unique(result["diagnostics"], message)

        throttle_modal_indicators = [
            "weekly invitation limit",
            "you've reached the weekly invitation limit",
            "invitation limit",
            "unable to send invitation",
            "temporarily restricted",
            "protect our members",
        ]

        # Navigate to search
        if not self._navigate_to_search(keyword, location):
            result["navigation_failed"] = True

            nav_issue = (getattr(self.browser, "last_navigation_issue", "") or "").strip()
            if nav_issue:
                add_diagnostic(nav_issue)

            page_state = self._inspect_search_page_state()
            for diagnostic in page_state.get("diagnostics", []):
                add_diagnostic(diagnostic)

            if page_state.get("empty_results"):
                result["empty_results_detected"] = True
            if page_state.get("session_lost"):
                result["session_lost"] = True
            if page_state.get("rate_limited"):
                result["throttled"] = True
                if not result["throttle_reason"]:
                    result["throttle_reason"] = (
                        "LinkedIn displayed a temporary restriction or rate-limit message during search navigation."
                    )
                    add_diagnostic(result["throttle_reason"])

            try:
                if not self.browser.is_logged_in():
                    result["session_lost"] = True
                    add_diagnostic(
                        "LinkedIn session check failed while opening search results; cookie may be expired."
                    )
            except Exception:
                pass

            if not result["diagnostics"]:
                add_diagnostic("Search page failed to load; likely rate-limited or temporarily blocked.")
            
            # Save debug snapshot on navigation failure
            self.browser.save_debug_snapshot(f"nav_fail_{keyword[:10]}")
            return result

        max_pages = 5  # Don't go beyond 5 pages per query to stay safe
        for page_num in range(1, max_pages + 1):
            if result["sent"] >= remaining:
                break

            result["pages_scanned"] += 1

            _print(f"\n  --- Page {page_num} ---")

            # Light scroll to ensure results are loaded (NOT human_scroll which hangs)
            self.driver.execute_script("window.scrollTo(0, 300);")
            self.browser.random_delay(2, 3)

            # Get all result cards on this page
            _print("  Looking for result cards...")
            cards = self._get_result_cards()
            if not cards:
                _print("  No result cards found on this page")
                
                # Save debug snapshot when no cards found
                self.browser.save_debug_snapshot(f"no_cards_{keyword[:10]}_page{page_num}")

                page_state = self._inspect_search_page_state()
                for diagnostic in page_state.get("diagnostics", []):
                    add_diagnostic(diagnostic)

                if page_state.get("empty_results"):
                    result["empty_results_detected"] = True
                if page_state.get("session_lost"):
                    result["session_lost"] = True
                if page_state.get("rate_limited"):
                    result["throttled"] = True
                    if not result["throttle_reason"]:
                        result["throttle_reason"] = (
                            "LinkedIn displayed a temporary restriction or rate-limit message on search page."
                        )
                        add_diagnostic(result["throttle_reason"])

                if not page_state.get("diagnostics"):
                    add_diagnostic(
                        "Search page loaded but no result cards were detected. LinkedIn layout/loading may have changed."
                    )

                try:
                    if not self.browser.is_logged_in():
                        result["session_lost"] = True
                        add_diagnostic(
                            "LinkedIn session check failed while reading search results; refresh cookie if this repeats."
                        )
                except Exception:
                    pass
                break

            _print(f"  Found {len(cards)} result cards")
            result["cards_seen"] += len(cards)
            page_candidates = 0
            page_follow_only = 0

            for i, card in enumerate(cards):
                if result["sent"] >= remaining:
                    break

                # Extract person info
                person = self._extract_person_from_card(card)
                if not person:
                    _print(f"  [{i+1}] Could not extract person info, skipping")
                    # Save snapshot if extraction fails (limiting to first failure per page to avoid spam)
                    if i == 0:
                        self.browser.save_debug_snapshot(f"extract_fail_{keyword[:10]}")
                    continue

                name = person["name"]
                title = person["title"]
                url = person["url"]
                page_candidates += 1
                _print(f"  [{i+1}] {name} | {title[:50]} | {url[:40] if url else 'no-url'}")

                # Skip if already invited
                if url and self.is_already_invited(url):
                    _print(f"       -> already invited, skipping")
                    result["skipped"] += 1
                    continue

                # Find Connect button (skip if Follow or no button)
                connect_btn = self._find_connect_button_in_card(card)
                if not connect_btn:
                    if self._card_has_follow_action(card):
                        page_follow_only += 1
                    _print(f"       -> no Connect button (Follow only?), skipping")
                    result["skipped"] += 1
                    continue

                # Scroll the Connect button into view
                try:
                    self.driver.execute_script(
                        "arguments[0].scrollIntoView({block:'center',behavior:'smooth'});",
                        connect_btn
                    )
                    self.browser.random_delay(0.5, 1)
                except Exception:
                    pass

                # Click Connect
                _print(f"       -> clicking Connect button...")
                try:
                    connect_btn.click()
                except ElementClickInterceptedException:
                    try:
                        self.driver.execute_script("arguments[0].click();", connect_btn)
                    except Exception as e:
                        _print(f"       -> CLICK FAILED: {e}")
                        result["failed"] += 1
                        continue
                except Exception as e:
                    _print(f"       -> CLICK FAILED: {e}")
                    result["failed"] += 1
                    continue

                self.browser.random_delay(1, 2)

                # Wait for modal
                _print(f"       -> waiting for modal...")
                modal = self._wait_for_modal(timeout=8)
                if not modal:
                    _print(f"       -> no modal appeared, skipping")
                    result["skipped"] += 1
                    continue

                # Check if 'Send without a note' exists in modal
                if not self._has_send_without_note(modal):
                    modal_text = ""
                    try:
                        modal_text = (modal.text or "").lower()
                    except Exception:
                        pass

                    matched = next(
                        (indicator for indicator in throttle_modal_indicators if indicator in modal_text),
                        "",
                    )
                    if matched:
                        result["throttled"] = True
                        result["throttle_reason"] = (
                            f"LinkedIn invite throttling detected in modal: '{matched}'"
                        )
                        add_diagnostic(result["throttle_reason"])
                        _print(f"       -> {result['throttle_reason']}")
                        self._dismiss_modal()
                        return result

                    _print(f"       -> no 'Send without a note' button, dismissing modal")
                    self._dismiss_modal()
                    result["skipped"] += 1
                    continue

                # Click 'Send without a note'
                _print(f"       -> clicking 'Send without a note'...")
                sent = self._click_send_without_note(modal)
                if sent:
                    _print(f"       ** SENT invite to {name}! **")
                    self.record_invite(url or name, name, title, "sent")
                    result["sent"] += 1
                    result["recruiters"].append(person)
                else:
                    _print(f"       -> FAILED to send invite to {name}")
                    self._dismiss_modal()
                    self.record_invite(url or name, name, title, "send_btn_failed")
                    result["failed"] += 1

                # Human-like delay between invites (15-30 seconds)
                _print(f"       -> waiting 15-30s before next...")
                self.browser.random_delay(15, 30)

            if page_candidates > 0 and page_follow_only == page_candidates:
                if not result["follow_only_detected"]:
                    _print(
                        "  Diagnostic: all visible profiles are Follow-only on this page. "
                        "Likely out-of-network results or temporary invite throttling."
                    )
                result["follow_only_detected"] = True
                add_diagnostic("All visible profiles on this page were Follow-only (no Connect action available).")

            if result["session_lost"]:
                break

            # Go to next page if we still need more invites
            if result["sent"] < remaining:
                if not self._go_to_next_page():
                    break
            else:
                break

        return result

    # ------------------------------------------------------------------
    # Main orchestrator
    # ------------------------------------------------------------------

    def run_daily_outreach(self, limit: Optional[int] = None, dry_run: bool = False) -> Dict:
        """Run the daily outreach routine using search-page connect flow."""
        # Warm-up: Scroll the feed a bit to look human before jumping to search
        _print("Warming up on the feed to humanize behavior...")
        try:
            # Scroll down
            self.browser.driver.execute_script("window.scrollTo(0, document.body.scrollHeight/3);")
            time.sleep(random.uniform(2, 4))
            # Scroll up a tiny bit
            self.browser.driver.execute_script("window.scrollBy(0, -300);")
            time.sleep(random.uniform(1, 3))
        except Exception:
            _print("Warm-up scroll failed (harmless)")

        limit = limit or config.DAILY_INVITE_LIMIT

        already_sent = self.get_today_invite_count()
        remaining = max(0, limit - already_sent)

        if remaining == 0:
            _print(f"Daily limit reached. Already sent {already_sent} invites today.")
            return {
                "success": True,
                "sent": 0,
                "failed": 0,
                "skipped": 0,
                "total_today": already_sent,
                "recruiters_found": [],
                "errors": [],
                "warnings": [],
                "diagnostics": ["Daily invite limit already reached before outreach started."],
                "limit_reached": True,
                "queries_attempted": 0,
                "queries_navigation_failed": 0,
                "queries_empty_results": 0,
                "queries_follow_only": 0,
            }

        _print(f"Target: {remaining} more invites (already sent {already_sent} today)")

        results = {
            "success": True,
            "sent": 0,
            "failed": 0,
            "skipped": 0,
            "recruiters_found": [],
            "errors": [],
            "warnings": [],
            "diagnostics": [],
            "limit_reached": False,
            "queries_attempted": 0,
            "queries_navigation_failed": 0,
            "queries_empty_results": 0,
            "queries_follow_only": 0,
        }

        # Keep query volume intentionally small to stay role-focused and avoid broad probing.
        search_queries = self._get_search_queries(max_queries=9)
        queries_used = []
        total_sent = 0
        follow_only_queries = 0

        for keyword, location in search_queries:
            if total_sent >= remaining:
                break

            # Only search in priority locations
            if location not in config.PRIORITY_LOCATIONS:
                continue

            _print(f"\n{'='*60}")
            _print(f"Search: '{keyword}' in '{location}'")
            _print(f"{'='*60}")
            queries_used.append(f"{keyword} | {location}")
            results["queries_attempted"] += 1

            search_result = self.search_and_connect(
                keyword, location, remaining - total_sent
            )

            total_sent += search_result["sent"]
            results["sent"] += search_result["sent"]
            results["failed"] += search_result["failed"]
            results["skipped"] += search_result["skipped"]
            results["recruiters_found"].extend(search_result["recruiters"])

            for diagnostic in search_result.get("diagnostics", []):
                self._append_unique(results["diagnostics"], diagnostic)

            if search_result.get("navigation_failed"):
                results["queries_navigation_failed"] += 1

            if search_result.get("empty_results_detected"):
                results["queries_empty_results"] += 1

            if search_result.get("follow_only_detected"):
                follow_only_queries += 1
                results["queries_follow_only"] += 1

            if search_result.get("session_lost"):
                session_msg = (
                    "LinkedIn session appears invalid during outreach. "
                    "Refresh LINKEDIN_LI_AT cookie and retry."
                )
                self._append_unique(results["errors"], session_msg)
                _print(f"  {session_msg}")
                break

            if search_result.get("throttled"):
                throttle_reason = search_result.get("throttle_reason") or "LinkedIn invite throttling detected"
                self._append_unique(results["errors"], throttle_reason)
                _print(f"  {throttle_reason}")
                break

            if total_sent >= remaining:
                _print(f"\nDaily target reached! Sent {total_sent} invites.")
                break

            # Delay between different search queries.
            self.browser.random_delay(10, 18)

        if results["sent"] == 0 and follow_only_queries > 0:
            follow_only_msg = (
                "Search returned Follow-only profiles; now forcing 2nd-degree network filter. "
                "If this persists, LinkedIn may be throttling invites."
            )
            self._append_unique(results["warnings"], follow_only_msg)

        if results["sent"] == 0 and results["queries_empty_results"] > 0:
            self._append_unique(
                results["warnings"],
                "LinkedIn search returned no matching profiles for one or more query/location combinations.",
            )

        if (
            results["sent"] == 0
            and results["queries_attempted"] > 0
            and results["queries_navigation_failed"] == results["queries_attempted"]
        ):
            self._append_unique(
                results["warnings"],
                "All search queries failed to load. LinkedIn may be rate-limiting or blocking this session.",
            )

        if results["sent"] == 0 and results["failed"] > 0:
            self._append_unique(
                results["warnings"],
                "Invite actions were attempted but failed before confirmation. Review modal/button diagnostics.",
            )

        if results["sent"] == 0 and not results["errors"] and not results["warnings"]:
            self._append_unique(
                results["warnings"],
                "No invites were sent and LinkedIn did not expose a clear failure reason.",
            )
            # innovative: capture state if we did work but got zero results
            if results["queries_attempted"] > 0:
                 self.browser.save_debug_snapshot("zero_invites_mystery")

        results["total_today"] = already_sent + results["sent"]
        self._record_daily_stats(results["sent"], results["failed"], queries_used)

        _print(f"\n{'='*60}")
        _print(f"OUTREACH COMPLETE")
        _print(f"  Sent: {results['sent']}")
        _print(f"  Failed: {results['failed']}")
        _print(f"  Skipped: {results['skipped']}")
        _print(f"  Total today: {results['total_today']}")
        _print(f"{'='*60}")

        return results
