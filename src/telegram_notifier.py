"""
Telegram Notification System for LinkedIn Automation.
Sends daily summaries and error alerts.
"""
import asyncio
import html as html_mod
import re
from datetime import datetime
from typing import Optional, Dict, List

from telegram import Bot
from telegram.error import TelegramError

from config import config


def _print_safe(message: str):
    """Print safely on Windows consoles that may not support Unicode."""
    safe = str(message).encode("ascii", errors="replace").decode("ascii")
    print(safe)


class TelegramNotifier:
    """Telegram bot for sending notifications."""
    
    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None):
        self.bot_token = bot_token or config.TELEGRAM_BOT_TOKEN
        self.chat_id = chat_id or config.TELEGRAM_CHAT_ID

    @staticmethod
    def _sanitize_text(value: object) -> str:
        """Return UTF-8-safe text without NUL bytes."""
        text = "" if value is None else str(value)
        text = text.replace("\x00", "")
        return text.encode("utf-8", errors="replace").decode("utf-8")

    @staticmethod
    def _strip_html(text: str) -> str:
        """Strip basic HTML tags for plain-text fallback messages."""
        no_tags = re.sub(r"<[^>]+>", "", text)
        return html_mod.unescape(no_tags)

    def send_message(self, message: str, parse_mode: Optional[str] = "HTML") -> bool:
        """Send a message (sync wrapper). Creates a fresh Bot each time to avoid event loop issues."""
        if not self.bot_token or not self.chat_id:
            _print_safe("Telegram not configured. Message not sent.")
            return False

        clean_message = self._sanitize_text(message)

        async def _send(text: str, msg_parse_mode: Optional[str]) -> bool:
            bot = Bot(token=self.bot_token)
            async with bot:
                await bot.send_message(
                    chat_id=self.chat_id,
                    text=text,
                    parse_mode=msg_parse_mode,
                )
            return True

        try:
            # Create a FRESH Bot + httpx session for each call.
            # This avoids the "Event loop is closed" error that happens when
            # a Bot object's internal httpx client is tied to a dead event loop.
            return asyncio.run(_send(clean_message, parse_mode))
        except TelegramError as e:
            error_text = self._sanitize_text(e)
            # Common failure when dynamic text accidentally breaks HTML entities.
            if parse_mode == "HTML" and "can't parse entities" in error_text.lower():
                try:
                    plain_message = self._sanitize_text(self._strip_html(clean_message))
                    return asyncio.run(_send(plain_message, None))
                except Exception as fallback_error:
                    _print_safe(f"Telegram fallback send failed: {self._sanitize_text(fallback_error)}")
                    return False

            _print_safe(f"Telegram send failed: {error_text}")
            return False
        except Exception as e:
            _print_safe(f"Telegram send failed: {self._sanitize_text(e)}")
            return False
    
    def send_daily_summary(self, results: Dict) -> bool:
        """Send the daily outreach summary."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        queries_attempted = int(results.get("queries_attempted", 0) or 0)
        queries_navigation_failed = int(results.get("queries_navigation_failed", 0) or 0)
        queries_empty_results = int(results.get("queries_empty_results", 0) or 0)
        queries_follow_only = int(results.get("queries_follow_only", 0) or 0)
        limit_reached = bool(results.get("limit_reached", False))
        sent_count = int(results.get("sent", 0) or 0)
        failed_count = int(results.get("failed", 0) or 0)
        errors = results.get("errors", [])
        warnings = results.get("warnings", [])
        diagnostics = results.get("diagnostics", [])
        
        message = f"""<b>LinkedIn Outreach Report</b>
<i>{timestamp}</i>

<b>Statistics:</b>
- Invites Sent: <b>{sent_count}</b>
- Failed: {failed_count}
- Skipped: {results.get('skipped', 0)}
- Total Today: {results.get('total_today', 0)}

