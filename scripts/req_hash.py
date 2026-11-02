"""Print a hash of the requirements files so start.bat knows when to reinstall packages."""
import hashlib
from pathlib import Path

root = Path(__file__).resolve().parent.parent
digest = hashlib.md5()
for name in ("requirements.txt", "requirements-dev.txt"):
    path = root / name
    if path.exists():
        digest.update(path.read_bytes().replace(b"\r\n", b"\n"))
print(digest.hexdigest())
