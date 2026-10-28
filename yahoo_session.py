"""Save your Yahoo login session (cookies from your logged-in Chrome) as a GitHub secret.

Run on your Mac; macOS asks once to allow Keychain access to "Chrome Safe Storage":

    uv run yahoo_session.py

The cookies go straight from Chrome to `gh secret set YAHOO_COOKIES`; nothing is printed or
written to disk. Re-run whenever the page says the Yahoo session expired.
"""
import json
import subprocess
import sys

import browser_cookie3

REPO = "robSanders818/fantasy-desk"


def main() -> None:
    jar = browser_cookie3.chrome(domain_name="yahoo.com")
    cookies = {c.name: c.value for c in jar if c.domain.lstrip(".").endswith("yahoo.com")}
    if not cookies:
        sys.exit("No yahoo.com cookies found in Chrome. Log in to Yahoo Fantasy in Chrome first.")
    subprocess.run(["gh", "secret", "set", "YAHOO_COOKIES", "--repo", REPO],
                   input=json.dumps(cookies).encode(), check=True)
    print(f"Saved {len(cookies)} Yahoo cookies to the {REPO} secret YAHOO_COOKIES.")


if __name__ == "__main__":
    main()
