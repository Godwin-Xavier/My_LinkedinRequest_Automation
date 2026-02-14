"""
LinkedIn Cookie Refresher Tool (Simple Version).
Updates the .env file with the li_at cookie value.
"""
from pathlib import Path

def get_env_path() -> Path:
    """Get .env file path."""
    return Path(__file__).parent.parent / ".env"

def update_env_file(li_at_value: str) -> bool:
    """Update .env file with new LINKEDIN_LI_AT value."""
    env_path = get_env_path()
    
    if not env_path.exists():
        print(f"Error: .env file not found at {env_path}")
        # Create it from example if missing? No, safer to just report error.
        return False
    
    try:
        content = env_path.read_text(encoding="utf-8")
        lines = content.splitlines()
        
        # Prepare the new line
        new_line = f"LINKEDIN_LI_AT={li_at_value}"
        
        # Track if we found/updated the variable
        updated = False
        cookies_removed = False
        
        new_lines = []
        for line in lines:
            # Remove old LINKEDIN_COOKIES line if it exists
            if line.startswith("LINKEDIN_COOKIES="):
                cookies_removed = True
                continue
                
            # Update existing LINKEDIN_LI_AT
            if line.startswith("LINKEDIN_LI_AT="):
                new_lines.append(new_line)
                updated = True
            else:
                new_lines.append(line)
        
        # If we didn't update existing, apppend it
        if not updated:
            # Insert near the top or where cookies used to be
            if cookies_removed:
                # Find where description might be
                for i, line in enumerate(new_lines):
                    if "LINKEDIN AUTHENTICATION" in line:
                        new_lines.insert(i+4, new_line)
                        updated = True
                        break
            
            if not updated:
                new_lines.insert(0, new_line)
        
        # Write back
        env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        return True
        
    except Exception as e:
        print(f"Error updating .env file: {e}")
        return False

def show_instructions():
    """Show simple instructions."""
    print("""
============================================================
  LinkedIn Cookie Update Helper
============================================================

To fix authentication, you need the 'li_at' cookie from LinkedIn:

1. Open LinkedIn in your browser and login
2. Press F12 (Developer Tools)
3. Go to 'Application' tab -> Cookies -> https://www.linkedin.com
4. Find the cookie named 'li_at'
5. Double-click its Value and Copy it
    """)

def main():
    show_instructions()
    
    print("\nPaste your 'li_at' cookie value below:")
    li_at = input("> ").strip()
    
    # Remove quotes if user pasted them
    if (li_at.startswith('"') and li_at.endswith('"')) or (li_at.startswith("'") and li_at.endswith("'")):
        li_at = li_at[1:-1]
        
    if len(li_at) < 10:
        print("ERROR: Cookie value looks too short. Aborting.")
        return
        
    if update_env_file(li_at):
        print("\nSUCCESS! .env file updated with your new cookie.")
        print("\nYou can now run the automation:")
        print("  python main.py --run-now")
    else:
        print("\nFailed to update .env file.")

if __name__ == "__main__":
    main()
