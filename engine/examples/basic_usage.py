"""
Create and inspect profiles with the Python API.

Run:  python examples/basic_usage.py
"""

from persona import ProfileStore, generate, Profile, Proxy, validate

store = ProfileStore()  # uses ~/.persona

# A US Windows identity behind a proxy.
win = Profile(
    name="us-windows-01",
    fingerprint=generate(os="windows", locale="en-US"),
    proxy=Proxy(server="http://proxy.example.com:8080", country="US"),
    tags=["demo"],
)
store.save(win)

# A Pakistani mobile identity; locale/timezone follow the proxy country.
mob = Profile(
    name="pk-mobile-01",
    fingerprint=generate(mobile=True, proxy=Proxy(server="http://p:1", country="PK")),
    tags=["demo"],
)
store.save(mob)

for prof in store.list():
    fp = prof.fingerprint
    coherent = "OK" if not validate(fp) else "ISSUES"
    print(f"{prof.name:<16} {fp.os:<8} {fp.locale:<7} "
          f"{fp.screen_width}x{fp.screen_height}  [{coherent}]")
