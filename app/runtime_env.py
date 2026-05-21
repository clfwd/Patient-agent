"""Helpers for loading project-level .env files without extra dependencies."""

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_PATH = PROJECT_ROOT / ".env"


def _parse_env_line(line):
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None, None
    if stripped.startswith("export "):
        stripped = stripped[7:].strip()
    if "=" not in stripped:
        return None, None

    key, raw_value = stripped.split("=", 1)
    key = key.strip()
    value = raw_value.strip()
    if not key:
        return None, None

    if value and value[0] == value[-1] and value[0] in ("'", '"'):
        quote = value[0]
        value = value[1:-1]
        if quote == '"':
            value = value.encode("utf-8").decode("unicode_escape")
    return key, value


def load_dotenv_file(path=None, override=False):
    """Load key-value pairs from a .env file into os.environ."""

    env_path = Path(path or DEFAULT_ENV_PATH)
    if not env_path.exists() or not env_path.is_file():
        return {"loaded": False, "path": str(env_path), "count": 0}

    loaded = 0
    for line in env_path.read_text(encoding="utf-8").splitlines():
        key, value = _parse_env_line(line)
        if not key:
            continue
        if not override and key in os.environ:
            continue
        os.environ[key] = value
        loaded += 1

    return {"loaded": True, "path": str(env_path), "count": loaded}
