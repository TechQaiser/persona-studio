# Contributing to Persona

Thanks for helping improve Persona! Contributions of every size are welcome —
bug reports, new device archetypes, docs, and features.

## Repo layout

```
engine/       Python core (fingerprints, storage, launcher, CLI)
dashboard/    React web console
docs/         Architecture & guides
start.bat     Windows one-click launcher
```

## Setup

**Engine**

```bash
cd engine
pip install -e ".[dev]"
python -m pytest          # should be all green
```

**Dashboard**

```bash
cd dashboard
npm install
npm run dev
```

## High-value contributions

- **Device archetypes** (engine/persona/devices.py) — the most valuable, lowest-risk
  contribution. Add realistic OS/GPU/screen/hardware combos. Every entry must stay
  internally consistent (e.g. Apple GPUs only under `macos`) and still pass
  `validate()`. Add a test proving it.
- **Locales** — extend the locale → timezone/language maps.
- **Roadmap features** — cookie import/export, automation API, leak checker,
  trust-score checker (see the roadmap in the main README).
- **Launch engines** (engine/persona/drivers.py) — add a backend with
  `@register("name", requires=...)`; it gets the profile, proxy and session dir
  for free.

## Guidelines

1. **Coherence is the whole point.** Any change that lets `generate()` produce a
   fingerprint that fails `validate()` will be rejected.
2. **Keep the engine's core dependency-free.** Heavier deps go under optional extras.
3. **Write a test** for behaviour changes; run `python -m pytest` before a PR.
4. **Keep it readable** — this is a learning-friendly project.

## Pull requests

- Branch from `main`, keep PRs focused, describe what and why.
- Green tests required. Screenshots help for dashboard changes.

## Scope

Persona is for legitimate use only. PRs whose sole purpose is to enable fraud or
abuse won't be merged. See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
