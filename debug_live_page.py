"""
Quick diagnostic: Save the current search results page HTML and test selectors.
Run this WHILE the browser from main.py is still open (it isn't - so we'll launch fresh).
"""
import time
import sys
from config import config
from src.browser_stealth import StealthBrowser

def main():
    print("=== LinkedIn Search Page Diagnostic ===\n")

    browser = StealthBrowser(headless=False)
    browser.start()

    # Login
    print("Logging in...")
    if not browser.login_with_cookie(config.LINKEDIN_LI_AT):
        print("Login failed!")
        browser.close()
        return

    print("Login OK. Navigating to search page...")
    time.sleep(3)

    # Navigate to a search page
    url = "https://www.linkedin.com/search/results/people/?keywords=Technical+Recruiter&geoUrn=%5B%22103644278%22%5D&origin=SWITCH_SEARCH_VERTICAL"
    browser.driver.get(url)
    time.sleep(8)

    # Save full page source
    html = browser.driver.page_source or ""
    with open("debug_live_search.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Saved page source ({len(html)} chars) to debug_live_search.html")

    # Test all card selectors
    from selenium.webdriver.common.by import By

    card_selectors = [
        "li.reusable-search__result-container",
        ".reusable-search__result-container",
        "div.entity-result",
        "[data-chameleon-result-urn]",
        ".scaffold-layout__list-container li",
        "li.reusable-search-simple-insight",  # possible new class
        ".search-results-container li",
        "div[data-view-name='search-entity-result-universal-template']",
        "li div.linked-area",  # generic
        "ul.reusable-search__entity-result-list li",
        "div.mb1",  # very generic fallback
    ]

    print("\n--- Testing card selectors ---")
    for sel in card_selectors:
        try:
            elems = browser.driver.find_elements(By.CSS_SELECTOR, sel)
            count = len(elems)
            if count > 0:
                print(f"  [FOUND {count:2d}] {sel}")
                # Show first element's tag and classes
                first = elems[0]
                tag = first.tag_name
                cls = first.get_attribute("class") or ""
                text_preview = (first.text or "")[:100].replace("\n", " | ")
                print(f"             tag={tag} class='{cls[:80]}'")
                print(f"             text='{text_preview}'")
            else:
                print(f"  [   0    ] {sel}")
        except Exception as e:
            print(f"  [ERROR   ] {sel} -> {e}")

    # Test finding Connect buttons directly
    print("\n--- Testing button detection ---")
    all_buttons = browser.driver.find_elements(By.TAG_NAME, "button")
    print(f"Total buttons on page: {len(all_buttons)}")

    connect_buttons = []
    follow_buttons = []
    for btn in all_buttons:
        try:
            txt = btn.text.strip()
            if txt == "Connect":
                connect_buttons.append(btn)
            elif txt == "Follow":
                follow_buttons.append(btn)
        except Exception:
            pass

    print(f"Connect buttons: {len(connect_buttons)}")
    print(f"Follow buttons: {len(follow_buttons)}")

    # For each Connect button, inspect its parent structure
    if connect_buttons:
        print("\n--- Connect button parent analysis ---")
        for i, btn in enumerate(connect_buttons[:3]):
            try:
                # Get parent chain
                parent = browser.driver.execute_script(
                    """
                    var el = arguments[0];
                    var chain = [];
                    var current = el;
                    for (var j = 0; j < 8; j++) {
                        current = current.parentElement;
                        if (!current) break;
                        chain.push({
                            tag: current.tagName,
                            cls: (current.className || '').substring(0, 100),
                            id: current.id || ''
                        });
                    }
                    return chain;
                    """,
                    btn
                )
                print(f"\n  Connect button [{i}] parent chain:")
                for level, p in enumerate(parent):
                    print(f"    {'  ' * level}{p['tag']}.{p['cls'][:60]} {'#' + p['id'] if p['id'] else ''}")

                # Try to find the name near this button
                card_container = browser.driver.execute_script(
                    """
                    var el = arguments[0];
                    // Walk up to find the li or containing block
                    var current = el;
                    for (var j = 0; j < 10; j++) {
                        current = current.parentElement;
                        if (!current) return null;
                        if (current.tagName === 'LI') return current;
                    }
                    return null;
                    """,
                    btn
                )
                if card_container:
                    card_cls = card_container.get_attribute("class") or ""
                    card_text = (card_container.text or "")[:150].replace("\n", " | ")
                    print(f"    Found parent LI: class='{card_cls[:80]}'")
                    print(f"    Card text: '{card_text}'")
                else:
                    print(f"    No parent LI found!")

                # Check button attributes
                aria = btn.get_attribute("aria-label") or ""
                cls = btn.get_attribute("class") or ""
                print(f"    Button class: '{cls[:80]}'")
                print(f"    Button aria-label: '{aria}'")

            except Exception as e:
                print(f"  Error analyzing button [{i}]: {e}")

    # Also try XPath approach to find Connect buttons
    print("\n--- XPath button tests ---")
    xpath_tests = [
        "//button[normalize-space(.)='Connect']",
        "//button[contains(@aria-label, 'connect')]",
        "//button[contains(@aria-label, 'Connect')]",
        "//button[contains(@aria-label, 'Invite')]",
        "//span[text()='Connect']/ancestor::button",
    ]
    for xpath in xpath_tests:
        try:
            elems = browser.driver.find_elements(By.XPATH, xpath)
            print(f"  [{len(elems):2d}] {xpath}")
        except Exception as e:
            print(f"  [ERR] {xpath} -> {e}")

    print("\n--- Done. Browser will close in 30 seconds ---")
    print("(Or close it manually)")
    time.sleep(30)
    browser.close()


if __name__ == "__main__":
    main()
