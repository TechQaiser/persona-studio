<div align="center">

# Persona

### Open-source, self-hosted anti-detect browser & profile manager

Create browser profiles that each look like a real, separate device — a
*coherent* fingerprint, its own proxy, and a persistent session — then manage
and launch them from a clean web console or CLI.

A self-hosted alternative to GoLogin, Multilogin and AdsPower.

![python](https://img.shields.io/badge/python-3.9%2B-blue)
![react](https://img.shields.io/badge/react-18-61DAFB)
![license](https://img.shields.io/badge/license-MIT-green)
![tests](https://img.shields.io/badge/tests-passing-brightgreen)
![status](https://img.shields.io/badge/status-beta-orange)

<br>

![Persona Studio dashboard](docs/screenshot-dashboard.png)

</div>

---

## What's new: 25 Oct 2026

- **Locked-down local API.** `persona serve` now needs a per-start token, only
  accepts CORS from the dashboard and rejects DNS-rebinding `Host` headers, so
  other web pages can't launch profiles or read cookies through `localhost`.
- **No DNS leaks behind a proxy.** Chromium engines start with resolver rules
  that send every lookup through the proxy instead of your ISP.
- **Timezone and geolocation from the proxy's exit IP.** Rotating and
  residential proxies no longer contradict the profile's stored zone.
- **SOCKS5 proxies with username/password** work in Chromium engines through
  a local bridge.
- **Same device on every launch.** Camoufox profiles keep a pinned fingerprint,
  and CloakBrowser now presents Persona's cores, RAM, screen, GPU and platform.
- **More realistic devices.** `navigator.deviceMemory` is capped like real
  Chrome, the UA follows the engine's real Chrome version, Client Hints match
  the UA, and `devicePixelRatio` fits the device (Retina Macs, exact phone
  ratios).
- **Launch warnings** when a profile's OS can't be presented faithfully on this
  machine or engine, plus **per-profile extra launch flags**.
- **One profile, one browser.** An active-session lock stops a profile from
  being opened twice, from the dashboard, a terminal or the scheduler.
- **Profile history.** Each session end saves a snapshot (last 5 kept), and
  you can roll a profile back from the editor's Session tab. Browser caches
  are pruned on close, so snapshots and backups stay small.
- **Choose what each profile keeps:** local storage, IndexedDB, history,
  passwords, open tabs, bookmarks and extensions can each be cleared on close.
- **Real WebGL checks.** The trust check reads the full WebGL table (limits,
  extensions, shader precision) and flags a GPU name the limits contradict, or
  a GPU that changed since last time. Headless sessions now use the real GPU
  instead of software rendering.
- **Exact GPU strings.** The dashboard now sends the renderer strings real
  Chrome reports (Metal on macOS), and upgrades profiles saved with old labels.
- **Languages from the exit IP** (opt-in), **SOCKS4**, a **Change IP** button
  for rotating proxies, and **paste a proxy in any format**.
- **Sturdier launches:** the proxy lookup overlaps engine startup, a launch
  that never comes up is stopped after 5 minutes, and browsers left running
  after a stop or crash are cleaned up.

Full details in the [CHANGELOG](CHANGELOG.md#2026-10-25).

---

## Why Persona?

Most fingerprint tools randomise each value on its own — and that's exactly what
gets them caught. Anti-bot systems don't read values in isolation; they
**cross-check** them. A macOS user-agent with an NVIDIA GPU, or a 4-core phone
claiming a 1440p screen, is an instant tell.

Persona's core idea is **coherence**. It picks a realistic device archetype
first, then draws *every* value (OS, user-agent, GPU, screen, CPU, RAM, timezone,
language) from that archetype's real-world pool. The result is an identity whose
parts all agree — and a live coherence check that proves it, both in the engine
(`validate()`) and in the dashboard's real-time meter.

That coherence-first design is the thing commercial tools don't surface, and it's
what makes Persona distinctive.

## Persona vs the commercial tools

|  | **Persona** | Multilogin | GoLogin | AdsPower |
|---|:---:|:---:|:---:|:---:|
| **Price** | **Free** | from ~$99/mo | from ~$49/mo | free tier + paid |
| **Open source** | ✅ MIT | ❌ | ❌ | ❌ |
| **Self-hosted — data never leaves your machine** | ✅ | ❌ cloud | ❌ cloud | ❌ cloud |
| **Live coherence meter** (proves the fingerprint agrees with itself) | ✅ | ❌ | ❌ | ❌ |
| **Trust checker** — grades the *real* browser, not the config | ✅ | ❌ | ❌ | ❌ |
| **Patched-binary stealth engine** | ✅ Cloak / Camoufox | ✅ | ⚠️ | ✅ |
| **Proxy pool + leak/DNS/TLS tests** | ✅ | partial | partial | partial |
| **CLI + Python API** | ✅ | ❌ | limited | limited |
| **Cloud team sync** | ❌ *(local-first by design)* | ✅ | ✅ | ✅ |

<sub>Pricing and feature comparison are approximate and based on each vendor's public plans at the time of writing — check their sites for current details. Persona doesn't do hosted team sync on purpose (see the roadmap); everything else is local and free.</sub>

## What's in the box

Persona is a monorepo with two parts that work together:

```
persona-studio/
├── engine/        Python core — fingerprints, storage, launcher, CLI
├── dashboard/     React web console — the visual profile manager
└── start.bat      Windows one-click launcher (installs + starts both)
```

| | |
|---|---|
| 🧬 **Coherent fingerprints** | OS, UA, GPU, screen, hardware, timezone & language always agree |
| 🛡️ **Live coherence meter** | Real-time consistency score as you edit — nobody else shows this |
| 🌐 **Proxy-aware** | Set a proxy's country and locale/timezone auto-align to it |
| 🎛️ **Rich editor** | Canvas, WebRTC, audio, fonts, geolocation, media devices, DNT |
| 💾 **Persistent sessions** | Cookies & localStorage survive between launches |
| 🍪 **Cookie import/export** | Move a logged-in session in or out — Cookie-Editor JSON, Playwright state, or `cookies.txt` |
| 🔎 **Trust checker** | Grades the *real* browser against the checks a fingerprinter runs |
| ✨ **Auto-adjust** | One click aligns a profile to what its browser actually presents — grade jumps to A |
| 📡 **Proxy & leak test** | Exit IP, country and timezone match + WebRTC leak detection |
| 🌐 **DNS leak check** | Confirms name lookups exit through the proxy, not your real ISP's resolver |
| 🌐 **Proxy pool** | Import, health-check and assign proxies round-robin across profiles |
| 📌 **Same device every launch** | Each profile's engine identity is pinned, so a logged-in account never sees its device change |
| 📍 **Exit-IP geo** | Timezone and city-level geolocation come from the proxy's *real* exit IP at every launch |
| 🧱 **DNS lockdown** | With a proxy, nothing is resolved by your own DNS, so there's nothing to leak |
| 🧦 **Authenticated SOCKS5** | `socks5://user:pass@host` works through a local bridge (Chromium can't do this natively) |
| 🔐 **TLS/JA3 check** | Reads the handshake fingerprint — the one layer JS injection can't reach |
| ❤️ **Health overview** | One page: coherence, proxy, trust grade and warm-up schedule per profile |
| 🔑 **Encrypted vault** | Proxy passwords encrypted at rest behind a master password |
| 🧩 **Extensions** | Per-profile unpacked extensions, isolated from every other profile |
| ✨ **Warm-up + schedule** | Human-paced browsing (per-vertical presets) so a fresh profile isn't obviously fresh — and a recurring schedule so it never goes cold |
| 🤖 **Automation attach** | Drive a live profile from Selenium, Puppeteer or Playwright over CDP |
| 🔁 **Bulk edit** | One change applied to hundreds of profiles, coherently |
| 📥 **Migrate in** | Import profiles from GoLogin, AdsPower or Multilogin exports |
| 📦 **Bulk create at scale** | Generate thousands of coherent profiles — mixed OS, country, browser, per-profile hardware |
| 🗂️ **Folders, tags, search** | Organize hundreds of accounts |
| 🖥️ **Real browser** | Launches a real browser, per-profile isolation |
| 🔌 **Pluggable engines** | Swap the stealth backend: CloakBrowser, Camoufox, Patchright, Playwright |
| 🔗 **Startup URLs** | Each profile opens the pages you want, in its own tabs |
| 🖱️ **One-click launcher** | `start.bat` installs everything and starts both halves on Windows |
| ⌨️ **CLI + Python API** | Script it or drive it by hand |

## Quick start

**Prerequisites:** [Python 3.9+](https://www.python.org/downloads/) and (for the
dashboard) [Node.js 18+](https://nodejs.org/). Check with `python --version` and
`node --version`.

```bash
git clone https://github.com/TechQaiser/persona-studio.git
cd persona-studio
```

### Easiest (Windows): one-click launcher

Double-click **`start.bat`** in the project folder. On first run it installs
everything, lets you pick the default browser engine (CloakBrowser first), then
starts the engine API + dashboard and opens the console in your browser. Two
terminal windows stay open while it runs — close them to stop. To re-run setup,
delete `.persona_setup_done`.

The engine you pick "wins": it becomes the default for every new profile you
create afterwards, from the batch menu, the CLI, or the dashboard. Change it any
time with `persona default-engine cloak`.

Prefer to do it by hand, or on macOS/Linux? Follow the manual steps below —
the two parts are independent, so you can run the engine, the dashboard, or both.

### 1. Engine (backend)

```bash
cd engine
pip install -e ".[launch]"      # omit [launch] to skip Playwright
playwright install chromium     # downloads the browser (needed for `launch`)

persona create acct-01 --os windows --locale en-US
persona launch acct-01          # opens a Chromium window; close it to exit
```

> **Windows / PowerShell:** keep the quotes around `".[launch]"` exactly as
> shown — without them the shell mis-reads the brackets.
>
> **`persona` not recognized?** The install worked but its Scripts folder isn't
> on your PATH. Either reopen your terminal, or run it as a module instead:
> `python -m persona create acct-01 --os windows --locale en-US`.

### 2. Dashboard (frontend)

```bash
cd dashboard
npm install
npm run dev                      # then open http://localhost:5173
```

> The dashboard runs on its own with in-memory **sample data**, so you can
> explore it without the engine (the footer shows *Demo mode*).

### 3. Connect them (launch real browsers from the dashboard)

Start the engine's API, then reload the dashboard — its footer flips to
*Engine online* and the launch (▶) button now opens a **real Chromium window**,
with profiles saved to disk.

```bash
cd engine
pip install -e ".[api,launch]"
playwright install chromium
persona serve                    # HTTP API on http://localhost:8787
```

Leave `persona serve` running and start the dashboard (`npm run dev`) in a second
terminal. That's it — clicking ▶ launches the profile for real.

Full details live in each part's README:
[engine/README.md](engine/README.md) · [dashboard/README.md](dashboard/README.md).

## How it works

```
             ┌──────────────┐
   pick OS → │  archetype   │   curated real-world combos (engine/persona/devices.py)
             └──────┬───────┘
                    │  every value drawn from this archetype's pool
                    ▼
             ┌──────────────┐        ┌──────────────┐
             │ Fingerprint  │───────▶│  validate()  │   coherence gate
             └──────┬───────┘        └──────────────┘
                    │
        ┌───────────┴────────────┐
        ▼                        ▼
  context options          stealth.js init script
  (UA, viewport, locale,   (navigator.platform, WebGL,
   timezone, proxy, CH)     hardwareConcurrency, webdriver, canvas noise)
        └───────────┬────────────┘
                    ▼
          Chromium (persistent context per profile)
```

See [docs/architecture.md](docs/architecture.md) for the full walkthrough,
including how to connect the dashboard to the engine.

## Manager + pluggable engines

Persona's job is to be the **manager** — coherent identities, proxies, sessions,
folders, and a dashboard. The actual stealth browser is a **pluggable engine** you
choose per profile:

| Engine | Strength | Notes |
|---|---|---|
| `cloak` ⭐ | Patched Chromium binary | **Recommended.** CloakBrowser — C++-level fingerprint/TLS/CDP patches; reaches Cloudflare/DataDome/reCAPTCHA-v3-grade evasion. |
| `camoufox` ⭐ | Patched Firefox (C++-level) | **Recommended.** Among the strongest open options; brings its own coherent fingerprint, pinned per profile by Persona. |
| `patchright` | Runtime-patched Playwright | Drop-in; fixes `webdriver`/CDP leaks the stock engine can't. |
| `playwright` | Built-in, always available | Stock Chromium + injected stealth script. Passes basic bot tests (BrowserScan, sannysoft); can't beat TLS/CDP-level detection. |

```bash
persona engines                          # see what's installed + which is default
persona create acct-01 --engine cloak    # pick a backend per profile
persona default-engine cloak             # set the default for new profiles
```

CloakBrowser is the default out of the box. The last engine you choose anywhere
becomes the default for the next profile you create.

Being honest about limits: pure JavaScript injection (the `playwright` engine)
has a ceiling — for Cloudflare / DataDome / reCAPTCHA-v3-grade evasion, pair a
runtime-patched engine with a residential proxy and a warmed-up session. Persona
stays the same manager over all of them.

## What happens at launch

A coherent fingerprint on paper isn't enough. What matters is what the site
*actually sees* when the browser opens. Every launch applies these, and each
one was checked against a real browser, not only in unit tests:

| Protection | What it fixes |
|---|---|
| **Pinned identity** | Camoufox would otherwise generate a new device on every launch, and Cloak picks its own seed. Each profile's engine fingerprint is created once and kept in its user-data dir (`.persona-camoufox-fingerprint.json`, `.cloakbrowser-seed`). A backup/restore keeps the device; "duplicate as template" gets a new one. |
| **Persona's values reach Cloak** | Cores, RAM, screen, GPU vendor/renderer and platform are passed as `--fingerprint-*` flags, so the Coherence meter grades what the site sees. |
| **Real Chrome version** | The UA moves to the engine's real Chromium major (e.g. Playwright 151, Cloak 146), and the dashboard follows. A UA older than the engine gets caught by feature detection. |
| **`userAgentData` + Client Hints** | On Playwright/Patchright the full UA metadata is set through CDP, so `navigator.userAgentData`, `sec-ch-ua*` headers and the UA all agree. Without it, `HeadlessChrome` would show through. |
| **`devicePixelRatio`** | Part of the device: Macs are 2, phones use their panel's exact ratio, Windows 1536x864 is 1.25. A Mac at 1 is an instant tell. |
| **`deviceMemory`** | Reported the way Chrome does it (a power of two, max 8). A raw "16" is a value no real Chrome produces. |
| **Exit-IP timezone + geolocation** | The proxy's exit IP is looked up *through the proxy*, and the browser uses that IP's timezone and city. Each profile gets its own nearby spot, stable across launches, instead of every profile sharing one capital-city point. If the lookup fails, the stored values are used. |
| **DNS lockdown** | `--host-resolver-rules="MAP * ~NOTFOUND, EXCLUDE <proxy>, EXCLUDE localhost"`: no local DNS lookups, so prefetch or WebRTC STUN can't reach your ISP's resolver. `persona dns` verifies it from the outside. |
| **WebRTC** | Real IP never exposed. On Cloak the ICE candidate is rewritten to the proxy's exit IP. |
| **SOCKS5 with auth** | A loopback bridge holds the credentials and passes hostnames to the proxy unresolved. The proxy pool's health check uses it too. |
| **Engine/machine warnings** | No JS patch can change the fonts your machine really has. A profile whose OS differs from this machine on Playwright/Patchright, a Linux/Android profile on Cloak, or a macOS profile on Cloak off a Mac gets a warning at `persona launch` and on the Health page. |
| **Extra launch flags** | Per profile (dashboard → editor → *Extra launch flags*). Flags Persona manages itself (proxy, user-data dir, DNS lockdown, debugging port, extensions, Cloak seed) are ignored with a warning instead of silently undoing a protection. |

**Engine coverage**

| | `cloak` | `camoufox` | `patchright` / `playwright` |
|---|:---:|:---:|:---:|
| Pinned identity across launches | ✅ | ✅ | ✅ (seeded stealth script) |
| Persona's hardware/GPU/screen presented | ✅ | its own (Firefox) | ✅ |
| Chrome version synced to engine | ✅ | n/a (Firefox) | ✅ |
| Exit-IP timezone + geolocation | ✅ | ✅ (its own geoip) | ✅ |
| DNS lockdown | ✅ | Firefox proxies DNS | ✅ |
| Authenticated SOCKS5 | ✅ via bridge | ✅ via bridge | ✅ via bridge |
| Real-OS font rendering | Windows/macOS personas | ✅ | ❌ host fonts (warned) |

**Known limits**

- Cloak in a visible window takes `devicePixelRatio` from the real screen, so a
  macOS profile needs a HiDPI display (and the Mac fonts installed). The trust
  check flags a mismatch; headless launches are emulated correctly.
- Camoufox profiles still show a Chrome-style fingerprint in the dashboard,
  while the site sees Camoufox's own pinned Firefox fingerprint.
- Camoufox's canvas changes per session. Firefox's built-in fingerprinting
  protection does that for every real Firefox user, so Persona leaves it as is.
- SOCKS4 proxies aren't supported yet.
- The exit-IP lookup calls a public echo service (ipwho.is / ipapi.co)
  *through the proxy*. Your real IP isn't exposed, but launch takes about a
  second longer.

## Local API security

`persona serve` listens on `127.0.0.1` only. Any web page open in your browser
can reach localhost, so the API also requires a per-start token, which the
dashboard picks up automatically. CORS only allows the dashboard's own origin,
and requests with a non-loopback `Host` header are refused (this blocks DNS
rebinding). Scripts read the token from `~/.persona/api-token`. See
[engine/README.md](engine/README.md#http-api) for details and the environment
variables to extend it.

## Roadmap

**Built**

- [x] Coherent fingerprint engine + `validate()`
- [x] Profile storage, import/export, persistent sessions
- [x] Playwright launcher with proxy support
- [x] Full CLI
- [x] Web dashboard: profile grid, fingerprint editor, coherence meter, bulk create, proxies
- [x] HTTP API (`persona serve`) connecting the dashboard to the engine — launch real browsers from the UI
- [x] Pluggable launch engines (CloakBrowser, Camoufox, Patchright, Playwright)
- [x] Persisted default engine + one-click Windows launcher (`start.bat`)
- [x] Per-profile startup URLs
- [x] Cookie import/export (CLI, API, dashboard) — Cookie-Editor JSON,
      Playwright storage state, Netscape `cookies.txt`

- [x] Account warm-up — human-paced browsing that ages a fresh profile
- [x] Local automation API — `persona attach` opens CDP for Selenium/Puppeteer/Playwright,
      plus a dashboard **Automation** page (one-click attach + copy-paste connect snippets)
- [x] Multi-profile synchronizer — `persona apply`, plus "Edit all" in the dashboard
- [x] Proxy tester + WebRTC leak checker (`persona proxy test`)
- [x] Fingerprint trust checker (`persona trust`) — grades the real browser, not the config
- [x] Extensions manager, plus fonts, media devices, ClientRects & audio noise

- [x] TLS/JA3 handshake checker (`persona tls`) — the pre-JS network layer
- [x] Encrypted secrets at rest (`persona vault`) — proxy passwords, master-password
- [x] Geolocation aligned to the proxy country + WebRTC IP-handling enforced at launch

- [x] Import from GoLogin / AdsPower / Multilogin (`persona import-from`)

- [x] Auto-adjust (`persona align`) — align a profile to what its browser really
      shows so a low trust grade jumps to A
- [x] Bulk create at scale (`persona bulk-create`, dashboard) — thousands of
      coherent profiles across OS / country / browser, with a paginated grid
- [x] Proxy pool — import a list, health-check it, and assign round-robin across
      profiles (aligning each profile's locale to its proxy country)
- [x] Dashboard-side import (GoLogin / AdsPower / Multilogin) — an Import button
      that maps each export to a coherent profile

- [x] DNS leak checker (`persona dns`) — reads which resolvers actually saw the
      lookups and fails if any escaped the proxy's country
- [x] Warm-up presets per vertical (`--preset ads|ecommerce|crypto|social|news`)
- [x] Scheduled warm-up (`persona schedule`) — recurring, unattended; the server
      fires due runs from a background thread, or drive it from cron with
      `schedule run-due`
- [x] Profile health overview — one page grading coherence, proxy, cached trust
      and warm-up schedule across every profile, with one-click fix
- [x] Fingerprint collision detector (`persona collisions`, Health page) —
      catches profiles that share a fingerprint before a site links the accounts
- [x] Backup & restore (`persona backup` / `restore`) — a profile **and its
      session** zipped into one portable file, movable to another machine
- [x] Bulk grid actions (warm up / export the selection) + tag filtering
- [x] Folders manager (dashboard) — create / rename / delete folders with live
      counts; renaming or deleting one moves its profiles instead of dropping them
- [x] Settings page (dashboard) — theme, default launch engine, storage location
      and data summary, backed by `GET`/`PUT /api/config`
- [x] Mobile (Android) profiles — coherent handset fingerprints (real model in
      the UA, matching GPU/screen/RAM) with touch + device-scale emulation at launch
- [x] Session health (`persona session`, dashboard) — reads the cookie jar and
      flags expired / soon-to-expire cookies and which logins are still live
- [x] Duplicate as template — clone a profile's settings with a *fresh* coherent
      fingerprint, so the copy is a distinct device, never a fingerprint twin
- [x] Per-profile activity log — launches, warm-ups, trust runs and session
      checks, shown as a timeline in the editor
- [x] Pinned engine identities: Camoufox and CloakBrowser present the same
      device every launch, and Cloak presents Persona's own hardware/GPU/screen
- [x] Launch-time geo: timezone + city-level geolocation from the proxy's exit
      IP, with DNS lockdown so nothing resolves outside the proxy
- [x] Authenticated SOCKS5 proxies via a local bridge (remote DNS)
- [x] Device-accurate `devicePixelRatio` and `deviceMemory`; the UA and Client
      Hints follow the engine's real Chrome version

**Next**

- [ ] Cloud sync + team roles — deliberately unbuilt: it needs a hosted backend,
      accounts and a threat model of its own. Persona stays local-first until
      that's designed properly rather than bolted on.

Want to help? See [CONTRIBUTING.md](CONTRIBUTING.md).

## Legitimate use & responsibility

Persona is a tool for **legitimate multi-account management**: marketing agencies
handling many client ad accounts, QA and ad-verification testing, web-automation
development, and privacy research — the same use cases served openly by
commercial anti-detect browsers.

Do **not** use it for fraud, credential stuffing, spam, evading bans you've
earned, or anything that violates a site's terms of service or the law. You are
responsible for how you use it.

## License

[MIT](LICENSE) — free to use, modify and distribute.
