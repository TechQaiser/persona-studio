"""Warm-up preset resolution. The browse loop needs a browser, but choosing
*which* sites a vertical warms up is pure and worth pinning."""

from persona.warmup import DEFAULT_SITES, PRESETS, preset_sites


def test_known_presets_exist():
    for name in ("general", "ads", "ecommerce", "crypto", "social", "news"):
        assert name in PRESETS
        assert len(PRESETS[name]) >= 5


def test_preset_sites_resolves_by_name():
    assert preset_sites("crypto") == PRESETS["crypto"]
    assert "coingecko" in " ".join(preset_sites("crypto"))


def test_preset_sites_is_case_insensitive():
    assert preset_sites("ADS") == PRESETS["ads"]


def test_unknown_preset_falls_back_to_default():
    assert preset_sites("nonsense") == DEFAULT_SITES
    assert preset_sites(None) == DEFAULT_SITES


def test_preset_sites_returns_a_copy():
    # Callers shuffle the list in place; that must not mutate the module table.
    got = preset_sites("news")
    got.append("https://example.com/")
    assert "https://example.com/" not in PRESETS["news"]
