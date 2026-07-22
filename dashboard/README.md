# Persona Dashboard

The web front-end for [Persona](../README.md) — an operations console for
managing browser profiles, styled after commercial anti-detect browsers but
open-source and self-hosted.

> This is the UI. For the engine that actually generates fingerprints and
> launches browsers, see [`../engine`](../engine).

## Run it

```bash
cd dashboard
npm install
npm run dev        # opens http://localhost:5173
```

Build for production:

```bash
npm run build      # outputs to dist/
npm run preview
```

## What's inside

- **Profile grid** — live running/stopped status, environment, proxy, last active,
  and per-row launch / edit / clone / delete.
- **Fingerprint editor** — a tabbed drawer covering OS, browser, user-agent,
  screen, CPU/RAM, WebGL, and the spoofing modes for canvas, WebRTC, audio and
  fonts, plus timezone, locale, geolocation and media devices.
- **Launch engine selector** — pick the stealth backend per profile
  (`playwright` / `patchright` / `camoufox`); Persona manages, the engine renders.
- **Live coherence meter** — the signature feature. As you edit a fingerprint it
  re-checks consistency in real time (mirroring the engine's `validate()`), so a
  Windows profile wearing an Apple GPU is flagged instantly.
- **Proxy manager, bulk create, folders, tags, search, multi-select.**

## Live mode vs demo mode

On load the dashboard pings the engine API (`persona serve`, default
`http://localhost:8787`). The sidebar footer shows which mode you're in:

- **Engine online** — the API is reachable. Profiles are read from and saved to
  disk, and the launch (▶) button opens a **real Chromium window**.
- **Demo mode** — the API is offline, so the UI runs on in-memory sample data.
  Perfect for exploring the project; nothing is persisted and launch is simulated.

To go live, start the engine API in another terminal:

```bash
cd ../engine
pip install -e ".[api,launch]"
playwright install chromium
persona serve
```

Point the dashboard at a different API URL with a `VITE_API_URL` env var. The API
client lives in [`src/api.js`](src/api.js).

## Tech

Plain React 18 + Vite. Icons from `lucide-react`. Styling is a single scoped
`<style>` block — no CSS framework dependency.
