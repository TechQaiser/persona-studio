"""Real-browser proof that the WebRTC modes do what they claim.

Chromium's --force-webrtc-ip-handling-policy does not reliably stop ICE from
offering a public address, so the in-page filter is what actually holds. Only a
real browser can show that, and only when the environment can reach STUN - if
"real" mode surfaces no public address there is nothing to suppress and the
comparison would pass vacuously, so the test skips instead of lying.
"""

import re

import pytest

from dataclasses import replace

from persona import generate
from persona.models import Profile
from persona.store import ProfileStore

pytest.importorskip("playwright")

IPV4 = re.compile(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b")
PRIVATE = re.compile(r"^(10\.|127\.|0\.|169\.254\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)")

GATHER = """() => new Promise(res => {
  if (!window.RTCPeerConnection) return res({removed: true, cands: [], sdp: ''});
  const cands = [];
  const pc = new RTCPeerConnection({iceServers: [{urls: 'stun:stun.l.google.com:19302'}]});
  pc.createDataChannel('probe');
  pc.onicecandidate = e => { if (e.candidate) cands.push(e.candidate.candidate); };
  pc.createOffer().then(o => pc.setLocalDescription(o));
  setTimeout(() => {
    const sdp = (pc.localDescription && pc.localDescription.sdp) || '';
    pc.close();
    res({removed: false, cands, sdp});
  }, 8000);
})"""


def _gather(tmp_path, mode):
    from persona.drivers import get
    store = ProfileStore(tmp_path)
    prof = Profile(name="rtc-" + mode,
                   fingerprint=replace(generate(seed=7), webrtc=mode))
    store.save(prof)
    try:
        pw, ctx, page = get("playwright")(prof, store, headless=True, keep_open=True)
    except Exception as e:
        pytest.skip(f"chromium unavailable: {str(e).splitlines()[0][:80]}")
    try:
        page.goto("about:blank")
        out = page.evaluate(GATHER)
    finally:
        ctx.close()
        pw.stop()
    text = " ".join(out["cands"]) + " " + " ".join(
        l for l in out["sdp"].splitlines() if l.startswith("a=candidate:"))
    public = {ip for ip in IPV4.findall(text) if not PRIVATE.match(ip) and ip != "0.0.0.0"}
    return out["removed"], public


def test_altered_hides_public_addresses(tmp_path):
    _, baseline = _gather(tmp_path, "real")
    if not baseline:
        pytest.skip("no STUN reachability here - nothing to suppress")
    removed, leaked = _gather(tmp_path, "altered")
    assert not removed, "altered must keep RTCPeerConnection usable"
    assert not leaked, f"public address still offered: {sorted(leaked)}"


def test_disabled_removes_the_api(tmp_path):
    removed, leaked = _gather(tmp_path, "disabled")
    assert removed
    assert not leaked
