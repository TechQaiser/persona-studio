"""Spintax name templates for bulk create."""

import random
import re
from datetime import date

from persona import spintax
from persona.bulk import generate_profiles
from persona.cli import main
from persona.store import ProfileStore

DAY = date(2026, 11, 26)


def ex(t, **kw):
    return spintax.expand(t, rng=random.Random(7), today=DAY, **kw)


def test_number_and_date():
    assert ex("Shop-{n}", n=7, pad=4) == "Shop-0007"
    assert ex("{date}-{n}", n=12) == "2026-11-26-12"


def test_words_names_and_choices_come_from_their_lists():
    assert ex("{word}") in spintax.WORDS
    assert ex("{name}") in spintax.NAMES
    assert ex("{US|UK|DE}") in {"US", "UK", "DE"}
    seen = {spintax.expand("{a|b}", rng=random.Random(i)) for i in range(40)}
    assert seen == {"a", "b"}


def test_nested_choices():
    for i in range(20):
        out = spintax.expand("{shop|{word}-store}", rng=random.Random(i))
        assert out == "shop" or (out.endswith("-store") and out[:-6] in spintax.WORDS)


def test_unknown_tokens_and_plain_text_are_left_alone():
    assert ex("{foo} and {n}", n=1) == "{foo} and 1"
    assert ex("plain") == "plain"
    assert ex("{n}") == "{n}"          # no number given
    assert ex("{x|{bar}}") in {"x", "{bar}"}


def test_tokens_are_case_insensitive():
    assert ex("{N}-{Date}", n=3) == "3-2026-11-26"


def test_unique_name_rerolls_random_parts():
    taken = {f"{w}" for w in spintax.WORDS[:-1]}
    # Only one word is free; 25 tries make finding it very likely, not certain,
    # so use a seed that's known to land on it.
    name = spintax.unique_name("{word}", taken, rng=random.Random(1), tries=500)
    assert name == spintax.WORDS[-1]


def test_unique_name_returns_a_fixed_clash_for_the_caller():
    assert spintax.unique_name("same", {"same"}) == "same"


def test_bulk_batch_uses_templates_for_names_and_tags():
    profs = generate_profiles(30, name_template="{word}-{n}", tags=["bulk", "{q3|q4}"],
                              pad=2, seed=5)
    names = [p.name for p in profs]
    assert len(set(names)) == 30
    assert all(re.fullmatch(r"[a-z]+-\d{2}", n) for n in names)
    assert {p.tags[1] for p in profs} <= {"q3", "q4"}
    assert all(p.tags[0] == "bulk" for p in profs)


def test_bulk_without_template_keeps_the_old_names_and_seeds():
    a = generate_profiles(3, name_prefix="P", seed=9)
    b = generate_profiles(3, name_template="P-{n}", seed=9)
    assert [p.name for p in a] == ["P-0001", "P-0002", "P-0003"]
    assert [p.fingerprint.seed for p in a] == [p.fingerprint.seed for p in b]


def test_bulk_rerolls_away_from_existing_names():
    taken = set(spintax.NAMES[:20])
    profs = generate_profiles(5, name_template="{name}", taken=taken, seed=2)
    assert all(p.name not in taken for p in profs)


def test_cli_bulk_create_with_a_template(tmp_path, capsys):
    store = ProfileStore(tmp_path)
    assert main(["--data-dir", str(tmp_path), "bulk-create", "--count", "5",
                 "--name", "acct-{US|UK}-{n}", "--pad", "2", "--tag", "{a|b}"]) == 0
    names = sorted(p.name for p in store.list())
    assert len(names) == 5
    assert all(re.fullmatch(r"acct-(US|UK)-0[1-5]", n) for n in names)
    assert "Created 5" in capsys.readouterr().out
