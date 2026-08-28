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
    persona backup <name|id> <file.zip>           (profile + whole session, portable)
    persona restore <file.zip> [--new-id]         (recreate a profile from a backup)
    persona collisions [--json]                   (profiles that share a fingerprint)
    persona check <name|id>                       (validate fingerprint coherence)
    persona trust <name|id>                       (score it like a fingerprinter would)
    persona session <name|id>                     (session health: expired cookies + live logins)
    persona proxy test <name|id>                  (exit IP, country + WebRTC leaks)
    persona dns <name|id>                         (do DNS lookups leak past the proxy?)
    persona tls <name|id>                         (TLS/JA3 handshake — the pre-JS layer)
    persona cookies list|export|import <name|id>  (move a session in or out)
    persona ext list|add|remove <name|id> [path]  (browser extensions)
    persona warmup <name|id> [--minutes] [--preset]  (age a fresh profile by browsing)
    persona schedule add|list|remove|run-due      (recurring unattended warm-up)
    persona attach <name|id> [--port]             (open it for Selenium/Puppeteer/Playwright)
    persona apply [refs] [--tag|--all] --engine …  (one change, many profiles)
    persona engines                               (list launch engines + install status)
    persona default-engine [name]                 (show/set the engine new profiles use)
    persona import-from <file>                    (import from GoLogin/AdsPower/Multilogin)
    persona vault enable|status                   (encrypt proxy passwords at rest)
    persona serve [--host] [--port]               (run the HTTP API for the dashboard)
