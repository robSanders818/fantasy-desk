"""Save your Yahoo login session (cookies from your logged-in browser: Brave, Chrome, Arc, Edge or Chromium) as a GitHub secret.

Run on your Mac; macOS asks once to allow Keychain access (e.g. "Brave Safe Storage"):

    uv run yahoo_session.py

The cookies go straight from the browser to `gh secret set YAHOO_COOKIES`; nothing is printed or
written to disk. Re-run whenever the page says the Yahoo session expired.
"""
import json
import subprocess
import sys

import browser_cookie3

REPO = "robSanders818/fantasy-desk"


BROWSERS = [("Brave", browser_cookie3.brave), ("Chrome", browser_cookie3.chrome),
            ("Arc", getattr(browser_cookie3, "arc", None)), ("Edge", browser_cookie3.edge),
            ("Chromium", browser_cookie3.chromium)]


def main() -> None:
    cookies, used = {}, None
    for name, loader in BROWSERS:
        if loader is None:
            continue
        try:
            jar = loader(domain_name="yahoo.com")
        except Exception:
            continue                      # browser not installed / no cookie store
        found = {c.name: c.value for c in jar if c.domain.lstrip(".").endswith("yahoo.com")}
        if found:
            cookies, used = found, name
            break
    if not cookies:
        sys.exit("No yahoo.com cookies found in Brave/Chrome/Arc/Edge/Chromium. Log in to Yahoo Fantasy first.")
    print(f"Using Yahoo cookies from {used}.")
    subprocess.run(["gh", "secret", "set", "YAHOO_COOKIES", "--repo", REPO],
                   input=json.dumps(cookies).encode(), check=True)
    print(f"Saved {len(cookies)} Yahoo cookies to the {REPO} secret YAHOO_COOKIES.")


if __name__ == "__main__":
    main()
