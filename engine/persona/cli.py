"""
Command-line interface for Persona.

    persona create <name> [--os] [--locale] [--proxy] [--seed] [--mobile]
    persona list [--tag TAG]
    persona show <name|id>
    persona launch <name|id> [--headless]
    persona edit <name|id> [--notes] [--add-tag] [--proxy]
    persona regen <name|id> [--os] [--locale]   (new fingerprint, same identity slot)
    persona delete <name|id>
    persona export <name|id> <file>
    persona import <file>
    persona check <name|id>                       (validate fingerprint coherence)
    persona cookies list|export|import <name|id>  (move a session in or out)
    persona engines                               (list launch engines + install status)
    persona default-engine [name]                 (show/set the engine new profiles use)
    persona serve [--host] [--port]               (run the HTTP API for the dashboard)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

from . import __version__
from .fingerprint import generate, validate
from .models import Profile, Proxy
from .store import ProfileStore


# ---- pretty output helpers ----------------------------------------------
class C:
    B = "\033[1m"; DIM = "\033[2m"; GRN = "\033[32m"; RED = "\033[31m"
    YEL = "\033[33m"; CYN = "\033[36m"; END = "\033[0m"


def _c(text: str, color: str) -> str:
    return f"{color}{text}{C.END}" if sys.stdout.isatty() else text


def _parse_proxy(raw: Optional[str], country: Optional[str]) -> Optional[Proxy]:
    """Accept 'scheme://[user:pass@]host:port' and return a Proxy."""
    if not raw:
        return None
    server, user, pw = raw, None, None
    if "@" in raw:
        scheme, rest = raw.split("://", 1) if "://" in raw else ("http", raw)
        creds, hostport = rest.rsplit("@", 1)
        if ":" in creds:
            user, pw = creds.split(":", 1)
        server = f"{scheme}://{hostport}"
    return Proxy(server=server, username=user, password=pw, country=country)


# ---- commands ------------------------------------------------------------
def cmd_create(args, store: ProfileStore) -> int:
    if store.find_by_name(args.name):
        print(_c(f"A profile named '{args.name}' already exists.", C.RED))
        return 1
    proxy = _parse_proxy(args.proxy, args.country)
    fp = generate(seed=args.seed, os=args.os, locale=args.locale,
                  proxy=proxy, mobile=args.mobile)
    # No --engine given? Fall back to the saved default (CloakBrowser first).
    # If one IS given, remember it as the new default ("last engine wins").
    engine = args.engine or store.get_default_engine()
    if args.engine:
        store.set_default_engine(args.engine)
    from . import drivers
    if engine in drivers.names() and not drivers.is_installed(engine):
        print(_c(f"Note: engine '{engine}' isn't installed yet; install it before launching.", C.YEL))
    prof = Profile(name=args.name, fingerprint=fp, proxy=proxy,
                   notes=args.notes or "", tags=args.tag or [], engine=engine)
    store.save(prof)
    print(_c(f"Created profile '{prof.name}'  ", C.GRN) + _c(f"[{prof.id}]", C.DIM))
    _print_summary(prof)
    return 0


def cmd_list(args, store: ProfileStore) -> int:
    profiles = store.list()
    if args.tag:
        profiles = [p for p in profiles if args.tag in p.tags]
    if not profiles:
        print(_c("No profiles yet. Create one with:  persona create <name>", C.DIM))
        return 0
    print(_c(f"{'ID':<14}{'NAME':<22}{'OS':<9}{'LOCALE':<9}PROXY", C.B))
    for p in profiles:
        proxy = p.proxy.server if p.proxy else "-"
        print(f"{_c(p.id, C.DIM):<23}{p.name:<22}{p.fingerprint.os:<9}"
              f"{p.fingerprint.locale:<9}{proxy}")
    print(_c(f"\n{len(profiles)} profile(s).", C.DIM))
    return 0


def cmd_show(args, store: ProfileStore) -> int:
    prof = store.resolve(args.ref)
    if not prof:
        print(_c(f"No profile matching '{args.ref}'.", C.RED))
        return 1
    _print_summary(prof, full=True)
    return 0


def cmd_launch(args, store: ProfileStore) -> int:
    prof = store.resolve(args.ref)
    if not prof:
        print(_c(f"No profile matching '{args.ref}'.", C.RED))
        return 1
    problems = validate(prof.fingerprint)
    if problems:
        print(_c("Warning: fingerprint has consistency issues:", C.YEL))
        for p in problems:
            print(f"  - {p}")
    engine = args.engine or prof.engine or "playwright"
    print(_c(f"Launching '{prof.name}' via {engine}...", C.CYN))
    from .launcher import launch  # imported lazily (browser deps optional)
    launch(prof, store, headless=args.headless, keep_open=False, engine=engine)
    return 0


def cmd_engines(args, store: ProfileStore) -> int:
    from . import drivers
    default = store.get_default_engine()
    print(_c("Launch engines:", C.B))
    for name, ok in drivers.available().items():
        mark = _c("installed", C.GRN) if ok else _c("not installed", C.DIM)
        star = _c("  <- default (new profiles)", C.CYN) if name == default else ""
        print(f"  {name:<14}{mark}{star}")
    return 0


def cmd_default_engine(args, store: ProfileStore) -> int:
    from . import drivers
    if not args.name:
        print(_c(f"Default engine for new profiles: ", C.B) + _c(store.get_default_engine(), C.CYN))
        print(_c(f"Set it with:  persona default-engine <{'|'.join(drivers.names())}>", C.DIM))
        return 0
    if args.name not in drivers.names():
        print(_c(f"Unknown engine '{args.name}'. Choose one of: {', '.join(drivers.names())}.", C.RED))
        return 1
    store.set_default_engine(args.name)
    note = "" if drivers.is_installed(args.name) else _c("  (not installed yet — install it before launching)", C.YEL)
    print(_c(f"Default engine for new profiles is now '{args.name}'.", C.GRN) + note)
    return 0


def cmd_edit(args, store: ProfileStore) -> int:
    prof = store.resolve(args.ref)
    if not prof:
        print(_c(f"No profile matching '{args.ref}'.", C.RED))
        return 1
    if args.notes is not None:
        prof.notes = args.notes
    if args.add_tag:
        for t in args.add_tag:
            if t not in prof.tags:
                prof.tags.append(t)
    if args.proxy is not None:
        prof.proxy = _parse_proxy(args.proxy, args.country) if args.proxy else None
    store.save(prof)
    print(_c(f"Updated '{prof.name}'.", C.GRN))
    return 0


def cmd_regen(args, store: ProfileStore) -> int:
    prof = store.resolve(args.ref)
    if not prof:
        print(_c(f"No profile matching '{args.ref}'.", C.RED))
        return 1
    prof.fingerprint = generate(os=args.os, locale=args.locale, proxy=prof.proxy)
    store.save(prof)
    print(_c(f"Regenerated fingerprint for '{prof.name}'.", C.GRN))
    _print_summary(prof)
    return 0


def cmd_delete(args, store: ProfileStore) -> int:
    prof = store.resolve(args.ref)
    if not prof:
        print(_c(f"No profile matching '{args.ref}'.", C.RED))
        return 1
    if not args.yes:
        ans = input(f"Delete '{prof.name}' [{prof.id}]? This removes its session too. (y/N) ")
        if ans.strip().lower() != "y":
            print("Aborted.")
            return 0
    store.delete(prof.id)
    print(_c(f"Deleted '{prof.name}'.", C.GRN))
    return 0


def cmd_export(args, store: ProfileStore) -> int:
    prof = store.resolve(args.ref)
    if not prof:
        print(_c(f"No profile matching '{args.ref}'.", C.RED))
        return 1
    dest = store.export(prof.id, args.file)
    print(_c(f"Exported to {dest}", C.GRN))
    return 0


def cmd_import(args, store: ProfileStore) -> int:
    prof = store.import_file(args.file)
    print(_c(f"Imported '{prof.name}'  ", C.GRN) + _c(f"[{prof.id}]", C.DIM))
    return 0


def _resolve_or_fail(args, store: ProfileStore) -> Optional[Profile]:
    prof = store.resolve(args.ref)
    if not prof:
        print(_c(f"No profile matching '{args.ref}'.", C.RED))
    return prof


def cmd_cookies_list(args, store: ProfileStore) -> int:
    prof = _resolve_or_fail(args, store)
    if not prof:
        return 1
    from . import cookies as ck
    jar = ck.read(prof, store, engine=args.engine)
    if not jar:
        print(_c(f"'{prof.name}' has no cookies yet.", C.DIM))
        return 0
    by_domain: dict[str, int] = {}
    for c in jar:
        by_domain[c["domain"]] = by_domain.get(c["domain"], 0) + 1
    print(_c(f"{len(jar)} cookie(s) across {len(by_domain)} domain(s):", C.B))
    for domain, n in sorted(by_domain.items(), key=lambda kv: -kv[1]):
        print(f"  {domain:<40}{_c(str(n), C.DIM)}")
    return 0


def cmd_cookies_export(args, store: ProfileStore) -> int:
    prof = _resolve_or_fail(args, store)
    if not prof:
        return 1
    from . import cookies as ck
    print(_c(f"Reading cookies from '{prof.name}'...", C.CYN))
    jar = ck.read(prof, store, engine=args.engine)
    # A .txt destination almost always means "give me curl's cookies.txt".
    fmt = args.format or ("netscape" if str(args.file).lower().endswith(".txt") else "json")
    Path(args.file).write_text(ck.dumps(jar, fmt), encoding="utf-8")
    print(_c(f"Exported {len(jar)} cookie(s) to {args.file}  ", C.GRN) + _c(f"({fmt})", C.DIM))
    return 0


def cmd_cookies_import(args, store: ProfileStore) -> int:
    prof = _resolve_or_fail(args, store)
    if not prof:
        return 1
    from . import cookies as ck
    jar = ck.read_file(args.file)
    if not jar:
        print(_c(f"No usable cookies found in {args.file}.", C.RED))
        return 1
    print(_c(f"Importing {len(jar)} cookie(s) into '{prof.name}'...", C.CYN))
    n = ck.write(prof, store, jar, clear=args.clear, engine=args.engine)
    note = _c("  (existing cookies were cleared first)", C.DIM) if args.clear else ""
    print(_c(f"Imported {n} cookie(s).", C.GRN) + note)
    return 0


def cmd_serve(args, store: ProfileStore) -> int:
    from .server import serve
    serve(host=args.host, port=args.port, data_dir=args.data_dir)
    return 0


def cmd_check(args, store: ProfileStore) -> int:
    prof = store.resolve(args.ref)
    if not prof:
        print(_c(f"No profile matching '{args.ref}'.", C.RED))
        return 1
    problems = validate(prof.fingerprint)
    if not problems:
        print(_c(f"'{prof.name}' fingerprint is coherent.", C.GRN))
        return 0
    print(_c(f"'{prof.name}' has {len(problems)} issue(s):", C.RED))
    for p in problems:
        print(f"  - {p}")
    return 1


# ---- rendering -----------------------------------------------------------
def _print_summary(prof: Profile, full: bool = False) -> None:
    fp = prof.fingerprint
    rows = [
        ("id", prof.id),
        ("engine", prof.engine),
        ("os", fp.os + (" (mobile)" if fp.is_mobile else "")),
        ("chrome", fp.chrome_version),
        ("screen", f"{fp.screen_width}x{fp.screen_height}"),
        ("cpu / ram", f"{fp.hardware_concurrency} cores / {fp.device_memory} GB"),
        ("gpu", fp.webgl_renderer),
        ("locale / tz", f"{fp.locale}  {fp.timezone}"),
    ]
    if full:
        rows.insert(2, ("user-agent", fp.user_agent))
        rows.append(("languages", ", ".join(fp.languages)))
        rows.append(("proxy", prof.proxy.server if prof.proxy else "-"))
        rows.append(("tags", ", ".join(prof.tags) or "-"))
        rows.append(("notes", prof.notes or "-"))
        rows.append(("seed", str(fp.seed)))
    for k, v in rows:
        print(f"  {_c(k + ':', C.DIM):<24}{v}")


# ---- parser --------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="persona",
        description="Open-source browser fingerprint & profile manager.",
    )
    p.add_argument("--version", action="version", version=f"persona {__version__}")
    p.add_argument("--data-dir", default=None,
                   help="Override the data directory (default: ~/.persona)")
    sub = p.add_subparsers(dest="command", required=True)

    c = sub.add_parser("create", help="Create a new profile")
    c.add_argument("name")
    c.add_argument("--os", choices=["windows", "macos", "linux", "android"])
    c.add_argument("--locale")
    c.add_argument("--proxy", help="scheme://[user:pass@]host:port")
    c.add_argument("--country", help="ISO code to align locale/timezone (e.g. US, PK)")
    c.add_argument("--seed", type=int, help="Fixed seed for a reproducible fingerprint")
    c.add_argument("--mobile", action="store_true", help="Generate a mobile device")
    c.add_argument("--engine", help="Launch backend: cloak | camoufox | patchright | playwright "
                                    "(default: saved default engine)")
    c.add_argument("--notes", default="")
    c.add_argument("--tag", action="append", help="Add a tag (repeatable)")
    c.set_defaults(func=cmd_create)

    c = sub.add_parser("list", help="List profiles")
    c.add_argument("--tag", help="Filter by tag")
    c.set_defaults(func=cmd_list)

    c = sub.add_parser("show", help="Show full profile details")
    c.add_argument("ref", help="Profile name or id")
    c.set_defaults(func=cmd_show)

    c = sub.add_parser("launch", help="Launch a profile in a browser")
    c.add_argument("ref")
    c.add_argument("--headless", action="store_true")
    c.add_argument("--engine", help="Override the profile's launch engine for this run")
    c.set_defaults(func=cmd_launch)

    c = sub.add_parser("engines", help="List available launch engines")
    c.set_defaults(func=cmd_engines)

    c = sub.add_parser("default-engine",
                       help="Show or set the engine used for new profiles")
    c.add_argument("name", nargs="?",
                   help="Engine to make default (omit to show the current one)")
    c.set_defaults(func=cmd_default_engine)

    c = sub.add_parser("edit", help="Edit notes / tags / proxy")
    c.add_argument("ref")
    c.add_argument("--notes")
    c.add_argument("--add-tag", action="append")
    c.add_argument("--proxy")
    c.add_argument("--country")
    c.set_defaults(func=cmd_edit)

    c = sub.add_parser("regen", help="Regenerate the fingerprint")
    c.add_argument("ref")
    c.add_argument("--os", choices=["windows", "macos", "linux", "android"])
    c.add_argument("--locale")
    c.set_defaults(func=cmd_regen)

    c = sub.add_parser("delete", help="Delete a profile")
    c.add_argument("ref")
    c.add_argument("-y", "--yes", action="store_true", help="Skip confirmation")
    c.set_defaults(func=cmd_delete)

    c = sub.add_parser("export", help="Export a profile to JSON")
    c.add_argument("ref"); c.add_argument("file")
    c.set_defaults(func=cmd_export)

    c = sub.add_parser("import", help="Import a profile from JSON")
    c.add_argument("file")
    c.set_defaults(func=cmd_import)

    c = sub.add_parser("cookies", help="List, export or import a profile's cookies")
    ck = c.add_subparsers(dest="cookies_command", required=True)

    s = ck.add_parser("list", help="Show what's in the profile's cookie jar")
    s.add_argument("ref")
    s.add_argument("--engine", help="Open with a different engine than the profile's")
    s.set_defaults(func=cmd_cookies_list)

    s = ck.add_parser("export", help="Write the profile's cookies to a file")
    s.add_argument("ref"); s.add_argument("file")
    s.add_argument("--format", choices=["json", "netscape"],
                   help="Output format (default: netscape for .txt, else json)")
    s.add_argument("--engine", help="Open with a different engine than the profile's")
    s.set_defaults(func=cmd_cookies_export)

    s = ck.add_parser("import", help="Load cookies from a file into the profile")
    s.add_argument("ref"); s.add_argument("file")
    s.add_argument("--clear", action="store_true",
                   help="Empty the existing jar first (replace instead of merge)")
    s.add_argument("--engine", help="Open with a different engine than the profile's")
    s.set_defaults(func=cmd_cookies_import)

    c = sub.add_parser("check", help="Validate fingerprint coherence")
    c.add_argument("ref")
    c.set_defaults(func=cmd_check)

    c = sub.add_parser("serve", help="Run the HTTP API for the dashboard")
    c.add_argument("--host", default="127.0.0.1")
    c.add_argument("--port", type=int, default=8787)
    c.set_defaults(func=cmd_serve)

    return p


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    store = ProfileStore(args.data_dir)
    try:
        return args.func(args, store)
    except RuntimeError as e:
        print(_c(str(e), C.RED))
        return 1
    except KeyboardInterrupt:
        print("\nAborted.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
