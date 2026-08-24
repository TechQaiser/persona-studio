"""WebRTC handling: the mode has to reach the page, not just the UI.

The dashboard has offered an "Altered / Disabled / Real" WebRTC picker since the
first release, but the engine had no such field - the choice was dropped on the
way through and every profile behaved the same. These pin the plumbing; the
live test pins the behaviour.
"""

from dataclasses import replace

from persona import generate
from persona.models import Fingerprint
from persona.server import to_dashboard_profile, to_engine_profile
from persona.stealth import build_init_script


def test_default_mode_is_altered():
    assert generate(seed=1).webrtc == "altered"


def test_profiles_saved_before_the_field_existed_still_load():
    fp = generate(seed=1)
    older = {k: v for k, v in fp.to_dict().items() if k != "webrtc"}
    assert Fingerprint.from_dict(older).webrtc == "altered"


def test_mode_reaches_the_init_script():
    for mode in ("altered", "disabled", "real"):
        js = build_init_script(replace(generate(seed=1), webrtc=mode))
        assert f'"webrtc": "{mode}"' in js


def test_real_mode_leaves_webrtc_alone():
    # The guard is in the script either way; "real" must not take the branch.
    js = build_init_script(replace(generate(seed=1), webrtc="real"))
    assert "cfg.webrtc === 'disabled'" in js
    assert "cfg.webrtc !== 'real'" in js


def test_candidate_filter_keeps_private_and_mdns():
    # Stripping private/mDNS candidates too would itself be a tell: a real
    # browser behind NAT offers them.
    js = build_init_script(generate(seed=1))
    assert ".local" in js                      # mDNS kept
    assert r"192\.168\." in js               # RFC1918 kept
    assert "a=candidate:" in js                # SDP scrubbed as well as events


def test_dashboard_choice_survives_the_round_trip():
    for shown, stored in (("Altered", "altered"), ("Disabled", "disabled"), ("Real", "real")):
        d = {"id": "x", "name": "n", "os": "Windows", "screen": "1920x1080",
             "cores": 8, "memory": 16, "locale": "en-US",
             "timezone": "America/New_York", "webrtc": shown,
             "webglRenderer": "ANGLE (NVIDIA GeForce RTX 3060 Direct3D11)"}
        prof = to_engine_profile(d)
        assert prof.fingerprint.webrtc == stored
        assert to_dashboard_profile(prof)["webrtc"] == shown
