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
import hashlib
import json
import os
import secrets
import subprocess
import sys
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "web" / "public" / "data" / "desk.fdk"
MAGIC = b"FDK1"
ITERATIONS = 310_000
REPO = "robSanders818/fantasy-desk"


def passphrase() -> str:
    p = os.environ.get("FD_PASSPHRASE")
    if p:
        return p
    r = subprocess.run(["security", "find-generic-password", "-s", "fantasy-desk", "-w"],
                       capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        sys.exit('No passphrase: set $FD_PASSPHRASE or create the Keychain item "fantasy-desk".')
    return r.stdout.strip()


def encrypt(plain: bytes, pw: str) -> bytes:
    salt, iv = secrets.token_bytes(16), secrets.token_bytes(12)
    key = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, ITERATIONS, 32)
    return MAGIC + salt + iv + AESGCM(key).encrypt(iv, gzip.compress(plain, 9), None)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*", help="league JSON files (named <league>.json)")
    ap.add_argument("--save-secret", action="store_true", help="store the Keychain passphrase as the FD_PASSPHRASE secret")
    a = ap.parse_args()
    pw = passphrase()
    if a.save_secret:
        subprocess.run(["gh", "secret", "set", "FD_PASSPHRASE", "--repo", REPO], input=pw.encode(), check=True)
        print(f"Saved the passphrase to the {REPO} secret FD_PASSPHRASE.")
    if not a.files:
        return
    leagues = {Path(f).stem: json.loads(Path(f).read_text()) for f in a.files}
    bundle = {"generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="minutes"),
              "leagues": leagues}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(encrypt(json.dumps(bundle, separators=(",", ":"), ensure_ascii=False).encode(), pw))
    print(f"encrypted {', '.join(leagues)} -> {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
