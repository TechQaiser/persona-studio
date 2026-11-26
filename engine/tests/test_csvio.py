"""CSV round-trip: export profiles, edit them in a spreadsheet, import back."""

import csv
import io

import pytest

from persona import csvio
from persona.cli import main
from persona.server import DashboardStore

BASE = {
    "id": "a1b2c3d4e5f6", "name": "Shop-01", "folder": "Ads", "tags": ["fb", "q3"],
    "notes": "main", "engine": "playwright", "os": "Windows", "browserVersion": "151.0.0.0",
    "userAgent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"),
    "screen": "1920x1080", "cores": 8, "memory": 16,
    "webglVendor": "Google Inc. (NVIDIA)",
    "webglRenderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 (0x00002504) Direct3D11 vs_5_0 ps_5_0, D3D11)",
    "locale": "en-US", "timezone": "America/New_York",
    "proxy": {"type": "SOCKS5", "host": "1.2.3.4", "port": "1080", "user": "bob",
              "pass": "s3cret", "country": "US", "changeIpUrl": "https://rot.example/x"},
    "autoLang": False, "blockImages": True, "blockVideo": False,
    "storage": {"history": False, "passwords": False},
    "startupUrls": "https://a.example\nhttps://b.example", "extensions": "", "launchArgs": "",
}


def rows_of(text):
    return list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))


def one(row_patch, base=BASE, **kw):
    """Export ``base``, change cells in its row, import it back."""
    row = rows_of(csvio.export_csv([base], **kw))[0]
    row.update(row_patch)
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=list(row))
    w.writeheader()
    w.writerow(row)
    rows, _ = csvio.read_rows(out.getvalue())
    saved = []
    rep = csvio.import_rows(rows, [base], "playwright", save=lambda d: saved.append(d) or d)
    return rep[0], (saved[0] if saved else None)


def test_export_columns_and_cells():
    text = csvio.export_csv([BASE])
    assert text.startswith("﻿")                  # Excel reads it as UTF-8
    row = rows_of(text)[0]
    assert list(row) == csvio.HEADERS
    assert row["tags"] == "fb, q3"
    assert row["proxy"] == "socks5://bob@1.2.3.4:1080"  # no password by default
    assert row["proxyCountry"] == "US"
    assert row["blockImages"] == "yes" and row["blockVideo"] == "no"
    assert row["clearOnClose"] == "history, passwords"
    assert row["startupUrls"] == "https://a.example\nhttps://b.example"


def test_passwords_only_on_request():
    row = rows_of(csvio.export_csv([BASE], passwords=True))[0]
    assert row["proxy"] == "socks5://bob:s3cret@1.2.3.4:1080"


def test_untouched_sheet_changes_nothing():
    rep, saved = one({})
    assert rep["action"] == "unchanged" and saved is None


def test_untouched_sheet_with_passwords_changes_nothing():
    rep, saved = one({}, passwords=True)
    assert rep["action"] == "unchanged"


def test_edit_updates_only_what_changed():
    rep, saved = one({"notes": "new note", "tags": "fb; q4", "cores": "12", "blockVideo": "Yes"})
    assert rep["action"] == "updated"
    assert set(rep["changed"]) == {"notes", "tags", "cores", "blockVideo"}
    assert saved["id"] == BASE["id"]
    assert saved["tags"] == ["fb", "q4"] and saved["cores"] == 12 and saved["blockVideo"] is True
    assert saved["proxy"]["pass"] == "s3cret"           # kept though not exported


def test_empty_text_cells_clear_but_empty_device_cells_keep():
    rep, saved = one({"notes": "", "tags": "", "proxy": "", "startupUrls": "",
                      "clearOnClose": "", "cores": "", "userAgent": "", "blockImages": ""})
    assert saved["notes"] == "" and saved["tags"] == [] and saved["proxy"] is None
    assert saved["startupUrls"] == ""
    assert csvio.normalize_storage(saved["storage"]) == {k: True for k in csvio.STORAGE_KINDS}
    assert saved["cores"] == 8 and saved["userAgent"] == BASE["userAgent"]
    assert saved["blockImages"] is True


def test_new_proxy_replaces_password_and_country():
    _, saved = one({"proxy": "http://ann:pw@5.6.7.8:8080", "proxyCountry": "de"})
    assert saved["proxy"]["host"] == "5.6.7.8" and saved["proxy"]["pass"] == "pw"
    assert saved["proxy"]["country"] == "DE"
    # The sheet's own changeIpUrl cell wins; emptying it clears it.
    assert saved["proxy"]["changeIpUrl"] == "https://rot.example/x"
    _, saved = one({"proxy": "http://ann:pw@5.6.7.8:8080", "changeIpUrl": ""})
    assert saved["proxy"]["changeIpUrl"] == ""


def test_locale_moves_timezone_unless_given():
    _, saved = one({"locale": "de-DE", "timezone": ""})
    assert saved["timezone"] == "Europe/Berlin"
    _, saved = one({"locale": "de-DE", "timezone": "Europe/Vienna"})
    assert saved["timezone"] == "Europe/Vienna"


