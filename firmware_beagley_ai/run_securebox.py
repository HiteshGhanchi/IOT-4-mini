#!/usr/bin/env python3
"""Start the SecureBox sensor demo from this directory."""

from pathlib import Path
import runpy
import sys


ROOT = Path(__file__).resolve().parent
MAIN = ROOT / "main.py"
CONFIG = ROOT / "config.py"


def main():
    if not CONFIG.exists():
        raise SystemExit(
            "Missing config.py. Copy config.py.example to config.py and "
            "verify the GPIO chip paths."
        )
    if not MAIN.exists():
        raise SystemExit("Missing main.py in " + str(ROOT))

    print("SecureBox sensor demo")
    print("Location: %s" % ROOT)
    print("Press Ctrl+C to stop. CSV: %s" % (ROOT / "readings.csv"))
    sys.path.insert(0, str(ROOT))
    runpy.run_path(str(MAIN), run_name="__main__")


if __name__ == "__main__":
    main()
