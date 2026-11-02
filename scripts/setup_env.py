"""Create a ready-to-use .env on first run (SQLite + a random SECRET_KEY)."""
import secrets
from pathlib import Path

root = Path(__file__).resolve().parent.parent
env_file, example = root / ".env", root / ".env.example"

if env_file.exists():
    raise SystemExit(0)  # never overwrite the user's settings

overrides = {
    "SECRET_KEY": secrets.token_hex(32),
    "DATABASE_URL": "sqlite:///shortener.db",
    "BASE_URL": "http://localhost:5000",
}
lines: list[str] = []
for line in example.read_text(encoding="utf-8").splitlines():
    key = line.split("=", 1)[0].strip()
    if "=" in line and not line.lstrip().startswith("#") and key in overrides:
        line = f"{key}={overrides[key]}"
    lines.append(line)

env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("Created .env with a random SECRET_KEY and a local SQLite database.")
