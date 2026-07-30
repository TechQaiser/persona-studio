import React, { useState, useMemo, useEffect } from "react";
import { api } from "./api";
import {
  Layers, Globe, FolderTree, Copy, Trash2, Play, Square, Pencil,
  Search, Plus, Filter, ShieldCheck, ShieldAlert, X, Zap, Users,
  Cpu, MonitorSmartphone, Fingerprint, Wifi, WifiOff, Check, Clipboard,
  Settings, Boxes, Activity, MapPin, Clock, Camera, Mic, Blocks,
  RefreshCw, Server, Sparkles, ArrowRight, Star, Circle,
  Cookie, Download, Upload, Flame, Link2,
} from "lucide-react";

/* ================================================================== *
 *  Persona Studio — anti-detect browser profile manager
 *
 *  Persona MANAGES the identity (coherent fingerprint, proxy, session).
 *  A pluggable ENGINE renders it in a real browser. The UI is theme-aware,
 *  dark-first, and connects to the engine API when it's running (live mode),
 *  otherwise falls back to sample data (demo mode).
 * ================================================================== */

/* ---- design tokens: "ink violet" identity console ---------------- */
const T = {
  bg: "#0B0B10", bg2: "#101017", surface: "#15151F", surface2: "#1C1C2A",
  line: "#282840", lineSoft: "#1E1E2E",
  text: "#ECEDF5", muted: "#989BB6", dim: "#5B5E7A",
  violet: "#8B7CFF", violetDeep: "#6D5CE8", violetDim: "#2C265221",
  lilac: "#B7ADFF", mint: "#4FE0B0", mintDim: "#123A31",
  amber: "#F2B84B", red: "#FF6B7A", grey: "#6B6E88",
};
const FONT = {
  display: '"Space Grotesk", ui-sans-serif, system-ui, sans-serif',
  body: '"Inter", ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif',
  mono: '"JetBrains Mono", ui-monospace, Menlo, monospace',
};

/* ---- warm-up verticals (mirrors persona/warmup.py PRESETS) ------- */
const WARMUP_PRESETS = [
  { key: "general", label: "General" },
  { key: "ads", label: "Ads / media" },
  { key: "ecommerce", label: "E-commerce" },
  { key: "crypto", label: "Crypto" },
  { key: "social", label: "Social" },
  { key: "news", label: "News" },
];

/* ---- device data (mirrors persona/devices.py) -------------------- */
const OS_LIST = ["Windows", "macOS", "Linux", "Android"];
const GPUS = {
  Windows: [
    "ANGLE (NVIDIA GeForce RTX 3060 Direct3D11)",
    "ANGLE (NVIDIA GeForce GTX 1660 Ti Direct3D11)",
    "ANGLE (Intel UHD Graphics 630 Direct3D11)",
    "ANGLE (AMD Radeon RX 6600 Direct3D11)",
  ],
  macOS: [
    "ANGLE (Apple M1, OpenGL 4.1)",
    "ANGLE (Apple M2, OpenGL 4.1)",
    "ANGLE (Intel Iris Plus Graphics, OpenGL 4.1)",
  ],
  Linux: [
    "ANGLE (NVIDIA GeForce GTX 1050 Ti, OpenGL 4.5)",
    "ANGLE (Mesa Intel UHD Graphics, OpenGL 4.6)",
  ],
  Android: [
    "ANGLE (Qualcomm Adreno 660, OpenGL ES 3.2)",
    "ANGLE (ARM Mali-G78, OpenGL ES 3.2)",
  ],
};
const SCREENS = {
  Windows: ["1920x1080", "1366x768", "2560x1440", "1536x864"],
  macOS: ["2560x1600", "1440x900", "1728x1117"],
  Linux: ["1920x1080", "1366x768"],
  Android: ["360x800", "393x873", "412x915"],
};
const CORES = { Windows: [4, 6, 8, 12, 16], macOS: [8, 10, 12], Linux: [4, 8, 16], Android: [6, 8] };
const RAM = { Windows: [8, 16, 32], macOS: [8, 16, 32], Linux: [8, 16], Android: [4, 6, 8] };
const LOCALES = {
  "en-US": "America/New_York", "en-GB": "Europe/London", "en-PK": "Asia/Karachi",
  "en-IN": "Asia/Kolkata", "de-DE": "Europe/Berlin", "fr-FR": "Europe/Paris",
  "es-ES": "Europe/Madrid", "tr-TR": "Europe/Istanbul",
};
const COUNTRY_LOCALE = { US: "en-US", GB: "en-GB", PK: "en-PK", IN: "en-IN", DE: "de-DE", FR: "fr-FR", ES: "es-ES", TR: "tr-TR" };
const MODES = {
  canvas: ["Noise", "Block", "Real"], webrtc: ["Altered", "Disabled", "Real"],
  audio: ["Noise", "Real"], fonts: ["Masked", "Real"], geo: ["Prompt", "Allow", "Block"],
};

/* ---- launch engines (mirrors persona/drivers.py) ----------------- */
const ENGINE_ORDER = ["cloak", "camoufox", "patchright", "playwright"];
const ENGINE_META = {
  cloak: {
    label: "CloakBrowser", kind: "Patched Chromium", strength: 4, recommended: true,
    tagline: "Fingerprints patched at the C++ source level.",
    desc: "A real Chromium binary, not JavaScript tricks. Reaches TLS/CDP-grade detection (Cloudflare, DataDome, reCAPTCHA v3) that injection can't touch.",
    install: "pip install cloakbrowser", docs: "https://github.com/CloakHQ/CloakBrowser",
  },
  camoufox: {
    label: "Camoufox", kind: "Patched Firefox", strength: 4, recommended: true,
    tagline: "Engine-level spoofing with its own coherent fingerprint.",
    desc: "A patched Firefox that spoofs at the C++ level and generates its own consistent identity. Among the strongest open options.",
    install: 'pip install "camoufox[geoip]" && camoufox fetch', docs: "https://github.com/daijro/camoufox",
  },
  patchright: {
    label: "Patchright", kind: "Patched Playwright", strength: 3, recommended: false,
    tagline: "Drop-in patched Playwright.",
    desc: "Closes navigator.webdriver and CDP leaks the stock engine leaves behind. Same API you already know, meaningfully stealthier.",
    install: "pip install patchright && patchright install chromium",
    docs: "https://github.com/Kaliiiiiiiiii-Vinyzu/patchright-python",
  },
  playwright: {
    label: "Playwright", kind: "Stock Chromium", strength: 2, recommended: false, builtin: true,
    tagline: "Built in. Works out of the box.",
    desc: "Stock Chromium plus Persona's injected stealth script. Clears basic bot tests (BrowserScan, sannysoft); not Cloudflare-grade.",
    install: null, docs: null,
  },
};

/* ---- coherence check (mirrors persona/fingerprint.validate) ------ */
// A GPU is coherent if it's one we offer, or if its graphics API matches the OS
// (Windows → Direct3D, macOS/Linux → desktop OpenGL). The second clause lets a
// profile carry the machine's real GPU after "Auto-adjust" without a false flag.
function webglPlausible(os, renderer) {
  if (!renderer) return true;
  if (GPUS[os]?.includes(renderer)) return true;
  const r = renderer.toLowerCase();
  const d3d = r.includes("direct3d") || r.includes("d3d11");
  const gl = r.includes("opengl");
  if (os === "Windows") return d3d;
  if (os === "macOS") return gl && !d3d;
  if (os === "Linux") return gl && !d3d;
  if (os === "Android") return r.includes("opengl es") || r.includes("adreno") || r.includes("mali");
  return false;
}
function screenPlausible(os, screen) {
  if (!screen || SCREENS[os]?.includes(screen)) return true;
  const [w, h] = screen.split("x").map(Number);
  return w >= 320 && w <= 8000 && h >= 480 && h <= 5000;   // any real display
}
function coherence(p) {
  const issues = [];
  if (p.webglRenderer && !webglPlausible(p.os, p.webglRenderer))
    issues.push("GPU doesn't belong to " + p.os);
  if (p.screen && !screenPlausible(p.os, p.screen))
    issues.push("Screen resolution unusual for " + p.os);
  if (p.locale && p.timezone && LOCALES[p.locale] !== p.timezone)
    issues.push("Timezone doesn't match locale");
  if (p.cores && !(Number(p.cores) >= 2 && Number(p.cores) <= 128))
    issues.push("CPU cores atypical for " + p.os);
  if (p.proxy?.country && COUNTRY_LOCALE[p.proxy.country] &&
      COUNTRY_LOCALE[p.proxy.country] !== p.locale)
    issues.push("Locale differs from proxy country (" + p.proxy.country + ")");
  return issues;
}

/* ---- seed data --------------------------------------------------- */
const FOLDERS = ["All profiles", "Facebook Ads", "Amazon Stores", "Crypto", "QA Testing"];
let uid = 100;
// Collision-resistant local id: a counter (unique within a page load) plus a
// random suffix (so ids don't repeat across reloads / other sessions). In live
// mode the server assigns its own id anyway; this is for demo/local state.
const nid = () => (++uid).toString(36) + Math.random().toString(36).slice(2, 6);

const seed = [
  mk("FB-Ads-01", "Facebook Ads", "running", "Windows", ["client-a"], "US"),
  mk("FB-Ads-02", "Facebook Ads", "stopped", "Windows", ["client-a"], "US"),
  mk("AMZ-Store-EU", "Amazon Stores", "running", "macOS", ["eu"], "DE"),
  mk("Crypto-Air-07", "Crypto", "stopped", "Linux", ["airdrop"], null),
  mk("PK-Mobile-01", "QA Testing", "running", "Android", ["mobile", "urdu"], "PK"),
  mk("QA-Sandbox", "QA Testing", "stopped", "Windows", ["internal"], "GB"),
];

function mk(name, folder, status, os, tags, country) {
  const locale = country && COUNTRY_LOCALE[country] ? COUNTRY_LOCALE[country] : "en-US";
  return {
    id: nid(), name, folder, status, os, tags, engine: "playwright",
    browser: "Chrome", browserVersion: "128.0.0.0", userAgent: uaFor(os),
    screen: SCREENS[os][0], cores: CORES[os][1], memory: RAM[os][1],
    webglVendor: os === "macOS" ? "Google Inc. (Apple)" : "Google Inc. (NVIDIA)",
    webglRenderer: GPUS[os][0],
    canvas: "Noise", webrtc: "Altered", audio: "Noise", fonts: "Masked",
    locale, timezone: LOCALES[locale], geo: "Prompt",
    mediaVideo: 1, mediaAudio: 1, dnt: false,
    proxy: country ? { type: "HTTP", host: "res-" + country.toLowerCase() + ".proxy.io", port: "8080", user: "u" + name.length, pass: "•••••", country } : null,
    notes: "", startupUrls: "", extensions: "",
    lastActive: status === "running" ? "now" : ["2h ago", "yesterday", "3d ago"][name.length % 3],
  };
}
function uaFor(os, chrome = "128.0.0.0") {
  const tok = { Windows: "Windows NT 10.0; Win64; x64", macOS: "Macintosh; Intel Mac OS X 10_15_7", Linux: "X11; Linux x86_64", Android: "Linux; Android 13; Pixel 7" }[os];
  const mob = os === "Android" ? " Mobile" : "";
  return `Mozilla/5.0 (${tok}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/${chrome}${mob} Safari/537.36`;
}
// Guess the WebGL vendor string from a renderer's GPU family (mirrors server).
function vendorFor(renderer) {
  const r = (renderer || "").toLowerCase();
  for (const [tok, name] of [["nvidia", "NVIDIA"], ["radeon", "AMD"], ["amd", "AMD"],
    ["intel", "Intel"], ["apple", "Apple"], ["adreno", "Qualcomm"], ["mali", "ARM"]])
    if (r.includes(tok)) return `Google Inc. (${name})`;
  return "Google Inc.";
}
const CHROME_VERSIONS = ["125.0.0.0", "126.0.0.0", "127.0.0.0", "128.0.0.0"];

