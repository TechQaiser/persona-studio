"""Print the CHANGELOG section for one version, as GitHub release notes.

    python packaging/release_notes.py 0.2.0 notes.md
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def section(version: str) -> str:
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    m = re.search(rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## )", text, re.M | re.S)
    if not m:
        raise SystemExit(f"No '## [{version}]' section in CHANGELOG.md")
    return m.group(1).strip()


def main() -> None:
    version = sys.argv[1].lstrip("v")
    body = section(version)
    notes = f"""## Download

**Windows:** `PersonaStudio-{version}-windows-x64.zip` below. Unzip it anywhere and
run `PersonaStudio.exe`. It starts the engine and the dashboard together and opens
http://localhost:8787. The first start downloads Chromium (about 170 MB).
Bundled engines: Playwright, Patchright, CloakBrowser (Camoufox needs a source
install). Check the download against `SHA256SUMS.txt`.

**From source:** see the [Quick start](https://github.com/TechQaiser/persona-studio#quick-start).

## What's new in {version}

{body}

Full history: [CHANGELOG.md](https://github.com/TechQaiser/persona-studio/blob/v{version}/CHANGELOG.md)
"""
    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_text(notes, encoding="utf-8")
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(notes)


if __name__ == "__main__":
    main()
