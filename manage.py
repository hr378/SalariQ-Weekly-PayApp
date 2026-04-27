#!/usr/bin/env python
import os
import sys
from pathlib import Path


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    vendor_dir = base_dir / "vendor"
    try:
        import django  # noqa: F401
    except ModuleNotFoundError:
        if vendor_dir.exists():
            sys.path.insert(0, str(vendor_dir))

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