/* ================================================================== */
export default function App() {
  const [profiles, setProfiles] = useState(seed);
  const [view, setView] = useState("profiles");
  const [folder, setFolder] = useState("All profiles");
  const [query, setQuery] = useState("");
  const [sel, setSel] = useState(new Set());
  const [editor, setEditor] = useState(null);
  const [bulk, setBulk] = useState(false);
  const [sync, setSync] = useState(false);   // "edit all selected" modal
  const [filters, setFilters] = useState({ status: "", engine: "", os: "", proxy: "", tag: "" });
  const [mode, setMode] = useState("connecting");   // connecting | live | demo
  const [engines, setEngines] = useState(null);      // {name: installed} from API
  const [defaultEngine, setDefaultEngine] = useState(ENGINE_ORDER[0]); // new-profile default

  const live = mode === "live";

  const refresh = async () => setProfiles(await api.list());
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const up = await api.health();
      if (cancelled) return;
      if (up) {
        try {
          await refresh();
          try { setEngines(await api.engines()); } catch { /* optional */ }
          try { const cfg = await api.getConfig(); if (cfg?.default_engine) setDefaultEngine(cfg.default_engine); } catch { /* optional */ }
          setMode("live");
        } catch { setMode("demo"); }
      } else { setMode("demo"); }
    })();
    return () => { cancelled = true; };
  }, []);

  // Keep run status in sync: the browser can be closed by the user directly, so
  // poll the API in live mode and flip the launch button back to "start".
  useEffect(() => {
    if (!live) return;
    let cancelled = false;
    // Poll less often once the list is large — refetching thousands of profiles
    // every few seconds is wasteful, and run-status doesn't change that fast.
    const every = profiles.length > 500 ? 12000 : 3000;
    const id = setInterval(() => {
      if (!cancelled && !editor && !bulk && !sync) refresh().catch(() => {});
    }, every);
    return () => { cancelled = true; clearInterval(id); };
  }, [live, editor, bulk, sync, profiles.length > 500]);

  const filtered = useMemo(() =>
    profiles.filter(p =>
      (folder === "All profiles" || p.folder === folder) &&
      (p.name.toLowerCase().includes(query.toLowerCase()) ||
       p.tags.some(t => t.includes(query.toLowerCase()))) &&
      (!filters.status || p.status === filters.status) &&
      (!filters.engine || (p.engine || "playwright") === filters.engine) &&
      (!filters.os || p.os === filters.os) &&
      (!filters.tag || (p.tags || []).includes(filters.tag)) &&
      (!filters.proxy || (filters.proxy === "with" ? !!p.proxy : !p.proxy))),
    [profiles, folder, query, filters]);

  // Every distinct tag in use, for the filter popover.
  const allTags = useMemo(
    () => [...new Set(profiles.flatMap(p => p.tags || []))].sort(),
    [profiles]);

  // Memoised so a 10k-profile list isn't re-scanned on every render / poll tick.
  const { running, proxyCount, coherentCount } = useMemo(() => ({
    running: profiles.filter(p => p.status === "running").length,
    proxyCount: new Set(profiles.filter(p => p.proxy).map(p => p.proxy.host)).size,
    coherentCount: profiles.filter(p => coherence(p).length === 0).length,
  }), [profiles]);

  const toggleRun = async (id) => {
    const p = profiles.find(x => x.id === id);
    if (live) {
      try { await (p?.status === "running" ? api.stop(id) : api.launch(id)); await refresh(); }
      catch (e) { alert("Launch failed: " + e.message); }
      return;
    }
    setProfiles(ps => ps.map(x => x.id === id ? { ...x, status: x.status === "running" ? "stopped" : "running", lastActive: "now" } : x));
  };
  const clone = async (p) => {
    const copy = { ...p, id: undefined, name: p.name + "-copy", status: "stopped", lastActive: "never", _new: true };
    if (live) { try { await api.create(copy); await refresh(); } catch (e) { alert("Clone failed: " + e.message); } return; }
    setProfiles(ps => [...ps, { ...copy, id: nid() }]);
  };
  const remove = async (id) => {
    if (live) { try { await api.remove(id); await refresh(); } catch (e) { alert("Delete failed: " + e.message); } return; }
    setProfiles(ps => ps.filter(p => p.id !== id));
  };
  const save = async (p) => {
    if (p.engine) setDefaultEngine(p.engine);   // "last engine wins" for the next new profile
    if (live) {
      try { const exists = profiles.some(x => x.id === p.id) && !p._new; await (exists ? api.update(p) : api.create({ ...p, id: undefined })); await refresh(); }
      catch (e) { alert("Save failed: " + e.message); }
      return;
    }
    setProfiles(ps => ps.some(x => x.id === p.id) ? ps.map(x => x.id === p.id ? p : x) : [...ps, p]);
  };

  // Import profiles exported from GoLogin / AdsPower / Multilogin.
  const importProfiles = () => {
    if (!live) { alert("Start the engine (persona serve) to import profiles."); return; }
    const inp = document.createElement("input");
    inp.type = "file"; inp.accept = ".json,application/json";
    inp.onchange = async () => {
      const f = inp.files?.[0];
      if (!f) return;
      try {
        const res = await api.importProfiles(await f.text());
        await refresh();
        const flagged = (res.results || []).filter(r => r.issues?.length).length;
        alert(`Imported ${res.imported} profile${res.imported === 1 ? "" : "s"}.`
          + (flagged ? ` ${flagged} flagged for review — open them to see the coherence notes.` : ""));
      } catch (e) { alert("Import failed: " + e.message); }
    };
    inp.click();
  };

  const toggleSel = (id) => setSel(s => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const allSel = filtered.length > 0 && filtered.every(p => sel.has(p.id));

  return (
    <div style={{ background: T.bg, color: T.text, minHeight: "100vh", fontFamily: FONT.body }}>
      <style>{css}</style>
      <div className="ps-shell">
        {/* ---- Sidebar ---- */}
        <aside className="ps-side">
          <div className="ps-brand">
            <div className="ps-logo"><span className="ps-logo-glow" /><Fingerprint size={19} color="#fff" strokeWidth={2.2} /></div>
            <div>
              <div className="ps-brand-name">Persona</div>
              <div className="ps-brand-sub">Studio</div>
            </div>
          </div>

          <nav className="ps-nav">
            {[
              ["profiles", Layers, "Profiles"],
              ["health", Activity, "Health"],
              ["engines", Blocks, "Engines"],
              ["proxies", Globe, "Proxies"],
              ["folders", FolderTree, "Folders"],
              ["automation", Zap, "Automation"],
              ["team", Users, "Team"],
              ["settings", Settings, "Settings"],
            ].map(([k, Ic, label]) => (
              <button key={k} onClick={() => setView(k)} className={"ps-navitem" + (view === k ? " active" : "")}>
                <Ic size={16} /> <span>{label}</span>
                {k === "engines" && <span className="ps-nav-tag">new</span>}
              </button>
            ))}
          </nav>

          <div className="ps-folders">
            <div className="ps-folders-h">Folders</div>
            {FOLDERS.map(f => (
              <button key={f} onClick={() => { setView("profiles"); setFolder(f); }}
                className={"ps-folder" + (folder === f && view === "profiles" ? " active" : "")}>
                <FolderTree size={13} />
                <span style={{ flex: 1, textAlign: "left" }}>{f}</span>
                <span className="ps-count">{f === "All profiles" ? profiles.length : profiles.filter(p => p.folder === f).length}</span>
              </button>
            ))}
          </div>

          <div className={"ps-side-foot " + mode} title={live ? "Connected to the engine — launching opens a real browser." : "Engine API not found — sample data only. Start it with: persona serve"}>
            <span className="ps-foot-dot" />
            <span>{mode === "connecting" ? "Connecting…" : live ? "Engine online" : "Demo mode"}</span>
            <span className="ps-foot-ver">v0.1.0</span>
          </div>
        </aside>

        {/* ---- Main ---- */}
        <main className="ps-main">
          <div className="ps-stats">
            <Stat icon={<Boxes size={16} />} label="Profiles" value={profiles.length} />
            <Stat icon={<Activity size={16} />} label="Running" value={running} accent={T.mint} pulse={running > 0} />
            <Stat icon={<Server size={16} />} label="Proxies" value={proxyCount} accent={T.lilac} />
            <Stat icon={<ShieldCheck size={16} />} label="Coherent"
              value={coherentCount + "/" + profiles.length} accent={T.violet} />
            <div style={{ flex: 1 }} />
            <button className="ps-btn ghost" onClick={importProfiles}><Download size={14} /> Import</button>
            <button className="ps-btn ghost" onClick={() => setBulk(true)}><Boxes size={14} /> Bulk create</button>
            <button className="ps-btn primary" onClick={() => setEditor(newProfile(folder, defaultEngine))}><Plus size={15} /> New profile</button>
          </div>

          {view === "profiles" && (
            <ProfilesView {...{ filtered, query, setQuery, folder, sel, setSel, toggleSel, allSel, toggleRun, clone, remove, setEditor, setProfiles, setSync, filters, setFilters, allTags, live, refresh }} />
          )}
          {view === "health" && <HealthView profiles={profiles} live={live} refresh={refresh} setEditor={setEditor} />}
          {view === "engines" && <EnginesView engines={engines} live={live} />}
          {view === "proxies" && <ProxiesView profiles={profiles} live={live} refresh={refresh} />}
          {view === "automation" && <AutomationView profiles={profiles} live={live} refresh={refresh} />}
          {!["profiles", "health", "engines", "proxies", "automation"].includes(view) && <Placeholder view={view} />}
        </main>
      </div>

      {editor && <Editor profile={editor} live={live} onClose={() => setEditor(null)} onSave={(p) => { save(p); setEditor(null); }} />}
      {sync && <SyncModal ids={[...sel]} onClose={() => setSync(false)} onApply={async (patch) => {
        const ids = [...sel];
        if (live) {
          try { await api.bulkUpdate(ids, patch); await refresh(); }
          catch (e) { alert("Bulk edit failed: " + e.message); }
        } else {
          const { addTags, ...fields } = patch;
          setProfiles(ps => ps.map(p => !ids.includes(p.id) ? p : {
            ...p, ...fields,
            timezone: patch.locale ? LOCALES[patch.locale] : p.timezone,
            tags: addTags ? [...new Set([...p.tags, ...addTags])] : p.tags,
          }));
        }
        if (patch.engine) setDefaultEngine(patch.engine);
        setSel(new Set());
        setSync(false);
      }} />}
      {bulk && <BulkModal onClose={() => setBulk(false)} folder={folder} defaultEngine={defaultEngine}
        onCreate={async (list, onProgress) => {
          if (live) {
            const CHUNK = 500;   // one request per chunk keeps 10k creates snappy
            for (let i = 0; i < list.length; i += CHUNK) {
              await api.batchCreate(list.slice(i, i + CHUNK));
              onProgress?.(Math.min(list.length, i + CHUNK), list.length);
            }
            await refresh();
          } else {
            setProfiles(ps => [...ps, ...list]);
            onProgress?.(list.length, list.length);
          }
        }} />}
    </div>
  );
}

