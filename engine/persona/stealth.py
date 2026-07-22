"""
Stealth script generation.

Playwright can set the user-agent, viewport, locale, timezone and proxy at the
context level, but a number of high-signal values live inside the page and have
to be patched there. This module builds a single JavaScript init script tailored
to a fingerprint, which the launcher injects before any page code runs via
``add_init_script``.

The patches here mirror the well-known, publicly documented evasions used by
anti-detect browsers (and puppeteer/playwright stealth plugins). The goal is that
the in-page values agree with the context-level values *and* don't carry the
tell-tale traces of an automated browser:

  * ``navigator.webdriver`` reads ``false`` and looks native (defined on the
    prototype, not as an own property);
  * ``window.chrome`` exists with a ``runtime`` stub;
  * ``navigator.plugins`` / ``mimeTypes`` report the modern Chrome PDF set
    instead of an empty list;
  * ``navigator.permissions.query`` agrees with ``Notification.permission``;
  * platform, hardwareConcurrency, deviceMemory, languages, WebGL vendor/renderer
    match the chosen device;
  * canvas noise is seeded so it stays stable per profile;
  * patched functions report native ``toString()`` so they can't be spotted.

Kept intentionally readable so contributors can audit exactly what is spoofed.
"""

from __future__ import annotations

import json

from .models import Fingerprint


