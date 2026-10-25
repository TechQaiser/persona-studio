# Changelog

Format based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

## [0.2.0] - 2026-10-25

### Added
- **Windows app** (`packaging/PersonaStudio.spec`, `persona/app.py`): one
  `PersonaStudio.exe` that runs the engine and serves the built dashboard on
  http://localhost:8787, with no Python or Node needed. It downloads Chromium on
  first run and bundles Playwright, Patchright and CloakBrowser. With arguments
  it acts as the `persona` CLI. `persona serve --dashboard dashboard/dist` does
  the same from source. Version is now 0.2.0.

### Fixed
- A profile created through the API or an import without `tags` blanked the
  whole dashboard. The server now fills in missing fields, and the list
  tolerates old records.

### Security
- **Local API locked down.** `persona serve` used to accept CORS from any origin
  without auth, so any web page open in the user's browser could launch profiles
  or read their cookies through `localhost:8787`. It now requires a per-start
  `X-Persona-Token` (written to `<data-dir>/api-token`, given via `/api/token`
  only to the dashboard's origins). CORS is restricted to the dashboard, and
  non-loopback `Host` headers are rejected to block DNS rebinding.
  `/api/health` stays open. The dashboard picks up the token automatically.

- **DNS lockdown at launch.** With a proxy, Chromium engines now start with
  `--host-resolver-rules="MAP * ~NOTFOUND, EXCLUDE <proxy host>, EXCLUDE localhost"`,
  so prefetching, WebRTC STUN names and the like can't ask the real ISP's
  resolver. Before, DNS leaks were only *detected* (`persona dns`), never prevented.

### Fixed
- **GPU strings no real Chrome reports.** The dashboard's GPU picker used short
  labels (`ANGLE (NVIDIA GeForce RTX 3060 Direct3D11)`) and sent them to the
  browser as-is, while real Chrome reports `ANGLE (NVIDIA, NVIDIA GeForce RTX
  3060 Direct3D11 vs_5_0 ps_5_0, D3D11)`. The picker now offers the exact
  strings, and profiles saved with an old label are upgraded on launch. Picking
  a GPU or switching OS also updates the WebGL vendor to match.
- **macOS GPUs are Metal now.** Chrome on macOS renders WebGL through ANGLE's
  Metal backend, so it reports `ANGLE (Apple, ANGLE Metal Renderer: Apple M1,
  Unspecified Version)`. New macOS profiles use those strings, old OpenGL 4.1
  ones are upgraded, and the coherence check accepts Metal on macOS only.
- Dashboard: new and bulk-created profiles start on Chrome 148–151 like the
  engine, instead of 125–128.
- **Same device on every launch (Camoufox).** Camoufox salted each launch
  randomly, so a profile came up as a new device every session (a different
  screen each time in testing). Each profile's Camoufox fingerprint is now
  generated once and pinned in its user-data dir
  (`.persona-camoufox-fingerprint.json`). Backup/restore carries the pin along,
  and "duplicate as template" gets a fresh one. Canvas still varies per session
  there, because Firefox's own baseline fingerprinting protection does that for
  every real Firefox user.
- **CloakBrowser presents Persona's fingerprint.** Hardware cores, RAM, screen,
  GPU vendor/renderer and platform are now passed as `--fingerprint-*` flags, and
  the seed comes from the profile (a profile Cloak already opened keeps its
  existing seed). The UA is no longer forced, so UA and Client Hints both come
  from the binary and agree. Before, Cloak showed `Chrome/128` in the UA but 146
  in `sec-ch-ua`.
- **`navigator.deviceMemory` was impossible.** Profiles reported raw RAM (16, 32,
  6, 12); Chrome only ever reports a power of two capped at 8. Fixed in the
  stealth script, Cloak flags, the trust check and auto-adjust.
- **Chrome version follows the engine.** At launch, a profile's UA moves to the
  engine's real Chromium major (Playwright 151, Cloak 146 today) and the
  dashboard copy follows. A UA older than the engine is caught by feature
  detection. Default versions for new profiles moved from 125–128 to 148–151.
- **`navigator.userAgentData` on Playwright/Patchright** reported
  `HeadlessChrome`/`Chromium` with no "Google Chrome", which contradicted the UA
  and `sec-ch-ua`. Now set through CDP `Emulation.setUserAgentOverride` with full
  metadata (brands, full version, platform version, architecture, model), so JS
  and every Client Hints header agree.
- Dashboard: `api.health` was defined twice, so the startup liveness probe was
  actually calling `/api/profiles/health`. The probe is now `api.ping()`.

### Added
- **Active session lock** (`persona/locks.py`). A profile can only be open in one
  live process. Opening it twice is the "same account, two devices at once"
  signal, and two browsers writing one user-data dir corrupt it. The lock is a
  file in the profile's user-data dir naming its process, taken atomically by
  every launch path (dashboard, `persona launch`, attach, warm-up, cookie and
  trust tools). A lock left by a crashed process is detected and taken over.
  The dashboard now shows a profile opened from a terminal as running, and
  refuses to open its session. `persona unlock <profile>` clears a lock by hand.
- **Profile history** (`persona/history.py`). When a session ends (launch,
  warm-up, automation), the caches the browser rebuilds by itself (HTTP cache,
  code cache, GPU shader caches) are deleted, and the rest of the session is
  saved as a zipped snapshot. The last 5 are kept (`history_keep` in Settings
  or `PUT /api/config`, 0 turns it off). An unchanged session isn't saved twice.
  Restore rolls cookies and site data back, and snapshots the current state
  first so a restore can be undone. In the dashboard: editor **Session** tab →
  *Session history*. From the CLI: `persona history <profile>`, with
  `--snapshot` or `--restore <id>`. API: `GET/POST /api/profiles/{id}/history`,
  `POST …/history/{snapshot}/restore`.
- Backups leave out those same caches and the browser's lock files, so they're
  much smaller.
- **Per-profile storage toggles** (editor **Advanced** → *Keep between
  sessions*, `persona storage <profile> --off history passwords`). Local
  storage, IndexedDB, history, saved passwords, open tabs, bookmarks and Web
  Store extensions can each be switched off. Switched-off data is cleared when
  the browser closes (and before the next launch, in case it crashed), so it
  never builds up or lands in snapshots and backups. Works for Chromium engines
  and Camoufox. Cookies are always kept.
- **WebGL capability table** (`persona/webgl.py`). Fingerprinters read the
  whole WebGL table (limits, extensions, shader precision), not just the GPU
  name. The trust check now reads it and verifies two things. First, that the
  limits fit the GPU's graphics API: Chrome's Direct3D 11 backend has a unique
  signature (32767 viewport, 4095 vertex and 1024 fragment uniform vectors,
  measured on Chrome 151), so a profile claiming an Apple GPU on a Windows PC,
  or a Windows GPU on SwiftShader, is caught. Second, that it's the same device
  as before: the first reading is stored with the profile, and a later change
  is flagged. Auto-adjust re-baselines it, `validate()` and the dashboard's
  coherence meter flag a recorded table that no longer fits the chosen GPU.
  The table is read, never faked: a JS patch can't make the GPU honour limits
  it doesn't have.
- **Headless sessions use the real GPU** (`--enable-gpu` on Playwright and
  Patchright). Headless Chrome otherwise renders WebGL in software
  (SwiftShader), a known headless tell that also contradicts the claimed GPU.
  This affects trust checks, warm-ups and headless automation.
- **Launch-flag denylist, with reasons.** Extra launch flags that would change
  the identity behind Persona's back are now ignored too: `--user-agent`,
  `--lang`, `--window-size` (it has to agree with the spoofed screen),
  `--force-device-scale-factor`, `--use-angle`/`--use-gl` (GPU backend),
  `--webrtc-ip-handling-policy`, `--no-sandbox`, `--headless`, and CloakBrowser's
  identity flags (`--fingerprint-gpu-renderer` and friends; `--fingerprint-noise`
  stays allowed). Each ignored flag now says why, both in launch warnings and
  live under the field in the editor. A flag must look like a flag
  (`--name` or `--name=value`).
- **Languages from the exit IP** (opt-in per profile: editor **Proxy** tab →
  *Languages follow the exit IP*, or `persona edit <profile> --auto-lang on`).
  Each launch sets `navigator.languages`, the locale and the Accept-Language
  header from the proxy's exit country, in the shape real non-English users
  have: `de-DE, de, en-US, en`. 70 countries are mapped (English where it's the
  usual browser language, e.g. India, Pakistan, Nigeria). The trust check
  expects the launch languages and auto-adjust doesn't write them back. Off by
  default, because moving an existing account to a new language is a signal of
  its own.
- **SOCKS4 proxies** work on every engine and in the pool's health check. They
  go through the local bridge, spoken as SOCKS4a so hostnames resolve at the
  proxy (no DNS leak). The dashboard was quietly saving SOCKS4 as HTTP; it's
  now a proxy type of its own.
- **Change-IP URL** for rotating and mobile proxies. Save the vendor's
  rotation URL on a proxy, then press **Change IP** in the editor (or
  `persona proxy change-ip <profile>`, `POST /api/profiles/{id}/proxy/change-ip`,
  `POST /api/proxies/{id}/change-ip`). The next launch re-reads the new exit
  IP's timezone and location. Assigning a pool proxy carries its URL along.
- **Paste a proxy in any format.** The editor's Proxy tab fills itself in from
  a pasted `host:port:user:pass`, `user:pass@host:port` or
  `socks5://user:pass@host:port`, and `persona create/edit --proxy` accept the
  same formats.
- **Launch lifecycle.** The exit-IP lookup now starts first and runs while the
  engine starts, so a proxied launch takes about as long as the slower of the
  two, not both. Each driver marks the launch *ready* in the session lock once
  its window exists (`ready` in the API). The dashboard logs a slow start after
  60 s and stops a launch that isn't up after 5 minutes, with a clear error,
  instead of the profile showing as running forever.
- **No more orphaned browsers** (`persona/procs.py`). Stopping a profile on
  Windows used to end only the launcher, leaving Chrome running and holding the
  profile folder, so the next launch failed with "profile in use". Browser
  processes are now found by the profile directory on their command line and
  ended on stop, and any left over from a crash are ended before the next launch.
- **devicePixelRatio as part of the device.** Macs are 2, phones carry their
  panel's exact ratio (Pixel 7 2.625, Galaxy S21 3, …), and Windows 1536x864 is
  1.25 (a 1920x1080 laptop at 125%). Before, every desktop was 1, so every macOS
  profile was a tell. `validate()` flags impossible ratios, and the trust check
  and auto-adjust read the real one. Old profiles derive it automatically.
  Deliberately *not* GoLogin's "+0.00000001" trick: a real Retina Mac reports
  exactly 2.
- **Timezone + geolocation from the proxy's exit IP** (`persona/geo.py`). At
  launch the exit IP is looked up *through the proxy*, and the browser presents
  that IP's timezone and city. Rotating/residential pools no longer contradict
  the stored zone. Geolocation is a per-profile spot within a few km of the city,
  stable across launches. Before, every profile in a country reported the same
  capital-city coordinate. Falls back to the stored values if the lookup fails.
  The trust check expects the launch timezone, and auto-adjust won't rewrite an
  account's locale to follow it. Cloak also gets the resolved IP for WebRTC.
- **SOCKS5 proxies with username/password** (`persona/bridge.py`). Chromium can't
  authenticate to SOCKS5 (launch failed with "Browser does not support socks5
  proxy authentication"). A loopback HTTP bridge now carries the credentials,
  hands hostnames to the proxy unresolved (no local DNS), and is shared per
  upstream. The proxy pool's health check now tests SOCKS5 through it too.
- **Engine/machine warnings** (`launch_warnings`): a profile whose OS differs
  from this machine on Playwright/Patchright gets a warning, because text renders
  with the machine's real fonts and no JS patch hides that. Cloak warns for
  Linux/Android profiles (it can only present Windows/macOS) and for macOS
  profiles off a Mac (needs Mac fonts and a HiDPI screen). Shown at
  `persona launch`, on the Health page, and from `/api/fingerprint/validate`.
- **Per-profile extra launch flags** (`launch_args` / dashboard "Extra launch
  flags"). Flags Persona manages itself (proxy, user-data dir, DNS lockdown,
  debugging port, extensions, Cloak seed) are dropped with a warning instead of
  silently undoing a guarantee.

## Earlier in the 0.2.0 cycle

### Added
- **Mobile (Android) profiles**: fingerprint generation now assembles a whole
  handset — the model in the User-Agent (`Pixel 7`, `SM-G991B`, …), the Android
  version, the GPU, screen and RAM all describe one real phone rather than mixed
  parts. Launch adds touch support and a phone device-scale factor. Android was
  already selectable in the dashboard; it's now coherent end-to-end.
- **Session health** (`persona session <ref>` / `POST /api/profiles/{id}/session`):
  reads the profile's real cookie jar and reports how many cookies are expired or
  expiring within a week, and which services still have a live login (Facebook,
  Instagram, Google, X, LinkedIn, …). Surfaced as a badge and per-row check on the
  **Health** page, and a **Session** tab in the profile editor. Cached as
  `_session` so the Health grid shows it without re-opening every profile;
  stale / expiring sessions now count toward "needs attention".
- **Duplicate as template** (`POST /api/profiles/{id}/duplicate`, the ⧉ card
  action): clones a profile's settings (proxy, folder, tags, notes, engine,
  startup URLs, OS + locale) but re-rolls the fingerprint, so the copy is a
  genuinely different device instead of a fingerprint twin that a site could link
  back to the original.
- **Per-profile activity log** (`GET /api/profiles/{id}/activity`, editor
  **Session** tab): records launches, session ends, warm-ups, trust runs,
  auto-adjusts, cookie imports and session checks as a timeline.
- **Folders manager** (dashboard **Folders** tab): create, rename and delete
  folders, each shown as a card with live profile / running / coherent counts and
  one-click open. Folders are persisted server-side (`GET /api/config` →
  `folders`, plus `POST /api/folders`, `…/folders/rename`, `…/folders/delete`), so
  an empty folder survives a reload; renaming or deleting one moves the profiles
  inside it (delete reassigns to *Unfiled*) rather than dropping anything. The
  editor, bulk-edit and sidebar dropdowns now read this live list.
- **Settings page** (dashboard **Settings** tab): theme toggle, the default launch
  engine for new profiles (persisted via `PUT /api/config`, with an "not
  installed" hint per engine), the on-disk storage location and a data summary
  (profiles / folders / proxies), and an about card. `GET /api/config` now also
  returns `root` and `version`.
- **Command palette** (dashboard, ⌘K / Ctrl-K): fuzzy-search across views,
  actions (new profile, toggle theme) and every profile (open / launch / stop),
  driven entirely from the keyboard (↑/↓/Enter, Esc to close).
- **Light / dark theme** (dashboard): a Sun/Moon toggle in the top bar switches
  the whole app between a new light theme and the original dark one; the choice
  is remembered in `localStorage`. The palette repaints inline styles, icons and
  the full stylesheet in one pass.
- **Toast notifications** (dashboard): success / error / info actions now surface
  as stacked, auto-dismissing toasts instead of blocking `alert()` popups.
- **Headless attach** (`persona attach --headless`, `POST …/attach {headless}`):
  attach a profile's DevTools endpoint without opening a visible window — for
  servers and CI. Exposed as a checkbox on the Automation page.

### Fixed
- **Auto-adjust capped at grade B** — `align` matched everything to the browser
  *except the timezone*, so on an engine that shows the host clock (e.g.
  CloakBrowser) the "timezone matches" check stayed failed forever, holding the
  grade at B (15/16). Align now follows the machine's real timezone and moves
  the locale to the coherent one for that zone (e.g. `Asia/Karachi` → `en-PK`),
  so a fully-aligned profile can reach A. Only moves the timezone when a locale
  models it, so coherence never regresses.
- Coherence's language check now compares the **base** language (`en`), not the
  region (`en-US` vs `en-PK`): an English browser in a Karachi timezone is a
  real, coherent user and shouldn't be flagged. A genuine mismatch (`de` vs
  `en`) is still caught.

### Changed
- Automation attach now reports success as a toast (with the port and whether it
  came up headless).

### Added (earlier this cycle)
- **Automation page** (dashboard, `POST /api/profiles/{id}/attach`): the engine
  already spoke CDP (`persona attach`) — now the dashboard drives it. One click
  opens a profile with a DevTools endpoint and hands back the connection details
  with ready-to-paste **Playwright / Puppeteer / Selenium** snippets (copy
  buttons, language tabs), so your script attaches to the *same* spoofed,
  warmed-up window instead of launching a fresh un-spoofed one. Detach = stop.
  Chromium engines only (cloak / patchright / playwright); the endpoint rejects
  Firefox-based camoufox with a clear message.
- **Fingerprint collision detector** (`persona collisions`, `collision.py`,
  `GET /api/profiles/collisions`): finds profiles that present the *same*
  fingerprint — identical WebGL, screen, hardware and user-agent read as one
  device wearing two hats, so a site can link the accounts and ban them
  together. Pure logic over the stored profiles (no browser), flagged on the
  dashboard **Health** page with a "Shared FP" count and a per-row badge, plus a
  CLI table. `identical` marks the worst case (same canvas/audio seed too).
- **Backup & restore** (`persona backup` / `persona restore`,
  `ProfileStore.backup`/`restore`): zip a profile **and its whole browser
  session** (cookies, localStorage — everything under user-data) into one
  portable file to archive it or move it to another machine. `restore --new-id`
  brings it in as a fresh copy instead of overwriting the original. (Unlike
  `export`/`import`, which move only the config.)
- **Bulk grid actions & tag filtering** (dashboard): the multi-select bar now
  also **warms up** and **exports** the selected profiles in one go (alongside
  the existing launch / edit-all / delete); the filter popover gained a **Tag**
  filter, and tags shown on a profile are clickable to filter by them.
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