"""

        if queries_attempted > 0 or queries_navigation_failed > 0 or queries_empty_results > 0 or queries_follow_only > 0:
            message += "<b>Search Diagnostics:</b>\n"
            message += f"- Queries Attempted: {queries_attempted}\n"
            message += f"- Navigation Failures: {queries_navigation_failed}\n"
            message += f"- Empty Result Queries: {queries_empty_results}\n"
            message += f"- Follow-only Queries: {queries_follow_only}\n\n"
        
        recruiters = results.get('recruiters_found', [])[:5]
        if recruiters:
            message += "<b>Recent Invites:</b>\n"
            for r in recruiters:
                name = html_mod.escape(self._sanitize_text(r.get('name', 'Unknown'))[:30])
                title = html_mod.escape(self._sanitize_text(r.get('title', ''))[:40])
                message += f"- {name}\n  <i>{title}</i>\n"
        
        if errors:
            message += f"\n<b>Errors:</b>\n"
            for error in errors[:3]:
                safe_error = html_mod.escape(self._sanitize_text(error)[:120])
                message += f"- {safe_error}\n"

        if warnings:
            message += f"\n<b>Warnings:</b>\n"
            for warning in warnings[:3]:
                safe_warning = html_mod.escape(self._sanitize_text(warning)[:120])
                message += f"- {safe_warning}\n"

        if diagnostics:
            message += f"\n<b>Diagnostics:</b>\n"
            for diagnostic in diagnostics[:3]:
                safe_diag = html_mod.escape(self._sanitize_text(diagnostic)[:120])
                message += f"- {safe_diag}\n"
        
        if errors:
            message += "\n<b>Status: Error</b>"
        elif limit_reached:
            message += "\n<b>Status: Daily Limit Reached</b>"
        elif sent_count > 0 and (failed_count > 0 or warnings or diagnostics):
            message += "\n<b>Status: Success with Warnings</b>"
        elif sent_count > 0:
            message += "\n<b>Status: Success</b>"
        elif failed_count > 0:
            message += "\n<b>Status: Partial Failure</b>"
        elif warnings or diagnostics:
            message += "\n<b>Status: Warning</b>"
        else:
            message += "\n<b>Status: No Action Needed</b>"
        
        return self.send_message(message)
    
    def send_error_alert(self, error: str, context: str = "") -> bool:
        """Send an error alert."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        safe_context = html_mod.escape(self._sanitize_text(context or "Unknown"))
        safe_error = html_mod.escape(self._sanitize_text(error)[:500])

        message = f"""<b>LinkedIn Automation Error</b>
<i>{timestamp}</i>

<b>Context:</b> {safe_context}

<b>Error:</b>
<code>{safe_error}</code>

Please check the logs for more details.
"""
        return self.send_message(message)
    
    def send_cookie_warning(self) -> bool:
        """Send a warning about cookie expiration."""
        message = """<b>LinkedIn Cookie Warning</b>

The LinkedIn session has expired. 
Please refresh your cookie.

<b>Quick fix:</b>
Run <code>python telegram_login.py</code> or double-click <code>telegram_login.bat</code>

<b>Manual steps:</b>
1. Log into LinkedIn in your browser
2. Press F12 &gt; Application &gt; Cookies &gt; linkedin.com
3. Copy the 'li_at' cookie value
4. Update the .env file
5. Restart the automation
"""
        return self.send_message(message)
    
    def send_startup_message(self) -> bool:
        """Send a message when automation starts."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        locations = '\n'.join(
            f"- {html_mod.escape(self._sanitize_text(loc))}"
            for loc in config.PRIORITY_LOCATIONS
        )
        message = f"""<b>LinkedIn Automation Started</b>
<i>{timestamp}</i>

Daily job scheduled for: <b>{config.SCHEDULE_TIME} IST</b>
Daily invite limit: <b>{config.DAILY_INVITE_LIMIT}</b>

Priority locations:
{locations}
"""
        return self.send_message(message)


    def send_log_file(self, file_path: str, caption: str = "Execution Log") -> bool:
        """Send a log file to Telegram."""
        if not self.bot_token or not self.chat_id:
            return False

        async def _send_doc():
            bot = Bot(token=self.bot_token)
            async with bot:
                try:
                    with open(file_path, 'rb') as f:
                        await bot.send_document(
                            chat_id=self.chat_id,
                            document=f,
                            caption=caption
                        )
                    return True
                except Exception as e:
                    _print_safe(f"Failed to upload log file: {e}")
                    return False

        try:
            return asyncio.run(_send_doc())
        except Exception as e:
            _print_safe(f"Telegram file upload failed: {e}")
            return False


# Singleton instance
notifier = TelegramNotifier()
