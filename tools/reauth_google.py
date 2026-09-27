"""
Reconnect the Google accounts listed in config.yaml.

Google logins normally last until you revoke them, but they can die (unused
for months, password change, or an OAuth app left in "Testing" mode, which
expires logins after 7 days). The morning brief tells you when that happens.
Run this and it opens a browser tab per account so you can log in again:

    python tools/reauth_google.py

Add --check to only report which logins are alive, without opening anything.
"""

import argparse
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from google_auth import account_email, all_labels, get_credentials


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true",
                        help="Only report status, never open a browser.")
    args = parser.parse_args()

    labels = all_labels()
    if not labels:
        print("No Google accounts in config.yaml. Run setup.py to add one.")
        return 0

    failed = []
    for label in labels:
        try:
            get_credentials(label, allow_browser=not args.check)
            print(f"OK      {label} ({account_email(label)})")
        except Exception as e:
            failed.append(label)
            print(f"BROKEN  {label} -> {type(e).__name__}: {e}")

    print()
    if failed:
        print("Still broken: " + ", ".join(failed))
        if args.check:
            print("Run without --check to log back in.")
        return 1

    print("All Google accounts connected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
