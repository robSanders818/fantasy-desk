"""Check whether the saved Yahoo session works from wherever this runs (e.g. GitHub Actions).

Prints only status codes and yes/no checks -- never page content or cookie values -- because
Actions logs on a public repo are public.

    YAHOO_COOKIES='{"...": "..."}' uv run probe.py
"""
import json
import os
import sys
from urllib.parse import urlparse

import requests

LEAGUE, TEAM = 13126, 9
URL = f"https://basketball.fantasysports.yahoo.com/nba/{LEAGUE}/{TEAM}"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")


def main() -> None:
    raw = os.environ.get("YAHOO_COOKIES", "")
    if not raw:
        sys.exit("YAHOO_COOKIES is not set")
    cookies = json.loads(raw)
    r = requests.get(URL, cookies=cookies, headers={"User-Agent": UA}, timeout=30, allow_redirects=True)
    host = urlparse(r.url).netloc
    checks = {
        "http_status": r.status_code,
        "final_host": host,                                   # login.yahoo.com means a redirect to sign in
        "redirected_to_login": "login.yahoo.com" in host,
        "roster_table_found": 'id="statTable0"' in r.text,
        "own_team_page": "Pick and Rollin" in r.text,
        "request_denied_999": r.status_code == 999,
        "cookie_count": len(cookies),
    }
    for k, v in checks.items():
        print(f"{k}: {v}")
    ok = checks["roster_table_found"] and checks["own_team_page"]
    print("RESULT:", "logged in OK" if ok else "NOT logged in")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
