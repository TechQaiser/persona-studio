"""
Entry point of the packaged Windows app (``PersonaStudio.exe``).

* Double-clicked (no arguments): starts the engine API with the built dashboard
  on http://localhost:8787, downloads the browser on first run, and opens the
  dashboard in the default browser. Closing the console window stops it.
* With arguments: behaves exactly like the ``persona`` CLI. That's how the
  server runs its child processes inside the app (see runtime.persona_cmd),
  and it means ``PersonaStudio.exe list`` works from a terminal too.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.request
import webbrowser

PORT = int(os.environ.get("PERSONA_PORT", "8787"))
URL = f"http://localhost:{PORT}/"


def _already_running() -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/health", timeout=2) as r:
            return json.loads(r.read()).get("ok") is True
    except Exception:
        return False


def _open(url: str) -> None:
    if not os.environ.get("PERSONA_NO_BROWSER"):      # e.g. on a server
        webbrowser.open(url)


def _open_when_up() -> None:
    for _ in range(120):
        if _already_running():
            _open(URL)
            return
        time.sleep(0.5)


def run_app() -> int:
    from . import __version__
    print(f"\n  Persona Studio {__version__}\n")
    if _already_running():
        print(f"  Already running. Opening {URL}")
        _open(URL)
        return 0
    from . import engines
    if not engines.chromium_ready():
        print("  First run: downloading the Chromium browser (about 170 MB)...")
        engines.install("chromium")
    # CloakBrowser's larger download (~560 MB) is offered by the dashboard,
    # with a progress window, instead of holding up the start here.
    print(f"  Dashboard: {URL}")
    print("  Keep this window open while you use Persona. Close it to stop.\n")
    threading.Thread(target=_open_when_up, daemon=True).start()
    from .server import serve
    serve(host="127.0.0.1", port=PORT)
    return 0


def main() -> int:
    args = sys.argv[1:]
    if args:
        from .cli import main as cli_main
        return cli_main(args)
    try:
        return run_app()
    except KeyboardInterrupt:
        return 0
    except Exception as e:  # noqa: BLE001 - keep the window open so the error can be read
        print(f"\n  Persona couldn't start: {e}")
        input("  Press Enter to close.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
