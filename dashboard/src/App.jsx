import React, { useState, useMemo, useEffect } from "react";
import { api } from "./api";
import {
  Layers, Globe, FolderTree, Copy, Trash2, Play, Square, Pencil,
  Search, Plus, Filter, ShieldCheck, ShieldAlert, X, Zap, Users,
  Cpu, MonitorSmartphone, Fingerprint, Wifi, WifiOff, Check, Clipboard,
  Settings, Boxes, Activity, MapPin, Clock, Camera, Mic, Blocks,
  RefreshCw, Server, Sparkles, ArrowRight, Star, Circle,
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
function coherence(p) {
  const issues = [];
  if (p.webglRenderer && !GPUS[p.os].includes(p.webglRenderer))
    issues.push("GPU doesn't belong to " + p.os);
  if (p.screen && !SCREENS[p.os].includes(p.screen))
    issues.push("Screen resolution unusual for " + p.os);
  if (p.locale && p.timezone && LOCALES[p.locale] !== p.timezone)
    issues.push("Timezone doesn't match locale");
  if (p.cores && !CORES[p.os].includes(Number(p.cores)))
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
    notes: "", startupUrls: "",
    lastActive: status === "running" ? "now" : ["2h ago", "yesterday", "3d ago"][name.length % 3],
  };
}
function uaFor(os) {
  const tok = { Windows: "Windows NT 10.0; Win64; x64", macOS: "Macintosh; Intel Mac OS X 10_15_7", Linux: "X11; Linux x86_64", Android: "Linux; Android 13; Pixel 7" }[os];
  const mob = os === "Android" ? " Mobile" : "";
  return `Mozilla/5.0 (${tok}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0${mob} Safari/537.36`;
}

/* ================================================================== */
export default function App() {
  const [profiles, setProfiles] = useState(seed);
  const [view, setView] = useState("profiles");
  const [folder, setFolder] = useState("All profiles");
  const [query, setQuery] = useState("");
  const [sel, setSel] = useState(new Set());
  const [editor, setEditor] = useState(null);
  const [bulk, setBulk] = useState(false);
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
    const id = setInterval(() => {
      if (!cancelled && !editor && !bulk) refresh().catch(() => {});
    }, 3000);
    return () => { cancelled = true; clearInterval(id); };
  }, [live, editor, bulk]);

  const filtered = useMemo(() =>
    profiles.filter(p =>
      (folder === "All profiles" || p.folder === folder) &&
      (p.name.toLowerCase().includes(query.toLowerCase()) ||
       p.tags.some(t => t.includes(query.toLowerCase())))),
    [profiles, folder, query]);

  const running = profiles.filter(p => p.status === "running").length;
  const proxyCount = new Set(profiles.filter(p => p.proxy).map(p => p.proxy.host)).size;

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
              value={profiles.filter(p => coherence(p).length === 0).length + "/" + profiles.length} accent={T.violet} />
            <div style={{ flex: 1 }} />
            <button className="ps-btn ghost" onClick={() => setBulk(true)}><Boxes size={14} /> Bulk create</button>
            <button className="ps-btn primary" onClick={() => setEditor(newProfile(folder, defaultEngine))}><Plus size={15} /> New profile</button>
          </div>

          {view === "profiles" && (
            <ProfilesView {...{ filtered, query, setQuery, folder, sel, setSel, toggleSel, allSel, toggleRun, clone, remove, setEditor, setProfiles, live, refresh }} />
          )}
          {view === "engines" && <EnginesView engines={engines} live={live} />}
          {view === "proxies" && <ProxiesView profiles={profiles} />}
          {!["profiles", "engines", "proxies"].includes(view) && <Placeholder view={view} />}
        </main>
      </div>

      {editor && <Editor profile={editor} onClose={() => setEditor(null)} onSave={(p) => { save(p); setEditor(null); }} />}
      {bulk && <BulkModal onClose={() => setBulk(false)} folder={folder} onCreate={async (list) => {
        if (live) { for (const p of list) { try { await api.create({ ...p, id: undefined, _new: true }); } catch {} } await refresh(); }
        else { setProfiles(ps => [...ps, ...list]); }
        setBulk(false);
      }} />}
    </div>
  );
}

