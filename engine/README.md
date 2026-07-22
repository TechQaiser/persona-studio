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
| `stealth.py` | Generates the page-level JS patch for a fingerprint |
| `launcher.py` | Thin dispatcher: picks the profile's engine and hands off |
| `drivers.py` | Pluggable launch backends (playwright / patchright / camoufox) |
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
