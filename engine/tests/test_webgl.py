"""WebGL capability table: backend agreement and stability.

The two tables below were measured on a real Windows PC (Chrome 151, RTX 5070):
headed/GPU Chrome goes through ANGLE's Direct3D 11 backend, headless Chrome
without --enable-gpu through SwiftShader."""

from persona import webgl
from persona.fingerprint import generate, validate

D3D11 = {"params": {
    "MAX_TEXTURE_SIZE": 16384, "MAX_VIEWPORT_DIMS": [32767, 32767], "MAX_RENDERBUFFER_SIZE": 16384,
    "MAX_CUBE_MAP_TEXTURE_SIZE": 16384, "ALIASED_POINT_SIZE_RANGE": [1, 1024],
    "ALIASED_LINE_WIDTH_RANGE": [1, 1], "MAX_VERTEX_ATTRIBS": 16, "MAX_TEXTURE_IMAGE_UNITS": 16,
    "MAX_VERTEX_TEXTURE_IMAGE_UNITS": 16, "MAX_COMBINED_TEXTURE_IMAGE_UNITS": 32,
    "MAX_VERTEX_UNIFORM_VECTORS": 4095, "MAX_VARYING_VECTORS": 30, "MAX_FRAGMENT_UNIFORM_VECTORS": 1024},
    "extensions": ["ANGLE_instanced_arrays", "EXT_texture_filter_anisotropic"],
    "precision": {"fragmentHighFloat": [127, 127, 23]}, "anisotropy": 16}
SWIFTSHADER = {"params": {
    "MAX_TEXTURE_SIZE": 8192, "MAX_VIEWPORT_DIMS": [8192, 8192], "MAX_RENDERBUFFER_SIZE": 8192,
    "MAX_CUBE_MAP_TEXTURE_SIZE": 16384, "ALIASED_POINT_SIZE_RANGE": [1, 1023],
    "ALIASED_LINE_WIDTH_RANGE": [1, 1], "MAX_VERTEX_ATTRIBS": 16, "MAX_TEXTURE_IMAGE_UNITS": 32,
    "MAX_VERTEX_TEXTURE_IMAGE_UNITS": 32, "MAX_COMBINED_TEXTURE_IMAGE_UNITS": 64,
    "MAX_VERTEX_UNIFORM_VECTORS": 4096, "MAX_VARYING_VECTORS": 31, "MAX_FRAGMENT_UNIFORM_VECTORS": 4096},
    "extensions": ["ANGLE_instanced_arrays"], "precision": {"fragmentHighFloat": [127, 127, 23]},
    "anisotropy": 16}

WIN = "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)"
MAC = "ANGLE (Apple, ANGLE Metal Renderer: Apple M1, Unspecified Version)"


def test_renderer_backend():
    assert webgl.renderer_backend(WIN) == "d3d11"
    assert webgl.renderer_backend(MAC) == "metal"
    assert webgl.renderer_backend("ANGLE (ARM, Mali-G78, OpenGL ES 3.2)") == "gles"
    assert webgl.renderer_backend("ANGLE (Intel, Mesa Intel(R) UHD Graphics, OpenGL 4.6)") == "opengl"
    assert webgl.renderer_backend("ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device))") == "vulkan"
    assert webgl.renderer_backend("Intel Iris") is None


def test_d3d11_shape_from_real_tables():
    assert webgl.is_d3d11_shape(D3D11) is True
    assert webgl.is_d3d11_shape(SWIFTSHADER) is False
    older = {"params": {**D3D11["params"], "MAX_VERTEX_UNIFORM_VECTORS": 4096}}
    assert webgl.is_d3d11_shape(older) is True            # pre-reservation ANGLE
    assert webgl.is_d3d11_shape({"params": {}}) is None
    assert webgl.is_d3d11_shape(None) is None


def test_backend_mismatch():
    assert webgl.backend_mismatch(WIN, D3D11) is None
    assert "Windows machine" in webgl.backend_mismatch(MAC, D3D11)        # Mac profile on a PC
    assert "aren't Direct3D 11's" in webgl.backend_mismatch(WIN, SWIFTSHADER)  # headless tell
    assert webgl.backend_mismatch(MAC, SWIFTSHADER) is None               # no evidence either way
    assert webgl.backend_mismatch("ANGLE (x, Direct3D9Ex)", SWIFTSHADER) is None


def test_signature_is_stable_and_sensitive():
    a, b = webgl.summarize(D3D11), webgl.summarize(dict(D3D11))
    assert a["signature"] == b["signature"] == webgl.signature(a)
    other = webgl.summarize({**D3D11, "anisotropy": 8})
    assert other["signature"] != a["signature"]


def test_changes_explains_the_difference():
    diff = webgl.changes(webgl.summarize(D3D11), webgl.summarize(SWIFTSHADER))
    assert any(d.startswith("MAX_VIEWPORT_DIMS [32767, 32767] -> [8192, 8192]") for d in diff)
    assert any("missing extensions: EXT_texture_filter_anisotropic" in d for d in diff)
    assert webgl.changes(D3D11, D3D11) == []


def test_validate_flags_a_table_that_no_longer_fits_the_gpu():
    fp = generate(os="windows", seed=3)
    fp.webgl = webgl.summarize(D3D11)
    assert validate(fp) == []
    mac = generate(os="macos", seed=3)
    mac.webgl = webgl.summarize(D3D11)          # GPU switched to a Mac after the reading
    assert any("webgl limits" in i for i in validate(mac))


def test_grade_uses_the_table():
    from persona.probe import _grade
    fp = generate(os="windows", seed=4)
    seen = {"webdriver": False, "webdriverOwn": False, "hasChrome": True, "plugins": 5,
            "userAgent": fp.user_agent, "platform": fp.platform, "languages": list(fp.languages),
            "cores": fp.hardware_concurrency, "memory": 8, "timezone": fp.timezone,
            "toStringNative": True, "permissionsAgree": True, "canvasStable": True,
            "webglVendor": fp.webgl_vendor, "webglRenderer": fp.webgl_renderer}
    names = lambda rep: {c["name"]: c["ok"] for c in rep["checks"]}

    good = names(_grade(fp, {**seen, "webgl": webgl.summarize(D3D11)}, "playwright"))
    assert good["WebGL limits fit the GPU's graphics API"] is True
    assert "Same WebGL device as before" not in good          # no baseline yet

    fp.webgl = webgl.summarize(D3D11)
    moved = names(_grade(fp, {**seen, "webgl": webgl.summarize(SWIFTSHADER)}, "playwright"))
    assert moved["WebGL limits fit the GPU's graphics API"] is False
    assert moved["Same WebGL device as before"] is False

    camoufox = names(_grade(fp, {**seen, "webgl": webgl.summarize(SWIFTSHADER)}, "camoufox"))
    assert not any("WebGL" in n for n in camoufox)            # Firefox brings its own


def test_dashboard_roundtrip_keeps_the_table():
    from persona.server import to_dashboard_profile, to_engine_profile
    d = {"id": "a", "name": "x", "os": "Windows", "webglRenderer": WIN,
         "webglTable": webgl.summarize(D3D11)}
    prof = to_engine_profile(d)
    assert prof.fingerprint.webgl["signature"] == d["webglTable"]["signature"]
    assert to_dashboard_profile(prof)["webglTable"] == d["webglTable"]


def test_headless_playwright_uses_the_gpu():
    import inspect
    from persona import drivers
    assert '"--enable-gpu"' in inspect.getsource(drivers._launch_playwright_like)
