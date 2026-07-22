# Persona Engine

The Python core of [Persona](../README.md): coherent fingerprint generation,
profile storage, and a Playwright-based launcher, with a full CLI.

> This is the backend. For the visual dashboard see [`../dashboard`](../dashboard).

## Install

```bash
cd engine
pip install -e .

# To launch real browsers (optional):
pip install -e ".[launch]"
playwright install chromium

# To serve the HTTP API for the dashboard (optional):
pip install -e ".[api]"
```

## CLI

```bash
persona create acct-01 --os windows --locale en-US --tag client-x
persona create acct-02 --mobile --proxy "http://user:pass@host:8080" --country PK
persona list
persona show acct-01
persona check acct-01          # validate fingerprint coherence
persona engines                # list available launch engines
persona default-engine cloak   # set the engine new profiles use (CloakBrowser)
persona launch acct-01
persona export acct-01 acct-01.json
persona import acct-01.json
persona serve                  # run the HTTP API the dashboard talks to
```

### Inspecting a profile

```bash
persona trust acct-01            # score it the way a fingerprinting script would
persona proxy test acct-01       # exit IP, country, timezone match + WebRTC leaks
```

`trust` opens the profile and runs the checks a real fingerprinter runs —
`navigator.webdriver`, plugins, UA vs platform, WebGL, timezone, font probing,
media devices, and whether canvas reads the same twice. It grades the *browser*,
not the config; `persona check` grades the config. Add `--json` to either for
machine-readable output.

`proxy test` needs internet: it routes a real request through the profile and
reports where it came out, then asks WebRTC whether it would give away an
address the proxy was meant to hide. It works without a proxy too — that's your
baseline.

### Extensions, warm-up, automation

```bash
persona ext add acct-01 ./ublock        # unpacked folder (the one with manifest.json)
persona ext list acct-01
persona warmup acct-01 --minutes 10     # browse normally so the session isn't brand-new
persona attach acct-01 --port 9222      # open it for Selenium / Puppeteer / Playwright
```

`attach` launches the profile with the DevTools protocol listening and prints
ready-to-paste snippets. Your automation drives *that* browser, so the identity,
proxy and session stay exactly as Persona set them up — a browser started by
Selenium itself would have none of them.

### Changing many profiles at once

```bash
persona apply --tag client-a --engine cloak        # move a whole set to CloakBrowser
persona apply --all --locale de-DE                 # locale, timezone and languages together
persona apply acct-01 acct-02 --add-tag q3 --regen # fresh fingerprints, same accounts
persona apply --tag old --proxy "" -y              # "" means go direct
```

Only the flags you pass are changed — everything else is left alone, so the same
command is safe to run again later for one more tweak.

### Cookies

Move a logged-in session between machines, or seed a fresh profile with one you
already have:

```bash
persona cookies list   acct-01                   # what's in the jar, by domain
persona cookies export acct-01 session.json      # Playwright storage state
persona cookies export acct-01 cookies.txt       # Netscape format (curl/wget)
persona cookies import acct-01 session.json      # merge into the profile
persona cookies import acct-01 session.json --clear   # replace instead
```

Import understands whatever you have on hand: Cookie-Editor / EditThisCookie
JSON, Playwright storage state, and Netscape `cookies.txt`. Export picks the
format from the file extension (`.txt` → Netscape) unless you pass `--format`.

Two things the browser decides, not Persona: **session cookies aren't stored** (
Chromium keeps them in memory only, so they don't survive an export), and
Chromium **caps cookie lifetime at ~400 days**, so far-future expiry dates come
back shortened. Close the profile before moving cookies — a session can't be
open twice.

## HTTP API

`persona serve` (needs `pip install -e ".[api]"`) starts a small FastAPI app the
dashboard uses to manage and launch profiles for real. It listens on
`http://127.0.0.1:8787` by default (`--host` / `--port` to change).