@pytest.mark.parametrize("patch,needle", [
    ({"os": "Solaris"}, "os:"),
    ({"engine": "netscape"}, "engine:"),
    ({"locale": "xx-YY"}, "locale:"),
    ({"screen": "big"}, "screen:"),
    ({"cores": "lots"}, "cores:"),
    ({"blockImages": "maybe"}, "blockImages:"),
    ({"clearOnClose": "cookies"}, "clearOnClose:"),
    ({"proxy": "not a proxy"}, "proxy:"),
])
def test_bad_cells_fail_the_row_with_a_reason(patch, needle):
    rep, saved = one(patch)
    assert rep["action"] == "error" and needle in rep["error"] and saved is None


def test_os_and_screen_are_tidied():
    _, saved = one({"os": "macos", "screen": "2560 × 1440"})
    assert saved["os"] == "macOS" and saved["screen"] == "2560x1440"


def test_coherence_issues_are_reported():
    rep, _ = one({"os": "macOS"})                  # UA and GPU still say Windows/NVIDIA
    assert rep["action"] == "updated" and rep["issues"]


def test_rows_without_a_known_id_create_coherent_profiles():
    text = "name,os,locale,tags,blockImages\nNew-1,macOS,de-DE,imported,yes\n"
    rows, _ = csvio.read_rows(text)
    saved = []
    rep = csvio.import_rows(rows, [BASE], "cloak", save=lambda d: saved.append(d) or d)
    assert rep[0]["action"] == "created" and rep[0]["issues"] == []
    d = saved[0]
    assert d["name"] == "New-1" and d["os"] == "macOS" and d["locale"] == "de-DE"
    assert "Mac OS X" in d["userAgent"] and d["engine"] == "cloak"
    assert d["blockImages"] is True and d["folder"] == "Unfiled" and d["seed"]
    assert "id" not in d                           # the store mints one


def test_new_row_needs_a_name():
    rows, _ = csvio.read_rows("name,notes\n,orphan\n")
    assert csvio.import_rows(rows, [], "playwright")[0]["action"] == "error"


def test_mangled_id_falls_back_to_a_unique_name():
    # Excel turns an all-digit id into a number, e.g. "001234567890" -> 1234567890.
    base = dict(BASE, id="001234567890")
    rep, saved = one({"id": "1234567890", "notes": "x"}, base=base)
    assert rep["action"] == "updated" and saved["id"] == "001234567890"


def test_semicolon_sheets_bom_and_odd_headers():
    text = "﻿ID;Name;Block Images;Notes;Colour\na1b2c3d4e5f6;Shop-01;no;hi;red\n"
    rows, ignored = csvio.read_rows(text)
    assert ignored == ["Colour"]
    assert rows[0] == {"id": "a1b2c3d4e5f6", "name": "Shop-01", "blockImages": "no", "notes": "hi"}


def test_a_file_without_headers_is_refused():
    with pytest.raises(ValueError):
        csvio.read_rows("foo,bar\n1,2\n")


def test_dry_run_saves_nothing():
    rows, _ = csvio.read_rows("name\nBrand-new\n")
    rep = csvio.import_rows(rows, [], "playwright", save=None)
    assert rep[0]["action"] == "created"
    assert csvio.summary(rep)["created"] == 1


def test_cli_round_trip(tmp_path, capsys):
    dash = DashboardStore(tmp_path)
    dash.save(dict(BASE))
    sheet = tmp_path / "p.csv"
    assert main(["--data-dir", str(tmp_path), "csv", "export", str(sheet)]) == 0
    text = sheet.read_text(encoding="utf-8-sig").replace("main", "edited")
    sheet.write_text(text + ",New-2,,,,,,,,,,,,,,,,,,,,,,,,\n", encoding="utf-8")
    assert main(["--data-dir", str(tmp_path), "csv", "import", str(sheet), "--dry-run"]) == 0
    assert dash.get(BASE["id"])["notes"] == "main"
    assert main(["--data-dir", str(tmp_path), "csv", "import", str(sheet)]) == 0
    assert dash.get(BASE["id"])["notes"] == "edited"
    assert sorted(d["name"] for d in dash.list()) == ["New-2", "Shop-01"]
    assert "1 created, 1 updated" in capsys.readouterr().out


def test_api_export_and_import(tmp_path):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from persona.server import TOKEN_HEADER, create_app
    app = create_app(str(tmp_path), start_scheduler=False)
    c = TestClient(app, base_url="http://localhost", headers={TOKEN_HEADER: app.state.api_token})
    DashboardStore(tmp_path).save(dict(BASE))

    r = c.get("/api/profiles/export.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "s3cret" not in r.text
    assert "s3cret" in c.get("/api/profiles/export.csv?passwords=true").text
    assert c.get("/api/profiles/export.csv?ids=nope").text.count("\n") == 1   # header only

    edited = r.text.replace("main", "from sheet")
    dry = c.post("/api/profiles/import-csv", json={"text": edited, "dryRun": True}).json()
    assert dry["summary"]["updated"] == 1
    assert c.get("/api/profiles").json()[0]["notes"] == "main"
    res = c.post("/api/profiles/import-csv", json={"text": edited}).json()
    assert res["summary"]["updated"] == 1 and res["results"][0]["changed"] == ["notes"]
    assert c.get("/api/profiles").json()[0]["notes"] == "from sheet"
    assert c.post("/api/profiles/import-csv", json={"text": "x,y\n"}).status_code == 400
