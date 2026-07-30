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
persona bulk-create --count 500 --os windows --os macos \
        --locale en-US --locale de-DE --prefix Batch --tag bulk   # many at once
persona list
persona show acct-01
persona check acct-01          # validate fingerprint coherence
persona engines                # list available launch engines
persona default-engine cloak   # set the engine new profiles use (CloakBrowser)
persona launch acct-01
persona export acct-01 acct-01.json
persona import acct-01.json
persona backup acct-01 acct-01.zip        # profile + whole session, one portable file
persona restore acct-01.zip               # bring it back (add --new-id to clone it)
persona collisions                        # any two profiles sharing a fingerprint?
persona import-from gologin-export.json   # migrate from another anti-detect tool
persona serve                  # run the HTTP API the dashboard talks to
```

`export`/`import` move a profile's *config* (a JSON file). `backup`/`restore`
move the whole identity — the config **and** its browser session (cookies,
localStorage) — zipped together, so a warmed-up account survives a move to
another machine. Treat a backup as sensitive: the archive holds the proxy
password in plaintext.

`collisions` catches an easy self-inflicted wound: two profiles that render the
*same* fingerprint (same WebGL, screen, hardware, user-agent) look like one
device to a site and can be linked, so a ban on one can take the others with it.
Regenerate one side of each pair (`persona regen <name>`).

### Migrating from GoLogin / AdsPower / Multilogin

```bash
persona import-from their-export.json
```

Point it at a profile export (a single object or a list) from GoLogin, AdsPower
or Multilogin. The mapping is tolerant — those tools rename fields between
releases, so Persona looks for each value under any of the names it's known by,
fills gaps from a coherent generated base, and runs `validate()` on the result.
Anything that didn't line up is flagged for review; run `persona check <name>`
to see the details. Treat an import as a reviewed starting point, not a
guaranteed one-to-one copy. (Lands in the engine store / CLI; dashboard-side
import isn't wired yet.)

### Inspecting a profile

```bash
persona trust acct-01            # score it the way a fingerprinting script would
persona align acct-01            # auto-adjust: match the profile to what the browser shows
persona proxy test acct-01       # exit IP, country, timezone match + WebRTC leaks
persona dns acct-01              # do DNS lookups exit through the proxy, or leak to your ISP?
persona tls acct-01              # the TLS/JA3 handshake — the one layer JS can't touch
```

`dns` is the companion to `proxy test`: even with the proxy hiding your IP, if
name lookups go to your own ISP's resolver the sites you visit are still visible
at your real location. It hands a third-party test service a batch of unique
subdomains to resolve, reads back which resolvers actually did the work, and
fails if any sits outside the proxy's country. (It's also folded into `proxy
test`.) Needs internet.

`align` is the fix for a low trust score. The checker fails whenever the
*declared* identity and the *presented* one disagree — which is unavoidable with
an engine that renders the host's real hardware (CloakBrowser patches at the C++
level, so it shows this machine's GPU/CPU, not Persona's). `align` opens the
profile, reads back platform, CPU, memory, GPU, screen, fonts, media and
languages, and rewrites the fingerprint to those values — regenerating the OS
identity (user-agent, platform) if the machine is a different OS than the profile
claimed. Afterwards nothing contradicts and the grade jumps to A. (On the
`playwright`/`patchright` engines the injected script already spoofs the hardware
to the declared identity, so there's usually nothing to align.)

`tls` reads the profile's own TLS/HTTP2 handshake back from an echo service and
reports its **JA3** and **JA4** fingerprints. This is the layer the whole
"JS injection isn't enough" argument is really about: a server sees the TLS
ClientHello *before* the browser has a document, so no page script — yours or an
anti-detect browser's — can change it. Run it on two engines and compare the
JA3/JA4 side by side to see, rather than argue, what each engine actually sends.
(Chromium engines send Chrome's real handshake because they *are* Chromium; the
check confirms nothing downstream turned it into a tell.)

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
persona warmup acct-01 --minutes 10               # browse normally so the session isn't brand-new
persona warmup acct-01 --preset crypto            # warm up on that vertical's sites
persona schedule add acct-01 --every 12 --preset ads   # recurring, unattended warm-up
persona schedule list                             # what's scheduled and when it next runs
persona schedule run-due                          # run everything due now (for cron/Task Scheduler)
persona attach acct-01 --port 9222      # open it for Selenium / Puppeteer / Playwright
```

`attach` launches the profile with the DevTools protocol listening and prints
ready-to-paste snippets. Your automation drives *that* browser, so the identity,
proxy and session stay exactly as Persona set them up — a browser started by
Selenium itself would have none of them.

