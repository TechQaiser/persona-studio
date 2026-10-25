"""Launch hardening: the claimed Chrome version follows the real engine, and
with a proxy no name is resolved by the local DNS."""

from persona import drivers
from persona.drivers import _dns_lockdown_arg, sync_engine_version
from persona.fingerprint import generate, set_chrome_version, sec_ch_ua
from persona.models import Profile, Proxy


def test_set_chrome_version_rewrites_ua_and_client_hints():
    fp = generate(os="windows", seed=1)
    fp.chrome_version, fp.user_agent = "128.0.0.0", fp.user_agent.replace(
        fp.user_agent.split("Chrome/")[1].split(" ")[0], "128.0.0.0")
    assert set_chrome_version(fp, "151.0.7922.34")
    assert fp.chrome_version == "151.0.0.0" and "Chrome/151.0.0.0 " in fp.user_agent
    assert '"Google Chrome";v="151"' in sec_ch_ua(fp)
    assert not set_chrome_version(fp, "151.0.0.0")          # already there


def test_android_keeps_its_handset_in_the_ua():
    fp = generate(os="android", seed=4)
    model = fp.user_agent.split("; ")[2].split(")")[0]
    set_chrome_version(fp, "100.0.0.0")
    assert f"; {model})" in fp.user_agent and "Mobile Safari" in fp.user_agent


def test_sync_uses_the_engine_version(monkeypatch):
    monkeypatch.setitem(drivers._engine_versions, "cloak", "146.0.7680.177.5")
    p = Profile(name="v", fingerprint=generate(os="windows", seed=2))
    assert sync_engine_version(p, "cloak") and p.fingerprint.chrome_version == "146.0.0.0"


def test_unknown_engine_version_leaves_profile_alone(monkeypatch):
    monkeypatch.setitem(drivers._engine_versions, "camoufox", None)
    p = Profile(name="v", fingerprint=generate(os="windows", seed=2))
    before = p.fingerprint.user_agent
    assert not sync_engine_version(p, "camoufox") and p.fingerprint.user_agent == before


def test_dns_lockdown_only_with_a_proxy():
    p = Profile(name="d", fingerprint=generate(seed=1))
    assert _dns_lockdown_arg(p) == []
    p.proxy = Proxy(server="http://proxy.example:8080")
    (arg,) = _dns_lockdown_arg(p)
    assert arg.startswith("--host-resolver-rules=MAP * ~NOTFOUND")
    assert "EXCLUDE proxy.example" in arg and "EXCLUDE localhost" in arg


def test_dns_lockdown_with_bridged_socks_excludes_loopback_only():
    p = Profile(name="d", fingerprint=generate(seed=1),
                proxy=Proxy(server="socks5://127.0.0.1:1", username="u", password="p"))
    (arg,) = _dns_lockdown_arg(p)
    assert "EXCLUDE 127.0.0.1" in arg


def test_ua_metadata_matches_the_header_and_device():
    from persona.drivers import ua_metadata
    fp = generate(os="windows", seed=1)
    set_chrome_version(fp, "151")
    m = ua_metadata(fp, "151.0.7922.34")
    assert [b["brand"] for b in m["brands"]] == ["Chromium", "Google Chrome", "Not-A.Brand"]
    for b in m["brands"]:
        assert f'"{b["brand"]}";v="{b["version"]}"' in sec_ch_ua(fp)   # JS == header
    assert m["fullVersion"] == "151.0.7922.34" and m["platform"] == "Windows"
    assert m["mobile"] is False and m["architecture"] == "x86" and m["model"] == ""


def test_ua_metadata_ignores_a_full_version_from_another_major():
    from persona.drivers import ua_metadata
    fp = generate(os="windows", seed=1)
    set_chrome_version(fp, "150")
    assert ua_metadata(fp, "151.0.7922.34")["fullVersion"] == "150.0.0.0"


