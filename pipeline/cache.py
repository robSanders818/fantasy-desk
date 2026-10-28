"""Encrypted per-league cache committed to the repo: every team's daily active-lineup totals and each
week's matchup pairs. Finished days don't change (bar stat corrections), so runs only fetch what's
missing plus the last day or two.

Layout: {"days": {"YYYY-MM-DD": {"<team_id>": [FGM, FGA, FTM, FTA, 3PTM, PTS, REB, AST, ST, BLK, TO]}},
         "pairs": {"<week>": [[a, b], ...]}}
"""
import gzip
import json
from pathlib import Path

from crypt import decrypt, encrypt

DIR = Path(__file__).resolve().parent / "cache"
MAGIC = b"FDC1"


def load(league: str) -> dict:
    f = DIR / f"{league}.fdk"
    if not f.exists():
        return {"days": {}, "pairs": {}}
    return json.loads(gzip.decompress(decrypt(f.read_bytes(), MAGIC)))


def save(league: str, data: dict) -> None:
    DIR.mkdir(exist_ok=True)
    blob = gzip.compress(json.dumps(data, separators=(",", ":"), sort_keys=True).encode(), 9)
    (DIR / f"{league}.fdk").write_bytes(encrypt(blob, MAGIC))
