# Architecture

Persona has two parts: a Python **engine** that does the real work, and a React
**dashboard** that drives it. This doc explains how they fit together.

## The coherence principle

Every design decision follows from one idea: a fingerprint is only convincing
when its parts agree. Anti-bot systems cross-check values, so the failure mode
isn't an unusual value — it's a *contradiction* (a Mac UA with a Windows GPU, a
timezone that doesn't match the language, a phone with a desktop screen).

So instead of randomising fields independently, the engine picks a device
**archetype** first, then draws every value from that archetype's realistic pool.
A `validate()` function encodes the same cross-checks and can gate any fingerprint
before it's used.

## Engine flow

```
pick OS ──▶ archetype (devices.py) ──▶ Fingerprint ──▶ validate()
                                             │
                        ┌────────────────────┴────────────────────┐
                        ▼                                          ▼
              context-level options                     page-level init script
              (launcher.py → Playwright)                (stealth.py)
              UA, viewport, screen, locale,             navigator.platform, WebGL
              timezone, proxy, Client-Hints             vendor/renderer, cores,
                                                        deviceMemory, webdriver=false,
                                                        seeded canvas noise
                        └────────────────────┬────────────────────┘
                                             ▼
                          Chromium persistent context per profile
                          (cookies + localStorage persist)
```

### Modules

| Module | Role |
|---|---|
| `devices.py` | Curated OS/GPU/screen/hardware/locale building blocks |
| `fingerprint.py` | `generate()` assembles a coherent fingerprint; `validate()` checks it; `sec_ch_ua()` builds Client-Hints |
| `models.py` | `Fingerprint`, `Proxy`, `Profile` dataclasses + (de)serialization |
| `store.py` | `ProfileStore` — one JSON file per profile under `~/.persona`, plus a `user-data/<id>` dir per profile for the browser session |
| `stealth.py` | Builds the per-fingerprint JS patch injected via `add_init_script` |
| `launcher.py` | Thin dispatcher — resolves `profile.engine` and hands off to a driver |
| `drivers.py` | Pluggable launch backends (playwright / patchright / camoufox) |
| `cli.py` | Command-line interface over the store + launcher |

### Pluggable launch engines

Persona is the *manager*; a **driver** renders an identity in a real browser.
`launcher.launch()` looks up `profile.engine` in the `drivers.py` registry and
delegates. Built-ins:

- **playwright** — stock Chromium + the `stealth.py` init script. Always available.
  Its ceiling is the JS-injection ceiling: no control over TLS/JA3 or the CDP
  transport, so it clears basic bot checks but not Cloudflare/DataDome-grade ones.
- **patchright** — a drop-in, API-compatible *patched* Playwright that closes
  `webdriver`/CDP leaks at the runtime level.
- **camoufox** — a patched Firefox with C++-level fingerprint spoofing and its own
  coherent fingerprint generator.

Drivers share the same signature and either return launch handles
(`keep_open=True`) or block until the window closes (`keep_open=False`). Register
a new one with `@drivers.register("name", requires="pip-module")`.

### Why two levels of spoofing?

Playwright sets some values at the browser-context level (user-agent, viewport,
locale, timezone, proxy). But a few high-signal values live inside the page and
must be patched there (navigator.platform, WebGL strings, hardwareConcurrency,
the `webdriver` flag, canvas noise). The stealth script handles the second set,
and the launcher makes sure both levels describe the *same* device.

## Storage layout

```
~/.persona/
├── profiles/
│   ├── <id>.json          # profile metadata + fingerprint + proxy
│   └── …
└── user-data/
    ├── <id>/              # Chromium user-data dir (cookies, localStorage)
    └── …
```

One JSON file per profile keeps things transparent, diff-friendly and easy to
back up or sync.

## Connecting the dashboard to the engine

This is implemented. `engine/persona/server.py` exposes the engine over HTTP
(`persona serve`, default `http://127.0.0.1:8787`), and the dashboard talks to it
through `dashboard/src/api.js`.

```
 Dashboard (React)                     Engine API (FastAPI)              Engine core
 ─────────────────                     ────────────────────             ───────────
 on load → GET /api/health ───────────▶ health()
   ok?  → live mode                     GET  /api/profiles ────────────▶ DashboardStore
   no   → demo mode (sample data)       POST /api/profiles                (JSON per profile)
                                        PUT/DELETE /api/profiles/{id}
 click ▶ → POST /…/{id}/launch ────────▶ to_engine_profile() ──────────▶ launcher.launch
                                          + subprocess: persona launch     (real Chromium)
 click ■ → POST /…/{id}/stop ──────────▶ terminate the launch process
```

Key points:

- **Two profile shapes.** The dashboard's profile is richer than the engine's
  (folders, per-signal spoof modes, media counts). The API stores the dashboard
  JSON as-is and only converts to an engine `Fingerprint`/`Profile` at launch
  time (`to_engine_profile`), so nothing in the UI is lost on a round-trip.
- **Launching is a subprocess.** `/launch` runs `persona launch <id>` in its own
  process rather than driving Playwright's sync API from inside the async server.
  A profile is "running" while that process is alive; `/stop` terminates it.
- **Coherence** stays in the dashboard (its meter mirrors `validate()`) for
  instant feedback; the engine re-validates the real fingerprint at launch.
- **Graceful fallback.** If the API is offline the dashboard runs on in-memory
  sample data (demo mode), so it still works standalone.
