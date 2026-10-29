"""Bundle league JSON files and encrypt them for the page: web/public/data/desk.fdk

    uv run scripts/encrypt.py basketball.json [hockey.json ...]      # passphrase from Keychain
    uv run scripts/encrypt.py --save-secret                           # copy Keychain passphrase to the
                                                                      # FD_PASSPHRASE GitHub secret
The passphrase comes from $FD_PASSPHRASE (GitHub Actions) or the macOS Keychain item
"fantasy-desk" (create it once: security add-generic-password -s fantasy-desk -a "$USER" -w).
It is never printed.

Format (must match web/src/crypto.ts):
    "FDK1" | salt(16) | iv(12) | AES-256-GCM(gzip(json)),  key = PBKDF2-SHA256(passphrase, salt, 310000)
"""
import argparse
import datetime
import gzip
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
from crypt import decrypt, encrypt, passphrase

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "web" / "public" / "data" / "desk.fdk"
REPO = "robSanders818/fantasy-desk"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*", help="league JSON files (named <league>.json)")
    ap.add_argument("--save-secret", action="store_true", help="store the Keychain passphrase as the FD_PASSPHRASE secret")
    ap.add_argument("--keep-previous", action="store_true",
                    help="for any sport whose JSON is missing this run, keep its section from the current desk.fdk")
    a = ap.parse_args()
    pw = passphrase()
    if a.save_secret:
        subprocess.run(["gh", "secret", "set", "FD_PASSPHRASE", "--repo", REPO], input=pw.encode(), check=True)
        print(f"Saved the passphrase to the {REPO} secret FD_PASSPHRASE.")
    if not a.files:
        return
    leagues = {Path(f).stem: json.loads(Path(f).read_text()) for f in a.files if Path(f).exists()}
    if a.keep_previous and OUT.exists():
        prev = json.loads(gzip.decompress(decrypt(OUT.read_bytes(), b"FDK1", pw)))
        for k, v in prev.get("leagues", {}).items():
            if k not in leagues:
                v.setdefault("status", {})["stale"] = True      # this sport's update failed; showing the last good one
                leagues[k] = v
    if not leagues:
        print("nothing to encrypt")
        return
    bundle = {"generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="minutes"),
              "leagues": leagues}
    token = os.environ.get("FD_REFRESH_TOKEN")
    if token:   # lets the page's Refresh button start update.yml (only after the passphrase unlocks it)
        bundle["refresh"] = {"repo": REPO, "workflow": "update.yml", "token": token}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(encrypt(gzip.compress(json.dumps(bundle, separators=(",", ":"), ensure_ascii=False).encode(), 9), b"FDK1", pw))
    print(f"encrypted {', '.join(leagues)} -> {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
