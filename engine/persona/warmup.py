"""
Account warm-up — give a brand-new profile a plausible past.

A profile created five minutes ago has no history, no cookies, no cached
anything. Sites that score risk notice: the "brand-new browser that goes
straight to a login form" is one of the oldest signals there is. Warming up
means browsing normally first — ordinary sites, ordinary pauses — so the
profile arrives with a believable trail.

What this does is deliberately modest and readable: open a page, wait a human
amount of time, scroll in irregular steps, move the mouse, sometimes follow an
internal link, then move on. It is *not* a bot that pretends to be a person on
sites that forbid it — it's a way to age a session on pages you're happy to
visit. Point it at your own list with ``--site``.
"""

from __future__ import annotations

import random
import time
from typing import Callable, Optional

from .drivers import session
from .models import Profile
from .store import ProfileStore

# Neutral, high-traffic destinations that any real browser would have seen.
DEFAULT_SITES = [
    "https://en.wikipedia.org/wiki/Special:Random",
    "https://www.bbc.com/news",
    "https://news.ycombinator.com/",
    "https://weather.com/",
    "https://www.reddit.com/r/popular/",
    "https://stackoverflow.com/questions",
    "https://www.imdb.com/chart/top/",
]

# Per-vertical warm-up sets. The account you're aging usually lives in one
# world — an ad account, a store, a crypto wallet — and its "normal" browsing
# history looks like that world, not a random walk. Seeding the cookie jar and
# history with sites of the right kind makes the profile read as a real user of
# that vertical, and (for ads especially) primes the ad/analytics cookies a
# real visitor would already carry. All neutral, publicly reachable pages.
PRESETS = {
    "general": DEFAULT_SITES,
    "ads": [
        "https://www.youtube.com/",
        "https://www.forbes.com/",
        "https://www.cnn.com/",
        "https://www.espn.com/",
        "https://www.buzzfeed.com/",
        "https://www.weather.com/",
        "https://www.accuweather.com/",
    ],
    "ecommerce": [
        "https://www.amazon.com/",
        "https://www.ebay.com/",
        "https://www.etsy.com/",
        "https://www.walmart.com/",
        "https://www.bestbuy.com/",
        "https://www.aliexpress.com/",
        "https://www.target.com/",
    ],
    "crypto": [
        "https://www.coingecko.com/",
        "https://coinmarketcap.com/",
        "https://www.tradingview.com/",
        "https://www.binance.com/en",
        "https://www.reddit.com/r/CryptoCurrency/",
        "https://cointelegraph.com/",
        "https://decrypt.co/",
    ],
    "social": [
        "https://www.reddit.com/r/popular/",
        "https://www.pinterest.com/",
        "https://www.quora.com/",
        "https://www.tumblr.com/explore",
        "https://medium.com/",
        "https://www.youtube.com/",
    ],
    "news": [
        "https://www.bbc.com/news",
        "https://www.reuters.com/",
        "https://apnews.com/",
        "https://www.theguardian.com/",
        "https://www.cnbc.com/",
        "https://news.ycombinator.com/",
    ],
}


def preset_sites(name: Optional[str]) -> list[str]:
    """Resolve a preset name to its site list (falling back to the general set)."""
    return list(PRESETS.get((name or "general").lower(), DEFAULT_SITES))


def _human_pause(rng: random.Random, lo: float, hi: float) -> None:
    time.sleep(rng.uniform(lo, hi))


def _browse_page(page, rng: random.Random, seconds: float) -> None:
    """Spend ``seconds`` on the current page the way a person would."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        action = rng.random()
        try:
            if action < 0.6:
                # Scroll a screenful-ish, in the uneven amounts a wheel produces.
                page.mouse.wheel(0, rng.randint(200, 900))
            elif action < 0.85:
                page.mouse.move(rng.randint(50, 900), rng.randint(80, 600),
                                steps=rng.randint(5, 20))
            else:
                page.mouse.wheel(0, -rng.randint(100, 500))   # scroll back up
        except Exception:
            return   # page navigated away or closed; nothing to recover from
        _human_pause(rng, 0.8, 3.5)


def _follow_internal_link(page, rng: random.Random) -> bool:
    """Click a link that stays on this site. Returns whether it worked."""
    try:
        host = page.evaluate("() => location.host")
        hrefs = page.evaluate(
            """(host) => [...document.querySelectorAll('a[href]')]
                 .map(a => a.href)
                 .filter(h => h.startsWith('http') && new URL(h).host === host)
                 .slice(0, 40)""", host)
        if not hrefs:
            return False
        page.goto(rng.choice(hrefs), wait_until="domcontentloaded", timeout=30000)
        return True
    except Exception:
        return False


def warm_up(profile: Profile, store: ProfileStore, minutes: float = 5,
            sites: Optional[list[str]] = None, engine: Optional[str] = None,
            headless: bool = False, preset: Optional[str] = None,
            on_event: Optional[Callable[[str], None]] = None) -> dict:
    """Browse for ``minutes`` to age the profile. Returns a small summary.

    ``sites`` wins if given; otherwise ``preset`` picks a per-vertical set
    (``ads``/``ecommerce``/``crypto``/``social``/``news``/``general``).
    ``on_event`` receives progress lines so a CLI can narrate the run; the
    dashboard just waits for the summary.
    """
    rng = random.Random()
    pool = list(sites) if sites else preset_sites(preset)
    rng.shuffle(pool)
    say = on_event or (lambda _msg: None)

    deadline = time.time() + minutes * 60
    visited: list[str] = []
    errors = 0

    with session(profile, store, engine, headless=headless) as context:
        page = context.pages[0] if context.pages else context.new_page()
        i = 0
        while time.time() < deadline:
            url = pool[i % len(pool)]
            i += 1
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
            except Exception:
                errors += 1
                say(f"  skipped {url} (unreachable)")
                continue

            visited.append(url)
            say(f"  browsing {url}")
            # Split the visit between the landing page and one page deeper, but
            # never overshoot the deadline the caller asked for.
            budget = min(rng.uniform(20, 60), max(5.0, deadline - time.time()))
            _browse_page(page, rng, budget * 0.6)
            if time.time() < deadline and rng.random() < 0.7 and _follow_internal_link(page, rng):
                say("    followed a link")
                _browse_page(page, rng, budget * 0.4)
            _human_pause(rng, 1.0, 3.0)

    return {"visited": visited, "pages": len(visited), "errors": errors,
            "minutes": round(minutes, 2),
            "preset": (preset or "general").lower() if not sites else "custom"}
