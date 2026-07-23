"""The multi-profile synchroniser: one patch, many profiles."""

import pytest

from persona import generate, validate
from persona.bulk import apply_patch, select, generate_profiles
from persona.models import Profile, Proxy


def mk(name, **kw):
    return Profile(name=name, fingerprint=generate(seed=7, os="windows", locale="en-US"), **kw)


def test_absent_keys_are_left_alone():
    p = mk("a", notes="keep me", tags=["x"])
    assert apply_patch(p, {}) == []
    assert p.notes == "keep me" and p.tags == ["x"]


def test_engine_and_notes():
    p = mk("a")
    changed = apply_patch(p, {"engine": "cloak", "notes": "q3"})
    assert set(changed) == {"engine", "notes"}
    assert p.engine == "cloak" and p.notes == "q3"


def test_setting_the_same_value_is_not_a_change():
    p = mk("a", engine="cloak")
    assert apply_patch(p, {"engine": "cloak"}) == []


def test_locale_moves_timezone_and_languages():
    p = mk("a")
    apply_patch(p, {"locale": "de-DE"})
    assert p.fingerprint.locale == "de-DE"
    assert p.fingerprint.timezone == "Europe/Berlin"
    assert p.fingerprint.languages[0] == "de-DE"


def test_unknown_locale_is_ignored():
    p = mk("a")
    before = p.fingerprint.timezone
    assert "locale" not in apply_patch(p, {"locale": "xx-XX"})
    assert p.fingerprint.timezone == before


def test_tags_added_and_removed():
    p = mk("a", tags=["old", "keep"])
    changed = apply_patch(p, {"add_tags": ["new"], "remove_tags": ["old"]})
    assert changed == ["tags"]
    assert p.tags == ["keep", "new"]


def test_tag_already_present_is_not_a_change():
    p = mk("a", tags=["keep"])
    assert apply_patch(p, {"add_tags": ["keep"]}) == []


def test_proxy_can_be_set_and_explicitly_cleared():
    p = mk("a")
    apply_patch(p, {"proxy": Proxy(server="http://h:1", country="DE")})
    assert p.proxy.country == "DE"
    # None means "go direct", which is different from "not mentioned".
    assert apply_patch(p, {"proxy": None}) == ["proxy"]
    assert p.proxy is None


def test_regen_keeps_os_and_locale_but_changes_the_device():
    p = mk("a")
    before = p.fingerprint
    apply_patch(p, {"locale": "de-DE", "regen": True})
    assert p.fingerprint.os == before.os
    assert p.fingerprint.locale == "de-DE"
    assert p.fingerprint.seed != before.seed


def test_regenerated_fingerprint_is_still_coherent():
    from persona import validate
    p = mk("a")
    apply_patch(p, {"regen": True})
    assert validate(p.fingerprint) == []


@pytest.fixture
def three():
    return [mk("a", tags=["prod"]), mk("b", tags=["prod", "eu"]), mk("c")]


def test_select_by_tag(three):
    assert [p.name for p in select(three, tag="prod")] == ["a", "b"]


def test_select_by_name_or_id(three):
    assert [p.name for p in select(three, refs=["c", three[0].id])] == ["a", "c"]


def test_select_never_returns_duplicates(three):
    picked = select(three, refs=["a"], tag="prod")
    assert [p.name for p in picked] == ["a", "b"]


def test_select_all(three):
    assert len(select(three, everything=True)) == 3


def test_select_nothing_by_default(three):
    assert select(three) == []


# ---- bulk generation at scale --------------------------------------------
def test_generate_profiles_count_and_names():
    ps = generate_profiles(5, name_prefix="Batch", start_index=1, pad=3)
    assert len(ps) == 5
    assert [p.name for p in ps] == ["Batch-001", "Batch-002", "Batch-003",
                                    "Batch-004", "Batch-005"]


def test_generate_profiles_are_all_coherent():
    for p in generate_profiles(50, oses=["windows", "macos", "linux"],
                               locales=["en-US", "de-DE"]):
        assert validate(p.fingerprint) == [], p.name


def test_generate_profiles_spread_across_oses():
    ps = generate_profiles(6, oses=["windows", "macos"])
    kinds = {p.fingerprint.os for p in ps}
    assert kinds == {"windows", "macos"}          # both represented
    assert sum(p.fingerprint.os == "windows" for p in ps) == 3   # evenly


def test_generate_profiles_are_distinct_identities():
    ps = generate_profiles(20, oses=["windows"])
    seeds = {p.fingerprint.seed for p in ps}
    assert len(seeds) == 20                         # no cloned fingerprints


def test_generate_profiles_restricts_chrome_versions():
    ps = generate_profiles(10, chrome_versions=["128.0.0.0"])
    for p in ps:
        assert p.fingerprint.chrome_version == "128.0.0.0"
        assert "Chrome/128.0.0.0" in p.fingerprint.user_agent


def test_generate_profiles_reproducible_with_seed():
    a = generate_profiles(4, oses=["windows", "macos"], seed=99)
    b = generate_profiles(4, oses=["windows", "macos"], seed=99)
    assert [p.fingerprint.to_dict() for p in a] == [p.fingerprint.to_dict() for p in b]


def test_generate_profiles_tags_and_engine():
    ps = generate_profiles(3, engine="cloak", tags=["bulk", "q3"])
    assert all(p.engine == "cloak" and p.tags == ["bulk", "q3"] for p in ps)
