# Launch kit

Copy-paste-ready posts and settings for getting Persona in front of people.
Nothing here is automated — you submit these yourself. Order matters: do the
repo polish (topics, About, social image, a demo GIF) **before** posting, because
the first thing a visitor sees decides whether they star.

---

## 0. Before you post (do these first)

- [ ] **Demo GIF at the top of the README.** 15–30s: create a profile → the
      coherence meter moving live → launch a real browser → trust grade A. This is
      the single highest-leverage thing. Record with [ScreenToGif](https://www.screentogif.com/)
      (Windows) or [Kap](https://getkap.co/) (Mac). Drop it in `docs/` and link it
      above the screenshot.
- [ ] **GitHub topics** set (list below).
- [ ] **About / description + website** filled in (below).
- [ ] **Social preview image** uploaded (Settings → General → Social preview) so
      the link shows a real card on Reddit/X/HN, not a blank box.
- [ ] Skim the README on mobile — most HN/Reddit clicks are phones.

---

## 1. GitHub repo settings

**Description** (the one-liner under the repo name):

> Open-source, self-hosted anti-detect browser & profile manager. Coherent
> fingerprints, per-profile proxies & sessions. A free alternative to Multilogin,
> GoLogin and AdsPower.

**Website field:** your live demo URL if you host one, else the docs page.

**Topics** (Settings → paste these):

```
anti-detect-browser  antidetect  browser-fingerprinting  fingerprint  fingerprinting
privacy  self-hosted  multi-accounting  playwright  chromium  automation
stealth-browser  proxy  browser-automation  python  react  gologin-alternative
multilogin-alternative  adspower-alternative
```

The `*-alternative` topics are how people searching for a free replacement find you.

---

## 2. Show HN

**Title** (HN titles must be plain, no hype — "Show HN:" prefix required):

> Show HN: Persona – open-source, self-hosted alternative to Multilogin

**Body:**

> I built Persona because the commercial anti-detect browsers (Multilogin,
> GoLogin, AdsPower) are $50–100/mo, cloud-only, and closed. It's a self-hosted
> profile manager: each profile gets a *coherent* fingerprint, its own proxy, and
> a persistent session, launched from a web console or CLI.
>
> The part I care about most is coherence. Most fingerprint tools randomise each
> value independently — a macOS user-agent with an NVIDIA GPU, a 4-core phone
> claiming a 1440p screen — and that mismatch is exactly what anti-bot systems
> cross-check. Persona picks a real device archetype first and draws every value
> (OS, UA, GPU, screen, CPU, RAM, timezone, language) from that archetype's pool,
> then shows a live coherence meter and a trust checker that grades the *real*
> browser, not the config.
>
> Stealth backend is pluggable — patched-Chromium (CloakBrowser), patched-Firefox
> (Camoufox), Patchright, or stock Playwright. Python engine + React dashboard,
> MIT licensed. Everything stays on your machine; there's no cloud component.
>
> Honest about the space: anti-detect browsers are dual-use. It's meant for
> legit multi-account management (agencies, QA, ad verification, privacy research),
> and I say so in the README — not ban evasion or fraud.
>
> Repo: https://github.com/TechQaiser/persona-studio
> Feedback on the coherence approach especially welcome.

**Tips:** Post Tue–Thu, ~8–10am US Eastern. Reply to every comment in the first
2 hours — HN rewards author engagement. Don't ask for upvotes anywhere (fastest
way to get flagged).

---

## 3. Reddit

Read each sub's rules first; some require flair or ban self-promo. Space posts
out over days, don't blast all at once, and reply to comments.

### r/selfhosted (your best fit — loves free replacements for paid SaaS)

**Title:**

> Persona – a self-hosted, open-source alternative to Multilogin/GoLogin (anti-detect browser + profile manager)

**Body:**

> Got tired of the $50–100/mo cloud anti-detect browsers, so I built a self-hosted
> one. Each browser profile looks like a separate real device — coherent
> fingerprint, own proxy, persistent session — managed from a web dashboard or CLI.
> Python + React, MIT, runs entirely on your own box, no telemetry, no cloud.
>
> The thing I think is actually novel: a live *coherence* meter. Instead of
> randomising each fingerprint value, it picks a real device archetype and keeps
> every value consistent, then grades the real launched browser so you can see
> whether it'd actually pass a cross-check.
>
> Screenshots + one-command start in the README: [link]
>
> Happy to answer setup questions.

### r/privacy

Lead with the privacy/self-hosting angle, less with the multi-accounting angle
(that sub is wary of anything that smells like marketing/growth-hacking). Frame:
"I wanted browser profiles that stay isolated and never phone home to a vendor."

### Others worth a targeted, rules-respecting post

- r/opensource — straight project-launch post
- r/webscraping — the automation/CDP-attach + stealth-engine angle lands here
- r/coolgithubprojects — link + one-liner

---

## 4. Awesome-lists (slow but steady long-tail stars)

Open a PR adding Persona to:

- [awesome-selfhosted](https://github.com/awesome-selfhosted/awesome-selfhosted) —
  under a Browser/Privacy category. Read their strict entry rules (needs license,
  active repo, a one-line description in their exact format).
- [awesome-privacy](https://github.com/pluja/awesome-privacy)
- Any "awesome-web-scraping" / "awesome-playwright" list — the stealth engine fits.

Entry line to reuse:

> - [Persona](https://github.com/TechQaiser/persona-studio) - Self-hosted
>   anti-detect browser & profile manager with coherent fingerprints and per-profile
>   proxies. `MIT` `Python/React`

---

## 5. Product Hunt

Post as a maker. You need: a 240×240 logo, 3–5 gallery images (dashboard,
coherence meter, trust grade, comparison table), the demo GIF, and a first
comment explaining the "why". Launch 12:01am PT; rally a few people to comment
(not just upvote) through the day.

Tagline:

> The open-source, self-hosted anti-detect browser

---

## 6. A technical blog post (dev.to / Hashnode / your site)

Titles that pull in the exact audience searching for this:

- "How I built a *coherent* browser-fingerprint engine (and why randomising each value gets you caught)"
- "Building an open-source alternative to Multilogin in Python + React"

Cross-post to dev.to, Hashnode, and r/programming (if it's genuinely technical,
not a launch ad). Link the repo at the end, not the top.

---

## 7. X / Twitter

Thread, one idea per post, screenshot or GIF on the first:

> 1/ Most anti-detect browsers randomise every fingerprint value independently.
> That's exactly what gets them flagged — anti-bot systems cross-check the values.
>
> 2/ So I built Persona: it picks a real *device archetype* first, then every
> value (OS, GPU, screen, CPU, timezone, language) comes from that one device.
> They all agree.
>
> 3/ Live coherence meter proves it. A trust checker grades the *real* launched
> browser, not the config. [GIF]
>
> 4/ Self-hosted, open source (MIT), free. A local alternative to the $99/mo
> cloud tools. Python engine + React dashboard.
>
> 5/ Repo 👉 https://github.com/TechQaiser/persona-studio

Tag/关注 accounts in the web-scraping & automation space; use hashtags sparingly.

---

## Guardrails

- **Never buy or ask for upvotes/stars.** It gets you banned on HN, PH and Reddit
  and it's obvious in the graph.
- **Keep the "legitimate use" framing** visible everywhere. This space gets
  flagged fast; being upfront that it's for legit multi-account management (and
  not fraud/ban-evasion) is both honest and what keeps posts from getting removed.
- **Respond to everything** in the first few hours of any launch. Engagement, not
  the post itself, is what ranks.
