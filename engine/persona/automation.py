"""
Local automation API — drive a Persona profile from your own script.

Persona opens the browser wearing the identity; your automation attaches to that
same window over the Chrome DevTools Protocol and does the work. Nothing is
re-launched, so the session, cookies, proxy and fingerprint stay exactly as
Persona set them up — which is the whole point. A second browser started by
Selenium would be a different, un-warmed, un-spoofed browser.

    persona attach acct-01 --port 9222

prints the endpoint plus ready-to-paste snippets, and keeps the window open
until you close it.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Optional

from . import drivers
from .models import Profile
from .store import ProfileStore

CHROMIUM_ENGINES = ("playwright", "patchright", "cloak")


def cdp_info(port: int, timeout: float = 20.0) -> dict:
    """Wait for the DevTools endpoint to answer and return its ``/json/version``."""
    url = f"http://127.0.0.1:{port}/json/version"
    deadline = time.time() + timeout
    last: Optional[Exception] = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as res:
                return json.loads(res.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
            last = e
            time.sleep(0.3)
    raise RuntimeError(f"DevTools didn't come up on port {port}: {last}")


def attach(profile: Profile, store: ProfileStore, port: int = 9222,
           engine: Optional[str] = None, headless: bool = False):
    """Launch the profile with CDP listening. Returns ``(handles, info)``.

    ``handles`` is the driver's ``(pw, context, page)``; the caller owns closing
    them. ``info`` is the DevTools ``/json/version`` payload, whose
    ``webSocketDebuggerUrl`` is what Playwright and Puppeteer connect to.
    """
    name = engine or profile.engine or "playwright"
    if name not in CHROMIUM_ENGINES:
        raise RuntimeError(
            f"The '{name}' engine has no Chrome DevTools Protocol to attach to.\n"
            f"Use one of: {', '.join(CHROMIUM_ENGINES)} — e.g. persona attach "
            f"{profile.name} --engine cloak"
        )
    handles = drivers.get(name)(
        profile, store, headless=headless, keep_open=True,
        extra_args=[f"--remote-debugging-port={port}"],
    )
    return handles, cdp_info(port)


def snippets(port: int, ws_url: str) -> str:
    """Copy-paste examples for the three clients people actually use."""
    return f"""
Playwright (Python)
    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:{port}")
    page = browser.contexts[0].pages[0]

Puppeteer (Node)
    const browser = await puppeteer.connect({{ browserURL: "http://127.0.0.1:{port}" }});
    const [page] = await (await browser.pages());

Selenium (Python)
    from selenium import webdriver
    opts = webdriver.ChromeOptions()
    opts.add_experimental_option("debuggerAddress", "127.0.0.1:{port}")
    driver = webdriver.Chrome(options=opts)

WebSocket endpoint
    {ws_url}
"""