`warmup --preset` browses a per-vertical site set (`ads`, `ecommerce`, `crypto`,
`social`, `news`, or the default `general`) so the session's history looks like
a real user of that world, not a random walk. `schedule` reruns it unattended on
an interval: when `persona serve` is running it fires the due warm-ups itself
from a background thread; without the server, put `persona schedule run-due` on
cron or Windows Task Scheduler and it runs whatever's due. This keeps a session
that you log into once from going "cold" — no fresh cookies, an about-to-expire
token — which is itself a signal on your next visit.

### Changing many profiles at once

```bash
persona apply --tag client-a --engine cloak        # move a whole set to CloakBrowser
persona apply --all --locale de-DE                 # locale, timezone and languages together
persona apply acct-01 acct-02 --add-tag q3 --regen # fresh fingerprints, same accounts
persona apply --tag old --proxy "" -y              # "" means go direct
```

Only the flags you pass are changed — everything else is left alone, so the same
command is safe to run again later for one more tweak.

### Encrypting secrets at rest

By default the store is plaintext JSON — easy to read and back up, but a proxy
password sitting in a file is a risk. Turn on the vault to encrypt just the
secrets (the proxy password), leaving everything else readable:

```bash
pip install -e ".[secure]"                 # one-time: the crypto backend
persona vault enable                        # prompts for a master password
persona vault status                        # off / locked / unlocked
```

Enabling re-writes existing proxy passwords as `enc:v1:…` tokens
(AES via Fernet, key derived with PBKDF2-HMAC-SHA256). After that, give the
password when you need the proxy — set `PERSONA_PASSWORD` or pass `--password`:

```bash
PERSONA_PASSWORD=… persona launch acct-01   # subprocess inherits it; proxy works
persona list                                # works without it — only the secret is hidden
```

Names, OS, tags and the rest stay visible while locked, so you can still manage
profiles; only the proxy password is withheld until you unlock. **Keep the
password — there's no recovery.** This covers the engine store and CLI; the
dashboard's own profile store isn't encrypted yet (that needs the password in
the browser layer, which is a separate design).

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
| POST | `/api/profiles/{id}/trust` | Trust score + the individual checks (grade is cached for Health) |
| POST | `/api/profiles/{id}/align` | Auto-adjust to what the browser presents; before→after |
| POST | `/api/profiles/{id}/tls` | TLS/JA3/JA4 handshake fingerprint |
| POST | `/api/profiles/{id}/dns` | DNS leak check — which resolvers see the lookups |
| POST | `/api/profiles/{id}/warmup` | Start a background warm-up (`minutes`, `preset`) |
| POST | `/api/profiles/{id}/attach` | Open with a CDP endpoint; returns `port`, `wsUrl`, snippets |
| GET | `/api/profiles/health` | One row per profile: coherence, proxy, cached trust, schedule |
| GET | `/api/profiles/collisions` | Groups of profiles that share a fingerprint |
| POST | `/api/profiles/bulk` | Apply one `patch` to many `ids` |
| POST | `/api/profiles/batch` | Save many generated `profiles` at once (bulk create) |
| POST | `/api/profiles/import` | Import GoLogin/AdsPower/Multilogin export `text` |
| GET | `/api/proxies` | List the proxy pool |
| POST | `/api/proxies` | Import proxies from `text` (or a `proxies` list) |
| DELETE | `/api/proxies/{id}` | Remove a proxy from the pool |
| POST | `/api/proxies/{id}/test` | Health-check one proxy (exit IP/country) |
| POST | `/api/proxies/assign` | Assign the pool round-robin across profiles |
| GET | `/api/schedules` | List warm-up schedules + when each next runs |
| POST | `/api/schedules` | Schedule a recurring warm-up for a profile |
| PUT | `/api/schedules/{id}` | Change interval / preset / enabled |
| DELETE | `/api/schedules/{id}` | Remove a schedule |
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
| `crypto.py` | Encrypt-at-rest for secrets (optional `cryptography` backend) |
| `importers.py` | Tolerant import from GoLogin / AdsPower / Multilogin exports |
| `probe.py` | Proxy/DNS/leak/TLS test, the trust report, and the auto-aligner (`align`) |
| `collision.py` | Finds profiles that share a fingerprint (`persona collisions`) |
| `bulk.py` | Multi-profile synchroniser + bulk generator (`generate_profiles`) |
| `proxypool.py` | Parse pasted proxy lists (any layout) + health-check them |
| `warmup.py` | Human-paced browsing (per-vertical presets) that gives a fresh profile a past |
| `scheduler.py` | Recurring unattended warm-up bookkeeping (`persona schedule`) |
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