"""

from __future__ import annotations

import argparse
import json
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


def cmd_backup(args, store: ProfileStore) -> int:
    prof = store.resolve(args.ref)
    if not prof:
        print(_c(f"No profile matching '{args.ref}'.", C.RED))
        return 1
    dest = store.backup(prof.id, args.file)
    print(_c(f"Backed up '{prof.name}' (profile + session) to {dest}", C.GRN))
    print(_c("  keep it safe — the archive holds the proxy password in plaintext.", C.DIM))
    return 0


def cmd_restore(args, store: ProfileStore) -> int:
    prof = store.restore(args.file, new_id=args.new_id)
    print(_c(f"Restored '{prof.name}'  ", C.GRN) + _c(f"[{prof.id}]", C.DIM))
    return 0


def cmd_collisions(args, store: ProfileStore) -> int:
    from .collision import find_collisions
    profiles = store.list()
    groups = find_collisions(profiles)
    if args.json:
        print(json.dumps({"total": len(profiles), "groups": groups}))
        return 0 if not groups else 1
    if not groups:
        print(_c(f"No collisions — all {len(profiles)} profile(s) look unique.", C.GRN))
        return 0
    clashing = sum(len(g["members"]) for g in groups)
    print(_c(f"{clashing} of {len(profiles)} profiles share a fingerprint "
             f"({len(groups)} group(s)):\n", C.YEL))
    for g in groups:
        tag = _c(" IDENTICAL (same seed too)", C.RED) if g["identical"] else ""
        names = ", ".join(m["name"] for m in g["members"])
        sig = g["signals"]
        print(_c(f"  • {names}{tag}", C.B))
        print(_c(f"    {sig['os']} · {sig['webgl_renderer']} · "
                 f"{sig['screen_width']}x{sig['screen_height']} · "
                 f"{sig['hardware_concurrency']} cores / {sig['device_memory']}GB", C.DIM))
    print(_c("\nRegenerate one side of each pair:  persona regen <name>", C.DIM))
    return 1


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


def _print_checks(checks: list[dict]) -> None:
    for c in checks:
        mark = _c("PASS", C.GRN) if c["ok"] else _c("FAIL", C.RED)
        print(f"  [{mark}] {c['name']}")
        if c.get("detail") and not c["ok"]:
            print(f"         {_c(c['detail'], C.DIM)}")


def cmd_proxy_test(args, store: ProfileStore) -> int:
    prof = _resolve_or_fail(args, store)
    if not prof:
        return 1
    from .probe import check_proxy
    where = prof.proxy.server if prof.proxy else "no proxy (direct connection)"
    if not args.json:
        print(_c(f"Testing '{prof.name}' via {where}...", C.CYN))
    res = check_proxy(prof, store, engine=args.engine)
    if args.json:
        print(json.dumps(res))
        return 0 if res.get("ok") else 1
    if res.get("error"):
        print(_c(f"Failed: {res['error']}", C.RED))
        return 1
    print(f"  exit IP      {res['ip']}"
          + (f"  ({res['city']}, {res['country']})" if res.get("city") else ""))
    print(f"  round trip   {res['latencyMs']} ms")
    _print_checks(res["checks"])
    return 0 if res["ok"] else 1


def cmd_tls(args, store: ProfileStore) -> int:
    prof = _resolve_or_fail(args, store)
    if not prof:
        return 1
    from .probe import check_tls
    if not args.json:
        print(_c(f"Reading '{prof.name}' TLS/HTTP2 handshake...", C.CYN))
    res = check_tls(prof, store, engine=args.engine)
    if args.json:
        print(json.dumps(res))
        return 0 if res.get("ok") else 1
    if res.get("error"):
        print(_c(f"Failed: {res['error']}", C.RED))
        return 1
    print(f"  JA3 hash     {res.get('ja3Hash') or '-'}")
    print(f"  JA4          {res.get('ja4') or '-'}")
    print(f"  HTTP/2       {res.get('http2') or '-'}")
    _print_checks(res["checks"])
    print(_c("\n  Tip: run this on two engines and compare — TLS is the one layer "
             "JS can't touch.", C.DIM))
    return 0 if res["ok"] else 1


def cmd_dns(args, store: ProfileStore) -> int:
    prof = _resolve_or_fail(args, store)
    if not prof:
        return 1
    from .probe import check_dns
    if not args.json:
        print(_c(f"Checking '{prof.name}' for DNS leaks...", C.CYN))
    res = check_dns(prof, store, engine=args.engine)
    if args.json:
        print(json.dumps(res))
        return 0 if res.get("ok") else 1
    if res.get("error"):
        print(_c(f"Failed: {res['error']}", C.RED))
        return 1
    if res.get("countries"):
        print(f"  resolvers    {len(res['resolvers'])} in {', '.join(res['countries'])}")
    _print_checks(res["checks"])
    return 0 if res["ok"] else 1


def cmd_session(args, store: ProfileStore) -> int:
    prof = _resolve_or_fail(args, store)
    if not prof:
        return 1
    from . import session as session_mod
    if not args.json:
        print(_c(f"Reading '{prof.name}' session (opens it headlessly)...", C.CYN))
    rep = session_mod.check(prof, store, engine=args.engine)
    if args.json:
        print(json.dumps(rep))
        return 0 if rep["status"] in ("ok", "empty") else 1
    label = {"ok": C.GRN, "empty": C.DIM, "stale": C.RED, "expiring": C.YEL}
    print(_c(f"\n  Session: {rep['status']}", label.get(rep["status"], C.B)) +
          _c(f"   {rep['total']} cookies "
             f"({rep['persistent']} persistent, {rep['session']} session)", C.DIM))
    if rep["expired"] or rep["expiringSoon"]:
        print(_c(f"  {rep['expired']} expired, {rep['expiringSoon']} "
                 f"expiring within {rep['soonDays']} days", C.YEL))
    if rep["logins"]:
        print(_c("  Live logins: ", C.B) + _c(", ".join(rep["logins"]), C.GRN))
    else:
        print(_c("  No known live logins detected.", C.DIM))
    print()
    return 0 if rep["status"] in ("ok", "empty") else 1


def cmd_trust(args, store: ProfileStore) -> int:
    prof = _resolve_or_fail(args, store)
    if not prof:
        return 1
    from .probe import trust_report
    if not args.json:
        print(_c(f"Inspecting '{prof.name}' the way a fingerprinting script would...", C.CYN))
    rep = trust_report(prof, store, engine=args.engine)
    if args.json:
        print(json.dumps(rep))
        return 0
    colour = C.GRN if rep["score"] >= 95 else C.YEL if rep["score"] >= 70 else C.RED
    print(_c(f"\n  Trust score: {rep['score']}%  (grade {rep['grade']}, "
             f"{rep['passed']}/{rep['total']} checks)\n", colour))
    _print_checks(rep["checks"])
    return 0 if rep["score"] == 100 else 1


def cmd_align(args, store: ProfileStore) -> int:
    prof = _resolve_or_fail(args, store)
    if not prof:
        return 1
    from .probe import align_to_reality
    if not args.json:
        print(_c(f"Aligning '{prof.name}' to what its browser actually presents...", C.CYN))
    res = align_to_reality(prof, store, engine=args.engine)
    if args.json:
        print(json.dumps(res))
        return 0
    b, a = res["before"], res["after"]
    colour = C.GRN if a["score"] >= 95 else C.YEL if a["score"] >= 70 else C.RED
    print(_c(f"\n  grade {b['grade']} ({b['score']}%)  ->  grade {a['grade']} ({a['score']}%)"
             f"   {a['passed']}/{a['total']} checks\n", colour))
    if res["changed"]:
        print(_c("  Adjusted: ", C.B) + _c(", ".join(res["changed"]), C.DIM))
        print(_c(f"  Identity now reads as: {res['os']}", C.DIM))
    else:
        print(_c("  Nothing to change — the profile already matches its browser.", C.DIM))
    print()
    _print_checks(res["checks"])
    return 0 if a["score"] == 100 else 1


def cmd_bulk_create(args, store: ProfileStore) -> int:
    from .bulk import generate_profiles
    engine = args.engine or store.get_default_engine()
    profiles = generate_profiles(
        args.count,
        oses=args.os or None,
        locales=args.locale or None,
        chrome_versions=args.chrome or None,
        engine=engine,
        name_prefix=args.prefix,
        start_index=args.start,
        pad=args.pad,
        tags=args.tag or None,
        mobile=args.mobile,
        seed=args.seed,
    )
    existing = {p.name for p in store.list()}
    saved = skipped = 0
    for prof in profiles:
        if prof.name in existing:
            skipped += 1
            continue
        store.save(prof)
        existing.add(prof.name)
        saved += 1
    if args.engine:
        store.set_default_engine(args.engine)
    note = _c(f", skipped {skipped} name clash(es)", C.YEL) if skipped else ""
    print(_c(f"Created {saved} profile(s)", C.GRN) + note
          + _c(f"  (engine {engine})", C.DIM))
    return 0


def cmd_warmup(args, store: ProfileStore) -> int:
    prof = _resolve_or_fail(args, store)
    if not prof:
        return 1
    from .warmup import warm_up
    where = f" ({args.preset})" if args.preset and not args.site else ""
    print(_c(f"Warming up '{prof.name}'{where} for {args.minutes} minute(s)...", C.CYN))
    res = warm_up(prof, store, minutes=args.minutes, sites=args.site or None,
                  engine=args.engine, headless=args.headless, preset=args.preset,
                  on_event=print)
    print(_c(f"Done — visited {res['pages']} page(s)"
             + (f", {res['errors']} unreachable" if res["errors"] else "") + ".", C.GRN))
    return 0


def cmd_schedule(args, store: ProfileStore) -> int:
    import time as _time

    from .scheduler import ScheduleStore, due_schedules, next_run_at
    from .warmup import warm_up

    sched = ScheduleStore(store.root)
    sub = args.schedule_command

    if sub == "list":
        rows = sched.list()
        if not rows:
            print(_c("No warm-up schedules.", C.DIM))
            return 0
        by_id = {p.id: p.name for p in store.list()}
        for s in rows:
            name = by_id.get(s["profileId"], s["profileId"])
            state = _c("on", C.GRN) if s.get("enabled", True) else _c("off", C.DIM)
            nxt = next_run_at(s)
            when = "now" if nxt <= _time.time() else _time.strftime("%Y-%m-%d %H:%M", _time.localtime(nxt))
            print(f"  {s['id']}  {name:<20} every {s['everyHours']}h  "
                  f"{s['minutes']}min  {s['preset']:<10} [{state}]  next: {when}")
        return 0

    if sub == "add":
        prof = _resolve_or_fail(args, store)
        if not prof:
            return 1
        entry = sched.add(profile_id=prof.id, every_hours=args.every,
                          minutes=args.minutes, preset=args.preset or "general",
                          now=_time.time())
        print(_c(f"Scheduled '{prof.name}' — warm up every {entry['everyHours']}h "
                 f"for {entry['minutes']}min ({entry['preset']}).", C.GRN))
        print(_c(f"  id {entry['id']}", C.DIM))
        return 0

    if sub == "remove":
        ok = sched.delete(args.id)
        print(_c("Removed.", C.GRN) if ok else _c("No schedule with that id.", C.RED))
        return 0 if ok else 1

    if sub == "run-due":
        now = _time.time()
        due = due_schedules(sched.list(), now)
        if not due:
            print(_c("Nothing due.", C.DIM))
            return 0
        by_id = {p.id: p for p in store.list()}
        ran = 0
        for s in due:
            prof = by_id.get(s["profileId"])
            if not prof:
                print(_c(f"  skip {s['id']} — profile {s['profileId']} not in this store", C.YEL))
                continue
            print(_c(f"  warming '{prof.name}' ({s['preset']}, {s['minutes']}min)...", C.CYN))
            warm_up(prof, store, minutes=s["minutes"], preset=s["preset"], headless=True)
            sched.mark_run(s["id"], _time.time())
            ran += 1
        print(_c(f"Ran {ran} due schedule(s).", C.GRN))
        return 0

    return 1


def cmd_attach(args, store: ProfileStore) -> int:
    prof = _resolve_or_fail(args, store)
    if not prof:
        return 1
    from .automation import attach, snippets
    print(_c(f"Launching '{prof.name}' with DevTools on port {args.port}...", C.CYN))
    (pw, context, page), info = attach(prof, store, port=args.port, engine=args.engine,
                                       headless=args.headless)
    ws = info.get("webSocketDebuggerUrl", "")
    print(_c(f"\n  {info.get('Browser', 'Browser')} ready — attach your automation:", C.B))
    print(snippets(args.port, ws))
    print(_c("Close the browser window (or press Ctrl+C) to end the session.", C.DIM))
    try:
        page.wait_for_event("close", timeout=0)
    except KeyboardInterrupt:
        print("\nClosing.")
    finally:
        try:
            context.close()
        finally:
            if pw:
                pw.stop()
    return 0


def cmd_ext(args, store: ProfileStore) -> int:
    prof = _resolve_or_fail(args, store)
    if not prof:
        return 1
    if args.ext_command == "list":
        if not prof.extensions:
            print(_c(f"'{prof.name}' loads no extensions.", C.DIM))
            return 0
        print(_c(f"Extensions for '{prof.name}':", C.B))
        for path in prof.extensions:
            exists = Path(path).expanduser().is_dir()
            note = "" if exists else _c("  (folder not found)", C.RED)
            print(f"  {path}{note}")
        return 0

    path = str(Path(args.path).expanduser())
    if args.ext_command == "add":
        if not Path(path).is_dir():
            print(_c(f"'{path}' is not a folder. Point at an *unpacked* extension "
                     f"(the folder containing manifest.json).", C.RED))
            return 1
        if path in prof.extensions:
            print(_c("Already loaded.", C.DIM))
            return 0
        prof.extensions.append(path)
    else:  # remove
        if path not in prof.extensions:
            print(_c(f"'{path}' isn't on this profile.", C.RED))
            return 1
        prof.extensions.remove(path)
    store.save(prof)
    print(_c(f"{'Added' if args.ext_command == 'add' else 'Removed'} — "
             f"'{prof.name}' now loads {len(prof.extensions)} extension(s).", C.GRN))
    return 0


def cmd_apply(args, store: ProfileStore) -> int:
    from .bulk import apply_patch, select
    targets = select(store.list(), refs=args.ref, tag=args.tag, everything=args.all)
    if not targets:
        print(_c("Nothing matched. Pass profile names/ids, --tag TAG, or --all.", C.RED))
        return 1

    patch: dict = {}
    for key in ("engine", "notes", "locale", "timezone"):
        if getattr(args, key) is not None:
            patch[key] = getattr(args, key)
    if args.startup_url:
        patch["startup_urls"] = args.startup_url
    if args.add_tag:
        patch["add_tags"] = args.add_tag
    if args.remove_tag:
        patch["remove_tags"] = args.remove_tag
    if args.regen:
        patch["regen"] = True
    if args.proxy is not None:
        patch["proxy"] = _parse_proxy(args.proxy, args.country) if args.proxy else None
    if not patch:
        print(_c("No changes given. Try --engine, --proxy, --locale, --add-tag, --regen…", C.RED))
        return 1

    if not args.yes:
        print(_c(f"About to change {len(targets)} profile(s):", C.B))
        for p in targets[:10]:
            print(f"  {p.name}")
        if len(targets) > 10:
            print(_c(f"  … and {len(targets) - 10} more", C.DIM))
        if input("Continue? (y/N) ").strip().lower() != "y":
            print("Aborted.")
            return 0

    touched = 0
    for prof in targets:
        changed = apply_patch(prof, patch)
        if changed:
            store.save(prof)
            touched += 1
            print(f"  {prof.name:<24}{_c(', '.join(changed), C.DIM)}")
    if patch.get("engine"):
        store.set_default_engine(patch["engine"])   # "last engine wins"
    print(_c(f"Updated {touched} of {len(targets)} profile(s).", C.GRN))
    return 0


def _prompt_password(confirm: bool = False) -> str:
    import getpass
    pw = getpass.getpass("Master password: ")
    if confirm and getpass.getpass("Confirm master password: ") != pw:
        raise RuntimeError("Passwords didn't match.")
    return pw


def cmd_vault(args, store: ProfileStore) -> int:
    from . import crypto
    if args.vault_command == "status":
        if not store.vault_enabled():
            state = _c("off", C.DIM) + " — proxy passwords are stored in plaintext"
        elif store.unlocked():
            state = _c("unlocked", C.GRN)
        else:
            state = _c("locked", C.YEL) + " — set PERSONA_PASSWORD or pass --password"
        print(_c("Vault: ", C.B) + state)
        if not crypto.available():
            print(_c('  (install the backend with: pip install -e ".[secure]")', C.DIM))
        return 0

    if not crypto.available():
        print(_c('Encrypted storage needs the cryptography package:  pip install -e ".[secure]"', C.RED))
        return 1

    if args.vault_command == "enable":
        pw = store._password or _prompt_password(confirm=True)
        store._password = pw
        n = store.enable_vault(pw)
        print(_c(f"Vault enabled — encrypted secrets in {n} profile(s).", C.GRN))
        print(_c("Keep this password safe: without it, encrypted proxy passwords can't be recovered.", C.YEL))
        print(_c("Set PERSONA_PASSWORD (or pass --password) when launching so profiles can use their proxy.", C.DIM))
        return 0

    return 1


def cmd_import_from(args, store: ProfileStore) -> int:
    from . import importers
    try:
        results = importers.import_file(args.file, store)
    except (FileNotFoundError, ValueError) as e:
        print(_c(f"Couldn't read {args.file}: {e}", C.RED))
        return 1
    if not results:
        print(_c("No profiles found in that file.", C.RED))
        return 1
    clean = sum(1 for _, issues in results if not issues)
    print(_c(f"Imported {len(results)} profile(s)  ", C.GRN)
          + _c(f"({clean} coherent out of the box)", C.DIM))
    for prof, issues in results:
        if issues:
            print(f"  {prof.name:<24}{_c('review: ' + '; '.join(issues), C.YEL)}")
    print(_c("Run `persona check <name>` on any flagged profile to see details.", C.DIM))
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
    p.add_argument("--password", default=None,
                   help="Master password for the secrets vault "
                        "(or set the PERSONA_PASSWORD env var)")
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

    c = sub.add_parser("backup", help="Zip a profile + its whole session to a portable file")
    c.add_argument("ref"); c.add_argument("file", help="Destination .zip")
    c.set_defaults(func=cmd_backup)

    c = sub.add_parser("restore", help="Recreate a profile + session from a backup zip")
    c.add_argument("file", help="A backup made with `persona backup`")
    c.add_argument("--new-id", action="store_true",
                   help="Import as a fresh copy instead of overwriting the original id")
    c.set_defaults(func=cmd_restore)

    c = sub.add_parser("collisions",
                       help="Find profiles that share a fingerprint (a linkage risk)")
    c.add_argument("--json", action="store_true", help="Print the raw result as JSON")
    c.set_defaults(func=cmd_collisions)

    c = sub.add_parser("import-from",
                       help="Import profiles exported from GoLogin / AdsPower / Multilogin")
    c.add_argument("file", help="Their exported JSON (a single profile or a list)")
    c.set_defaults(func=cmd_import_from)

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

    c = sub.add_parser("proxy", help="Proxy tools")
    px = c.add_subparsers(dest="proxy_command", required=True)
    s = px.add_parser("test", help="Check the exit IP, country and WebRTC leaks")
    s.add_argument("ref")
    s.add_argument("--engine", help="Test with a different engine than the profile's")
    s.add_argument("--json", action="store_true", help="Print the raw result as JSON")
    s.set_defaults(func=cmd_proxy_test)

    c = sub.add_parser("tls", help="Show the profile's TLS/JA3 handshake fingerprint")
    c.add_argument("ref")
    c.add_argument("--engine", help="Read with a different engine than the profile's")
    c.add_argument("--json", action="store_true", help="Print the raw result as JSON")
    c.set_defaults(func=cmd_tls)

    c = sub.add_parser("dns", help="Check whether DNS lookups leak past the proxy")
    c.add_argument("ref")
    c.add_argument("--engine", help="Test with a different engine than the profile's")
    c.add_argument("--json", action="store_true", help="Print the raw result as JSON")
    c.set_defaults(func=cmd_dns)

    c = sub.add_parser("trust", help="Score the profile the way a fingerprinter would")
    c.add_argument("ref")
    c.add_argument("--engine", help="Inspect with a different engine than the profile's")
    c.add_argument("--json", action="store_true", help="Print the raw result as JSON")
    c.set_defaults(func=cmd_trust)

    c = sub.add_parser("session",
                       help="Check session health — expired/expiring cookies and live logins")
    c.add_argument("ref")
    c.add_argument("--engine", help="Read with a different engine than the profile's")
    c.add_argument("--json", action="store_true", help="Print the raw result as JSON")
    c.set_defaults(func=cmd_session)

    c = sub.add_parser("align",
                       help="Auto-adjust: match the profile to what its browser really shows")
    c.add_argument("ref")
    c.add_argument("--engine", help="Align against a different engine than the profile's")
    c.add_argument("--json", action="store_true", help="Print the raw result as JSON")
    c.set_defaults(func=cmd_align)

    c = sub.add_parser("bulk-create", help="Generate many coherent profiles at once")
    c.add_argument("--count", type=int, required=True, help="How many to create")
    c.add_argument("--os", action="append", choices=["windows", "macos", "linux", "android"],
                   help="OS to spread the batch across (repeatable; default windows)")
    c.add_argument("--locale", action="append",
                   help="Locale to spread across (repeatable; e.g. --locale en-US --locale de-DE)")
    c.add_argument("--chrome", action="append",
                   help="Chrome version to draw from (repeatable; e.g. 128.0.0.0)")
    c.add_argument("--engine", help="Launch backend for the batch")
    c.add_argument("--prefix", default="Profile", help="Name prefix (default: Profile)")
    c.add_argument("--start", type=int, default=1, help="First number in the sequence")
    c.add_argument("--pad", type=int, default=4, help="Zero-pad the number to this width")
    c.add_argument("--tag", action="append", help="Tag every profile (repeatable)")
    c.add_argument("--mobile", action="store_true", help="Generate mobile devices")
    c.add_argument("--seed", type=int, help="Fixed seed for a reproducible batch")
    c.set_defaults(func=cmd_bulk_create)

    c = sub.add_parser("warmup", help="Browse normally for a while to age the profile")
    c.add_argument("ref")
    c.add_argument("--minutes", type=float, default=5, help="How long to browse (default: 5)")
    c.add_argument("--site", action="append",
                   help="Site to visit (repeatable; replaces the preset/default list)")
    c.add_argument("--preset", choices=["general", "ads", "ecommerce", "crypto", "social", "news"],
                   help="Per-vertical warm-up set to browse (default: general)")
    c.add_argument("--headless", action="store_true")
    c.add_argument("--engine")
    c.set_defaults(func=cmd_warmup)

    c = sub.add_parser("schedule", help="Recurring unattended warm-up (add/list/remove/run-due)")
    sc = c.add_subparsers(dest="schedule_command", required=True)
    s = sc.add_parser("list", help="Show all warm-up schedules and when they next run")
    s.set_defaults(func=cmd_schedule)
    s = sc.add_parser("add", help="Schedule a recurring warm-up for a profile")
    s.add_argument("ref")
    s.add_argument("--every", type=float, required=True, help="Interval in hours (e.g. 12)")
    s.add_argument("--minutes", type=float, default=5, help="How long each warm-up runs")
    s.add_argument("--preset", choices=["general", "ads", "ecommerce", "crypto", "social", "news"],
                   help="Per-vertical warm-up set (default: general)")
    s.set_defaults(func=cmd_schedule)
    s = sc.add_parser("remove", help="Delete a schedule by id")
    s.add_argument("id")
    s.set_defaults(func=cmd_schedule)
    s = sc.add_parser("run-due", help="Run every schedule that's due now (for cron/Task Scheduler)")
    s.set_defaults(func=cmd_schedule)

    c = sub.add_parser("attach", help="Open the profile with DevTools for your own automation")
    c.add_argument("ref")
    c.add_argument("--port", type=int, default=9222, help="DevTools port (default: 9222)")
    c.add_argument("--engine")
    c.add_argument("--headless", action="store_true",
                   help="Attach without a visible window (for servers/CI)")
    c.set_defaults(func=cmd_attach)

    c = sub.add_parser("ext", help="Manage a profile's browser extensions")
    ex = c.add_subparsers(dest="ext_command", required=True)
    s = ex.add_parser("list", help="Show the extensions this profile loads")
    s.add_argument("ref")
    s.set_defaults(func=cmd_ext)
    for verb, helptext in (("add", "Load an unpacked extension folder"),
                           ("remove", "Stop loading an extension")):
        s = ex.add_parser(verb, help=helptext)
        s.add_argument("ref"); s.add_argument("path")
        s.set_defaults(func=cmd_ext)

    c = sub.add_parser("apply", help="Apply one change to many profiles at once")
    c.add_argument("ref", nargs="*", help="Profile names or ids")
    c.add_argument("--tag", help="Every profile carrying this tag")
    c.add_argument("--all", action="store_true", help="Every profile")
    c.add_argument("--engine", help="Switch them to this launch engine")
    c.add_argument("--proxy", help="scheme://[user:pass@]host:port  (empty string = go direct)")
    c.add_argument("--country", help="ISO code to align locale/timezone with the proxy")
    c.add_argument("--locale", help="Locale (also moves timezone + languages)")
    c.add_argument("--timezone")
    c.add_argument("--notes")
    c.add_argument("--startup-url", action="append", help="Startup URL (repeatable, replaces)")
    c.add_argument("--add-tag", action="append")
    c.add_argument("--remove-tag", action="append")
    c.add_argument("--regen", action="store_true",
                   help="Give each one a fresh fingerprint (same OS, locale and session)")
    c.add_argument("-y", "--yes", action="store_true", help="Skip confirmation")
    c.set_defaults(func=cmd_apply)

    c = sub.add_parser("vault", help="Encrypt proxy passwords at rest with a master password")
    vt = c.add_subparsers(dest="vault_command", required=True)
    vt.add_parser("status", help="Show whether the vault is on, locked or unlocked").set_defaults(func=cmd_vault)
    vt.add_parser("enable", help="Turn on encryption and encrypt existing secrets").set_defaults(func=cmd_vault)

    c = sub.add_parser("serve", help="Run the HTTP API for the dashboard")
    c.add_argument("--host", default="127.0.0.1")
    c.add_argument("--port", type=int, default=8787)
    c.set_defaults(func=cmd_serve)

    return p


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    store = ProfileStore(args.data_dir, password=args.password)
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
