"""
Launch a profile and verify the fingerprint took effect.

This opens the profile against a fingerprint-inspection site so you can visually
confirm the spoofed values. Requires Playwright:

    pip install playwright && playwright install chromium

Run:  python examples/launch_and_verify.py
"""

from persona import ProfileStore, generate, Profile
from persona.launcher import launch

store = ProfileStore()

prof = store.find_by_name("verify-demo")
if prof is None:
    prof = store.save(Profile(name="verify-demo",
                              fingerprint=generate(os="windows", locale="en-US")))

# keep_open=True hands back the live handles so you can automate the session.
pw, context, page = launch(prof, store, headless=False, keep_open=True)

# Navigate somewhere that echoes the detected fingerprint.
page.goto("https://browserleaks.com/javascript")
print("Reported user-agent:", page.evaluate("navigator.userAgent"))
print("Reported platform:  ", page.evaluate("navigator.platform"))
print("Reported cores:     ", page.evaluate("navigator.hardwareConcurrency"))
print("webdriver flag:     ", page.evaluate("navigator.webdriver"))

input("\nInspect the page, then press Enter to close...")
context.close()
pw.stop()
