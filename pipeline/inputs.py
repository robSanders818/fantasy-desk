"""Pack / unpack a league's model inputs (priors, keepers, team names, schedule...) as an encrypted
tarball, so they can live in this public repo.

    uv run pipeline/inputs.py pack basketball     # pipeline/basketball/data/ -> pipeline/basketball/inputs.fdk
    uv run pipeline/inputs.py unpack basketball   # the reverse (CI does this before each run)
"""
import io
import sys
import tarfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from crypt import decrypt, encrypt

ROOT = Path(__file__).resolve().parent
MAGIC = b"FDI1"


def pack(league: str) -> None:
    src = ROOT / league / "data"
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        tar.add(src, arcname="data")
    out = ROOT / league / "inputs.fdk"
    out.write_bytes(encrypt(buf.getvalue(), MAGIC))
    print(f"packed {league} inputs -> {out.relative_to(ROOT.parent)} ({out.stat().st_size / 1024:.0f} KB)")


def unpack(league: str) -> None:
    blob = (ROOT / league / "inputs.fdk").read_bytes()
    with tarfile.open(fileobj=io.BytesIO(decrypt(blob, MAGIC)), mode="r:gz") as tar:
        tar.extractall(ROOT / league, filter="data")
    print(f"unpacked {league} inputs")


if __name__ == "__main__":
    {"pack": pack, "unpack": unpack}[sys.argv[1]](sys.argv[2])
