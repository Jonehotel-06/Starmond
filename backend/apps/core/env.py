"""Minimal dependency-free .env loader (used only for local convenience)."""
import os


def load_dotenv(path=None):
    path = path or os.path.join(os.getcwd(), ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


def env(key, default=None, cast=str):
    raw = os.environ.get(key)
    if raw is None or raw == "":
        if default is not None and cast is list and isinstance(default, str):
            return [i.strip() for i in default.split(",") if i.strip()]
        return default
    if cast is bool:
        return raw.lower() in ("1", "true", "yes", "on")
    if cast is list:
        return [i.strip() for i in raw.split(",") if i.strip()]
    return cast(raw)
