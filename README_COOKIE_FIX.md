# LinkedIn Authentication Fix Guide

## Problem
The LinkedIn automation is failing with authentication errors because the cookies in your `.env` file have **expired**.

## Quick Fix (5 minutes)

### Step 1: Export Fresh Cookies

1. **Install Cookie Editor Extension**
   - [Chrome/Edge Extension](https://chrome.google.com/webstore/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm)

2. **Login to LinkedIn**
   - Open your browser (Chrome/Edge)
   - Go to https://www.linkedin.com
   - Login with your credentials
   - Make sure you can see your feed

3. **Export the Cookies**
   - Click the **Cookie Editor** extension icon (top right)
   - Make sure you're on the `linkedin.com` domain
   - Click **"Export"** button (bottom right of the popup)
   - This copies a JSON array to your clipboard

4. **Save to File**
   - Create a new file: `linkedin_cookies.json` (in the project root)
   - Paste the entire JSON you copied
   - Save the file

### Step 2: Update Your .env File

Run the cookie refresher script:

```powershell
python src/cookie_refresher.py
```

This will:
- ✅ Validate your exported cookies
- ✅ Check for critical authentication cookies (`li_at`, `JSESSIONID`)
- ✅ Update the `.env` file automatically

### Step 3: Test the Fix

Test if login works:

```powershell
python main.py --test-login
```

You should see:
- ✅ Browser opens
- ✅ Cookies injected
- ✅ Successfully logged into LinkedIn
- ✅ You're on the feed page

---

## Run Your Automation

Once login test passes, you can run the automation:

```powershell
# Dry run (test without sending invites)
python main.py --run-now --dry-run

# Real run
python main.py --run-now

# Scheduled mode (daily at 9:30 AM IST)
python main.py
```

---

## Why Did This Happen?

LinkedIn cookies have expiration dates. Looking at your `.env` file:
- `__cf_bm` cookie expired on **2025-02-07 17:16:43** (already past)
- `li_at` cookie might be revoked or expired
- When cookies expire, LinkedIn redirects to the login page

This is **normal** and will happen periodically. Just refresh cookies when authentication fails.

---

## Troubleshooting

### "li_at cookie missing or expired"
This is the **main authentication cookie**. You must export fresh cookies to fix this.

### "Login failed after cookie injection"
- Cookies might be from a different IP/location
- Try logging out and back in to LinkedIn before exporting
- Make sure you're exporting from the same browser you login with

### "Could not find 'linkedin_cookies.json'"
Make sure you created the file in the **project root directory** (same folder as `main.py`).

---

## Best Practices

1. **Refresh cookies every few weeks** - LinkedIn cookies typically last 30-60 days
2. **Don't share your cookies** - They contain your authentication credentials
3. **Use the same IP** - Export cookies from the same network you'll run automation
4. **Keep headless=false for testing** - Helps debug authentication issues

---

## Need Help?

If you still have issues:
1. Check that you're logged into LinkedIn in your browser
2. Make sure Cookie Editor shows 25+ cookies for linkedin.com
3. Verify `li_at` cookie is present in the export
4. Try exporting from an incognito window after fresh login