def test_ua_metadata_phone_and_apple_silicon():
    from persona.drivers import ua_metadata
    phone = generate(os="android", seed=4)
    m = ua_metadata(phone)
    assert m["mobile"] is True and m["model"] and m["platform"] == "Android"
    assert m["platformVersion"].split(".")[0] in ("13", "14")
    mac = generate(os="macos", seed=1)
    mac.webgl_renderer = "ANGLE (Apple, Apple M2, OpenGL 4.1)"
    assert ua_metadata(mac)["architecture"] == "arm"


def test_font_warning_when_profile_os_is_not_the_machines():
    from persona.drivers import launch_warnings
    mac = Profile(name="m", fingerprint=generate(os="macos", seed=1))
    win = Profile(name="w", fingerprint=generate(os="windows", seed=1))
    assert "fonts" in launch_warnings(mac, "playwright", host="windows")[0]
    assert launch_warnings(win, "playwright", host="windows") == []
    assert launch_warnings(win, "camoufox", host="linux") == []          # renders its own


def test_cloak_warnings():
    from persona.drivers import launch_warnings
    linux = Profile(name="l", fingerprint=generate(os="linux", seed=1))
    mac = Profile(name="m", fingerprint=generate(os="macos", seed=1))
    win = Profile(name="w", fingerprint=generate(os="windows", seed=1))
    assert "only present Windows or macOS" in launch_warnings(linux, "cloak", host="windows")[0]
    assert "Mac fonts" in launch_warnings(mac, "cloak", host="windows")[0]
    assert launch_warnings(mac, "cloak", host="macos") == []
    assert launch_warnings(win, "cloak", host="linux") == []


def test_profile_launch_args_keep_custom_drop_managed():
    from persona.drivers import launch_warnings, profile_launch_args
    p = Profile(name="a", fingerprint=generate(os="windows", seed=1),
                launch_args=["--disable-gpu", "  ", "--proxy-server=http://x:1",
                             "--fingerprint=123", "--fingerprint-noise=false", "rm -rf"])
    kept, dropped = profile_launch_args(p)
    assert kept == ["--disable-gpu", "--fingerprint-noise=false"]
    assert dropped == ["--proxy-server=http://x:1", "--fingerprint=123", "rm -rf"]
    warn = launch_warnings(p, "cloak", host="windows")
    assert "ignored launch flag --proxy-server: Persona sets the proxy and DNS lockdown" in warn
    assert "ignored launch flag rm -rf: not a browser flag" in warn


def test_flag_denylist_covers_identity_and_reports_why():
    from persona.drivers import flag_problem
    for flag in ("--window-size=800,600", "--lang=de", "--user-agent=x", "--use-angle=gl",
                 "--force-device-scale-factor=2", "--webrtc-ip-handling-policy=default",
                 "--fingerprint-gpu-renderer=x", "--no-sandbox", "--Proxy-Server=x",
                 "--remote-debugging-port=9", "--disable-blink-features=x", "--headless"):
        assert flag_problem(flag), flag
    assert "identity" in flag_problem("--window-size=1,1")
    assert "sandbox" in flag_problem("--no-sandbox")
    for flag in ("--disable-gpu", "--fingerprint-noise=false", "--mute-audio",
                 "--host-rules=MAP x y", "-private", "--force-dark-mode"):
        assert flag_problem(flag) is None, flag
    for junk in ("rm -rf", "--", "--bad flag", "x=1", "---x"):
        assert flag_problem(junk) == "not a browser flag", junk


def test_launch_args_round_trip_dashboard_and_disk():
    from persona.server import to_dashboard_profile, to_engine_profile
    p = Profile(name="a", fingerprint=generate(os="windows", seed=1), launch_args=["--disable-gpu"])
    assert Profile.from_dict(p.to_dict()).launch_args == ["--disable-gpu"]
    d = {**to_dashboard_profile(p), "id": p.id}
    assert d["launchArgs"] == "--disable-gpu"
    assert to_engine_profile(d).launch_args == ["--disable-gpu"]
