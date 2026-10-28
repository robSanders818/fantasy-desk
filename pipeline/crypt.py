"""Shared encryption for everything this public repo stores about the leagues.

Format: MAGIC(4) | salt(16) | iv(12) | AES-256-GCM(payload),  key = PBKDF2-SHA256(passphrase, salt, 310000)
The page's data file uses MAGIC "FDK1" with a gzipped JSON payload (must match web/src/crypto.ts).
Passphrase: $FD_PASSPHRASE (GitHub Actions) or the macOS Keychain item "fantasy-desk". Never printed.
"""
import hashlib
import os
import secrets
import subprocess
import sys

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ITERATIONS = 310_000


def passphrase() -> str:
    p = os.environ.get("FD_PASSPHRASE")
    if p:
        return p
    r = subprocess.run(["security", "find-generic-password", "-s", "fantasy-desk", "-w"],
                       capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        sys.exit('No passphrase: set $FD_PASSPHRASE or create the Keychain item "fantasy-desk".')
    return r.stdout.strip()


def _key(pw: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, ITERATIONS, 32)


def encrypt(payload: bytes, magic: bytes, pw: str | None = None) -> bytes:
    salt, iv = secrets.token_bytes(16), secrets.token_bytes(12)
    return magic + salt + iv + AESGCM(_key(pw or passphrase(), salt)).encrypt(iv, payload, None)


def decrypt(blob: bytes, magic: bytes, pw: str | None = None) -> bytes:
    if blob[:4] != magic:
        raise ValueError("unrecognized encrypted file")
    salt, iv = blob[4:20], blob[20:32]
    return AESGCM(_key(pw or passphrase(), salt)).decrypt(iv, blob[32:], None)
