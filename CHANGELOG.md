# Changelog

Format based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added
- **Profile health overview** (`GET /api/profiles/health`, dashboard **Health**
  page): one row per profile grading it at a glance — coherence (computed
  instantly from the stored fingerprint), whether a proxy is set and its country,
  the last measured trust grade (cached from the last trust/align run, since a
  live check opens a real browser), any warm-up schedule, and last-active. Rows
  that need attention (incoherent, or a C/D trust grade) are flagged, with
  one-click **trust check** and **auto-adjust** per row.
- **Scheduled warm-up** (`persona schedule`, `scheduler.py`, `/api/schedules*`):
  recurring, unattended warm-up so a session you log into once doesn't go
  "cold". Add a schedule per profile (interval + vertical); when `persona serve`
  is running a background thread fires the due runs itself, and for people who
  don't run the server, `persona schedule run-due` runs whatever's due from cron
  / Windows Task Scheduler. Exposed in the dashboard's Warm-up section as a
  toggle with interval and vertical controls.
- **Warm-up presets per vertical** (`persona warmup --preset`, `warmup.PRESETS`):
  `ads`, `ecommerce`, `crypto`, `social`, `news` (or the default `general`) each
  browse a site set that matches the account's world, so its history reads like
  a real user of that vertical rather than a random walk. Chosen from a dropdown
  in the dashboard; passed through `POST /api/profiles/{id}/warmup`.
- **DNS leak checker** (`persona dns`, `probe.check_dns`,
  `/api/profiles/{id}/dns`): the companion to the proxy test — even with the
  proxy hiding your IP, DNS lookups that go to your own ISP's resolver still
  reveal the sites you visit at your real location. It resolves a batch of
  unique subdomains through the profile, reads back which resolvers were seen
  (and their countries) from a third-party test service, and fails if any sits
  outside the proxy's country. Folded into `proxy test` and surfaced as a **DNS
  leak test** button next to the connection test in the dashboard.
- **Proxy pool — import, test, assign** (`proxypool.py`, `/api/proxies*`):
  a managed pool the dashboard's Proxies page now drives for real. Import a
  pasted list or file in any common layout (`host:port`, `host:port:user:pass`,
  `user:pass@host:port`, `scheme://…`, optional trailing country code),
  health-check each one over HTTP(S) without a browser (exit IP/country/latency),
  and **assign them round-robin across profiles** — which also aligns each
  profile's locale/timezone to its proxy's country. Bulk-created profiles start
  proxy-less and get real proxies from here, instead of the old placeholder
  hosts.
- **Dashboard-side import** (`/api/profiles/import`, `to_dashboard_profile`):
  the GoLogin / AdsPower / Multilogin importer is now wired to an **Import**
  button in the dashboard — pick an export file, and each profile is mapped to a
  coherent identity, saved, and flagged for review if anything didn't line up.
  (Previously the importer lived in the CLI/engine store only.)