/* ---- Profiles view ----------------------------------------------- */
function ProfilesView({ filtered, query, setQuery, folder, sel, setSel, toggleSel, allSel, toggleRun, clone, remove, setEditor, setProfiles, live, refresh }) {
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
            <button className="danger" onClick={async () => { const ids = [...sel]; setSel(new Set()); if (live) { for (const id of ids) { try { await api.remove(id); } catch {} } await refresh(); } else { setProfiles(ps => ps.filter(p => !ids.includes(p.id))); } }}><Trash2 size={13} /> Delete</button>
          </div>
        )}
        <button className="ps-btn ghost sm"><Filter size={13} /> Filter</button>
      </div>

      <div className="ps-scroll">
        {filtered.length === 0 ? (
          <div className="ps-empty">
            <Layers size={28} color={T.dim} />
            <div>No profiles here yet.</div>
            <button className="ps-btn primary sm" onClick={() => setEditor(newProfile(folder))}><Plus size={14} /> Create one</button>
          </div>
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
              {filtered.map((p, i) => {
                const iss = coherence(p);
                return (
                  <tr key={p.id} className={"ps-rise" + (sel.has(p.id) ? " sel" : "")} style={{ animationDelay: `${Math.min(i, 12) * 28}ms` }}>
                    <td><input type="checkbox" checked={sel.has(p.id)} onChange={() => toggleSel(p.id)} /></td>
                    <td>
                      <div className="ps-name">
                        <span className={"ps-status " + p.status} />
                        <div>
                          <div className="ps-pname">{p.name}</div>
                          <div className="ps-tags">{p.tags.map(t => <span key={t} className="ps-tag">{t}</span>)}</div>
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
    mediaVideo: 1, mediaAudio: 1, dnt: false, proxy: null, notes: "", startupUrls: "",
    lastActive: "never", _new: true,
  };
}

/* ---- Fingerprint editor ------------------------------------------ */
function Editor({ profile, onClose, onSave }) {
  const [p, setP] = useState(profile);
  const [tab, setTab] = useState("general");
  const set = (patch) => setP(x => ({ ...x, ...patch }));
  const changeOS = (os) => set({ os, userAgent: uaFor(os), screen: SCREENS[os][0], cores: CORES[os][1], memory: RAM[os][1], webglRenderer: GPUS[os][0] });
  const changeLocale = (locale) => set({ locale, timezone: LOCALES[locale] });
  const setProxy = (patch) => set({ proxy: { ...(p.proxy || { type: "HTTP", host: "", port: "", user: "", pass: "", country: "" }), ...patch } });

  const iss = coherence(p);
  const score = Math.max(0, 100 - iss.length * 22);

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
                  <button className="ps-btn ghost sm" style={{ marginTop: 4 }}><RefreshCw size={13} /> Test connection</button>
                  <div className="ps-hint"><MapPin size={12} /> Timezone & locale can auto-align to the proxy country to avoid geo-mismatch leaks.</div>
                </>
              ) : <div className="ps-hint">No proxy — this profile connects directly. Turn it on to route through a residential or datacenter proxy.</div>}
            </>
          )}

          {tab === "advanced" && (
            <>
              <Field label="Startup URLs (one per line)"><textarea className="ps-in mono" rows={3} value={p.startupUrls} onChange={e => set({ startupUrls: e.target.value })} placeholder={"https://facebook.com\nhttps://business.facebook.com"} /></Field>
              <Field label="WebGL vendor"><input className="ps-in mono" value={p.webglVendor} onChange={e => set({ webglVendor: e.target.value })} /></Field>
              <div className="ps-hint"><Fingerprint size={12} /> Seed & canvas noise are managed by the engine and stay stable across launches for this profile.</div>
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

/* ---- Bulk create ------------------------------------------------- */
function BulkModal({ onClose, onCreate, folder }) {
  const [n, setN] = useState(10);
  const [os, setOs] = useState("Windows");
  const [prefix, setPrefix] = useState("Batch");
  const [country, setCountry] = useState("US");
  const create = () => {
    const list = Array.from({ length: n }, (_, i) =>
      mk(`${prefix}-${String(i + 1).padStart(2, "0")}`, folder === "All profiles" ? "Facebook Ads" : folder, "stopped", os, ["bulk"], country));
    onCreate(list);
  };
  return (
    <div className="ps-overlay center" onClick={onClose}>
      <div className="ps-modal ps-pop" onClick={e => e.stopPropagation()}>
        <div className="ps-drawer-h">
          <div><div className="ps-eyebrow">Bulk create</div><div className="ps-drawer-title">Generate many profiles at once</div></div>
          <button className="ps-x" onClick={onClose}><X size={18} /></button>
        </div>
        <div style={{ padding: 20 }}>
          <Row>
            <Field label="How many"><input type="number" className="ps-in" value={n} min={1} max={200} onChange={e => setN(Math.min(200, Math.max(1, Number(e.target.value))))} /></Field>
            <Field label="Operating system"><select className="ps-in" value={os} onChange={e => setOs(e.target.value)}>{OS_LIST.map(o => <option key={o}>{o}</option>)}</select></Field>
          </Row>
          <Row>
            <Field label="Name prefix"><input className="ps-in" value={prefix} onChange={e => setPrefix(e.target.value)} /></Field>
            <Field label="Proxy country"><select className="ps-in" value={country} onChange={e => setCountry(e.target.value)}>{Object.keys(COUNTRY_LOCALE).map(c => <option key={c}>{c}</option>)}</select></Field>
          </Row>
          <div className="ps-hint"><Boxes size={12} /> Each profile gets its own coherent fingerprint & session. Preview: <b style={{ color: T.text }}>{prefix}-01 … {prefix}-{String(n).padStart(2, "0")}</b></div>
        </div>
        <div className="ps-drawer-foot">
          <button className="ps-btn ghost" onClick={onClose}>Cancel</button>
          <button className="ps-btn primary" onClick={create}><Plus size={15} /> Create {n} profiles</button>
        </div>
      </div>
    </div>
  );
}

/* ---- Proxies view ------------------------------------------------ */
function ProxiesView({ profiles }) {
  const proxies = useMemo(() => {
    const map = {};
    profiles.filter(p => p.proxy).forEach(p => { const k = p.proxy.host; if (!map[k]) map[k] = { ...p.proxy, used: 0 }; map[k].used++; });
    return Object.values(map);
  }, [profiles]);
  return (
    <div className="ps-scroll">
      <div className="ps-toolbar" style={{ paddingLeft: 0, paddingRight: 0 }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: T.muted }}>Proxy pool</div>
        <div style={{ flex: 1 }} /><button className="ps-btn ghost sm"><Plus size={13} /> Add proxy</button>
      </div>
      {proxies.length === 0
        ? <div className="ps-empty"><Globe size={26} color={T.dim} /><div>No proxies yet — profiles connect directly.</div></div>
        : (
          <table className="ps-table">
            <thead><tr><th>Host</th><th>Type</th><th>Country</th><th>Used by</th><th>Status</th></tr></thead>
            <tbody>
              {proxies.map((x, i) => (
                <tr key={i} className="ps-rise" style={{ animationDelay: `${i * 28}ms` }}>
                  <td className="ps-mono">{x.host}:{x.port}</td>
                  <td><span className="ps-os">{x.type}</span></td>
                  <td className="ps-mono">{x.country}</td>
                  <td className="ps-mono dim">{x.used} profile{x.used > 1 ? "s" : ""}</td>
                  <td><span className="ps-pill ok"><Check size={12} /> Live</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
    </div>
  );
}

function Placeholder({ view }) {
  const map = {
    folders: [FolderTree, "Folder manager", "Organize profiles into folders and drag between them."],
    automation: [Zap, "Automation", "Drive profiles with Playwright/Puppeteer scripts and a REST API."],
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
.ps-proxy-toggle { display: flex; align-items: center; justify-content: space-between; padding: 13px 15px; background: ${T.bg}; border: 1px solid ${T.line}; border-radius: 11px; margin-bottom: 16px; }
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
