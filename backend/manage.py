#!/usr/bin/env python
"""Django management entrypoint for STARMOND TECHNOLOGY LIMITED backend."""
import os
import sys


def main():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable?"
        ) from exc
    # Load .env for local convenience (never required in containers).
    try:
        from apps.core.env import load_dotenv
        load_dotenv()
    except Exception:
        pass
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
