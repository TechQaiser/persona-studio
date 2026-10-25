"""
WebGL capability table: the part of a GPU fingerprint beyond its name.

Fingerprinters don't stop at the renderer string. They read the whole
``getParameter`` table (texture and viewport limits, uniform and varying
counts), the supported-extension list and the shader precision formats. Those
come from the graphics stack the browser *really* runs on, so they give away a
renderer string that was changed without changing the machine: a profile that
says "Apple M1, Metal" but reports Direct3D 11 limits is a Windows PC.

Persona doesn't fake this table. A JS patch can't make the GPU honour limits it
doesn't have, and a getParameter that claims more than the driver delivers
breaks on the first big texture. Instead the real table is read during the
trust check, and two things are verified:

* **Backend agreement.** The table's shape must fit the renderer's graphics
  API. Only signatures that are unambiguous are used: Chrome's Direct3D 11
  backend (ANGLE) reports a 32767x32767 viewport, 4095 vertex uniform vectors
  (4096 before ANGLE reserved one) and 1024 fragment uniform vectors, which no
  OpenGL, Metal, GLES or SwiftShader stack does. (Measured on Chrome 151 with an
  RTX 5070; headless Chrome on the same PC renders through SwiftShader and
  reports an 8192 viewport.) Anything else gets no verdict rather than a guess.
* **Stability.** The table is stored with the profile the first time it's seen
  (``Fingerprint.webgl``). If it later changes, the profile is presenting a
  different GPU than the one its accounts already know.
"""

from __future__ import annotations

import hashlib
import json
from typing import Optional

# getParameter enums read by fingerprinting scripts (WebGL 1).
PARAMS = {
    "MAX_TEXTURE_SIZE": 0x0D33,
    "MAX_VIEWPORT_DIMS": 0x0D3A,
    "MAX_RENDERBUFFER_SIZE": 0x84E8,
    "MAX_CUBE_MAP_TEXTURE_SIZE": 0x851C,
    "ALIASED_POINT_SIZE_RANGE": 0x846D,
    "ALIASED_LINE_WIDTH_RANGE": 0x846E,
    "MAX_VERTEX_ATTRIBS": 0x8869,
    "MAX_TEXTURE_IMAGE_UNITS": 0x8872,
    "MAX_VERTEX_TEXTURE_IMAGE_UNITS": 0x8B4C,
    "MAX_COMBINED_TEXTURE_IMAGE_UNITS": 0x8B4D,
    "MAX_VERTEX_UNIFORM_VECTORS": 0x8DFB,
    "MAX_VARYING_VECTORS": 0x8DFC,
    "MAX_FRAGMENT_UNIFORM_VECTORS": 0x8DFD,
}

# Runs in the page; returns {params, extensions, precision, anisotropy} or null.
COLLECT_JS = """
(() => {
  const gl = document.createElement('canvas').getContext('webgl');
  if (!gl) return null;
  const params = {};
  for (const [name, num] of Object.entries(%s)) {
    const v = gl.getParameter(num);
    params[name] = (v && typeof v === 'object') ? Array.from(v) : v;
  }
  const prec = {};
  for (const [shader, sname] of [[gl.VERTEX_SHADER, 'vertex'], [gl.FRAGMENT_SHADER, 'fragment']])
    for (const [kind, kname] of [[gl.HIGH_FLOAT, 'HighFloat'], [gl.MEDIUM_FLOAT, 'MediumFloat'], [gl.HIGH_INT, 'HighInt']]) {
      const f = gl.getShaderPrecisionFormat(shader, kind);
      prec[sname + kname] = f ? [f.rangeMin, f.rangeMax, f.precision] : null;
    }
  const aniso = gl.getExtension('EXT_texture_filter_anisotropic');
  return {
    params,
    extensions: (gl.getSupportedExtensions() || []).slice().sort(),
    precision: prec,
    anisotropy: aniso ? gl.getParameter(aniso.MAX_TEXTURE_MAX_ANISOTROPY_EXT) : null,
  };
})()
""" % json.dumps(PARAMS)


def renderer_backend(renderer: str) -> Optional[str]:
    """The graphics API a renderer string claims: d3d11, d3d9, metal, gles,
    vulkan or opengl (None if it doesn't say)."""
    r = (renderer or "").lower()
    if "direct3d11" in r or "d3d11" in r:
        return "d3d11"
    if "direct3d9" in r or "d3d9" in r:
        return "d3d9"
    if "metal" in r:
        return "metal"
    if "opengl es" in r:
        return "gles"
    if "vulkan" in r:
        return "vulkan"
    if "opengl" in r:
        return "opengl"
    return None


def is_d3d11_shape(table: Optional[dict]) -> Optional[bool]:
    """Does this table come from Chrome's Direct3D 11 backend? None if the
    table is missing the values needed to tell."""
    params = (table or {}).get("params") or {}
    dims = params.get("MAX_VIEWPORT_DIMS")
    vuv = params.get("MAX_VERTEX_UNIFORM_VECTORS")
    fuv = params.get("MAX_FRAGMENT_UNIFORM_VECTORS")
    if not dims or vuv is None or fuv is None:
        return None
    return list(dims) == [32767, 32767] and vuv in (4095, 4096) and fuv == 1024


def backend_mismatch(renderer: str, table: Optional[dict]) -> Optional[str]:
    """Why the table can't belong to this renderer, or None if it can (or if
    there isn't enough evidence to say)."""
    claimed = renderer_backend(renderer)
    d3d = is_d3d11_shape(table)
    if claimed is None or d3d is None or claimed == "d3d9":
        return None
    if d3d and claimed != "d3d11":
        return (f"the renderer claims {claimed}, but the limits are Direct3D 11's "
                "(a Windows machine)")
    if not d3d and claimed == "d3d11":
        return "the renderer claims Direct3D 11, but the limits aren't Direct3D 11's"
    return None


def summarize(table: Optional[dict]) -> Optional[dict]:
    """What a profile stores: the table plus a short signature to compare."""
    if not table:
        return None
    return {**table, "signature": signature(table)}


def signature(table: dict) -> str:
    """A short, stable hash of everything in the table except the signature."""
    body = {k: v for k, v in table.items() if k != "signature"}
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def changes(stored: Optional[dict], seen: Optional[dict]) -> list[str]:
    """Human list of what differs between the stored table and a new reading."""
    if not stored or not seen:
        return []
    out = []
    sp, np_ = stored.get("params") or {}, seen.get("params") or {}
    for name in sorted(set(sp) | set(np_)):
        if sp.get(name) != np_.get(name):
            out.append(f"{name} {sp.get(name)} -> {np_.get(name)}")
    se, ne = set(stored.get("extensions") or []), set(seen.get("extensions") or [])
    if se != ne:
        gained, lost = sorted(ne - se), sorted(se - ne)
        if gained:
            out.append("new extensions: " + ", ".join(gained[:4]) + ("…" if len(gained) > 4 else ""))
        if lost:
            out.append("missing extensions: " + ", ".join(lost[:4]) + ("…" if len(lost) > 4 else ""))
    if stored.get("precision") != seen.get("precision"):
        out.append("shader precision formats changed")
    if stored.get("anisotropy") != seen.get("anisotropy"):
        out.append(f"max anisotropy {stored.get('anisotropy')} -> {seen.get('anisotropy')}")
    return out
