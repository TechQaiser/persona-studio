"""
CSV round-trip: edit many profiles at once in a spreadsheet.

Export writes one row per profile with the columns below; edit it in Excel,
LibreOffice or Google Sheets; import it back. Rows are matched to profiles by
``id``, so an edited sheet updates the profiles it came from. A row with no
``id`` (or one this install doesn't know) creates a new profile, and any
hardware it leaves blank comes from a fresh coherent device.

Cells work the way a spreadsheet suggests:

* Text and list cells (notes, tags, folder, proxy, startup URLs, extensions,
  launch flags, clearOnClose) are written as they are: emptying one clears it.
* Device cells (OS, user agent, screen, CPU, RAM, GPU, locale, timezone) and
  yes/no cells can't sensibly be empty, so an empty one leaves the profile as
  it was.
* Lists are one item per line in the cell; tags may also be comma-separated.
* Proxies are ``scheme://user:pass@host:port`` (any format the proxy pool
  reads). Passwords aren't exported unless asked for; a proxy cell with the
  same user, host and port but no password keeps the stored password.

Every imported row is run through the coherence check, and its issues are
reported (not fixed): a sheet that changes ``os`` but not ``userAgent`` gets
told so.

Excel may turn an all-digit id into a number. A row whose id isn't found
falls back to the profile with the same name, if exactly one has it.

The rows are the dashboard's profile records (``server.DashboardStore``),
which is what Persona Studio shows and edits.
"""

from __future__ import annotations

import csv
import io
import re
from typing import Callable, Optional

from . import devices, proxypool
from .fingerprint import generate
from .history import STORAGE_KINDS, normalize_storage

# Header -> how the cell maps onto a dashboard profile. Order is the export order.
#   text   : string, empty clears
#   keep   : string, empty leaves it unchanged
#   int    : whole number, empty leaves it unchanged
#   bool   : yes/no, empty leaves it unchanged
#   lines  : one item per line, empty clears
COLUMNS: list[tuple[str, str]] = [
    ("id", "id"),
    ("name", "keep"),
    ("folder", "text"),
    ("tags", "tags"),
    ("notes", "text"),
    ("engine", "keep"),
    ("os", "keep"),
    ("browserVersion", "keep"),
    ("userAgent", "keep"),
    ("screen", "keep"),
    ("cores", "int"),
    ("memory", "int"),
    ("webglVendor", "keep"),
    ("webglRenderer", "keep"),
    ("locale", "keep"),
    ("timezone", "keep"),
    ("proxy", "proxy"),
    ("proxyCountry", "proxy_extra"),
    ("changeIpUrl", "proxy_extra"),
    ("autoLang", "bool"),
    ("blockImages", "bool"),
    ("blockVideo", "bool"),
    ("clearOnClose", "storage"),
    ("startupUrls", "lines"),
    ("extensions", "lines"),
    ("launchArgs", "lines"),
]
HEADERS = [h for h, _ in COLUMNS]
_KIND = dict(COLUMNS)
# Header lookup that forgives case, spaces and underscores ("Block Images").
_CANON = {h.lower(): h for h in HEADERS}

_TRUE = {"yes", "y", "true", "1", "on", "x"}
_FALSE = {"no", "n", "false", "0", "off"}


def _canon(header: str) -> Optional[str]:
    return _CANON.get((header or "").strip().lstrip("﻿").replace(" ", "").replace("_", "").lower())


# ---------------------------------------------------------------- export ----
def proxy_cell(proxy: Optional[dict], passwords: bool = False) -> str:
    """A dashboard proxy dict as one ``scheme://user:pass@host:port`` cell."""
    if not proxy or not str(proxy.get("host") or "").strip():
        return ""
    scheme = {"HTTP": "http", "HTTPS": "https", "SOCKS5": "socks5",
              "SOCKS4": "socks4"}.get(proxy.get("type") or "HTTP", "http")
    user = proxy.get("user") or ""
    creds = ""
    if user:
        creds = user + (f":{proxy['pass']}" if passwords and proxy.get("pass") else "") + "@"
    port = str(proxy.get("port") or "").strip()
    return f"{scheme}://{creds}{str(proxy['host']).strip()}" + (f":{port}" if port else "")


def _cell(d: dict, header: str, passwords: bool) -> str:
    kind = _KIND[header]
    if header == "proxy":
        return proxy_cell(d.get("proxy"), passwords)
    if header == "proxyCountry":
        return (d.get("proxy") or {}).get("country") or ""
    if header == "changeIpUrl":
        return (d.get("proxy") or {}).get("changeIpUrl") or ""
    if kind == "tags":
        return ", ".join(d.get("tags") or [])
    if kind == "bool":
        return "yes" if d.get(header) else "no"
    if kind == "storage":
        keep = normalize_storage(d.get("storage"))
        return ", ".join(k for k in STORAGE_KINDS if not keep[k])
    value = d.get(header)
    if isinstance(value, list):
        return "\n".join(str(v) for v in value)
    return "" if value is None else str(value)