/* ---- Profiles view ----------------------------------------------- */
function ProfilesView({ filtered, query, setQuery, folder, sel, setSel, toggleSel, allSel, toggleRun, clone, remove, setEditor, setProfiles, setSync, filters, setFilters, allTags, live, refresh }) {
  const [filterOpen, setFilterOpen] = useState(false);
  const activeFilters = Object.values(filters).filter(Boolean).length;
  const setFilter = (key, value) => setFilters(f => ({ ...f, [key]: f[key] === value ? "" : value }));
  const clearFilters = () => setFilters({ status: "", engine: "", os: "", proxy: "", tag: "" });

  // Warm up every selected profile (live only — it opens real headless browsers).
  const warmSelected = async () => {
    const ids = [...sel];
    if (!live) { alert("Warm-up runs against the live engine — start `persona serve` first."); return; }
    setSel(new Set());
    await Promise.all(ids.map(id => api.warmup(id, 5, "general").catch(() => {})));
    await refresh();
  };

  // Export the selected profiles as one JSON file (config: fingerprint, proxy,
  // tags — not the browser session; use `persona backup` for a full session).
  const exportSelected = () => {
    const chosen = filtered.filter(p => sel.has(p.id));
    const blob = new Blob([JSON.stringify(chosen, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `persona-profiles-${chosen.length}.json`; a.click();
    URL.revokeObjectURL(url);
  };

  // Pagination keeps the grid responsive when there are thousands of profiles.
  const PAGE = 100;
  const [page, setPage] = useState(0);
  useEffect(() => { setPage(0); }, [query, folder, filters.status, filters.engine, filters.os, filters.proxy]);
  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE));
  const cur = Math.min(page, pageCount - 1);
  const rows = filtered.slice(cur * PAGE, cur * PAGE + PAGE);

  const FilterRow = ({ label, options, value, onPick }) => (
    <div className="ps-filter-row">
      <span className="ps-filter-label">{label}</span>
      <div className="ps-filter-opts">
        {options.map(([val, text]) => (
          <button key={val} className={"ps-chip" + (value === val ? " on" : "")}
            onClick={() => onPick(val)}>{text}</button>
        ))}
      </div>
    </div>
  );

  return (
    <>
      <div className="ps-toolbar">
        <div className="ps-search">
          <Search size={15} color={T.dim} />
          <input placeholder="Search profiles, tags…" value={query} onChange={e => setQuery(e.target.value)} />
        </div>
        <div className="ps-crumb"><FolderTree size={13} /> {folder}</div>
        <div style={{ flex: 1 }} />
        {sel.size > 0 && (
          <div className="ps-bulkbar">
            <span>{sel.size} selected</span>
            <button onClick={() => { sel.forEach(toggleRun); setSel(new Set()); }}><Play size={13} /> Launch</button>
            <button onClick={warmSelected}><Flame size={13} /> Warm up</button>
            <button onClick={() => setSync(true)}><Copy size={13} /> Edit all</button>
            <button onClick={exportSelected}><Download size={13} /> Export</button>
            <button className="danger" onClick={async () => { const ids = [...sel]; setSel(new Set()); if (live) { for (const id of ids) { try { await api.remove(id); } catch {} } await refresh(); } else { setProfiles(ps => ps.filter(p => !ids.includes(p.id))); } }}><Trash2 size={13} /> Delete</button>
          </div>
        )}
        <div className="ps-filter-wrap">
          <button className={"ps-btn ghost sm" + (activeFilters ? " active" : "")}
            onClick={() => setFilterOpen(o => !o)}>
            <Filter size={13} /> Filter{activeFilters ? ` · ${activeFilters}` : ""}
          </button>
          {filterOpen && (
            <>
              <div className="ps-filter-scrim" onClick={() => setFilterOpen(false)} />
              <div className="ps-filter-pop">
                <div className="ps-filter-head">
                  <span>Filter profiles</span>
                  {activeFilters > 0 && <button className="ps-filter-clear" onClick={clearFilters}>Clear all</button>}
                </div>
                <FilterRow label="Status" value={filters.status} onPick={v => setFilter("status", v)}
                  options={[["running", "Running"], ["stopped", "Stopped"]]} />
                <FilterRow label="Engine" value={filters.engine} onPick={v => setFilter("engine", v)}
                  options={ENGINE_ORDER.map(en => [en, ENGINE_META[en].label])} />
                <FilterRow label="OS" value={filters.os} onPick={v => setFilter("os", v)}
                  options={OS_LIST.map(o => [o, o])} />
                <FilterRow label="Proxy" value={filters.proxy} onPick={v => setFilter("proxy", v)}
                  options={[["with", "With proxy"], ["without", "Direct"]]} />
                {allTags.length > 0 && (
                  <FilterRow label="Tag" value={filters.tag} onPick={v => setFilter("tag", v)}
                    options={allTags.map(t => [t, t])} />
                )}
              </div>
            </>
          )}
        </div>
      </div>

      <div className="ps-scroll">
        {filtered.length === 0 ? (
          (activeFilters || query) ? (
            <div className="ps-empty">
              <Filter size={28} color={T.dim} />
              <div>No profiles match your {activeFilters ? "filters" : "search"}.</div>
              <button className="ps-btn ghost sm" onClick={() => { clearFilters(); setQuery(""); }}>
                <X size={14} /> Clear {activeFilters ? "filters" : "search"}
              </button>
            </div>
          ) : (
          <div className="ps-empty">
            <Layers size={28} color={T.dim} />
            <div>No profiles here yet.</div>
            <button className="ps-btn primary sm" onClick={() => setEditor(newProfile(folder))}><Plus size={14} /> Create one</button>
          </div>
          )
        ) : (
          <table className="ps-table">
            <thead>
              <tr>
                <th style={{ width: 34 }}>
                  <input type="checkbox" checked={allSel} onChange={() => setSel(allSel ? new Set() : new Set(filtered.map(p => p.id)))} />
                </th>
                <th>Profile</th><th>Environment</th><th>Engine</th><th>Proxy</th>
                <th>Coherence</th><th>Last active</th><th style={{ width: 150, textAlign: "right" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((p, i) => {
                const iss = coherence(p);
                return (
                  <tr key={p.id} className={"ps-rise" + (sel.has(p.id) ? " sel" : "")} style={{ animationDelay: `${Math.min(i, 12) * 28}ms` }}>
                    <td><input type="checkbox" checked={sel.has(p.id)} onChange={() => toggleSel(p.id)} /></td>
                    <td>
                      <div className="ps-name">
                        <span className={"ps-status " + p.status} />
                        <div>
                          <div className="ps-pname">{p.name}</div>
                          <div className="ps-tags">{p.tags.map(t => (
                            <span key={t} className={"ps-tag clickable" + (filters.tag === t ? " on" : "")}
                              title={filters.tag === t ? "Clear tag filter" : `Filter by "${t}"`}
                              onClick={() => setFilter("tag", t)}>{t}</span>
                          ))}</div>
                        </div>
                      </div>
                    </td>
                    <td>
                      <div className="ps-env">
                        <span className="ps-os">{p.os}</span>
                        <span className="ps-mono">{p.browser} {p.browserVersion.split(".")[0]}</span>
                        <span className="ps-mono dim">{p.screen}</span>
                      </div>
                    </td>
                    <td><span className="ps-engine-chip">{ENGINE_META[p.engine]?.label || p.engine || "Playwright"}</span></td>
                    <td>
                      {p.proxy
                        ? <div className="ps-proxy"><Wifi size={13} color={T.mint} /><span className="ps-mono">{p.proxy.country}</span><span className="ps-mono dim">{p.proxy.type}</span></div>
                        : <div className="ps-proxy off"><WifiOff size={13} color={T.dim} /> <span className="dim">Direct</span></div>}
                    </td>
                    <td>
                      {iss.length === 0
                        ? <span className="ps-pill ok"><ShieldCheck size={12} /> Coherent</span>
                        : <span className="ps-pill warn" title={iss.join("\n")}><ShieldAlert size={12} /> {iss.length} issue{iss.length > 1 ? "s" : ""}</span>}
                    </td>
                    <td><span className="ps-mono dim">{p.lastActive}</span></td>
                    <td>
                      <div className="ps-actions">
                        <button title={p.status === "running" ? "Stop" : "Launch"} className={p.status === "running" ? "stop" : "run"} onClick={() => toggleRun(p.id)}>
                          {p.status === "running" ? <Square size={13} /> : <Play size={13} />}
                        </button>
                        <button title="Edit" onClick={() => setEditor({ ...p })}><Pencil size={13} /></button>
                        <button title="Clone" onClick={() => clone(p)}><Copy size={13} /></button>
                        <button title="Delete" className="del" onClick={() => remove(p.id)}><Trash2 size={13} /></button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
        {pageCount > 1 && (
          <div className="ps-pager">
            <button className="ps-btn ghost sm" disabled={cur === 0} onClick={() => setPage(0)}>« First</button>
            <button className="ps-btn ghost sm" disabled={cur === 0} onClick={() => setPage(cur - 1)}>‹ Prev</button>
            <span className="ps-pager-info">
              Page <b>{cur + 1}</b> of {pageCount} · <b>{filtered.length.toLocaleString()}</b> profiles
            </span>
            <button className="ps-btn ghost sm" disabled={cur >= pageCount - 1} onClick={() => setPage(cur + 1)}>Next ›</button>
            <button className="ps-btn ghost sm" disabled={cur >= pageCount - 1} onClick={() => setPage(pageCount - 1)}>Last »</button>
          </div>
        )}
      </div>
    </>
  );
}

/* ---- Engines view (the signature: pluggable stealth backends) ---- */
function EnginesView({ engines, live }) {
  const recommended = ENGINE_ORDER.filter(k => ENGINE_META[k].recommended);
  const others = ENGINE_ORDER.filter(k => !ENGINE_META[k].recommended);
  return (
    <div className="ps-scroll">
      <div className="ps-eng-hero ps-rise">
        <div className="ps-eng-hero-badge"><Blocks size={13} /> Pluggable engines</div>
        <h1 className="ps-eng-title">Persona manages the identity.<br /><span className="grad">The engine renders it.</span></h1>
        <p className="ps-eng-lead">
          Every profile carries a coherent fingerprint, a proxy and a session — that part is Persona's job.
          Plug in the stealth backend that matches your target. Install it, pick it per profile, launch.
        </p>
        <div className="ps-eng-flow">
          <span className="ps-flow-node"><Fingerprint size={14} /> Identity</span>
          <ArrowRight size={15} color={T.dim} />
          <span className="ps-flow-node"><Blocks size={14} /> Engine</span>
          <ArrowRight size={15} color={T.dim} />
          <span className="ps-flow-node"><MonitorSmartphone size={14} /> Real browser</span>
        </div>
      </div>

      <SectionHead icon={<Star size={13} />} text="Recommended" note="Strongest against modern detection" />
      <div className="ps-eng-grid">
        {recommended.map((k, i) => <EngineCard key={k} id={k} status={engines?.[k]} live={live} delay={i * 60} featured />)}
      </div>

      <SectionHead icon={<Blocks size={13} />} text="Also available" />
      <div className="ps-eng-grid">
        {others.map((k, i) => <EngineCard key={k} id={k} status={engines?.[k]} live={live} delay={i * 60} />)}
      </div>

      <div className="ps-eng-note">
        <Sparkles size={14} color={T.violet} />
        <span>Add your own backend by registering it in <code>engine/persona/drivers.py</code> — one function, one decorator.</span>
      </div>
    </div>
  );
}

function EngineCard({ id, status, live, delay, featured }) {
  const m = ENGINE_META[id];
  const [copied, setCopied] = useState(false);
  const copy = () => { navigator.clipboard?.writeText(m.install); setCopied(true); setTimeout(() => setCopied(false), 1400); };
  // status: true=installed, false=not, undefined=unknown (demo / builtin)
  const state = m.builtin ? "builtin" : status === true ? "ready" : status === false ? "missing" : "unknown";
  return (
    <div className={"ps-eng-card ps-rise" + (featured ? " featured" : "")} style={{ animationDelay: `${delay}ms` }}>
      <div className="ps-eng-card-top">
        <div>
          <div className="ps-eng-name">{m.label} {m.recommended && <span className="ps-rec"><Star size={10} /> Recommended</span>}</div>
          <div className="ps-eng-kind">{m.kind}</div>
        </div>
        <StatusDot state={state} />
      </div>
      <StrengthMeter value={m.strength} />
      <p className="ps-eng-desc">{m.desc}</p>
      {m.install ? (
        <div className="ps-eng-install">
          <code>{m.install}</code>
          <button onClick={copy} title="Copy install command">{copied ? <Check size={13} color={T.mint} /> : <Clipboard size={13} />}</button>
        </div>
      ) : (
        <div className="ps-eng-builtin"><Check size={13} color={T.mint} /> Ships with Persona — nothing to install.</div>
      )}
      {m.docs && <a className="ps-eng-docs" href={m.docs} target="_blank" rel="noreferrer">Setup guide <ArrowRight size={12} /></a>}
    </div>
  );
}

function StatusDot({ state }) {
  const map = {
    builtin: [T.mint, "Built-in"], ready: [T.mint, "Installed"],
    missing: [T.dim, "Not installed"], unknown: [T.violet, "Available"],
  };
  const [c, label] = map[state];
  return <span className="ps-eng-status" style={{ color: c }}><span className="ps-eng-status-dot" style={{ background: c }} />{label}</span>;
}

function StrengthMeter({ value }) {
  return (
    <div className="ps-strength" title={`Stealth strength ${value}/4`}>
      <span className="ps-strength-label">Stealth</span>
      <div className="ps-strength-bars">
        {[1, 2, 3, 4].map(n => <span key={n} className={"ps-sb" + (n <= value ? " on" : "")} />)}
      </div>
    </div>
  );
}

/* ---- small pieces ------------------------------------------------ */
function Stat({ icon, label, value, accent, pulse }) {
  return (
    <div className="ps-stat">
      <div className={"ps-stat-ic" + (pulse ? " pulse" : "")} style={{ color: accent || T.muted }}>{icon}</div>
      <div>
        <div className="ps-stat-val">{value}</div>
        <div className="ps-stat-label">{label}</div>
      </div>
    </div>
  );
}

function newProfile(folder, defaultEngine = ENGINE_ORDER[0]) {
  const os = "Windows";
  return {
    id: nid(), name: "", folder: folder === "All profiles" ? "Facebook Ads" : folder,
    status: "stopped", os, tags: [], engine: defaultEngine, browser: "Chrome", browserVersion: "128.0.0.0",
    userAgent: uaFor(os), screen: SCREENS[os][0], cores: CORES[os][1], memory: RAM[os][1],
    webglVendor: "Google Inc. (NVIDIA)", webglRenderer: GPUS[os][0],
    canvas: "Noise", webrtc: "Altered", audio: "Noise", fonts: "Masked",
    locale: "en-US", timezone: "America/New_York", geo: "Prompt",
    mediaVideo: 1, mediaAudio: 1, dnt: false, proxy: null, notes: "", startupUrls: "", extensions: "",
    lastActive: "never", _new: true,
  };
}

/* ---- Probe result panel (proxy test / trust check) ---------------- */
function ProbePanel({ probe, kind }) {
  if (!probe || probe.kind !== kind) return null;
  if (probe.state === "running")
    return <div className="ps-hint"><RefreshCw size={12} className="ps-spin" /> Opening the profile in the background — this takes a few seconds.</div>;
  if (probe.state === "error")
    return <div className="ps-hint"><ShieldAlert size={12} /> {probe.data}</div>;

  const d = probe.data || {};
  const checks = d.checks || [];
  const gColor = (s) => (s >= 95 ? T.mint : s >= 70 ? T.amber : T.red);
  return (
    <div className="ps-probe">
      {d.before && d.after && (
        <div className="ps-probe-head">
          <span className="ps-probe-score" style={{ color: gColor(d.before.score) }}>{d.before.grade} {d.before.score}%</span>
          <ArrowRight size={14} color={T.dim} />
          <span className="ps-probe-score" style={{ color: gColor(d.after.score) }}>{d.after.grade} {d.after.score}%</span>
          <span>{d.after.passed}/{d.after.total} checks passed</span>
        </div>
      )}
      {d.changed && (
        <div className="ps-check ok">
          <Sparkles size={12} />
          <span>{d.changed.length
            ? <>Aligned <em>{d.changed.join(", ")}</em> to the real browser{d.os ? ` · now reads as ${d.os}` : ""}.</>
            : "Already matched the browser — nothing to change."}</span>
        </div>
      )}
      {d.score !== undefined && (
        <div className="ps-probe-head">
          <span className="ps-probe-score" style={{ color: d.score >= 95 ? T.mint : d.score >= 70 ? T.amber : T.red }}>
            {d.score}%
          </span>
          <span>grade {d.grade} · {d.passed}/{d.total} checks passed</span>
        </div>
      )}
      {d.ip && (
        <div className="ps-probe-head">
          <span className="ps-probe-score" style={{ color: T.mint, fontSize: 15 }}>{d.ip}</span>
          <span>{[d.city, d.country].filter(Boolean).join(", ")}{d.latencyMs ? ` · ${d.latencyMs} ms` : ""}</span>
        </div>
      )}
      {(d.ja3Hash || d.ja4) && (
        <div className="ps-probe-head" style={{ display: "block" }}>
          {d.ja3Hash && <div className="ps-mono" style={{ fontSize: 11 }}>JA3 {d.ja3Hash}</div>}
          {d.ja4 && <div className="ps-mono" style={{ fontSize: 11 }}>JA4 {d.ja4}</div>}
        </div>
      )}
      {kind === "dns" && d.countries && (
        <div className="ps-probe-head">
          <span className="ps-probe-score" style={{ color: T.lilac, fontSize: 14 }}>
            {d.resolvers?.length || 0} resolver{(d.resolvers?.length || 0) === 1 ? "" : "s"}
          </span>
          <span>{d.countries.join(", ") || "unknown"}</span>
        </div>
      )}
      {d.error && <div className="ps-check">{d.error}</div>}
      {checks.map((c, i) => (
        <div key={i} className={"ps-check" + (c.ok ? " ok" : "")}>
          {c.ok ? <Check size={12} /> : <X size={12} />}
          <span>{c.name}{!c.ok && c.detail ? <em> — {c.detail}</em> : null}</span>
        </div>
      ))}
    </div>
  );
}

/* ---- Fingerprint editor ------------------------------------------ */
function Editor({ profile, live, onClose, onSave }) {
  const [p, setP] = useState(profile);
  const [tab, setTab] = useState("general");
  const set = (patch) => setP(x => ({ ...x, ...patch }));
  const changeOS = (os) => set({ os, userAgent: uaFor(os), screen: SCREENS[os][0], cores: CORES[os][1], memory: RAM[os][1], webglRenderer: GPUS[os][0] });
  const changeLocale = (locale) => set({ locale, timezone: LOCALES[locale] });
  const setProxy = (patch) => set({ proxy: { ...(p.proxy || { type: "HTTP", host: "", port: "", user: "", pass: "", country: "" }), ...patch } });

  const iss = coherence(p);
  const score = Math.max(0, 100 - iss.length * 22);

  // Cookies live in the profile's real browser session, so they can only be
  // moved when the engine is running and the profile has been saved.
  const cookiesReady = live && !p._new;
  const [ckBusy, setCkBusy] = useState("");
  const [ckMsg, setCkMsg] = useState("");
  const [ckReplace, setCkReplace] = useState(false);

  const exportCookies = async () => {
    setCkBusy("export"); setCkMsg("");
    try {
      const { cookies } = await api.exportCookies(p.id);
      const blob = new Blob([JSON.stringify({ cookies, origins: [] }, null, 2)], { type: "application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `${(p.name || "profile").replace(/[^\w.-]+/g, "-")}-cookies.json`;
      a.click();
      URL.revokeObjectURL(a.href);
      setCkMsg(`Exported ${cookies.length} cookie${cookies.length === 1 ? "" : "s"}.`);
    } catch (e) { setCkMsg("Export failed: " + e.message); }
    setCkBusy("");
  };

  // Probes and warm-up all open the profile headlessly, so they share one
  // "something is running" flag and one result panel per tab.
  const [probe, setProbe] = useState(null);     // { kind, state, data }
  const runProbe = async (kind, fn) => {
    setProbe({ kind, state: "running" });
    try { setProbe({ kind, state: "done", data: await fn() }); }
    catch (e) { setProbe({ kind, state: "error", data: e.message }); }
  };

  // Auto-adjust: align the profile to what its browser really shows, then pull
  // the rewritten values straight back into the editor so you see the change.
  const autoAdjust = async () => {
    setProbe({ kind: "align", state: "running" });
    try {
      const res = await api.align(p.id);
      if (res.profile) setP(x => ({ ...x, ...res.profile }));
      setProbe({ kind: "align", state: "done", data: res });
    } catch (e) { setProbe({ kind: "align", state: "error", data: e.message }); }
  };

  // Warm-up: pick a per-vertical site set, run it now, or schedule it to
  // recur unattended. The schedule for this profile (if any) is loaded live.
  const [preset, setPreset] = useState("general");
  const [sched, setSched] = useState(null);
  const [schedBusy, setSchedBusy] = useState(false);
  useEffect(() => {
    if (!cookiesReady) return;
    api.listSchedules().then(list => setSched(list.find(s => s.profileId === p.id) || null)).catch(() => {});
  }, [cookiesReady, p.id]);

  const warmNow = () =>
    api.warmup(p.id, 5, preset)
      .then(() => setCkMsg(`Warm-up started (${preset}) — runs in the background for ~5 minutes.`))
      .catch(e => setCkMsg("Warm-up failed: " + e.message));

  const toggleSchedule = async () => {
    setSchedBusy(true);
    try {
      if (sched) { await api.deleteSchedule(sched.id); setSched(null); }
      else { setSched(await api.addSchedule({ profileId: p.id, everyHours: 12, minutes: 5, preset })); }
    } catch (e) { setCkMsg("Schedule failed: " + e.message); }
    setSchedBusy(false);
  };
  const patchSchedule = async (patch) => {
    if (!sched) return;
    setSchedBusy(true);
    try { setSched(await api.updateSchedule(sched.id, patch)); }
    catch (e) { setCkMsg("Schedule failed: " + e.message); }
    setSchedBusy(false);
  };

  const importCookies = async (file) => {
    if (!file) return;
    setCkBusy("import"); setCkMsg("");
    try {
      const res = await api.importCookies(p.id, await file.text(), ckReplace);
      setCkMsg(`Imported ${res.imported} cookie${res.imported === 1 ? "" : "s"} from ${file.name}.`);
    } catch (e) { setCkMsg("Import failed: " + e.message); }
    setCkBusy("");
  };

  return (
    <div className="ps-overlay" onClick={onClose}>
      <div className="ps-drawer" onClick={e => e.stopPropagation()}>
        <div className="ps-drawer-h">
          <div>
            <div className="ps-eyebrow">{p._new ? "New profile" : "Edit profile"}</div>
            <div className="ps-drawer-title">{p.name || "Untitled profile"}</div>
          </div>
          <button className="ps-x" onClick={onClose}><X size={18} /></button>
        </div>

        <div className="ps-coh">
          <div className="ps-coh-top">
            <span className="ps-coh-h">
              {iss.length === 0 ? <ShieldCheck size={14} color={T.mint} /> : <ShieldAlert size={14} color={T.amber} />}
              Fingerprint coherence
            </span>
            <span className="ps-coh-score" style={{ color: iss.length ? T.amber : T.mint }}>{score}%</span>
          </div>
          <div className="ps-coh-bar"><div style={{ width: score + "%", background: iss.length ? T.amber : T.mint }} /></div>
          {iss.length > 0
            ? <div className="ps-coh-iss">{iss.map((i, k) => <div key={k}>· {i}</div>)}</div>
            : <div className="ps-coh-ok">All signals agree — this identity reads like one real device.</div>}
        </div>

        <div className="ps-tabs">
          {["general", "fingerprint", "proxy", "advanced"].map(t => (
            <button key={t} className={"ps-tab" + (tab === t ? " active" : "")} onClick={() => setTab(t)}>{t}</button>
          ))}
        </div>

        <div className="ps-drawer-body">
          {tab === "general" && (
            <>
              <Field label="Profile name"><input className="ps-in" value={p.name} onChange={e => set({ name: e.target.value })} placeholder="e.g. FB-Ads-03" /></Field>
              <Row>
                <Field label="Folder">
                  <select className="ps-in" value={p.folder} onChange={e => set({ folder: e.target.value })}>
                    {FOLDERS.filter(f => f !== "All profiles").map(f => <option key={f}>{f}</option>)}
                  </select>
                </Field>
                <Field label="Tags (comma separated)">
                  <input className="ps-in" value={p.tags.join(", ")} onChange={e => set({ tags: e.target.value.split(",").map(s => s.trim()).filter(Boolean) })} placeholder="client-a, priority" />
                </Field>
              </Row>
              <Field label="Notes"><textarea className="ps-in" rows={3} value={p.notes} onChange={e => set({ notes: e.target.value })} placeholder="Anything worth remembering about this account…" /></Field>
              <Field label="Launch engine">
                <select className="ps-in" value={p.engine || "playwright"} onChange={e => set({ engine: e.target.value })}>
                  {ENGINE_ORDER.map(en => <option key={en} value={en}>{ENGINE_META[en].label}{ENGINE_META[en].recommended ? "  ★ recommended" : ""}</option>)}
                </select>
              </Field>
              <div className="ps-hint"><Blocks size={12} /> Persona manages this profile; the engine renders it. Manage engines in the <b style={{ color: T.text }}>Engines</b> tab.</div>
            </>
          )}

          {tab === "fingerprint" && (
            <>
              <SectionLabel icon={<MonitorSmartphone size={13} />} text="Operating system & browser" />
              <Row>
                <Field label="Operating system">
                  <select className="ps-in" value={p.os} onChange={e => changeOS(e.target.value)}>{OS_LIST.map(o => <option key={o}>{o}</option>)}</select>
                </Field>
                <Field label="Browser version"><input className="ps-in" value={p.browserVersion} onChange={e => set({ browserVersion: e.target.value })} /></Field>
              </Row>
              <Field label="User-Agent"><textarea className="ps-in mono" rows={2} value={p.userAgent} onChange={e => set({ userAgent: e.target.value })} /></Field>

              <SectionLabel icon={<Cpu size={13} />} text="Hardware" />
              <Row>
                <Field label="Screen resolution">
                  <select className="ps-in" value={p.screen} onChange={e => set({ screen: e.target.value })}>{[...new Set([p.screen, ...SCREENS[p.os]])].map(s => <option key={s}>{s}</option>)}</select>
                </Field>
                <Field label="CPU cores">
                  <select className="ps-in" value={p.cores} onChange={e => set({ cores: Number(e.target.value) })}>{[...new Set([p.cores, ...CORES[p.os]])].map(c => <option key={c}>{c}</option>)}</select>
                </Field>
                <Field label="Memory (GB)">
                  <select className="ps-in" value={p.memory} onChange={e => set({ memory: Number(e.target.value) })}>{[...new Set([p.memory, ...RAM[p.os]])].map(m => <option key={m}>{m}</option>)}</select>
                </Field>
              </Row>
              <Field label="WebGL renderer (GPU)">
                <select className="ps-in mono" value={p.webglRenderer} onChange={e => set({ webglRenderer: e.target.value })}>{[...new Set([p.webglRenderer, ...GPUS[p.os]])].map(g => <option key={g}>{g}</option>)}</select>
              </Field>

              <SectionLabel icon={<Fingerprint size={13} />} text="Spoofing modes" />
              <Row><Pick label="Canvas" opts={MODES.canvas} val={p.canvas} on={v => set({ canvas: v })} /><Pick label="WebRTC" opts={MODES.webrtc} val={p.webrtc} on={v => set({ webrtc: v })} /></Row>
              <Row><Pick label="Audio context" opts={MODES.audio} val={p.audio} on={v => set({ audio: v })} /><Pick label="Fonts" opts={MODES.fonts} val={p.fonts} on={v => set({ fonts: v })} /></Row>

              <SectionLabel icon={<Globe size={13} />} text="Geo & language" />
              <Row>
                <Field label="Locale"><select className="ps-in" value={p.locale} onChange={e => changeLocale(e.target.value)}>{Object.keys(LOCALES).map(l => <option key={l}>{l}</option>)}</select></Field>
                <Field label={<span><Clock size={11} /> Timezone</span>}><input className="ps-in mono" value={p.timezone} onChange={e => set({ timezone: e.target.value })} /></Field>
                <Pick label="Geolocation" opts={MODES.geo} val={p.geo} on={v => set({ geo: v })} />
              </Row>
              <Row>
                <Field label={<span><Camera size={11} /> Cameras</span>}><input type="number" className="ps-in" value={p.mediaVideo} onChange={e => set({ mediaVideo: Number(e.target.value) })} /></Field>
                <Field label={<span><Mic size={11} /> Microphones</span>}><input type="number" className="ps-in" value={p.mediaAudio} onChange={e => set({ mediaAudio: Number(e.target.value) })} /></Field>
                <Field label="Do Not Track">
                  <button className={"ps-toggle" + (p.dnt ? " on" : "")} onClick={() => set({ dnt: !p.dnt })}><span className="knob" /> <em>{p.dnt ? "On" : "Off"}</em></button>
                </Field>
              </Row>

              <SectionLabel icon={<ShieldCheck size={13} />} text="Trust check" />
              <div className="ps-cookie-actions">
                <button className="ps-btn ghost sm" disabled={!cookiesReady || probe?.state === "running"}
                  onClick={() => runProbe("trust", () => api.trust(p.id))}>
                  <ShieldCheck size={13} /> Run trust check
                </button>
                <button className="ps-btn ghost sm" disabled={!cookiesReady || probe?.state === "running"}
                  onClick={() => runProbe("tls", () => api.tls(p.id))}>
                  <Wifi size={13} /> Check TLS / JA3
                </button>
                <button className="ps-btn primary sm" disabled={!cookiesReady || probe?.state === "running"}
                  onClick={autoAdjust} title="Rewrite mismatched values to match what the browser actually presents">
                  <Sparkles size={13} /> Auto-adjust
                </button>
              </div>
              <ProbePanel probe={probe} kind="trust" />
              <ProbePanel probe={probe} kind="tls" />
              <ProbePanel probe={probe} kind="align" />
              <div className="ps-hint"><ShieldCheck size={12} /> {cookiesReady
                ? "Trust check grades the real browser; TLS/JA3 reads the handshake JavaScript can't touch. Auto-adjust closes the gap — it rewrites platform, CPU, GPU, fonts and the rest to what the browser actually shows (regenerating the OS identity if the engine renders a different one), so nothing contradicts."
                : "Save the profile and start the engine to grade — and auto-adjust — the real browser."}</div>
            </>
          )}

          {tab === "proxy" && (
            <>
              <div className="ps-proxy-toggle">
                <span style={{ fontSize: 13, fontWeight: 600 }}>Use proxy for this profile</span>
                <button className={"ps-toggle" + (p.proxy ? " on" : "")} onClick={() => set({ proxy: p.proxy ? null : { type: "HTTP", host: "", port: "", user: "", pass: "", country: "US" } })}>
                  <span className="knob" /> <em>{p.proxy ? "On" : "Off"}</em>
                </button>
              </div>
              {p.proxy ? (
                <>
                  <Row>
                    <Field label="Type"><select className="ps-in" value={p.proxy.type} onChange={e => setProxy({ type: e.target.value })}>{["HTTP", "HTTPS", "SOCKS5"].map(t => <option key={t}>{t}</option>)}</select></Field>
                    <Field label="Country"><select className="ps-in" value={p.proxy.country} onChange={e => setProxy({ country: e.target.value })}>{Object.keys(COUNTRY_LOCALE).map(c => <option key={c}>{c}</option>)}</select></Field>
                  </Row>
                  <Row>
                    <Field label="Host"><input className="ps-in mono" value={p.proxy.host} onChange={e => setProxy({ host: e.target.value })} placeholder="host.proxy.io" /></Field>
                    <Field label="Port"><input className="ps-in mono" value={p.proxy.port} onChange={e => setProxy({ port: e.target.value })} placeholder="8080" /></Field>
                  </Row>
                  <Row>
                    <Field label="Username"><input className="ps-in mono" value={p.proxy.user} onChange={e => setProxy({ user: e.target.value })} /></Field>
                    <Field label="Password"><input className="ps-in mono" type="password" value={p.proxy.pass} onChange={e => setProxy({ pass: e.target.value })} /></Field>
                  </Row>
                  <div className="ps-cookie-actions" style={{ marginTop: 4 }}>
                    <button className="ps-btn ghost sm"
                      disabled={!cookiesReady || probe?.state === "running"}
                      onClick={() => runProbe("proxy", () => api.proxyTest(p.id))}>
                      <RefreshCw size={13} /> Test connection
                    </button>
                    <button className="ps-btn ghost sm"
                      disabled={!cookiesReady || probe?.state === "running"}
                      onClick={() => runProbe("dns", () => api.dns(p.id))}
                      title="Do the profile's DNS lookups exit through the proxy, or leak to your real ISP?">
                      <Globe size={13} /> DNS leak test
                    </button>
                  </div>
                  <ProbePanel probe={probe} kind="proxy" />
                  <ProbePanel probe={probe} kind="dns" />
                  <div className="ps-hint"><MapPin size={12} /> {cookiesReady
                    ? "Test connection routes a real request and reports the exit IP, country and WebRTC leaks. DNS leak test checks whether name lookups escape the proxy to your real ISP's resolver."
                    : "Save the profile and start the engine to test the connection for real."}</div>
                </>
              ) : <div className="ps-hint">No proxy — this profile connects directly. Turn it on to route through a residential or datacenter proxy.</div>}
            </>
          )}

          {tab === "advanced" && (
            <>
              <Field label="Startup URLs (one per line)"><textarea className="ps-in mono" rows={3} value={p.startupUrls} onChange={e => set({ startupUrls: e.target.value })} placeholder={"https://facebook.com\nhttps://business.facebook.com"} /></Field>
              <Field label="WebGL vendor"><input className="ps-in mono" value={p.webglVendor} onChange={e => set({ webglVendor: e.target.value })} /></Field>
              <div className="ps-hint"><Fingerprint size={12} /> Seed & canvas noise are managed by the engine and stay stable across launches for this profile.</div>

              <SectionLabel icon={<Blocks size={13} />} text="Extensions" />
              <Field label="Unpacked extension folders (one per line)">
                <textarea className="ps-in mono" rows={2} value={p.extensions || ""}
                  onChange={e => set({ extensions: e.target.value })}
                  placeholder={"C:\\\\tools\\\\metamask\\n/home/me/ext/ublock"} />
              </Field>
              <div className="ps-hint"><Blocks size={12} /> Point at the folder containing <code>manifest.json</code>. Only these extensions load, so nothing carries over between profiles.</div>

              <SectionLabel icon={<Sparkles size={13} />} text="Warm-up" />
              <Row>
                <Field label="Vertical (which sites to browse)">
                  <select className="ps-in" value={preset} onChange={e => setPreset(e.target.value)}>
                    {WARMUP_PRESETS.map(v => <option key={v.key} value={v.key}>{v.label}</option>)}
                  </select>
                </Field>
                <Field label="Run now">
                  <button className="ps-btn ghost sm" disabled={!cookiesReady} onClick={warmNow} style={{ width: "100%", justifyContent: "center" }}>
                    <Sparkles size={13} /> Warm up 5 min
                  </button>
                </Field>
              </Row>
              <div className="ps-proxy-toggle" style={{ marginTop: 8 }}>
                <span style={{ fontSize: 13, fontWeight: 600 }}>Schedule recurring warm-up</span>
                <button className={"ps-toggle" + (sched ? " on" : "")} disabled={!cookiesReady || schedBusy} onClick={toggleSchedule}>
                  <span className="knob" /> <em>{sched ? "On" : "Off"}</em>
                </button>
              </div>
              {sched && (
                <Row>
                  <Field label="Every (hours)">
                    <input type="number" min="1" className="ps-in" value={sched.everyHours}
                      disabled={schedBusy} onChange={e => patchSchedule({ everyHours: Number(e.target.value) })} />
                  </Field>
                  <Field label="Vertical">
                    <select className="ps-in" value={sched.preset} disabled={schedBusy}
                      onChange={e => patchSchedule({ preset: e.target.value })}>
                      {WARMUP_PRESETS.map(v => <option key={v.key} value={v.key}>{v.label}</option>)}
                    </select>
                  </Field>
                </Row>
              )}
              <div className="ps-hint"><Sparkles size={12} /> A profile created minutes ago with no history is a signal in itself. Warm-up browses that vertical's sites at human pace so the session arrives with a plausible past. Scheduling reruns it unattended (the engine must be running) so the session never goes cold. {cookiesReady ? "" : "Save the profile and start the engine to enable it."}</div>

              <SectionLabel icon={<Cookie size={13} />} text="Session cookies" />
              {cookiesReady ? (
                <>
                  <div className="ps-cookie-actions">
                    <button className="ps-btn ghost sm" disabled={!!ckBusy} onClick={exportCookies}>
                      <Download size={13} /> {ckBusy === "export" ? "Reading session…" : "Export cookies"}
                    </button>
                    <label className={"ps-btn ghost sm" + (ckBusy ? " disabled" : "")}>
                      <Upload size={13} /> {ckBusy === "import" ? "Writing session…" : "Import cookies"}
                      <input type="file" accept=".json,.txt" style={{ display: "none" }} disabled={!!ckBusy}
                        onChange={e => { importCookies(e.target.files?.[0]); e.target.value = ""; }} />
                    </label>
                    <button className={"ps-toggle sm" + (ckReplace ? " on" : "")} onClick={() => setCkReplace(v => !v)}>
                      <span className="knob" /> <em>Replace existing</em>
                    </button>
                  </div>
                  {ckMsg && <div className="ps-hint">{ckMsg}</div>}
                  <div className="ps-hint"><Cookie size={12} /> Reads and writes the profile's real cookie jar. Accepts Cookie-Editor / EditThisCookie JSON, Playwright storage state, and Netscape <code>cookies.txt</code>. Stop the profile first — its session can't be open twice.</div>
                </>
              ) : (
                <div className="ps-hint"><Cookie size={12} /> {p._new
                  ? "Save this profile first, then you can move a session in or out."
                  : "Cookie transfer needs the engine running — start it with persona serve."}</div>
              )}
            </>
          )}
        </div>

        <div className="ps-drawer-foot">
          <button className="ps-btn ghost" onClick={onClose}>Cancel</button>
          <button className="ps-btn primary" disabled={!p.name} onClick={() => onSave({ ...p, _new: false })}>
            <Check size={15} /> {p._new ? "Create profile" : "Save changes"}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ---- Multi-profile synchroniser: one change, applied to many ------ */
function SyncModal({ ids, onClose, onApply }) {
  const [engine, setEngine] = useState("");
  const [locale, setLocale] = useState("");
  const [tag, setTag] = useState("");
  const [folder, setFolder] = useState("");

  // Only the fields you actually filled in get sent — a bulk edit should never
  // quietly reset something you left blank.
  const patch = {};
  if (engine) patch.engine = engine;
  if (locale) patch.locale = locale;
  if (folder) patch.folder = folder;
  if (tag.trim()) patch.addTags = tag.split(",").map(s => s.trim()).filter(Boolean);
  const count = Object.keys(patch).length;

  return (
    <div className="ps-overlay center" onClick={onClose}>
      <div className="ps-modal ps-pop" onClick={e => e.stopPropagation()}>
        <div className="ps-drawer-h">
          <div>
            <div className="ps-eyebrow">Edit {ids.length} profiles</div>
            <div className="ps-drawer-title">Change once, apply to all</div>
          </div>
          <button className="ps-x" onClick={onClose}><X size={18} /></button>
        </div>
        <div style={{ padding: 20 }}>
          <Row>
            <Field label="Launch engine">
              <select className="ps-in" value={engine} onChange={e => setEngine(e.target.value)}>
                <option value="">— leave unchanged —</option>
                {ENGINE_ORDER.map(en => <option key={en} value={en}>{ENGINE_META[en].label}</option>)}
              </select>
            </Field>
            <Field label="Locale (moves timezone too)">
              <select className="ps-in" value={locale} onChange={e => setLocale(e.target.value)}>
                <option value="">— leave unchanged —</option>
                {Object.keys(LOCALES).map(l => <option key={l}>{l}</option>)}
              </select>
            </Field>
          </Row>
          <Row>
            <Field label="Move to folder">
              <select className="ps-in" value={folder} onChange={e => setFolder(e.target.value)}>
                <option value="">— leave unchanged —</option>
                {FOLDERS.filter(f => f !== "All profiles").map(f => <option key={f}>{f}</option>)}
              </select>
            </Field>
            <Field label="Add tags (comma separated)">
              <input className="ps-in" value={tag} onChange={e => setTag(e.target.value)} placeholder="q3-campaign" />
            </Field>
          </Row>
          <div className="ps-hint"><Copy size={12} /> Blank fields are left alone, so you can run this again later to change one more thing.</div>
        </div>
        <div className="ps-drawer-foot">
          <button className="ps-btn ghost" onClick={onClose}>Cancel</button>
          <button className="ps-btn primary" disabled={!count} onClick={() => onApply(patch)}>
            <Check size={15} /> Apply to {ids.length}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ---- Bulk create ------------------------------------------------- */
// A row of toggle chips for picking several values (OS, country, browser).
function ChipPick({ options, value, onToggle }) {
  return (
    <div className="ps-chiprow">
      {options.map(o => (
        <button key={o} type="button" className={"ps-chip-btn" + (value.includes(o) ? " on" : "")}
          onClick={() => onToggle(o)}>{value.includes(o) && <Check size={11} />}{o}</button>
      ))}
    </div>
  );
}

function BulkModal({ onClose, onCreate, folder, defaultEngine }) {
  const [n, setN] = useState(50);
  const [oses, setOses] = useState(["Windows"]);
  const [countries, setCountries] = useState(["US"]);
  const [browsers, setBrowsers] = useState([...CHROME_VERSIONS]);
  const [engine, setEngine] = useState(defaultEngine || ENGINE_ORDER[0]);
  const [randomize, setRandomize] = useState(true);
  const [prefix, setPrefix] = useState("Batch");
  const [start, setStart] = useState(1);
  const [tagStr, setTagStr] = useState("bulk");
  const [busy, setBusy] = useState(false);
  const [prog, setProg] = useState(0);

  // Keep at least one selected in each multi-pick.
  const toggle = (setArr) => (v) => setArr(a => a.includes(v) ? (a.length > 1 ? a.filter(x => x !== v) : a) : [...a, v]);
  const pad = Math.max(2, String(start + n - 1).length);

  const build = () => {
    const tags = tagStr.split(",").map(s => s.trim()).filter(Boolean);
    const rnd = (arr) => arr[Math.floor(Math.random() * arr.length)];
    const pick = (arr, dflt) => randomize ? rnd(arr) : (dflt ?? arr[0]);
    const list = new Array(n);
    for (let i = 0; i < n; i++) {
      const os = oses[i % oses.length];
      const country = countries[Math.floor(i / oses.length) % countries.length];
      const chrome = rnd(browsers) || "128.0.0.0";
      const gpu = pick(GPUS[os]);
      const locale = COUNTRY_LOCALE[country] || "en-US";
      list[i] = {
        name: `${prefix}-${String(start + i).padStart(pad, "0")}`,
        folder: folder === "All profiles" ? "Facebook Ads" : folder,
        status: "stopped", os, tags, engine, browser: "Chrome", browserVersion: chrome,
        userAgent: uaFor(os, chrome), screen: pick(SCREENS[os]),
        cores: pick(CORES[os], CORES[os][1]), memory: pick(RAM[os], RAM[os][1]),
        webglVendor: vendorFor(gpu), webglRenderer: gpu,
        canvas: "Noise", webrtc: "Altered", audio: "Noise", fonts: "Masked",
        locale, timezone: LOCALES[locale], geo: "Prompt", mediaVideo: 1, mediaAudio: 1, dnt: false,
        proxy: null,   // real proxies are attached from the pool (Proxies → Assign)
        notes: "", startupUrls: "", extensions: "", lastActive: "never", _new: true,
      };
    }
    return list;
  };

  const create = async () => {
    setBusy(true); setProg(0);
    try { await onCreate(build(), (done) => setProg(done)); onClose(); }
    catch (e) { alert("Bulk create failed: " + e.message); setBusy(false); }
  };

  return (
    <div className="ps-overlay center" onClick={busy ? undefined : onClose}>
      <div className="ps-modal ps-pop" onClick={e => e.stopPropagation()} style={{ maxWidth: 560 }}>
        <div className="ps-drawer-h">
          <div><div className="ps-eyebrow">Bulk create</div><div className="ps-drawer-title">Generate profiles at scale</div></div>
          <button className="ps-x" onClick={onClose} disabled={busy}><X size={18} /></button>
        </div>
        <div style={{ padding: 20, maxHeight: "62vh", overflowY: "auto" }}>
          <Row>
            <Field label="How many (up to 10,000)">
              <input type="number" className="ps-in" value={n} min={1} max={10000}
                onChange={e => setN(Math.min(10000, Math.max(1, Number(e.target.value) || 1)))} />
            </Field>
            <Field label="Launch engine">
              <select className="ps-in" value={engine} onChange={e => setEngine(e.target.value)}>
                {ENGINE_ORDER.map(en => <option key={en} value={en}>{ENGINE_META[en].label}{ENGINE_META[en].recommended ? "  ★" : ""}</option>)}
              </select>
            </Field>
          </Row>

          <Field label="Operating systems (spread across)"><ChipPick options={OS_LIST} value={oses} onToggle={toggle(setOses)} /></Field>
          <Field label="Countries / locales (spread across)"><ChipPick options={Object.keys(COUNTRY_LOCALE)} value={countries} onToggle={toggle(setCountries)} /></Field>
          <Field label="Browser versions (Chrome)"><ChipPick options={CHROME_VERSIONS} value={browsers} onToggle={toggle(setBrowsers)} /></Field>

          <Row>
            <Field label="Name prefix"><input className="ps-in" value={prefix} onChange={e => setPrefix(e.target.value)} /></Field>
            <Field label="Start number"><input type="number" className="ps-in" value={start} min={0} onChange={e => setStart(Math.max(0, Number(e.target.value) || 0))} /></Field>
            <Field label="Tags"><input className="ps-in" value={tagStr} onChange={e => setTagStr(e.target.value)} placeholder="bulk, q3" /></Field>
          </Row>

          <Field label="Vary GPU / screen / CPU / RAM">
            <button className={"ps-toggle" + (randomize ? " on" : "")} onClick={() => setRandomize(v => !v)}><span className="knob" /> <em>{randomize ? "Randomized per profile" : "Fixed per OS"}</em></button>
          </Field>

          <div className="ps-hint"><Boxes size={12} /> Each profile gets its own coherent fingerprint, seed & session — {randomize ? "hardware varies per profile" : "hardware fixed per OS"}. Preview: <b style={{ color: T.text }}>{prefix}-{String(start).padStart(pad, "0")} … {prefix}-{String(start + n - 1).padStart(pad, "0")}</b> · {oses.join("/")} · {countries.join("/")}</div>
          <div className="ps-hint"><Globe size={12} /> These are created without a proxy. Attach real proxies in bulk from <b style={{ color: T.text }}>Proxies → Assign to profiles</b> (round-robin, aligns locale to each proxy's country).</div>
        </div>
        <div className="ps-drawer-foot">
          <button className="ps-btn ghost" onClick={onClose} disabled={busy}>Cancel</button>
          <button className="ps-btn primary" onClick={create} disabled={busy}>
            {busy ? <><RefreshCw size={15} className="ps-spin" /> Creating {prog}/{n}…</> : <><Plus size={15} /> Create {n} profile{n > 1 ? "s" : ""}</>}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ---- Proxies view: a managed pool (import, test, assign) --------- */
function ProxyStatus({ p }) {
  const s = p.status;
  if (s === "ok") return <span className="ps-pill ok" title={p.lastCheck?.ip || ""}><Check size={12} /> {p.lastCheck?.country || "OK"}{p.lastCheck?.latencyMs ? ` · ${p.lastCheck.latencyMs}ms` : ""}</span>;
  if (s === "failed") return <span className="ps-pill warn" title={p.lastCheck?.error || ""}><ShieldAlert size={12} /> Failed</span>;
  if (s === "skipped") return <span className="ps-pill" title={p.lastCheck?.error || ""} style={{ background: T.violetDim, color: T.lilac }}><Circle size={10} /> SOCKS</span>;
  return <span className="ps-pill" style={{ color: T.dim }}><Circle size={10} /> Untested</span>;
}

/* ---- Health overview --------------------------------------------- */
function GradeBadge({ grade }) {
  if (!grade) return <span className="ps-mono dim">—</span>;
  const c = grade === "A" ? T.mint : grade === "B" ? T.lilac : grade === "C" ? T.amber : T.red;
  return <span className="ps-grade" style={{ color: c, borderColor: c + "55", background: c + "18" }}>{grade}</span>;
}

function HealthView({ profiles, live, refresh, setEditor }) {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState({});           // id -> action label
  const load = async () => { try { setData(await api.health()); } catch { /* offline */ } };
  useEffect(() => { if (live) load(); }, [live]);

  // Demo mode: no engine to grade against, so derive coherence/proxy from the
  // sample profiles and be honest that trust and schedules need the engine.
  if (!live) {
    const colliding = collidingIds(profiles);
    const rows = profiles.map(p => ({ ...p, coherent: coherence(p).length === 0, issues: coherence(p), collides: colliding.has(p.id) }));
    const coherent = rows.filter(r => r.coherent).length;
    return (
      <div className="ps-scroll">
        <div className="ps-health-summary">
          <HealthChip label="Profiles" value={rows.length} />
          <HealthChip label="Coherent" value={`${coherent}/${rows.length}`} color={T.mint} />
          <HealthChip label="With proxy" value={rows.filter(r => r.proxy).length} color={T.lilac} />
          <HealthChip label="Shared FP" value={colliding.size} color={colliding.size ? T.amber : T.mint} />
        </div>
        <div className="ps-hint"><Activity size={12} /> Start the engine (<code>persona serve</code>) for live trust grades, DNS/proxy status and warm-up schedules. Showing coherence and fingerprint collisions derived from the sample profiles.</div>
        <table className="ps-table" style={{ marginTop: 12 }}>
          <thead><tr><th>Profile</th><th>Engine</th><th>OS</th><th>Coherence</th><th>Proxy</th></tr></thead>
          <tbody>{rows.map((r, i) => (
            <tr key={r.id || i} className={r.collides ? "ps-attention" : ""}>
              <td>{r.name}{r.collides && <SharedTag />}</td>
              <td className="ps-mono dim">{r.engine || "—"}</td>
              <td><span className="ps-os">{r.os}</span></td>
              <td>{r.coherent ? <span className="ps-check ok" style={{ padding: 0, background: "none" }}><Check size={12} /> coherent</span>
                : <span className="ps-check" style={{ padding: 0, background: "none" }}><ShieldAlert size={12} /> {r.issues.length} issue(s)</span>}</td>
              <td className="ps-mono">{r.proxy ? (r.proxy.country || r.proxy.host) : "—"}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
    );
  }

  const rows = data?.profiles || [];
  const s = data?.summary || {};
  const act = async (id, label, fn) => {
    setBusy(b => ({ ...b, [id]: label }));
    try { await fn(); await load(); await refresh(); }
    catch (e) { alert(`${label} failed: ` + e.message); }
    setBusy(b => { const n = { ...b }; delete n[id]; return n; });
  };

  return (
    <div className="ps-scroll">
      <div className="ps-health-summary">
        <HealthChip label="Profiles" value={s.total ?? "—"} />
        <HealthChip label="Coherent" value={`${s.coherent ?? 0}/${s.total ?? 0}`} color={T.mint} />
        <HealthChip label="With proxy" value={`${s.withProxy ?? 0}/${s.total ?? 0}`} color={T.lilac} />
        <HealthChip label="Scheduled" value={s.scheduled ?? 0} color={T.violet} />
        <HealthChip label="Shared FP" value={s.colliding ?? 0} color={s.colliding ? T.amber : T.mint} />
        <HealthChip label="Needs attention" value={s.needsAttention ?? 0} color={s.needsAttention ? T.amber : T.mint} />
        <div style={{ flex: 1 }} />
        <button className="ps-btn ghost sm" onClick={load}><RefreshCw size={13} /> Refresh</button>
      </div>

      {rows.length === 0
        ? <div className="ps-empty"><Activity size={26} color={T.dim} /><div>No profiles yet.</div></div>
        : (
          <table className="ps-table">
            <thead><tr>
              <th>Profile</th><th>Engine</th><th>Coherence</th><th>Proxy</th>
              <th>Trust</th><th>Warm-up</th><th>Last active</th>
              <th style={{ width: 150, textAlign: "right" }}>Actions</th>
            </tr></thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={r.id} className={"ps-rise" + (r.needsAttention ? " ps-attention" : "")}
                    style={{ animationDelay: `${Math.min(i, 12) * 28}ms` }}>
                  <td>
                    <button className="ps-linkish" onClick={() => setEditor(profiles.find(p => p.id === r.id) || null)}>{r.name}</button>
                    {r.status === "running" && <span className="ps-runtag">live</span>}
                    {r.collides && <SharedTag />}
                  </td>
                  <td className="ps-mono dim">{r.engine}</td>
                  <td>{r.coherent
                    ? <span style={{ color: T.mint, display: "inline-flex", gap: 5, alignItems: "center" }}><Check size={13} /> ok</span>
                    : <span style={{ color: T.amber, display: "inline-flex", gap: 5, alignItems: "center" }} title={(r.issues || []).join("; ")}><ShieldAlert size={13} /> {r.issues.length}</span>}</td>
                  <td className="ps-mono">{r.proxy?.set ? (r.proxy.country || r.proxy.type || "set") : <span className="dim">none</span>}</td>
                  <td><GradeBadge grade={r.trust?.grade} /></td>
                  <td className="ps-mono dim">{r.schedule
                    ? <span title={`${r.schedule.preset}, every ${r.schedule.everyHours}h`} style={{ color: r.schedule.enabled ? T.lilac : T.dim }}><Clock size={11} /> {r.schedule.everyHours}h</span>
                    : "—"}</td>
                  <td className="ps-mono dim">{r.lastActive}</td>
                  <td>
                    <div className="ps-actions">
                      <button title="Run trust check" className="run" disabled={!!busy[r.id] || r.status === "running"}
                        onClick={() => act(r.id, "Trust check", () => api.trust(r.id))}>
                        {busy[r.id] === "Trust check" ? <RefreshCw size={13} className="ps-spin" /> : <ShieldCheck size={13} />}
                      </button>
                      <button title="Auto-adjust to grade A" className="run" disabled={!!busy[r.id] || r.status === "running"}
                        onClick={() => act(r.id, "Auto-adjust", () => api.align(r.id))}>
                        {busy[r.id] === "Auto-adjust" ? <RefreshCw size={13} className="ps-spin" /> : <Sparkles size={13} />}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      <div className="ps-hint"><Activity size={12} /> Coherence and proxy are read from each profile instantly; the <b style={{ color: T.text }}>trust grade is the last one measured</b> (a live check opens a real browser). Use <ShieldCheck size={11} /> to grade a profile and <Sparkles size={11} /> to auto-adjust it to grade A. Rows needing attention (incoherent, grade C/D, or a <Link2 size={11} /> shared fingerprint) are highlighted — regenerate one side of a shared pair so the accounts can't be linked.</div>
    </div>
  );
}

function HealthChip({ label, value, color }) {
  return (
    <div className="ps-hchip">
      <span className="ps-hchip-val" style={color ? { color } : undefined}>{value}</span>
      <span className="ps-hchip-label">{label}</span>
    </div>
  );
}

// Small "shared FP" flag for a profile that isn't fingerprint-unique.
function SharedTag() {
  return (
    <span className="ps-shared" title="Shares a fingerprint with another profile — a linkage risk">
      <Link2 size={10} /> shared FP
    </span>
  );
}

// Demo-mode fingerprint collision: which profiles look like the same device.
// Mirrors engine/collision.py's signature over the fields the sample data has.
function fpSignature(p) {
  return [p.os, p.userAgent, p.screen, p.cores, p.memory, p.webglRenderer].join("|");
}
function collidingIds(profiles) {
  const bySig = {};
  for (const p of profiles) (bySig[fpSignature(p)] ||= []).push(p.id);
  const out = new Set();
  for (const ids of Object.values(bySig)) if (ids.length > 1) ids.forEach(id => out.add(id));
  return out;
}

function ProxiesView({ profiles, live, refresh }) {
  const [pool, setPool] = useState([]);
  const [importOpen, setImportOpen] = useState(false);
  const [testing, setTesting] = useState(new Set());
  const [busy, setBusy] = useState("");

  const load = async () => { try { setPool(await api.listProxies()); } catch { /* offline */ } };
  useEffect(() => { if (live) load(); }, [live]);

  // Demo mode: no engine, so show the proxies derived from profiles, read-only.
  if (!live) {
    const derived = Object.values(profiles.filter(p => p.proxy).reduce((m, p) => {
      const k = p.proxy.host; (m[k] ||= { ...p.proxy, used: 0 }).used++; return m;
    }, {}));
    return (
      <div className="ps-scroll">
        <div className="ps-toolbar" style={{ paddingLeft: 0, paddingRight: 0 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: T.muted }}>Proxy pool</div>
        </div>
        <div className="ps-hint"><Globe size={12} /> Start the engine (<code>persona serve</code>) to import, test and assign a real proxy pool. Showing proxies in use by current profiles.</div>
        {derived.length > 0 && (
          <table className="ps-table" style={{ marginTop: 12 }}>
            <thead><tr><th>Host</th><th>Type</th><th>Country</th><th>Used by</th></tr></thead>
            <tbody>{derived.map((x, i) => (
              <tr key={i}><td className="ps-mono">{x.host}:{x.port}</td><td><span className="ps-os">{x.type}</span></td><td className="ps-mono">{x.country}</td><td className="ps-mono dim">{x.used}</td></tr>
            ))}</tbody>
          </table>
        )}
      </div>
    );
  }

  const testOne = async (id) => {
    setTesting(s => new Set(s).add(id));
    try { await api.testProxy(id); await load(); }
    catch (e) { alert("Test failed: " + e.message); }
    setTesting(s => { const n = new Set(s); n.delete(id); return n; });
  };
  const testAll = async () => {
    setBusy("test");
    for (const p of pool) { try { await api.testProxy(p.id); } catch { /* keep going */ } }
    await load(); setBusy("");
  };
  const del = async (id) => { try { await api.deleteProxy(id); await load(); } catch (e) { alert(e.message); } };
  const assign = async () => {
    if (!pool.length) return;
    if (!confirm(`Assign these ${pool.length} proxies round-robin across all ${profiles.length} profiles? Each profile's locale/timezone will align to its proxy's country.`)) return;
    setBusy("assign");
    try { const r = await api.assignProxies(); alert(`Assigned proxies to ${r.assigned} profile(s).`); await refresh(); }
    catch (e) { alert("Assign failed: " + e.message); }
    setBusy("");
  };

  const okCount = pool.filter(p => p.status === "ok").length;
  return (
    <div className="ps-scroll">
      <div className="ps-toolbar" style={{ paddingLeft: 0, paddingRight: 0 }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: T.muted }}>
          Proxy pool <span className="ps-mono dim">· {pool.length} total{okCount ? ` · ${okCount} live` : ""}</span>
        </div>
        <div style={{ flex: 1 }} />
        <button className="ps-btn ghost sm" disabled={!pool.length || busy === "test"} onClick={testAll}>
          {busy === "test" ? <><RefreshCw size={13} className="ps-spin" /> Testing…</> : <><Wifi size={13} /> Test all</>}
        </button>
        <button className="ps-btn ghost sm" disabled={!pool.length || !profiles.length || busy === "assign"} onClick={assign}>
          {busy === "assign" ? <><RefreshCw size={13} className="ps-spin" /> Assigning…</> : <><ArrowRight size={13} /> Assign to profiles</>}
        </button>
        <button className="ps-btn primary sm" onClick={() => setImportOpen(true)}><Plus size={13} /> Import proxies</button>
      </div>

      {pool.length === 0
        ? <div className="ps-empty"><Globe size={26} color={T.dim} /><div>No proxies yet.</div>
            <button className="ps-btn primary sm" onClick={() => setImportOpen(true)}><Plus size={14} /> Import proxies</button></div>
        : (
          <table className="ps-table">
            <thead><tr><th>Host</th><th>Type</th><th>Country</th><th>Auth</th><th>Status</th><th style={{ width: 120, textAlign: "right" }}>Actions</th></tr></thead>
            <tbody>
              {pool.map((x, i) => (
                <tr key={x.id} className="ps-rise" style={{ animationDelay: `${Math.min(i, 12) * 28}ms` }}>
                  <td className="ps-mono">{x.host}:{x.port}</td>
                  <td><span className="ps-os">{x.type}</span></td>
                  <td className="ps-mono">{x.country || "—"}</td>
                  <td className="ps-mono dim">{x.user ? "user:•••" : "none"}</td>
                  <td><ProxyStatus p={x} /></td>
                  <td>
                    <div className="ps-actions">
                      <button title="Test" className="run" disabled={testing.has(x.id)} onClick={() => testOne(x.id)}>
                        {testing.has(x.id) ? <RefreshCw size={13} className="ps-spin" /> : <Wifi size={13} />}
                      </button>
                      <button title="Delete" className="del" onClick={() => del(x.id)}><Trash2 size={13} /></button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      <div className="ps-hint"><Globe size={12} /> Import a list, test which are live, then <b style={{ color: T.text }}>Assign to profiles</b> spreads them round-robin and aligns each profile's locale/timezone to its proxy country. Health checks run over HTTP(S); SOCKS proxies are tested when you run a profile's proxy test.</div>

      {importOpen && <ImportProxiesModal onClose={() => setImportOpen(false)} onImport={async (text) => {
        const r = await api.addProxies(text); await load(); return r;
      }} />}
    </div>
  );
}

function ImportProxiesModal({ onClose, onImport }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const lines = text.split("\n").filter(l => l.trim() && !l.trim().startsWith("#")).length;
  const submit = async () => {
    setBusy(true);
    try { const r = await onImport(text); alert(`Added ${r.added} proxy(ies). Pool now has ${r.total}.`); onClose(); }
    catch (e) { alert("Import failed: " + e.message); setBusy(false); }
  };
  return (
    <div className="ps-overlay center" onClick={busy ? undefined : onClose}>
      <div className="ps-modal ps-pop" onClick={e => e.stopPropagation()} style={{ maxWidth: 540 }}>
        <div className="ps-drawer-h">
          <div><div className="ps-eyebrow">Proxy pool</div><div className="ps-drawer-title">Import proxies</div></div>
          <button className="ps-x" onClick={onClose} disabled={busy}><X size={18} /></button>
        </div>
        <div style={{ padding: 20 }}>
          <Field label="Paste one proxy per line">
            <textarea className="ps-in mono" rows={9} value={text} onChange={e => setText(e.target.value)}
              placeholder={"host:port\nhost:port:user:pass\nuser:pass@host:port\nhttp://user:pass@host:port\nsocks5://host:port\nhost:port:user:pass:US"} />
          </Field>
          <label className={"ps-btn ghost sm" + (busy ? " disabled" : "")} style={{ marginTop: 8 }}>
            <Upload size={13} /> Load from file
            <input type="file" accept=".txt,.csv,.json" style={{ display: "none" }} disabled={busy}
              onChange={async e => { const f = e.target.files?.[0]; if (f) setText(await f.text()); e.target.value = ""; }} />
          </label>
          <div className="ps-hint"><Server size={12} /> Understands <code>host:port</code>, <code>host:port:user:pass</code>, <code>user:pass@host:port</code> and <code>scheme://…</code>, with an optional trailing country code. {lines > 0 ? <b style={{ color: T.text }}>{lines} line{lines === 1 ? "" : "s"} detected.</b> : ""}</div>
        </div>
        <div className="ps-drawer-foot">
          <button className="ps-btn ghost" onClick={onClose} disabled={busy}>Cancel</button>
          <button className="ps-btn primary" onClick={submit} disabled={busy || !lines}>
            {busy ? <><RefreshCw size={15} className="ps-spin" /> Importing…</> : <><Plus size={15} /> Add {lines || ""} prox{lines === 1 ? "y" : "ies"}</>}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ---- Automation view --------------------------------------------- */
const CDP_LANGS = ["Playwright", "Puppeteer", "Selenium"];
function cdpSnippet(lang, port) {
  const base = `http://127.0.0.1:${port}`;
  if (lang === "Puppeteer")
    return `const browser = await puppeteer.connect({ browserURL: "${base}" });\nconst [page] = await browser.pages();`;
  if (lang === "Selenium")
    return `from selenium import webdriver\nopts = webdriver.ChromeOptions()\nopts.add_experimental_option("debuggerAddress", "127.0.0.1:${port}")\ndriver = webdriver.Chrome(options=opts)`;
  return `from playwright.sync_api import sync_playwright\npw = sync_playwright().start()\nbrowser = pw.chromium.connect_over_cdp("${base}")\npage = browser.contexts[0].pages[0]`;
}

function AutomationView({ profiles, live, refresh }) {
  const [info, setInfo] = useState({});     // pid -> { port, wsUrl, snippets }
  const [busy, setBusy] = useState("");
  const [lang, setLang] = useState("Playwright");
  const [copied, setCopied] = useState("");
  const CHROMIUM = ["cloak", "patchright", "playwright"];

  const copy = (text, key) => {
    navigator.clipboard?.writeText(text);
    setCopied(key); setTimeout(() => setCopied(c => (c === key ? "" : c)), 1200);
  };
  const attach = async (id) => {
    setBusy(id);
    try { const r = await api.attach(id); setInfo(m => ({ ...m, [id]: r })); await refresh(); }
    catch (e) { alert("Attach failed: " + e.message); }
    setBusy("");
  };
  const detach = async (id) => {
    setBusy(id);
    try { await api.stop(id); setInfo(m => { const n = { ...m }; delete n[id]; return n; }); await refresh(); }
    catch (e) { alert("Detach failed: " + e.message); }
    setBusy("");
  };

  const intro = (
    <div className="ps-hint"><Zap size={12} /> Persona opens the browser wearing the identity; your script <b style={{ color: T.text }}>attaches to that same window</b> over the Chrome DevTools Protocol — so the session, cookies, proxy and fingerprint stay exactly as set. (A browser your automation launches itself would be un-spoofed.) Chromium engines only — <code>cloak</code>, <code>patchright</code>, <code>playwright</code>.</div>
  );

  // Demo mode: no engine to attach to, so show how it works with the CLI and a
  // static example.
  if (!live) {
    return (
      <div className="ps-scroll">
        {intro}
        <div className="ps-cdp" style={{ marginTop: 12 }}>
          <div className="ps-cdp-h"><Server size={13} /> Start the engine, then attach</div>
          <pre className="ps-code">persona attach acct-01 --port 9222</pre>
          <div className="ps-lang-tabs">{CDP_LANGS.map(l => (
            <button key={l} className={"ps-chip" + (lang === l ? " on" : "")} onClick={() => setLang(l)}>{l}</button>
          ))}</div>
          <pre className="ps-code">{cdpSnippet(lang, 9222)}</pre>
        </div>
        <div className="ps-hint"><Activity size={12} /> Start <code>persona serve</code> to attach a real profile from here with one click.</div>
      </div>
    );
  }

  return (
    <div className="ps-scroll">
      {intro}
      {profiles.length === 0
        ? <div className="ps-empty"><Zap size={26} color={T.dim} /><div>No profiles to attach yet.</div></div>
        : (
          <table className="ps-table" style={{ marginTop: 12 }}>
            <thead><tr>
              <th>Profile</th><th>Engine</th><th>Status</th>
              <th style={{ width: 160, textAlign: "right" }}>Automation</th>
            </tr></thead>
            <tbody>
              {profiles.map((p, i) => {
                const canAttach = CHROMIUM.includes(p.engine || "playwright");
                const conn = info[p.id];
                const attachedHere = !!conn;
                const running = p.status === "running";
                return (
                  <React.Fragment key={p.id}>
                    <tr className={"ps-rise" + (attachedHere ? " sel" : "")} style={{ animationDelay: `${Math.min(i, 12) * 28}ms` }}>
                      <td className="ps-pname">{p.name}</td>
                      <td><span className="ps-engine-chip">{ENGINE_META[p.engine]?.label || p.engine || "Playwright"}</span></td>
                      <td>{attachedHere
                        ? <span style={{ color: T.mint, display: "inline-flex", gap: 5, alignItems: "center" }}><Circle size={9} /> attached :{conn.port}</span>
                        : running ? <span className="ps-mono dim">running</span> : <span className="ps-mono dim">stopped</span>}</td>
                      <td>
                        <div className="ps-actions" style={{ justifyContent: "flex-end" }}>
                          {attachedHere
                            ? <button className="danger" title="Close the attached browser" disabled={busy === p.id}
                                onClick={() => detach(p.id)}>{busy === p.id ? <RefreshCw size={13} className="ps-spin" /> : <Square size={13} />} Detach</button>
                            : <button className="run" disabled={!canAttach || running || busy === p.id}
                                title={!canAttach ? "This engine has no DevTools — switch to cloak/patchright/playwright"
                                       : running ? "Stop the profile first" : "Open with a CDP endpoint"}
                                onClick={() => attach(p.id)}>{busy === p.id ? <RefreshCw size={13} className="ps-spin" /> : <Zap size={13} />} Attach</button>}
                        </div>
                      </td>
                    </tr>
                    {attachedHere && (
                      <tr className="ps-cdp-row"><td colSpan={4}>
                        <div className="ps-cdp">
                          <div className="ps-cdp-h"><Server size={13} /> Connect your automation
                            <span style={{ flex: 1 }} />
                            <button className="ps-copy" onClick={() => copy(`http://127.0.0.1:${conn.port}`, p.id + "url")}>
                              <Clipboard size={12} /> {copied === p.id + "url" ? "Copied" : `127.0.0.1:${conn.port}`}</button>
                          </div>
                          <div className="ps-lang-tabs">{CDP_LANGS.map(l => (
                            <button key={l} className={"ps-chip" + (lang === l ? " on" : "")} onClick={() => setLang(l)}>{l}</button>
                          ))}</div>
                          <div className="ps-code-wrap">
                            <pre className="ps-code">{cdpSnippet(lang, conn.port)}</pre>
                            <button className="ps-copy floaty" onClick={() => copy(cdpSnippet(lang, conn.port), p.id + lang)}>
                              <Clipboard size={12} /> {copied === p.id + lang ? "Copied" : "Copy"}</button>
                          </div>
                        </div>
                      </td></tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        )}
    </div>
  );
}

function Placeholder({ view }) {
  const map = {
    folders: [FolderTree, "Folder manager", "Organize profiles into folders and drag between them."],
    team: [Users, "Team", "Invite members, set roles, and share profiles securely."],
    settings: [Settings, "Settings", "Engine paths, storage location, and defaults."],
  };
  const [Ic, title, desc] = map[view] || [Boxes, "Soon", ""];
  return (
    <div className="ps-scroll">
      <div className="ps-empty" style={{ marginTop: 48 }}>
        <div className="ps-empty-ic"><Ic size={26} color={T.violet} /></div>
        <div style={{ fontSize: 16, fontWeight: 600, fontFamily: FONT.display }}>{title}</div>
        <div style={{ color: T.muted, fontSize: 13, maxWidth: 360, textAlign: "center", lineHeight: 1.6 }}>{desc}</div>
        <span className="ps-pill" style={{ background: T.violetDim, color: T.lilac }}>On the roadmap</span>
      </div>
    </div>
  );
}

/* ---- form atoms -------------------------------------------------- */
const Field = ({ label, children }) => (<label className="ps-field"><span className="ps-flabel">{label}</span>{children}</label>);
const Row = ({ children }) => <div className="ps-row">{children}</div>;
const SectionLabel = ({ icon, text }) => (<div className="ps-seclabel">{icon}<span>{text}</span><div className="ps-secline" /></div>);
const SectionHead = ({ icon, text, note }) => (
  <div className="ps-sechead"><span className="ps-sechead-ic">{icon}</span><span className="ps-sechead-t">{text}</span>{note && <span className="ps-sechead-n">{note}</span>}</div>
);
const Pick = ({ label, opts, val, on }) => (
  <div className="ps-field"><span className="ps-flabel">{label}</span>
    <div className="ps-seg">{opts.map(o => <button key={o} className={val === o ? "on" : ""} onClick={() => on(o)}>{o}</button>)}</div>
  </div>
);

/* ---- styles ------------------------------------------------------ */
const css = `
* { box-sizing: border-box; }
::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-thumb { background: ${T.line}; border-radius: 6px; }
::-webkit-scrollbar-thumb:hover { background: #33334f; }
::-webkit-scrollbar-track { background: transparent; }
::selection { background: ${T.violet}44; }
a { color: inherit; }

@keyframes rise { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
@keyframes slidein { from { transform: translateX(28px); opacity: .3; } to { transform: none; opacity: 1; } }
@keyframes pop { from { transform: scale(.96) translateY(6px); opacity: 0; } to { transform: none; opacity: 1; } }
@keyframes pulsering { 0% { box-shadow: 0 0 0 0 ${T.mint}55; } 70% { box-shadow: 0 0 0 6px ${T.mint}00; } 100% { box-shadow: 0 0 0 0 ${T.mint}00; } }
@keyframes haloshift { 0%,100% { transform: rotate(0deg); } 50% { transform: rotate(180deg); } }
.ps-rise { animation: rise .42s cubic-bezier(.2,.7,.3,1) both; }

.ps-shell { display: flex; min-height: 100vh; }

/* sidebar */
.ps-side { width: 244px; flex-shrink: 0; background: linear-gradient(180deg, ${T.bg2}, ${T.bg}); border-right: 1px solid ${T.line}; display: flex; flex-direction: column; padding: 18px 13px; position: sticky; top: 0; height: 100vh; }
.ps-brand { display: flex; align-items: center; gap: 12px; padding: 4px 6px 20px; }
.ps-logo { position: relative; width: 36px; height: 36px; border-radius: 11px; background: linear-gradient(135deg, ${T.violet}, ${T.violetDeep}); display: flex; align-items: center; justify-content: center; overflow: hidden; box-shadow: 0 4px 18px ${T.violet}44; }
.ps-logo-glow { position: absolute; inset: -40%; background: conic-gradient(from 0deg, ${T.mint}00, ${T.mint}88, ${T.mint}00 40%); animation: haloshift 6s linear infinite; opacity: .5; }
.ps-brand-name { font-family: ${FONT.display}; font-weight: 700; font-size: 16px; letter-spacing: -.2px; }
.ps-brand-sub { font-size: 10px; color: ${T.dim}; letter-spacing: 3px; text-transform: uppercase; margin-top: 1px; }
.ps-nav { display: flex; flex-direction: column; gap: 3px; }
.ps-navitem { display: flex; align-items: center; gap: 11px; padding: 9px 11px; border-radius: 9px; border: none; background: transparent; color: ${T.muted}; font-size: 13px; font-weight: 500; cursor: pointer; transition: .14s; text-align: left; position: relative; }
.ps-navitem:hover { background: ${T.surface}; color: ${T.text}; }
.ps-navitem.active { background: ${T.surface2}; color: ${T.text}; box-shadow: inset 2px 0 0 ${T.violet}; }
.ps-nav-tag { position: absolute; right: 10px; font-size: 9px; font-weight: 700; letter-spacing: .5px; text-transform: uppercase; color: ${T.bg}; background: ${T.mint}; padding: 1px 5px; border-radius: 5px; }
.ps-folders { margin-top: 22px; flex: 1; overflow-y: auto; }
.ps-folders-h { font-size: 10px; letter-spacing: 1.6px; text-transform: uppercase; color: ${T.dim}; padding: 0 8px 8px; }
.ps-folder { display: flex; align-items: center; gap: 8px; width: 100%; padding: 7px 9px; border-radius: 8px; border: none; background: transparent; color: ${T.muted}; font-size: 12.5px; cursor: pointer; transition: .14s; }
.ps-folder:hover { background: ${T.surface}; color: ${T.text}; }
.ps-folder.active { color: ${T.lilac}; background: ${T.violetDim}; }
.ps-count { font-size: 11px; color: ${T.dim}; font-family: ${FONT.mono}; }
.ps-side-foot { display: flex; align-items: center; gap: 8px; font-size: 11.5px; color: ${T.muted}; padding: 11px 10px; margin-top: 8px; border-top: 1px solid ${T.lineSoft}; }
.ps-foot-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; background: ${T.grey}; }
.ps-side-foot.live .ps-foot-dot { background: ${T.mint}; animation: pulsering 2.4s infinite; }
.ps-side-foot.demo .ps-foot-dot { background: ${T.amber}; }
.ps-foot-ver { margin-left: auto; font-family: ${FONT.mono}; font-size: 10.5px; color: ${T.dim}; }

/* main */
.ps-main { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.ps-stats { display: flex; align-items: center; gap: 26px; padding: 18px 26px; border-bottom: 1px solid ${T.line}; background: ${T.bg2}; flex-wrap: wrap; }
.ps-stat { display: flex; align-items: center; gap: 11px; }
.ps-stat-ic { width: 34px; height: 34px; border-radius: 10px; background: ${T.surface}; border: 1px solid ${T.line}; display: flex; align-items: center; justify-content: center; }
.ps-stat-ic.pulse { animation: pulsering 2.4s infinite; }
.ps-stat-val { font-size: 19px; font-weight: 700; font-family: ${FONT.display}; letter-spacing: -.3px; }
.ps-stat-label { font-size: 10.5px; color: ${T.dim}; text-transform: uppercase; letter-spacing: 1.2px; margin-top: 1px; }

.ps-btn { display: inline-flex; align-items: center; gap: 7px; border-radius: 10px; padding: 9px 15px; font-size: 13px; font-weight: 600; cursor: pointer; border: 1px solid transparent; transition: .14s; font-family: inherit; }
.ps-btn.sm { padding: 7px 11px; font-size: 12px; }
.ps-btn.primary { background: linear-gradient(135deg, ${T.violet}, ${T.violetDeep}); color: #fff; box-shadow: 0 3px 14px ${T.violet}33; }
.ps-btn.primary:hover { filter: brightness(1.08); transform: translateY(-1px); }
.ps-btn.primary:active { transform: none; }
.ps-btn.primary:disabled { opacity: .4; cursor: not-allowed; box-shadow: none; transform: none; }
.ps-btn.ghost { background: ${T.surface}; border-color: ${T.line}; color: ${T.text}; }
.ps-btn.ghost:hover { background: ${T.surface2}; border-color: #33334f; }

.ps-toolbar { display: flex; align-items: center; gap: 12px; padding: 16px 26px; }
.ps-search { display: flex; align-items: center; gap: 8px; background: ${T.surface}; border: 1px solid ${T.line}; border-radius: 10px; padding: 9px 12px; width: 320px; max-width: 42vw; transition: .14s; }
.ps-search:focus-within { border-color: ${T.violet}; box-shadow: 0 0 0 3px ${T.violet}22; }
.ps-search input { background: transparent; border: none; outline: none; color: ${T.text}; font-size: 13px; width: 100%; font-family: inherit; }
.ps-crumb { display: flex; align-items: center; gap: 6px; font-size: 12px; color: ${T.muted}; }
.ps-bulkbar { display: flex; align-items: center; gap: 8px; font-size: 12px; color: ${T.muted}; background: ${T.surface}; padding: 5px 8px 5px 12px; border-radius: 9px; border: 1px solid ${T.line}; }
.ps-bulkbar button { display: flex; align-items: center; gap: 5px; border: none; background: ${T.violetDim}; color: ${T.lilac}; padding: 5px 9px; border-radius: 7px; font-size: 12px; cursor: pointer; font-family: inherit; }
.ps-bulkbar button.danger { background: transparent; color: ${T.red}; }

.ps-scroll { flex: 1; overflow: auto; padding: 8px 26px 28px; }

/* table */
.ps-table { width: 100%; border-collapse: separate; border-spacing: 0; }
.ps-table th { text-align: left; font-size: 10.5px; letter-spacing: 1px; text-transform: uppercase; color: ${T.dim}; font-weight: 600; padding: 11px 13px; border-bottom: 1px solid ${T.line}; position: sticky; top: 0; background: ${T.bg}; z-index: 1; }
.ps-table th:last-child { text-align: right; }
.ps-table td { padding: 13px; border-bottom: 1px solid ${T.lineSoft}; vertical-align: middle; }
.ps-table tbody tr { transition: background .14s; }
.ps-table tbody tr:hover td { background: ${T.bg2}; }
.ps-table tr.sel td { background: ${T.violetDim}; }
.ps-name { display: flex; align-items: center; gap: 12px; }
.ps-pname { font-weight: 600; font-size: 13px; }
.ps-status { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.ps-status.running { background: ${T.mint}; animation: pulsering 2.4s infinite; }
.ps-status.stopped { background: ${T.grey}; }
.ps-tags { display: flex; gap: 4px; margin-top: 4px; flex-wrap: wrap; }
.ps-tag { font-size: 10px; color: ${T.muted}; background: ${T.surface}; border: 1px solid ${T.line}; padding: 1px 6px; border-radius: 5px; }
.ps-tag.clickable { cursor: pointer; transition: border-color .15s, color .15s; }
.ps-tag.clickable:hover { color: ${T.text}; border-color: ${T.violet}; }
.ps-tag.on { color: ${T.bg}; background: ${T.violet}; border-color: ${T.violet}; }
.ps-shared { display: inline-flex; align-items: center; gap: 3px; margin-left: 8px; font-size: 9px; font-weight: 700; letter-spacing: .4px; text-transform: uppercase; color: ${T.amber}; background: ${T.amberDim || "rgba(240,180,80,.14)"}; padding: 1px 6px; border-radius: 5px; vertical-align: middle; }
.ps-cdp-row td { padding: 0 !important; background: none; }
.ps-cdp { margin: 2px 0 14px; border: 1px solid ${T.line}; border-radius: 10px; background: ${T.surface}; padding: 14px; }
.ps-cdp-h { display: flex; align-items: center; gap: 7px; font-size: 12px; font-weight: 600; color: ${T.muted}; margin-bottom: 10px; }
.ps-lang-tabs { display: flex; gap: 6px; margin-bottom: 10px; }
.ps-code-wrap { position: relative; }
.ps-code { font-family: ${FONT.mono}; font-size: 12px; line-height: 1.55; color: ${T.text}; background: ${T.bg}; border: 1px solid ${T.line}; border-radius: 8px; padding: 12px 14px; margin: 0; overflow-x: auto; white-space: pre; }
.ps-copy { display: inline-flex; align-items: center; gap: 5px; font-size: 11px; font-family: ${FONT.mono}; color: ${T.lilac}; background: ${T.violetDim}; border: 1px solid ${T.line}; border-radius: 6px; padding: 3px 9px; cursor: pointer; transition: color .15s, border-color .15s; }
.ps-copy:hover { color: ${T.text}; border-color: ${T.violet}; }
.ps-copy.floaty { position: absolute; top: 8px; right: 8px; }
.ps-env { display: flex; align-items: center; gap: 8px; }
.ps-os { font-size: 11px; font-weight: 600; color: ${T.lilac}; background: ${T.violetDim}; padding: 2px 8px; border-radius: 6px; }
.ps-engine-chip { font-size: 11px; font-weight: 500; color: ${T.muted}; background: ${T.surface}; border: 1px solid ${T.line}; padding: 3px 9px; border-radius: 6px; }
.ps-mono { font-family: ${FONT.mono}; font-size: 11.5px; }
.ps-mono.dim, .dim { color: ${T.dim}; }
.ps-proxy { display: flex; align-items: center; gap: 6px; font-size: 12px; }
.ps-proxy.off { color: ${T.dim}; }
.ps-pill { display: inline-flex; align-items: center; gap: 5px; font-size: 11px; font-weight: 600; padding: 3px 9px; border-radius: 20px; }
.ps-pill.ok { color: ${T.mint}; background: ${T.mint}1a; }
.ps-pill.warn { color: ${T.amber}; background: ${T.amber}1a; cursor: help; }
.ps-actions { display: flex; gap: 5px; justify-content: flex-end; }
.ps-actions button { width: 31px; height: 31px; border-radius: 8px; border: 1px solid ${T.line}; background: ${T.surface}; color: ${T.muted}; display: flex; align-items: center; justify-content: center; cursor: pointer; transition: .14s; }
.ps-actions button:hover { color: ${T.text}; background: ${T.surface2}; transform: translateY(-1px); }
.ps-actions button.run:hover { color: ${T.mint}; border-color: ${T.mint}; }
.ps-actions button.stop { color: ${T.amber}; border-color: ${T.amber}66; }
.ps-actions button.del:hover { color: ${T.red}; border-color: ${T.red}; }
.ps-empty { display: flex; flex-direction: column; align-items: center; gap: 13px; padding: 64px; color: ${T.muted}; font-size: 13px; }
.ps-empty-ic { width: 52px; height: 52px; border-radius: 14px; background: ${T.violetDim}; display: flex; align-items: center; justify-content: center; }
input[type=checkbox] { accent-color: ${T.violet}; width: 15px; height: 15px; cursor: pointer; }

/* health view */
.ps-health-summary { display: flex; gap: 10px; align-items: center; margin: 4px 0 16px; flex-wrap: wrap; }
.ps-hchip { display: flex; flex-direction: column; gap: 2px; padding: 10px 15px; border-radius: 12px; background: ${T.surface}; border: 1px solid ${T.line}; min-width: 92px; }
.ps-hchip-val { font-family: ${FONT.display}; font-size: 19px; font-weight: 600; color: ${T.text}; }
.ps-hchip-label { font-size: 10.5px; letter-spacing: .5px; text-transform: uppercase; color: ${T.dim}; }
.ps-grade { display: inline-flex; align-items: center; justify-content: center; min-width: 22px; height: 22px; padding: 0 6px; border-radius: 6px; border: 1px solid; font-family: ${FONT.mono}; font-size: 12px; font-weight: 700; }
.ps-table tr.ps-attention td { box-shadow: inset 2px 0 0 ${T.amber}; }
.ps-linkish { background: none; border: none; color: ${T.text}; font-weight: 600; font-size: 13px; cursor: pointer; padding: 0; font-family: inherit; }
.ps-linkish:hover { color: ${T.violet}; text-decoration: underline; }
.ps-runtag { margin-left: 8px; font-size: 9px; font-weight: 700; letter-spacing: .5px; text-transform: uppercase; color: ${T.mint}; background: ${T.mintDim}; padding: 1px 5px; border-radius: 5px; }

/* engines view */
.ps-eng-hero { padding: 30px 32px 26px; margin: 8px 0 22px; border-radius: 18px; background: radial-gradient(120% 140% at 0% 0%, ${T.violet}22, transparent 55%), linear-gradient(180deg, ${T.bg2}, ${T.surface}); border: 1px solid ${T.line}; position: relative; overflow: hidden; }
.ps-eng-hero-badge { display: inline-flex; align-items: center; gap: 6px; font-size: 11px; font-weight: 600; color: ${T.lilac}; background: ${T.violetDim}; border: 1px solid ${T.violet}44; padding: 4px 10px; border-radius: 20px; margin-bottom: 16px; }
.ps-eng-title { font-family: ${FONT.display}; font-size: 30px; font-weight: 700; line-height: 1.12; letter-spacing: -.6px; margin: 0 0 12px; }
.ps-eng-title .grad { background: linear-gradient(100deg, ${T.violet}, ${T.mint}); -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; }
.ps-eng-lead { color: ${T.muted}; font-size: 14px; line-height: 1.65; max-width: 640px; margin: 0 0 18px; }
.ps-eng-flow { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.ps-flow-node { display: inline-flex; align-items: center; gap: 7px; font-size: 12.5px; font-weight: 500; color: ${T.text}; background: ${T.surface}; border: 1px solid ${T.line}; padding: 8px 13px; border-radius: 10px; }
.ps-flow-node svg { color: ${T.violet}; }

.ps-sechead { display: flex; align-items: center; gap: 9px; margin: 8px 2px 14px; }
.ps-sechead-ic { color: ${T.violet}; display: flex; }
.ps-sechead-t { font-family: ${FONT.display}; font-size: 14px; font-weight: 600; }
.ps-sechead-n { font-size: 11.5px; color: ${T.dim}; }
.ps-eng-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 15px; margin-bottom: 30px; }
.ps-eng-card { background: ${T.surface}; border: 1px solid ${T.line}; border-radius: 15px; padding: 18px; display: flex; flex-direction: column; gap: 13px; transition: .16s; }
.ps-eng-card:hover { transform: translateY(-3px); border-color: #38385a; box-shadow: 0 10px 30px #00000055; }
.ps-eng-card.featured { border-color: ${T.violet}55; background: linear-gradient(180deg, ${T.violet}0e, ${T.surface}); }
.ps-eng-card-top { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
.ps-eng-name { font-family: ${FONT.display}; font-size: 16px; font-weight: 600; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.ps-rec { display: inline-flex; align-items: center; gap: 3px; font-size: 9.5px; font-weight: 700; text-transform: uppercase; letter-spacing: .4px; color: ${T.violet}; background: ${T.violetDim}; padding: 2px 7px; border-radius: 12px; font-family: ${FONT.body}; }
.ps-rec svg { fill: ${T.violet}; }
.ps-eng-kind { font-size: 11.5px; color: ${T.dim}; margin-top: 3px; }
.ps-eng-status { display: inline-flex; align-items: center; gap: 6px; font-size: 11px; font-weight: 600; white-space: nowrap; }
.ps-eng-status-dot { width: 7px; height: 7px; border-radius: 50%; }
.ps-strength { display: flex; align-items: center; gap: 9px; }
.ps-strength-label { font-size: 10px; text-transform: uppercase; letter-spacing: .8px; color: ${T.dim}; }
.ps-strength-bars { display: flex; gap: 4px; }
.ps-sb { width: 22px; height: 5px; border-radius: 3px; background: ${T.line}; transition: .2s; }
.ps-sb.on { background: linear-gradient(90deg, ${T.violet}, ${T.mint}); }
.ps-eng-desc { font-size: 12.5px; color: ${T.muted}; line-height: 1.6; margin: 0; flex: 1; }
.ps-eng-install { display: flex; align-items: center; gap: 8px; background: ${T.bg}; border: 1px solid ${T.line}; border-radius: 9px; padding: 8px 10px; }
.ps-eng-install code { font-family: ${FONT.mono}; font-size: 11px; color: ${T.lilac}; flex: 1; overflow-x: auto; white-space: nowrap; }
.ps-eng-install button { flex-shrink: 0; width: 28px; height: 28px; border-radius: 7px; border: 1px solid ${T.line}; background: ${T.surface}; color: ${T.muted}; cursor: pointer; display: flex; align-items: center; justify-content: center; transition: .14s; }
.ps-eng-install button:hover { color: ${T.text}; border-color: ${T.violet}; }
.ps-eng-builtin { display: flex; align-items: center; gap: 7px; font-size: 12px; color: ${T.muted}; background: ${T.mintDim}55; border: 1px solid ${T.mint}33; border-radius: 9px; padding: 9px 11px; }
.ps-eng-docs { display: inline-flex; align-items: center; gap: 5px; font-size: 12px; font-weight: 600; color: ${T.lilac}; text-decoration: none; }
.ps-eng-docs:hover { color: ${T.violet}; }
.ps-eng-note { display: flex; align-items: center; gap: 9px; font-size: 12.5px; color: ${T.muted}; background: ${T.surface}; border: 1px solid ${T.line}; border-radius: 12px; padding: 14px 16px; }
.ps-eng-note code { font-family: ${FONT.mono}; font-size: 11.5px; color: ${T.lilac}; background: ${T.bg}; padding: 2px 6px; border-radius: 5px; }

/* overlay + drawer */
.ps-overlay { position: fixed; inset: 0; background: #05060acc; backdrop-filter: blur(4px); display: flex; justify-content: flex-end; z-index: 50; animation: rise .18s ease; }
.ps-overlay.center { justify-content: center; align-items: center; }
.ps-drawer { width: 580px; max-width: 96vw; height: 100%; background: ${T.bg2}; border-left: 1px solid ${T.line}; display: flex; flex-direction: column; animation: slidein .24s cubic-bezier(.2,.7,.3,1); }
.ps-modal { width: 520px; max-width: 94vw; background: ${T.bg2}; border: 1px solid ${T.line}; border-radius: 16px; overflow: hidden; }
.ps-pop { animation: pop .2s cubic-bezier(.2,.7,.3,1); }
.ps-drawer-h { display: flex; align-items: flex-start; justify-content: space-between; padding: 22px; border-bottom: 1px solid ${T.line}; }
.ps-eyebrow { font-size: 11px; color: ${T.dim}; letter-spacing: 1.6px; text-transform: uppercase; }
.ps-drawer-title { font-family: ${FONT.display}; font-size: 18px; font-weight: 700; margin-top: 3px; letter-spacing: -.3px; }
.ps-x { width: 33px; height: 33px; border-radius: 9px; border: 1px solid ${T.line}; background: ${T.surface}; color: ${T.muted}; cursor: pointer; display: flex; align-items: center; justify-content: center; transition: .14s; }
.ps-x:hover { color: ${T.text}; background: ${T.surface2}; }
.ps-coh { padding: 16px 22px; background: ${T.bg}; border-bottom: 1px solid ${T.line}; }
.ps-coh-top { display: flex; align-items: center; justify-content: space-between; }
.ps-coh-h { display: flex; align-items: center; gap: 7px; font-size: 12.5px; font-weight: 600; }
.ps-coh-score { font-family: ${FONT.mono}; font-weight: 600; font-size: 14px; }
.ps-coh-bar { height: 6px; border-radius: 4px; background: ${T.surface2}; margin: 11px 0 9px; overflow: hidden; }
.ps-coh-bar div { height: 100%; border-radius: 4px; transition: width .35s cubic-bezier(.2,.7,.3,1), background .35s; }
.ps-coh-iss { font-size: 11.5px; color: ${T.amber}; display: flex; flex-direction: column; gap: 2px; }
.ps-coh-ok { font-size: 11.5px; color: ${T.muted}; }
.ps-tabs { display: flex; gap: 4px; padding: 13px 22px 0; border-bottom: 1px solid ${T.line}; }
.ps-tab { text-transform: capitalize; background: transparent; border: none; color: ${T.muted}; font-size: 13px; font-weight: 600; padding: 9px 13px; cursor: pointer; border-bottom: 2px solid transparent; margin-bottom: -1px; transition: .14s; font-family: inherit; }
.ps-tab:hover { color: ${T.text}; }
.ps-tab.active { color: ${T.lilac}; border-bottom-color: ${T.violet}; }
.ps-drawer-body { flex: 1; overflow-y: auto; padding: 20px 22px; }
.ps-field { display: flex; flex-direction: column; gap: 6px; margin-bottom: 15px; flex: 1; min-width: 0; }
.ps-flabel { font-size: 11px; color: ${T.muted}; font-weight: 600; display: flex; align-items: center; gap: 4px; }
.ps-in { background: ${T.bg}; border: 1px solid ${T.line}; border-radius: 9px; padding: 10px 12px; color: ${T.text}; font-size: 13px; outline: none; width: 100%; font-family: inherit; resize: vertical; transition: .14s; }
.ps-in:focus { border-color: ${T.violet}; box-shadow: 0 0 0 3px ${T.violet}22; }
.ps-in.mono { font-family: ${FONT.mono}; font-size: 11.5px; }
select.ps-in { cursor: pointer; }
.ps-row { display: flex; gap: 12px; }
.ps-seclabel { display: flex; align-items: center; gap: 9px; margin: 20px 0 13px; color: ${T.muted}; font-size: 11px; font-weight: 700; letter-spacing: .6px; text-transform: uppercase; }
.ps-seclabel svg { color: ${T.violet}; }
.ps-secline { flex: 1; height: 1px; background: ${T.lineSoft}; }
.ps-seg { display: flex; background: ${T.bg}; border: 1px solid ${T.line}; border-radius: 9px; padding: 2px; }
.ps-seg button { flex: 1; border: none; background: transparent; color: ${T.muted}; font-size: 11.5px; font-weight: 600; padding: 6px; border-radius: 7px; cursor: pointer; transition: .14s; font-family: inherit; }
.ps-seg button.on { background: ${T.violetDim}; color: ${T.lilac}; }
.ps-toggle { display: flex; align-items: center; gap: 9px; background: ${T.bg}; border: 1px solid ${T.line}; border-radius: 9px; padding: 8px 11px; cursor: pointer; }
.ps-toggle .knob { width: 32px; height: 18px; border-radius: 10px; background: ${T.line}; position: relative; transition: .18s; flex-shrink: 0; }
.ps-toggle .knob::after { content: ""; position: absolute; top: 2px; left: 2px; width: 14px; height: 14px; border-radius: 50%; background: ${T.muted}; transition: .18s; }
.ps-toggle.on .knob { background: ${T.violet}; }
.ps-toggle.on .knob::after { left: 16px; background: #fff; }
.ps-toggle em { font-style: normal; font-size: 12px; color: ${T.text}; }
.ps-toggle.sm { padding: 6px 10px; }
.ps-toggle.sm .knob { width: 26px; height: 15px; }
.ps-toggle.sm .knob::after { width: 11px; height: 11px; }
.ps-toggle.sm.on .knob::after { left: 13px; }
.ps-proxy-toggle { display: flex; align-items: center; justify-content: space-between; padding: 13px 15px; background: ${T.bg}; border: 1px solid ${T.line}; border-radius: 11px; margin-bottom: 16px; }
.ps-cookie-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 9px; }
.ps-probe { margin-top: 12px; border: 1px solid ${T.lineSoft}; border-radius: 10px; background: ${T.bg}; overflow: hidden; }
.ps-probe-head { display: flex; align-items: baseline; gap: 10px; padding: 12px 14px; border-bottom: 1px solid ${T.lineSoft}; font-size: 12px; color: ${T.muted}; }
.ps-probe-score { font-family: ${FONT.display}; font-size: 20px; font-weight: 700; }
.ps-check { display: flex; align-items: flex-start; gap: 8px; padding: 7px 14px; font-size: 11.5px; color: ${T.red}; line-height: 1.5; }
.ps-check.ok { color: ${T.muted}; }
.ps-check svg { flex-shrink: 0; margin-top: 2px; }
.ps-check.ok svg { color: ${T.mint}; }
.ps-check em { font-style: normal; color: ${T.dim}; }
.ps-spin { animation: ps-rot 1s linear infinite; }
@keyframes ps-rot { to { transform: rotate(360deg); } }
.ps-btn.active { border-color: ${T.violet}; color: ${T.lilac}; background: ${T.violet}1a; }
.ps-filter-wrap { position: relative; }
.ps-filter-scrim { position: fixed; inset: 0; z-index: 20; }
.ps-filter-pop { position: absolute; right: 0; top: calc(100% + 8px); z-index: 21; width: 300px;
  background: ${T.surface}; border: 1px solid ${T.line}; border-radius: 12px;
  box-shadow: 0 16px 40px rgba(0,0,0,.45); padding: 14px; animation: ps-pop .12s ease; }
.ps-filter-head { display: flex; align-items: center; justify-content: space-between;
  font-size: 12px; font-weight: 700; color: ${T.text}; margin-bottom: 10px; }
.ps-filter-clear { background: none; border: none; color: ${T.lilac}; font-size: 11px;
  cursor: pointer; font-family: inherit; }
.ps-filter-clear:hover { text-decoration: underline; }
.ps-filter-row { margin-bottom: 12px; }
.ps-filter-label { display: block; font-size: 10.5px; text-transform: uppercase;
  letter-spacing: .06em; color: ${T.muted}; margin-bottom: 6px; }
.ps-filter-opts { display: flex; flex-wrap: wrap; gap: 6px; }
.ps-chip { background: ${T.bg}; border: 1px solid ${T.line}; border-radius: 8px;
  padding: 5px 10px; font-size: 12px; color: ${T.muted}; cursor: pointer;
  font-family: inherit; transition: .12s; }
.ps-chip:hover { border-color: #33334f; color: ${T.text}; }
.ps-chip.on { background: ${T.violet}; border-color: ${T.violet}; color: #fff; }
.ps-chiprow { display: flex; flex-wrap: wrap; gap: 7px; }
.ps-chip-btn { display: inline-flex; align-items: center; gap: 5px; background: ${T.bg};
  border: 1px solid ${T.line}; border-radius: 8px; padding: 6px 11px; font-size: 12px;
  color: ${T.muted}; cursor: pointer; font-family: inherit; transition: .12s; }
.ps-chip-btn:hover { border-color: #33334f; color: ${T.text}; }
.ps-chip-btn.on { background: ${T.violetDim}; border-color: ${T.violet}; color: ${T.lilac}; }
.ps-pager { display: flex; align-items: center; justify-content: center; gap: 8px;
  padding: 16px 0 4px; flex-wrap: wrap; }
.ps-pager-info { font-size: 12px; color: ${T.muted}; margin: 0 6px; }
.ps-pager-info b { color: ${T.text}; font-weight: 600; }
@keyframes ps-pop { from { opacity: 0; transform: translateY(-4px); } to { opacity: 1; transform: none; } }
.ps-cookie-actions .ps-btn.disabled { opacity: .5; cursor: progress; }
.ps-hint code { font-family: ${FONT.mono}; font-size: 11px; color: ${T.text}; }
.ps-hint { display: flex; align-items: flex-start; gap: 8px; font-size: 11.5px; color: ${T.muted}; margin-top: 12px; line-height: 1.55; background: ${T.bg}; border: 1px solid ${T.lineSoft}; padding: 11px 13px; border-radius: 10px; }
.ps-hint svg { flex-shrink: 0; margin-top: 1px; color: ${T.violet}; }
.ps-drawer-foot { display: flex; justify-content: flex-end; gap: 10px; padding: 17px 22px; border-top: 1px solid ${T.line}; }

@media (max-width: 860px) {
  .ps-side { position: fixed; z-index: 40; transform: translateX(-100%); }
  .ps-search { max-width: 40vw; }
  .ps-row { flex-direction: column; gap: 0; }
  .ps-eng-title { font-size: 24px; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: .001ms !important; animation-iteration-count: 1 !important; transition-duration: .001ms !important; }
}
`;
