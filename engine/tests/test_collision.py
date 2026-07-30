"""Fingerprint collision detection: pure logic over profiles, no browser."""

from dataclasses import replace

from persona.collision import find_collisions, signature, summary
from persona.fingerprint import generate
from persona.models import Profile


def _profile(name, fp):
    return Profile(name=name, fingerprint=fp)


def test_unique_profiles_dont_collide():
    a = _profile("a", generate(os="windows", seed=1))
    b = _profile("b", generate(os="macos", seed=2))   # different OS -> different signature
    assert find_collisions([a, b]) == []
    assert summary([a, b])["clashing"] == 0


def test_same_device_collides_even_with_different_seed():
    fp = generate(os="windows", seed=1)
    a = _profile("a", fp)
    b = _profile("b", replace(fp, seed=99))            # same device, different canvas noise
    groups = find_collisions([a, b])
    assert len(groups) == 1
    assert {m["name"] for m in groups[0]["members"]} == {"a", "b"}
    assert groups[0]["identical"] is False             # seeds differ


def test_identical_when_seed_also_matches():
    fp = generate(os="windows", seed=1)
    groups = find_collisions([_profile("a", fp), _profile("b", replace(fp))])
    assert len(groups) == 1
    assert groups[0]["identical"] is True


def test_signature_ignores_the_seed():
    fp = generate(os="windows", seed=1)
    assert signature(fp) == signature(replace(fp, seed=999))


def test_summary_counts_clashing_profiles_not_groups():
    fp = generate(os="windows", seed=1)
    profs = [_profile("a", fp),
             _profile("b", replace(fp, seed=2)),        # collides with a
             _profile("c", generate(os="linux", seed=3))]  # unique
    s = summary(profs)
    assert s == {"total": 3, "groups": 1, "clashing": 2, "identical": 0}


def test_groups_are_most_linked_first():
    win = generate(os="windows", seed=1)
    mac = generate(os="macos", seed=1)
    profs = [_profile("w1", win), _profile("w2", replace(win, seed=2)),
             _profile("w3", replace(win, seed=3)),
             _profile("m1", mac), _profile("m2", replace(mac, seed=2))]
    groups = find_collisions(profs)
    assert [len(g["members"]) for g in groups] == [3, 2]