def export_csv(profiles: list[dict], passwords: bool = False) -> str:
    """The profiles as CSV text. It starts with a byte-order mark, so Excel
    opens it as UTF-8 (names and notes in any script survive)."""
    out = io.StringIO()
    out.write("﻿")
    w = csv.writer(out, lineterminator="\r\n")
    w.writerow(HEADERS)
    for d in profiles:
        w.writerow([_cell(d, h, passwords) for h in HEADERS])
    return out.getvalue()


# ---------------------------------------------------------------- import ----
def read_rows(text: str) -> tuple[list[dict], list[str]]:
    """Parse CSV text into ``[{header: cell}]`` plus the headers it ignored.

    Comma, semicolon (Excel in many European locales) and tab separators are
    all accepted."""
    text = (text or "").lstrip("﻿")
    first = text.split("\n", 1)[0]
    delim = max([",", ";", "\t"], key=first.count)
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    try:
        header = next(reader)
    except StopIteration:
        return [], []
    names = [_canon(h) for h in header]
    if "id" not in names and "name" not in names:
        raise ValueError("the first row must be the column headers (it needs at least "
                         "'id' or 'name'); export a sheet first to get the layout")
    ignored = [h.strip() for h, n in zip(header, names) if n is None and h.strip()]
    rows = []
    for cells in reader:
        if not any(c.strip() for c in cells):
            continue                     # blank line
        rows.append({n: c for n, c in zip(names, cells) if n is not None})
    return rows, ignored


def _bool(raw: str, header: str) -> bool:
    v = raw.strip().lower()
    if v in _TRUE:
        return True
    if v in _FALSE:
        return False
    raise ValueError(f"{header}: '{raw}' isn't yes or no")


def _lines(raw: str) -> str:
    return "\n".join(l.strip() for l in raw.replace("\r", "\n").split("\n") if l.strip())


def _storage(raw: str) -> dict:
    off = [k.strip().lower() for k in raw.replace(";", ",").replace("\n", ",").split(",") if k.strip()]
    bad = [k for k in off if k not in STORAGE_KINDS]
    if bad:
        raise ValueError(f"clearOnClose: unknown {', '.join(bad)} "
                         f"(choose from {', '.join(STORAGE_KINDS)})")
    return {k: k not in off for k in STORAGE_KINDS}


def _proxy(raw: str, current: Optional[dict]) -> Optional[dict]:
    raw = raw.strip()
    if not raw:
        return None
    parsed = proxypool.parse_line(raw)
    if not parsed:
        raise ValueError(f"proxy: can't read '{raw}' (use scheme://user:pass@host:port)")
    px = {"type": parsed["type"], "host": parsed["host"], "port": str(parsed["port"]),
          "user": parsed.get("user") or "", "pass": parsed.get("pass") or "",
          "country": parsed.get("country") or ""}
    cur = current or {}
    same = (cur.get("host"), str(cur.get("port") or ""), cur.get("user") or "") == \
           (px["host"], px["port"], px["user"])
    if same and not px["pass"]:
        px["pass"] = cur.get("pass") or ""        # exported without the password
    if same and not px["country"]:
        px["country"] = cur.get("country") or ""
    px["changeIpUrl"] = (cur.get("changeIpUrl") or "") if same else ""
    return px


_OS_NAMES = {"windows": "Windows", "macos": "macOS", "mac": "macOS", "linux": "Linux",
             "android": "Android"}
_SCREEN = re.compile(r"^\s*(\d{3,5})\s*[xX×]\s*(\d{3,5})\s*$")


def _check(header: str, value: str) -> str:
    """Validate (and tidy) a device cell, so a typo fails the row instead of
    silently launching as a default."""
    if header == "os":
        name = _OS_NAMES.get(value.lower())
        if not name:
            raise ValueError(f"os: '{value}' isn't Windows, macOS, Linux or Android")
        return name
    if header == "engine":
        from .drivers import names
        if value not in names():
            raise ValueError(f"engine: '{value}' isn't one of {', '.join(names())}")
    if header == "locale" and value not in devices.LOCALES:
        raise ValueError(f"locale: '{value}' isn't a supported locale (e.g. en-US, de-DE)")
    if header == "screen":
        m = _SCREEN.match(value)
        if not m:
            raise ValueError(f"screen: '{value}' should look like 1920x1080")
        return f"{m.group(1)}x{m.group(2)}"
    return value


def _norm(key: str, value):
    """A field's value in a form where "no change" compares equal."""
    if key == "storage":
        return normalize_storage(value)
    if key == "proxy":
        if not value or not str(value.get("host") or "").strip():
            return None
        return {k: str(value.get(k) or "") for k in
                ("type", "host", "port", "user", "pass", "country", "changeIpUrl")}
    if key == "folder":
        return value or "Unfiled"
    if value is None or value is False or value == [] or value == "":
        return ""                      # absent, off and empty all mean "nothing"
    return value