| Method | Path | Does |
|---|---|---|
| GET | `/api/health` | Liveness check the dashboard pings on load |
| GET | `/api/profiles` | List profiles (with live run status) |
| POST | `/api/profiles` | Create a profile |
| PUT | `/api/profiles/{id}` | Update a profile |
| DELETE | `/api/profiles/{id}` | Delete a profile + its session |
| POST | `/api/profiles/{id}/launch` | Open the profile in a real Chromium window |
| POST | `/api/profiles/{id}/stop` | Close a running profile |
| GET | `/api/profiles/{id}/cookies` | Read the profile's cookie jar |
| POST | `/api/profiles/{id}/cookies` | Import cookies (`text` or `cookies`, plus `clear`) |
| POST | `/api/profiles/{id}/proxy-test` | Exit IP, country and WebRTC leak check |
| POST | `/api/profiles/{id}/trust` | Trust score + the individual checks |
| POST | `/api/profiles/{id}/warmup` | Start a background warm-up (`minutes`) |
| POST | `/api/profiles/bulk` | Apply one `patch` to many `ids` |
| POST | `/api/fingerprint/validate` | Coherence check a fingerprint |

## Python API

```python
from persona import ProfileStore, generate, Profile, Proxy

store = ProfileStore()
profile = Profile(
    name="acct-01",
    fingerprint=generate(os="windows", locale="en-US"),
    proxy=Proxy(server="http://host:8080", country="US"),
)
store.save(profile)
```

## Modules

| Module | Responsibility |
|---|---|
| `devices.py` | Curated, internally-consistent hardware/OS building blocks |
| `fingerprint.py` | Assembles coherent fingerprints; `validate()` proves it |
| `models.py` | `Fingerprint`, `Proxy`, `Profile` data models |
| `store.py` | JSON-per-profile persistence + user-data dirs |
| `cookies.py` | Cookie import/export across the formats people actually have |
| `probe.py` | Proxy/leak test and the trust report a fingerprinter would produce |
| `bulk.py` | Multi-profile synchroniser: one patch, applied to many |
| `warmup.py` | Human-paced browsing that gives a fresh profile a past |
| `automation.py` | CDP attach so Selenium/Puppeteer/Playwright can drive a profile |
| `stealth.py` | Generates the page-level JS patch for a fingerprint |
| `launcher.py` | Thin dispatcher: picks the profile's engine and hands off |
| `drivers.py` | Pluggable launch backends (cloak / camoufox / patchright / playwright) |
| `server.py` | FastAPI HTTP API the dashboard drives (`persona serve`) |
| `cli.py` | Command-line interface |

## Launch engines (pluggable)

Persona *manages* identities; a **driver** actually opens the browser. Pick one
per profile with `--engine` (or in the dashboard), and see which are installed
with `persona engines`.

| Engine | What it is | Install |
|---|---|---|
| `cloak` | **Recommended.** CloakBrowser — a patched Chromium binary (C++-level fingerprint/TLS/CDP patches). Beats Cloudflare/DataDome-grade detection. | `pip install cloakbrowser` |
| `camoufox` | **Recommended.** Patched Firefox with C++-level fingerprint spoofing and its own coherent fingerprint. | `pip install "camoufox[geoip]" && camoufox fetch` |
| `patchright` | Drop-in **patched** Playwright — fixes `webdriver`/CDP leaks at runtime. | `pip install patchright && patchright install chromium` |
| `playwright` | Stock Chromium + Persona's injected stealth script. Built-in, always available. | included in `[launch]` |

```bash
persona engines                              # list engines + install status
persona create acct-01 --engine patchright   # choose a backend
persona launch acct-01                        # uses the profile's engine
persona launch acct-01 --engine camoufox      # override for one run
```

Add your own backend by registering a function in `drivers.py`.

> **Reality check.** `playwright` injects JavaScript into stock Chromium, so it
> can't change the TLS/JA3 fingerprint or hide the CDP transport — it passes basic
> bot tests but not Cloudflare/DataDome/reCAPTCHA-v3. For that, use a
> runtime-patched engine (`patchright`, `camoufox`) plus a residential proxy and a
> warmed-up session.

## Tests

```bash
pip install -e ".[dev]"
python -m pytest
```
