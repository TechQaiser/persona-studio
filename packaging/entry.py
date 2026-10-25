"""PyInstaller entry point for PersonaStudio.exe (see persona/app.py)."""

import sys

from persona.app import main

if __name__ == "__main__":
    sys.exit(main())