def changes(before: dict, after: dict) -> list[str]:
    """The fields a row actually changed."""
    return [k for k in after
            if not k.startswith("_") and _norm(k, after.get(k)) != _norm(k, before.get(k))]


def apply_row(base: dict, row: dict) -> dict:
    """Return ``base`` (a dashboard profile) with one CSV row applied."""
    d = dict(base)
    for header, raw in row.items():
        kind = _KIND[header]
        raw = raw if raw is not None else ""
        if kind in ("id", "proxy", "proxy_extra"):
            continue                               # handled below / not editable
        if kind == "text":
            d[header] = raw.strip() or ("Unfiled" if header == "folder" else "")
        elif kind == "keep":
            if raw.strip():
                d[header] = _check(header, raw.strip())
        elif kind == "int":
            if raw.strip():
                try:
                    d[header] = int(float(raw.strip()))
                except ValueError:
                    raise ValueError(f"{header}: '{raw}' isn't a whole number")
        elif kind == "bool":
            if raw.strip():
                d[header] = _bool(raw, header)
        elif kind == "tags":
            parts = raw.replace(";", ",").replace("\n", ",").split(",")
            d["tags"] = list(dict.fromkeys(t.strip() for t in parts if t.strip()))
        elif kind == "lines":
            d[header] = _lines(raw)
        elif kind == "storage":
            d["storage"] = _storage(raw)

    if "proxy" in row:
        d["proxy"] = _proxy(row["proxy"], base.get("proxy"))
    if d.get("proxy"):
        px = dict(d["proxy"])
        if "proxyCountry" in row:
            px["country"] = row["proxyCountry"].strip().upper()
        if "changeIpUrl" in row:
            px["changeIpUrl"] = row["changeIpUrl"].strip()
        d["proxy"] = px

    # A new locale with no timezone of its own moves the timezone with it, as
    # the editor and bulk edit do.
    if row.get("locale", "").strip() and not row.get("timezone", "").strip() \
            and row["locale"].strip() != base.get("locale"):
        tz = devices.LOCALES.get(row["locale"].strip(), (None, None))[0]
        if tz:
            d["timezone"] = tz
    return d


def new_profile(row: dict, default_engine: str) -> dict:
    """A complete dashboard profile for a row that creates one: a fresh coherent
    device for the row's OS and locale, then the row's own cells on top."""
    from .models import Profile
    from .server import OS_TO_ENGINE, to_dashboard_profile
    os_key = OS_TO_ENGINE.get((row.get("os") or "").strip(), "windows")
    locale = (row.get("locale") or "").strip() or None
    fp = generate(os=os_key, locale=locale if locale in devices.LOCALES else None)
    base = to_dashboard_profile(Profile(name="Imported", fingerprint=fp,
                                        engine=default_engine))
    base["seed"] = fp.seed
    base["folder"] = "Unfiled"
    return apply_row(base, row)


def import_rows(rows: list[dict], existing: list[dict], default_engine: str,
                save: Optional[Callable[[dict], dict]] = None) -> list[dict]:
    """Apply parsed rows: update the profiles they match, create the rest.

    Returns one report per row: ``{"row", "name", "action", "issues"}`` where
    action is created / updated / unchanged / error (with ``error``). With no
    ``save`` nothing is written: a dry run."""
    from .server import dashboard_coherence
    by_id = {p.get("id"): p for p in existing}
    by_name: dict[str, list[dict]] = {}
    for p in existing:
        by_name.setdefault(p.get("name") or "", []).append(p)

    reports = []
    for i, row in enumerate(rows, start=2):            # row 1 is the header
        rid = (row.get("id") or "").strip()
        name = (row.get("name") or "").strip()
        current = by_id.get(rid)
        if current is None and name and len(by_name.get(name, [])) == 1:
            current = by_name[name][0]                  # id mangled by a spreadsheet
        try:
            if current is not None:
                updated = apply_row(current, row)
                changed = changes(current, updated)
                action = "updated" if changed else "unchanged"
            else:
                if not name:
                    raise ValueError("a new profile needs a name")
                updated = new_profile(row, default_engine)
                changed, action = [], "created"
        except ValueError as e:
            reports.append({"row": i, "name": name, "action": "error", "error": str(e)})
            continue
        if save and action != "unchanged":
            updated = save(updated)
            if action == "created":
                by_id[updated.get("id")] = updated
        reports.append({"row": i, "name": updated.get("name", name), "action": action,
                        "id": updated.get("id"), "changed": changed,
                        "issues": dashboard_coherence(updated)})
    return reports


def summary(reports: list[dict]) -> dict:
    counts = {k: 0 for k in ("created", "updated", "unchanged", "error")}
    for r in reports:
        counts[r["action"]] += 1
    counts["flagged"] = sum(1 for r in reports if r.get("issues"))
    return counts
