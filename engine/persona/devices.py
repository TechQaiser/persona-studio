"""
Realistic device profile database.

A fingerprint is only convincing when its parts agree with each other. A macOS
user-agent paired with an NVIDIA GPU, or a 4-core phone reporting a 2560x1440
screen, is an instant tell. This module holds curated, internally-consistent
building blocks so the generator can only ever assemble plausible devices.

Everything here reflects real-world hardware/software combinations. Update the
Chrome/Safari versions periodically to stay current.
"""

from __future__ import annotations

# Recent stable Chrome major versions. Keep the newest 3-4 to look up-to-date.
# This is only the starting claim: at launch the profile moves to the version
# its engine really runs (drivers.sync_engine_version), since a UA older or
# newer than the engine is caught by feature detection.
CHROME_VERSIONS = ["148.0.0.0", "149.0.0.0", "150.0.0.0", "151.0.0.0"]

# WebGL unmasked vendor/renderer strings, grouped by OS so we never leak an
# Apple GPU on Windows or an NVIDIA card on a Mac.
WEBGL = {
    "windows": [
        ("Google Inc. (NVIDIA)",
         "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
        ("Google Inc. (NVIDIA)",
         "ANGLE (NVIDIA, NVIDIA GeForce GTX 1660 Ti Direct3D11 vs_5_0 ps_5_0, D3D11)"),
        ("Google Inc. (Intel)",
         "ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
        ("Google Inc. (AMD)",
         "ANGLE (AMD, AMD Radeon RX 6600 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ],
    # Chrome on macOS has rendered WebGL through ANGLE's Metal backend since
    # ~115, so a current Chrome reports a Metal renderer. The older "OpenGL 4.1"
    # strings belong to an old browser (see LEGACY_RENDERERS below).
    "macos": [
        ("Google Inc. (Apple)",
         "ANGLE (Apple, ANGLE Metal Renderer: Apple M1, Unspecified Version)"),
        ("Google Inc. (Apple)",
         "ANGLE (Apple, ANGLE Metal Renderer: Apple M2, Unspecified Version)"),
        ("Google Inc. (Intel)",
         "ANGLE (Intel, ANGLE Metal Renderer: Intel(R) Iris(TM) Plus Graphics, Unspecified Version)"),
    ],
    "linux": [
        ("Google Inc. (NVIDIA)",
         "ANGLE (NVIDIA, NVIDIA GeForce GTX 1050 Ti/PCIe/SSE2, OpenGL 4.5)"),
        ("Google Inc. (Intel)",
         "ANGLE (Intel, Mesa Intel(R) UHD Graphics (CML GT2), OpenGL 4.6)"),
    ],
    # Kept in sync with ANDROID_DEVICES below — a phone fingerprint draws its GPU
    # from its device bundle, and this curated pool must recognise every one.
    "android": [
        ("Google Inc. (Qualcomm)", "ANGLE (Qualcomm, Adreno (TM) 660, OpenGL ES 3.2)"),
        ("Google Inc. (Qualcomm)", "ANGLE (Qualcomm, Adreno (TM) 730, OpenGL ES 3.2)"),
        ("Google Inc. (ARM)", "ANGLE (ARM, Mali-G78, OpenGL ES 3.2)"),
        ("Google Inc. (ARM)", "ANGLE (ARM, Mali-G710, OpenGL ES 3.2)"),
        ("Google Inc. (ARM)", "ANGLE (ARM, Mali-G715, OpenGL ES 3.2)"),
        ("Google Inc. (ARM)", "ANGLE (ARM, Mali-G77 MC9, OpenGL ES 3.2)"),
    ],
}

# Renderer strings older Persona versions wrote, mapped to what a current Chrome
# reports for the same GPU. The dashboard used short labels that no real browser
# produces; macOS profiles carried pre-Metal OpenGL strings.
LEGACY_RENDERERS = {
    "ANGLE (NVIDIA GeForce RTX 3060 Direct3D11)": WEBGL["windows"][0],
    "ANGLE (NVIDIA GeForce GTX 1660 Ti Direct3D11)": WEBGL["windows"][1],
    "ANGLE (Intel UHD Graphics 630 Direct3D11)": WEBGL["windows"][2],
    "ANGLE (AMD Radeon RX 6600 Direct3D11)": WEBGL["windows"][3],
    "ANGLE (Apple M1, OpenGL 4.1)": WEBGL["macos"][0],
    "ANGLE (Apple M2, OpenGL 4.1)": WEBGL["macos"][1],
    "ANGLE (Intel Iris Plus Graphics, OpenGL 4.1)": WEBGL["macos"][2],
    "ANGLE (Apple, Apple M1, OpenGL 4.1)": WEBGL["macos"][0],
    "ANGLE (Apple, Apple M2, OpenGL 4.1)": WEBGL["macos"][1],
    "ANGLE (Intel, Intel(R) Iris(TM) Plus Graphics OpenGL Engine, OpenGL 4.1)": WEBGL["macos"][2],
    "ANGLE (NVIDIA GeForce GTX 1050 Ti, OpenGL 4.5)": WEBGL["linux"][0],
    "ANGLE (Mesa Intel UHD Graphics, OpenGL 4.6)": WEBGL["linux"][1],
    "ANGLE (Qualcomm Adreno 660, OpenGL ES 3.2)": WEBGL["android"][0],
    "ANGLE (ARM Mali-G78, OpenGL ES 3.2)": WEBGL["android"][2],
}

# Common desktop screen resolutions (width, height) per OS.
SCREENS = {
    "windows": [(1920, 1080), (1366, 768), (2560, 1440), (1536, 864), (1600, 900)],
    "macos": [(2560, 1600), (1440, 900), (1728, 1117), (1512, 982)],
    "linux": [(1920, 1080), (1366, 768), (2560, 1440)],
    "android": [(360, 800), (393, 873), (412, 915), (384, 854)],
}

# Plausible hardware for each platform: CPU threads and RAM (GB).
HARDWARE = {
    "windows": {"cores": [4, 6, 8, 12, 16], "memory": [4, 8, 16, 32]},
    "macos": {"cores": [8, 10, 12], "memory": [8, 16, 32]},
    "linux": {"cores": [4, 8, 16], "memory": [8, 16]},
    "android": {"cores": [6, 8], "memory": [4, 6, 8]},
}

# OS token that appears in the User-Agent string.
OS_UA_TOKEN = {
    "windows": "Windows NT 10.0; Win64; x64",
    "macos": "Macintosh; Intel Mac OS X 10_15_7",
    "linux": "X11; Linux x86_64",
    "android": "Linux; Android 13; Pixel 7",
}

# navigator.platform value per OS.
NAV_PLATFORM = {
    "windows": "Win32",
    "macos": "MacIntel",
    "linux": "Linux x86_64",
    "android": "Linux armv8l",
}

# sec-ch-ua-platform header value per OS.
CH_PLATFORM = {
    "windows": '"Windows"',
    "macos": '"macOS"',
    "linux": '"Linux"',
    "android": '"Android"',
}

# Locale -> (timezone, accept-language list). Used to keep language, timezone
# and (optionally) proxy geography in agreement.
LOCALES = {
    "en-US": ("America/New_York", ["en-US", "en"]),
    "en-GB": ("Europe/London", ["en-GB", "en"]),
    "en-PK": ("Asia/Karachi", ["en-PK", "en", "ur"]),
    "en-IN": ("Asia/Kolkata", ["en-IN", "en", "hi"]),
    "de-DE": ("Europe/Berlin", ["de-DE", "de", "en"]),
    "fr-FR": ("Europe/Paris", ["fr-FR", "fr", "en"]),
    "es-ES": ("Europe/Madrid", ["es-ES", "es", "en"]),
    "tr-TR": ("Europe/Istanbul", ["tr-TR", "tr", "en"]),
}

# Rough country -> locale hint, so a proxy's country can steer the locale.
COUNTRY_TO_LOCALE = {
    "US": "en-US", "GB": "en-GB", "UK": "en-GB", "PK": "en-PK",
    "IN": "en-IN", "DE": "de-DE", "FR": "fr-FR", "ES": "es-ES", "TR": "tr-TR",
}

# Approximate (city-level) coordinates per country, so a profile's
# geolocation can agree with its proxy/timezone instead of contradicting it.
# City chosen to match the locale's timezone (e.g. US -> New York for
# America/New_York). Accuracy is a plausible metres value, not a pinpoint.
COUNTRY_GEO = {
    "US": (40.7128, -74.0060), "GB": (51.5074, -0.1278),
    "UK": (51.5074, -0.1278),  "PK": (24.8607, 67.0011),
    "IN": (28.6139, 77.2090),  "DE": (52.5200, 13.4050),
    "FR": (48.8566, 2.3522),   "ES": (40.4168, -3.7038),
    "TR": (41.0082, 28.9784),
}

# Country -> the language its browsers are usually set to, for profiles whose
# languages follow the proxy's exit IP (Profile.auto_lang). Where English is
# the usual browser language despite another official one (India, Pakistan,
# Nigeria, the Philippines...), it's English.
COUNTRY_LANGUAGE = {
    "US": "en", "GB": "en", "UK": "en", "CA": "en", "AU": "en", "NZ": "en", "IE": "en",
    "IN": "en", "PK": "en", "NG": "en", "PH": "en", "SG": "en", "ZA": "en", "KE": "en",
    "BD": "bn", "DE": "de", "AT": "de", "CH": "de", "FR": "fr", "BE": "nl", "NL": "nl",
    "LU": "fr", "ES": "es", "MX": "es", "AR": "es", "CO": "es", "CL": "es", "PE": "es",
    "VE": "es", "EC": "es", "PT": "pt", "BR": "pt", "IT": "it", "PL": "pl", "CZ": "cs",
    "SK": "sk", "HU": "hu", "RO": "ro", "BG": "bg", "GR": "el", "HR": "hr", "RS": "sr",
    "SI": "sl", "UA": "uk", "RU": "ru", "BY": "ru", "KZ": "ru", "TR": "tr", "IL": "he",
    "SA": "ar", "AE": "ar", "EG": "ar", "MA": "ar", "DZ": "ar", "IQ": "ar", "IR": "fa",
    "SE": "sv", "NO": "nb", "DK": "da", "FI": "fi", "EE": "et", "LV": "lv", "LT": "lt",
    "JP": "ja", "KR": "ko", "CN": "zh", "TW": "zh", "HK": "zh", "VN": "vi", "TH": "th",
    "ID": "id", "MY": "ms",
}

# locale -> the country whose coordinates fit it, for when there's no proxy.
LOCALE_TO_COUNTRY = {
    "en-US": "US", "en-GB": "GB", "en-PK": "PK", "en-IN": "IN",
    "de-DE": "DE", "fr-FR": "FR", "es-ES": "ES", "tr-TR": "TR",
}

# Fonts that actually ship with each OS. Font-probing is a classic fingerprint
# vector — a "Windows" browser that can render Helvetica Neue but not Segoe UI
# is a giveaway — so each archetype carries its own realistic set.
FONTS = {
    "windows": [
        "Arial", "Arial Black", "Bahnschrift", "Calibri", "Cambria", "Candara",
        "Comic Sans MS", "Consolas", "Constantia", "Corbel", "Courier New",
        "Ebrima", "Franklin Gothic Medium", "Gabriola", "Gadugi", "Georgia",
        "Impact", "Ink Free", "Lucida Console", "Lucida Sans Unicode",
        "Malgun Gothic", "Microsoft Sans Serif", "MS Gothic", "MV Boli",
        "Nirmala UI", "Palatino Linotype", "Segoe Print", "Segoe Script",
        "Segoe UI", "SimSun", "Sylfaen", "Symbol", "Tahoma", "Times New Roman",
        "Trebuchet MS", "Verdana", "Webdings", "Wingdings",
    ],
    "macos": [
        "American Typewriter", "Andale Mono", "Arial", "Arial Black",
        "Avenir", "Avenir Next", "Baskerville", "Big Caslon", "Bodoni 72",
        "Bradley Hand", "Chalkboard", "Chalkduster", "Cochin", "Comic Sans MS",
        "Copperplate", "Courier", "Courier New", "Didot", "Futura", "Geneva",
        "Georgia", "Gill Sans", "Helvetica", "Helvetica Neue", "Herculanum",
        "Hoefler Text", "Impact", "Lucida Grande", "Luminari", "Marker Felt",
        "Menlo", "Monaco", "Optima", "Palatino", "Papyrus", "Phosphate",
        "Rockwell", "SF Pro", "Skia", "Snell Roundhand", "Times", "Times New Roman",
        "Trattatello", "Trebuchet MS", "Verdana", "Zapfino",
    ],
    "linux": [
        "Bitstream Charter", "Cantarell", "Century Schoolbook L", "Courier 10 Pitch",
        "DejaVu Sans", "DejaVu Sans Mono", "DejaVu Serif", "FreeMono", "FreeSans",
        "FreeSerif", "Liberation Mono", "Liberation Sans", "Liberation Serif",
        "Nimbus Mono PS", "Nimbus Roman", "Nimbus Sans", "Noto Sans", "Noto Serif",
        "Ubuntu", "Ubuntu Condensed", "Ubuntu Mono", "URW Bookman", "URW Gothic",
    ],
    "android": [
        "Droid Sans Mono", "Noto Color Emoji", "Noto Sans", "Noto Serif",
        "Roboto", "Roboto Condensed", "Roboto Mono",
    ],
}

# Real Android phones as coherent bundles. A mobile fingerprint is only
# convincing when the model name in the User-Agent, the Android version, the
# screen size, the GPU and the RAM all describe the *same* handset — a "Pixel 7"
# UA reporting an Adreno GPU on a 360x640 screen is an instant tell. The
# generator picks one of these whole, rather than mixing parts across phones.
# (screen is CSS pixels — what a phone browser reports for screen.width/height;
# dpr is the panel's devicePixelRatio, so screen x dpr = the real panel.)
ANDROID_DEVICES = [
    {"model": "Pixel 7", "dpr": 2.625, "android": "13", "screen": (412, 915), "cores": 8, "memory": 8,
     "webgl": ("Google Inc. (ARM)", "ANGLE (ARM, Mali-G710, OpenGL ES 3.2)")},
    {"model": "Pixel 8", "dpr": 2.625, "android": "14", "screen": (412, 915), "cores": 9, "memory": 8,
     "webgl": ("Google Inc. (ARM)", "ANGLE (ARM, Mali-G715, OpenGL ES 3.2)")},
    {"model": "Pixel 6", "dpr": 2.75, "android": "13", "screen": (393, 851), "cores": 8, "memory": 8,
     "webgl": ("Google Inc. (ARM)", "ANGLE (ARM, Mali-G78, OpenGL ES 3.2)")},
    {"model": "SM-G991B", "dpr": 3.0, "android": "13", "screen": (360, 800), "cores": 8, "memory": 8,
     "webgl": ("Google Inc. (ARM)", "ANGLE (ARM, Mali-G78, OpenGL ES 3.2)")},        # Galaxy S21
    {"model": "SM-S908B", "dpr": 3.75, "android": "14", "screen": (384, 854), "cores": 8, "memory": 12,
     "webgl": ("Google Inc. (Qualcomm)", "ANGLE (Qualcomm, Adreno (TM) 730, OpenGL ES 3.2)")},  # Galaxy S22 Ultra
    {"model": "M2101K6G", "dpr": 2.75, "android": "13", "screen": (393, 873), "cores": 8, "memory": 6,
     "webgl": ("Google Inc. (ARM)", "ANGLE (ARM, Mali-G77 MC9, OpenGL ES 3.2)")},    # Redmi Note 10
]

# devicePixelRatio per desktop screen. Every modern Mac is Retina (2), so a Mac
# reporting 1 is a tell. On Windows the CSS size gives the scaling away: 1536x864
# *is* a 1920x1080 panel at 125%, the default on most laptops; the other common
# sizes are 100%. Linux desktops overwhelmingly run unscaled.
DESKTOP_DPR = {
    "macos": {"default": 2.0},
    "windows": {(1536, 864): 1.25, (1280, 720): 1.5, "default": 1.0},
    "linux": {"default": 1.0},
}
# Scale factors real Windows / Linux display settings offer.
DESKTOP_DPR_STEPS = (1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5)


# The four desktop-capable operating systems we generate by default.
DESKTOP_OS = ["windows", "macos", "linux"]
ALL_OS = ["windows", "macos", "linux", "android"]