- **Auto-adjust — align a profile to reality** (`persona align`, `probe.py`):
  a one-click fix for a low trust grade. It opens the profile, reads back what
  the browser *actually* presents (platform, CPU, memory, GPU, screen, fonts,
  media, languages) and rewrites the fingerprint to match — regenerating the OS
  identity when the engine turns out to render a different OS than the profile
  claimed (e.g. CloakBrowser showing the host's real hardware). Afterwards the
  browser and the profile tell one story, so a detector sees no contradiction;
  the trust score jumps to A. Exposed as `POST /api/profiles/{id}/align` and an
  **Auto-adjust** button next to the trust check, which pulls the rewritten
  values straight back into the editor and shows the before→after grade.
- **Bulk create at scale** (`persona bulk-create`, `bulk.generate_profiles`,
  `POST /api/profiles/batch`): generate thousands of coherent profiles at once —
  up to 10,000 from the dashboard — spread across operating systems, countries/
  locales and Chrome versions, each with its own seed so no two share a
  fingerprint. The dashboard's bulk dialog gained OS/country/browser multi-pick,
  an engine choice, a randomize-hardware toggle and a per-country proxy switch,
  and posts in chunks; the profile grid is now **paginated** so a 10k list stays
  responsive.
- **Real GPUs and displays count as coherent.** `validate()` (and the dashboard
  meter) now accept any WebGL renderer whose graphics API fits the OS (Windows →
  Direct3D, macOS/Linux → desktop OpenGL) and any real-world screen size, not
  just the short curated lists — so a machine-aligned profile carrying its
  actual GPU/resolution isn't wrongly flagged. `navigator.languages` is matched
  on its primary language rather than an exact list.
- **Import from other anti-detect browsers** (`persona import-from`,
  `importers.py`): migrate profiles exported from GoLogin, AdsPower or
  Multilogin. Tolerant field mapping (each value looked up under its known
  aliases), gaps filled from a coherent generated base, and every imported
  profile run through `validate()` so mismatches are flagged for review rather
  than shipped silently.
- **Encrypt-at-rest for secrets** (`persona vault`, `crypto.py`): a master
  password encrypts proxy passwords in the store (Fernet/AES, key via
  PBKDF2-HMAC-SHA256), leaving the rest of each profile readable. Supply the
  password via `PERSONA_PASSWORD` or `--password` at use time so it never hits
  disk; locked stores still list/manage profiles but withhold the secret, and
  saving would-be-plaintext over an encrypted secret is refused. Optional
  `[secure]` extra; degrades gracefully when it isn't installed.
- **TLS/JA3 handshake checker** (`persona tls`, `probe.py`): reads the profile's
  own TLS/HTTP2 handshake back from an echo service and reports its JA3 and JA4
  fingerprints — the network layer JavaScript can never touch, since the server
  sees it before any page script runs. Checks it negotiates TLS 1.3 + HTTP/2 and
  sends GREASE like a real Chromium. Folded into `proxy test` too, plus
  `POST /api/profiles/{id}/tls` and a button in the dashboard.
- **Fingerprint trust checker** (`persona trust`, `probe.py`): opens the profile
  and runs the checks a fingerprinting script runs — webdriver, plugins, UA vs
  platform, WebGL, timezone, font probing, media devices, canvas stability — then
  scores the result. Grades the real browser, where `persona check` grades the
  config. Also `POST /api/profiles/{id}/trust` and a button in the dashboard.
- **Proxy tester + WebRTC leak checker** (`persona proxy test`): routes a real
  request through the profile, reports the exit IP/country/timezone and whether
  they agree with the identity, then checks whether WebRTC exposes an address the
  proxy was meant to hide. Wires up the dashboard's "Test connection" button.
- **Multi-profile synchroniser** (`persona apply`, `bulk.py`): one change applied
  to many profiles, selected by name, `--tag` or `--all`. Unmentioned fields are
  left alone; changing the locale moves timezone and languages with it. Exposed as
  `POST /api/profiles/bulk` and "Edit all" in the dashboard's selection bar.
- **Account warm-up** (`persona warmup`, `warmup.py`): browses ordinary sites at
  human pace so a fresh profile doesn't arrive with an empty history.
- **Local automation API** (`persona attach`, `automation.py`): launches the
  profile with the DevTools protocol open and prints connect snippets, so
  Selenium/Puppeteer/Playwright drive *that* browser — identity, proxy and
  session intact.
- **Extensions manager**: per-profile unpacked extensions (`persona ext
  add|list|remove`, `Profile.extensions`, dashboard field). Only the profile's own
  extensions load, so nothing carries between profiles.
- **More fingerprint signals**: per-OS installed fonts (answered by
  `document.fonts.check`), camera/microphone counts via `enumerateDevices` with
  seeded stable ids, sub-pixel ClientRects jitter, and seeded audio noise. Fonts
  and media counts are covered by `validate()` too.
- **Cookie import/export** (`persona/cookies.py`): move a logged-in session
  between machines or seed a fresh profile with one you already have. Reads
  Cookie-Editor / EditThisCookie JSON, Playwright storage state and Netscape
  `cookies.txt`; writes JSON or `cookies.txt`. Available as
  `persona cookies list|export|import`, `GET`/`POST /api/profiles/{id}/cookies`,
  and Import/Export buttons in the dashboard's **Advanced** tab.
- **One-click Windows launcher** (`start.bat`): double-click to install deps on
  first run, pick the default engine (CloakBrowser first), then start the engine
  API + dashboard and open the browser.
- **Persisted default engine** for new profiles (`config.json`): `persona
  default-engine [name]` command, `GET`/`PUT /api/config` endpoints, and the
  dashboard defaulting new profiles to it. CloakBrowser is the top-priority
  default, and the last engine you pick "wins" (becomes the next default).
- **HTTP API** (`persona serve`, `engine/persona/server.py`) wrapping the store,
  validator and launcher so the dashboard can manage and launch profiles for real.
- **`python -m persona`** entry point (`persona/__main__.py`).
- Dashboard **live/demo mode**: connects to the engine API when available
  (launching opens a real browser), falls back to sample data when it isn't.
- **Pluggable launch engines** (`persona/drivers.py`): choose a stealth backend
  per profile — `playwright` (built-in), `patchright`, `camoufox`, or `cloak`
  (CloakBrowser). New `persona engines` command, `--engine` flag, `Profile.engine`
  field, dashboard engine selector, and `GET /api/engines` endpoint.
- **Dashboard redesign**: new "ink violet" theme, Space Grotesk / Inter / JetBrains
  Mono typography, motion (load reveals, status pulses, drawer slide), and a
  dedicated **Engines** page recommending CloakBrowser & Camoufox with one-click
  install commands. Reduced-motion respected.

### Changed
- **Geolocation now agrees with the proxy.** Launches set
  `navigator.geolocation` to coordinates for the proxy's country (or the
  locale's, without a proxy) and pre-grant the permission, so a site that asks
  gets coordinates that match the exit IP instead of a US timezone with German
  GPS. New `devices.COUNTRY_GEO` / `LOCALE_TO_COUNTRY`.
- **WebRTC IP handling is enforced at launch.** With a proxy, non-proxied UDP is
  disabled (`disable_non_proxied_udp`) so WebRTC can't bypass it; without one,
  only the public interface is exposed so local IPs stay hidden.
- **Hardened the stealth script**: `navigator.webdriver` now reads `false` from the
  prototype (not an own property), `window.chrome`, realistic `navigator.plugins`/
  `mimeTypes` (native `PluginArray`), consistent `permissions.query`, and native
  `toString()` on all patched functions — passing BrowserScan's basic checks.
- `launcher.py` is now a thin dispatcher over `drivers.py`.

### Fixed
- **Canvas and audio noise are now stable across reads.** Both drew from a single
  advancing PRNG and mutated the caller's canvas/buffer in place, so reading the
  same canvas twice gave different bytes — itself a detection signal (CreepJS
  checks for exactly this). Each source now restarts from the profile seed and
  works on a copy.
- **`enumerateDevices` spoofing actually applies.** It was building device objects
  with `Object.assign` against getter-only `MediaDeviceInfo` properties, which
  threw and silently fell back to Chromium's real list. Found by the new trust
  checker.
- **Startup URLs are now opened** on launch (first in the main tab, the rest in
  new tabs) instead of always landing on `about:blank`.
- **Launch button no longer sticks on "running"** after you close the browser
  yourself — the dashboard polls run status in live mode and flips back to start.
- **"Last active" now updates** (server records when a session ends and shows a
  relative time) instead of always reading "never".
- **New profiles no longer overwrite an existing one** — the server assigns each
  profile a unique id, and the local id generator is collision-resistant.
- Suppressed Chromium's infobars: the "controlled by automated test software"
  bar (Playwright) and the cosmetic "--no-sandbox unsupported flag" bar
  (CloakBrowser, via `--test-type` — invisible to websites).
- `persona launch --headless` no longer hangs forever waiting for a window that
  never opens.

## [0.1.0] - 2025

### Added
- **Engine**: coherent fingerprint generator (device-archetype approach) with
  `validate()`; `Fingerprint`/`Proxy`/`Profile` models; JSON-per-profile store
  with import/export and persistent user-data dirs; stealth init-script
  generator; Playwright launcher with proxy support; full CLI.
- **Dashboard**: React web console with profile grid, tabbed fingerprint editor,
  live coherence meter, proxy manager, bulk create, folders, tags, search.
- Monorepo layout, CI, docs, and contribution guides.
