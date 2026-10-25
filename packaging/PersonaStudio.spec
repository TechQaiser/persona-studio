# PyInstaller spec for the Windows app. Build from the repo root, after
# `npm run build` in dashboard/:
#     pyinstaller packaging/PersonaStudio.spec --noconfirm
# Output: dist/PersonaStudio/PersonaStudio.exe (a folder build: the server
# re-runs the exe for each launch, which a one-file build would unpack each time).
from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = SPECPATH + "/.."

datas = [(ROOT + "/dashboard/dist", "dashboard")]
binaries = []
hiddenimports = collect_submodules("persona") + collect_submodules("uvicorn")
# Launch engines bundled in the app. Camoufox isn't: it needs an older Playwright.
for pkg in ("playwright", "patchright", "cloakbrowser"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    [ROOT + "/packaging/entry.py"],
    pathex=[ROOT + "/engine"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "pytest", "camoufox"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PersonaStudio",
    console=True,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="PersonaStudio", upx=False)