def build_init_script(fp: Fingerprint) -> str:
    """Return a JS string that patches a page to match ``fp``."""
    cfg = {
        "platform": fp.platform,
        "uaPlatform": fp.ch_platform.strip('"'),
        "isMobile": fp.is_mobile,
        "chromeMajor": int(fp.chrome_version.split(".")[0]),
        "hardwareConcurrency": fp.hardware_concurrency,
        "deviceMemory": fp.device_memory,
        "languages": fp.languages,
        "webglVendor": fp.webgl_vendor,
        "webglRenderer": fp.webgl_renderer,
        "seed": fp.seed,
    }
    cfg_json = json.dumps(cfg)

    return (
        "(() => {\n"
        f"  const cfg = {cfg_json};\n"
        "\n"
        "  // Make an overridden function report native code, so its toString()\n"
        "  // doesn't reveal the patch.\n"
        "  const nativeStr = Function.prototype.toString;\n"
        "  const masked = new WeakMap();\n"
        "  const asNative = (fn, name) => {\n"
        "    masked.set(fn, name || fn.name || '');\n"
        "    return fn;\n"
        "  };\n"
        "  const toStringProxy = new Proxy(nativeStr, {\n"
        "    apply(target, thisArg, args) {\n"
        "      if (masked.has(thisArg)) return `function ${masked.get(thisArg)}() { [native code] }`;\n"
        "      return Reflect.apply(target, thisArg, args);\n"
        "    },\n"
        "  });\n"
        "  // eslint-disable-next-line no-extend-native\n"
        "  Function.prototype.toString = toStringProxy;\n"
        "\n"
        "  const define = (obj, prop, getter) => {\n"
        "    try {\n"
        "      Object.defineProperty(obj, prop, { get: asNative(getter, `get ${prop}`), configurable: true, enumerable: true });\n"
        "    } catch (e) {}\n"
        "  };\n"
        "\n"
        "  // --- webdriver: false, and defined on the prototype like real Chrome ---\n"
        "  try { delete Object.getPrototypeOf(navigator).webdriver; } catch (e) {}\n"
        "  try { delete navigator.webdriver; } catch (e) {}\n"
        "  define(Navigator.prototype, 'webdriver', () => false);\n"
        "\n"
        "  // --- Navigator basics ---\n"
        "  define(Navigator.prototype, 'platform', () => cfg.platform);\n"
        "  define(Navigator.prototype, 'hardwareConcurrency', () => cfg.hardwareConcurrency);\n"
        "  define(Navigator.prototype, 'deviceMemory', () => cfg.deviceMemory);\n"
        "  define(Navigator.prototype, 'languages', () => Object.freeze(cfg.languages.slice()));\n"
        "\n"
        "  // --- window.chrome (present on real Chrome, missing under automation) ---\n"
        "  try {\n"
        "    if (!window.chrome) window.chrome = {};\n"
        "    if (!window.chrome.runtime) window.chrome.runtime = {};\n"
        "    if (!window.chrome.app) window.chrome.app = { isInstalled: false };\n"
        "  } catch (e) {}\n"
        "\n"
        "  // --- Plugins & mimeTypes ---\n"
        "  // Headed Chrome already exposes the authentic PDF PluginArray, so we\n"
        "  // only synthesize one when the list is empty (typically headless), and\n"
        "  // we wire up the real prototypes/tags so it still reads as native.\n"
        "  try {\n"
        "    if (navigator.plugins.length === 0 &&\n"
        "        window.PluginArray && window.MimeTypeArray && window.Plugin && window.MimeType) {\n"
        "      const pdfNames = [\n"
        "        'PDF Viewer', 'Chrome PDF Viewer', 'Chromium PDF Viewer',\n"
        "        'Microsoft Edge PDF Viewer', 'WebKit built-in PDF',\n"
        "      ];\n"
        "      const mkMime = (type) => {\n"
        "        const m = { type, suffixes: 'pdf', description: 'Portable Document Format' };\n"
        "        Object.setPrototypeOf(m, MimeType.prototype);\n"
        "        return m;\n"
        "      };\n"
        "      const mimes = [mkMime('application/pdf'), mkMime('text/pdf')];\n"
        "      const mkArr = (items, proto, key) => {\n"
        "        const arr = {};\n"
        "        items.forEach((it, i) => { arr[i] = it; });\n"
        "        Object.defineProperty(arr, 'length', { value: items.length, enumerable: false });\n"
        "        arr.item = asNative((i) => items[i] || null, 'item');\n"
        "        arr.namedItem = asNative((n) => items.find((x) => x[key] === n) || null, 'namedItem');\n"
        "        Object.setPrototypeOf(arr, proto);\n"
        "        return arr;\n"
        "      };\n"
        "      const plugins = pdfNames.map((name) => {\n"
        "        const p = { name, filename: 'internal-pdf-viewer', description: 'Portable Document Format' };\n"
        "        mimes.forEach((m, i) => { p[i] = m; });\n"
        "        Object.defineProperty(p, 'length', { value: mimes.length, enumerable: false });\n"
        "        p.item = asNative((i) => mimes[i] || null, 'item');\n"
        "        p.namedItem = asNative((t) => mimes.find((m) => m.type === t) || null, 'namedItem');\n"
        "        Object.setPrototypeOf(p, Plugin.prototype);\n"
        "        return p;\n"
        "      });\n"
        "      const pluginArray = mkArr(plugins, PluginArray.prototype, 'name');\n"
        "      const mimeArray = mkArr(mimes, MimeTypeArray.prototype, 'type');\n"
        "      define(Navigator.prototype, 'plugins', () => pluginArray);\n"
        "      define(Navigator.prototype, 'mimeTypes', () => mimeArray);\n"
        "    }\n"
        "  } catch (e) {}\n"
        "\n"
        "  // --- permissions.query agrees with Notification.permission ---\n"
        "  try {\n"
        "    const orig = navigator.permissions.query.bind(navigator.permissions);\n"
        "    navigator.permissions.query = asNative(function query(params) {\n"
        "      if (params && params.name === 'notifications')\n"
        "        return Promise.resolve({ state: Notification.permission, onchange: null });\n"
        "      return orig(params);\n"
        "    }, 'query');\n"
        "  } catch (e) {}\n"
        "\n"
        "  // --- WebGL vendor / renderer (UNMASKED params 37445 / 37446) ---\n"
        "  const patchGL = (proto) => {\n"
        "    if (!proto) return;\n"
        "    const orig = proto.getParameter;\n"
        "    proto.getParameter = asNative(function getParameter(p) {\n"
        "      if (p === 37445) return cfg.webglVendor;\n"
        "      if (p === 37446) return cfg.webglRenderer;\n"
        "      return orig.call(this, p);\n"
        "    }, 'getParameter');\n"
        "  };\n"
        "  if (window.WebGLRenderingContext) patchGL(WebGLRenderingContext.prototype);\n"
        "  if (window.WebGL2RenderingContext) patchGL(WebGL2RenderingContext.prototype);\n"
        "\n"
        "  // --- Deterministic canvas noise (seeded, so it is stable per profile) ---\n"
        "  let s = cfg.seed >>> 0;\n"
        "  const rnd = () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; };\n"
        "  const origToDataURL = HTMLCanvasElement.prototype.toDataURL;\n"
        "  HTMLCanvasElement.prototype.toDataURL = asNative(function toDataURL(...args) {\n"
        "    try {\n"
        "      const ctx = this.getContext('2d');\n"
        "      if (ctx && this.width && this.height) {\n"
        "        const img = ctx.getImageData(0, 0, this.width, this.height);\n"
        "        for (let i = 0; i < img.data.length; i += 4) {\n"
        "          if (rnd() < 0.02) {\n"
        "            img.data[i]   ^= (rnd() * 2) | 0;\n"
        "            img.data[i+1] ^= (rnd() * 2) | 0;\n"
        "            img.data[i+2] ^= (rnd() * 2) | 0;\n"
        "          }\n"
        "        }\n"
        "        ctx.putImageData(img, 0, 0);\n"
        "      }\n"
        "    } catch (e) {}\n"
        "    return origToDataURL.apply(this, args);\n"
        "  }, 'toDataURL');\n"
        "})();\n"
    )
