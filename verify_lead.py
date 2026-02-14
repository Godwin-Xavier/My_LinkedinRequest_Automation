"""
Mautic CRM Lead Verification Tool.
Credentials should be set in environment variables.
"""
import os
import requests
import json
from base64 import b64encode

# Load credentials from environment variables
BASE_URL = os.environ.get("MAUTIC_BASE_URL", "")
USERNAME = os.environ.get("MAUTIC_USERNAME", "")
PASSWORD = os.environ.get("MAUTIC_PASSWORD", "")

def get_headers():
    if not USERNAME or not PASSWORD:
        print("Error: MAUTIC_USERNAME and MAUTIC_PASSWORD environment variables must be set.")
        return None
    token = b64encode(f"{USERNAME}:{PASSWORD}".encode()).decode()
    return {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json"
    }

def check_lead(email):
    headers = get_headers()
    if not headers or not BASE_URL:
        print("Error: Mautic credentials not configured. Set MAUTIC_BASE_URL, MAUTIC_USERNAME, MAUTIC_PASSWORD.")
        return
        
    print(f"Checking lead: {email}")
    url = f"{BASE_URL}/api/contacts?search=email:{email}"
    try:
        res = requests.get(url, headers=headers)
        if res.status_code != 200:
             print(f"Error: {res.status_code} - {res.text}")
             return

        data = res.json()
        contacts = data.get("contacts", {})
        
        if not contacts:
            print("Lead NOT found.")
            return

        for cid, c in contacts.items():
            print(f"ID: {cid}")
            tags = c.get("tags", [])
            tag_names = []
            if isinstance(tags, dict):
                 tag_names = [t.get("tag") for t in tags.values()]
            elif isinstance(tags, list):
                 tag_names = [t.get("tag") if isinstance(t, dict) else t for t in tags]
                 
            print(f"Tags: {tag_names}")
            
            # Check Activity
            act_url = f"{BASE_URL}/api/contacts/{cid}/activity"
            act_res = requests.get(act_url, headers=headers)
            events = act_res.json().get("events", [])
            print(f"Activity ({len(events)} events):")
            for e in events:
                etype = e.get("type")
                if etype in ["email.sent", "form.submitted"]:
                    print(f" - {e.get('timestamp')}: {etype} ({e.get('name', 'Unknown')})")

    except Exception as e:
        print(f"Error: {e}")

def check_recent_contacts():
    headers = get_headers()
    if not headers or not BASE_URL:
        print("Error: Mautic credentials not configured.")
        return

    print("Fetching recent contacts...")
    url = f"{BASE_URL}/api/contacts?orderBy=dateAdded&orderByDir=desc&limit=5"
    try:
        res = requests.get(url, headers=headers)
        if res.status_code != 200:
             print(f"Error: {res.status_code} - {res.text}")
             return

        data = res.json()
        contacts = data.get("contacts", {})
        
        if not contacts:
            print("No recent contacts found.")
            return

        for cid, c in contacts.items():
            fields = c.get('fields', {}).get('all', {})
            email = fields.get('email')
            firstname = fields.get('firstname')
            lastname = fields.get('lastname')
            date_added = c.get('dateAdded')
            
            print(f"ID: {cid} | {firstname} {lastname} | {email} | Added: {date_added}")
            
            tags = c.get("tags", [])
            tag_names = []
            if isinstance(tags, dict):
                 tag_names = [t.get("tag") for t in tags.values()]
            elif isinstance(tags, list):
                 tag_names = [t.get("tag") if isinstance(t, dict) else t for t in tags]
            print(f"  Tags: {tag_names}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    if not BASE_URL:
        print("Please set MAUTIC_BASE_URL, MAUTIC_USERNAME, and MAUTIC_PASSWORD environment variables.")
    else:
        check_recent_contacts()
