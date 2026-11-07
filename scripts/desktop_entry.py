"""Entry for the optional Windows executable; package via scripts/build-windows.ps1."""
import multiprocessing
import sys
from pathlib import Path

from trendfinder.cli import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    # Frozen UI starts beside the executable, not in a transient extraction dir.
    if getattr(sys, "frozen", False):
        import os
        os.chdir(Path(sys.executable).parent)
    raise SystemExit(main(sys.argv[1:] or ["serve", "--open"]))
