#!/usr/bin/env python
import os
import sys


def main():
    # Always use this project's settings (docs often use myproject.settings).
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Install it with: pip install -r requirements.txt"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
