/* ------------------------------------------------------------------ *
 *  Tiny client for the Persona engine API (engine/persona/server.py).
 *
 *  The dashboard works in two modes:
 *   - LIVE  : the engine API is reachable, so launching actually opens a
 *             real Chromium window and profiles persist to disk.
 *   - DEMO  : the API is offline, so the UI runs on in-memory sample data
 *             (great for exploring the project without a backend).
 *
 *  Override the API location with a VITE_API_URL env var if needed.
 * ------------------------------------------------------------------ */

// The dev server (5173) and `vite preview` (4173) talk to the engine on 8787;
// a build served by the engine itself (the packaged app, `persona serve
// --dashboard`) talks to its own origin.
const BASE = import.meta.env.VITE_API_URL ||
  (["5173", "4173"].includes(window.location.port) || window.location.protocol === "file:"
    ? "http://localhost:8787" : window.location.origin);

// The engine issues a fresh API token each time it starts and only hands it to
// the dashboard's own origin. Fetch it lazily; refetch once if the engine
// restarted (401) since we last asked.
let tokenPromise = null;
function getToken(refresh = false) {
  if (refresh || !tokenPromise) {
    tokenPromise = fetch(BASE + "/api/token")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`token → ${r.status}`))))
      .then((d) => d.token)
      .catch((e) => { tokenPromise = null; throw e; });
  }
  return tokenPromise;
}

async function send(method, path, body, token) {
  const headers = { "X-Persona-Token": token };
  if (body) headers["Content-Type"] = "application/json";
  return fetch(BASE + path, { method, headers, body: body ? JSON.stringify(body) : undefined });
}

async function req(method, path, body) {
  let res = await send(method, path, body, await getToken());
  if (res.status === 401) res = await send(method, path, body, await getToken(true));
  if (!res.ok) throw new Error(`${method} ${path} → ${res.status}`);
  return res.status === 204 ? null : res.json();
}

export const api = {
  async ping() {
    try {
      const res = await fetch(BASE + "/api/health");
      return res.ok;
    } catch {
      return false;
    }
  },
  engines: () => req("GET", "/api/engines"),
  getConfig: () => req("GET", "/api/config"),
  setDefaultEngine: (name) => req("PUT", "/api/config", { default_engine: name }),
  setConfig: (patch) => req("PUT", "/api/config", patch),
  // Folders: a persisted list the sidebar and editor share. Rename/delete also
  // reassign the profiles that live in the folder.
  createFolder: (name) => req("POST", "/api/folders", { name }),
  renameFolder: (from, to) => req("POST", "/api/folders/rename", { from, to }),
  deleteFolder: (name, reassignTo) => req("POST", "/api/folders/delete", { name, reassignTo }),
  list: () => req("GET", "/api/profiles"),
  create: (p) => req("POST", "/api/profiles", p),
  update: (p) => req("PUT", `/api/profiles/${p.id}`, p),
  remove: (id) => req("DELETE", `/api/profiles/${id}`),
  launch: (id) => req("POST", `/api/profiles/${id}/launch`),
  stop: (id) => req("POST", `/api/profiles/${id}/stop`),
  // Cookies are read/written through the profile's real browser session, so
  // these calls open it headlessly and can take a couple of seconds.
  exportCookies: (id) => req("GET", `/api/profiles/${id}/cookies`),
  importCookies: (id, text, clear) => req("POST", `/api/profiles/${id}/cookies`, { text, clear }),
  // These open the profile headlessly too, so they're slow by nature.
  proxyTest: (id) => req("POST", `/api/profiles/${id}/proxy-test`),
  // Rotating/mobile proxies: request a new exit IP via the proxy's change-IP URL.
  changeIp: (id) => req("POST", `/api/profiles/${id}/proxy/change-ip`),
  // Quick check of a proxy straight from the editor form (no saved profile needed).
  checkProxy: (proxy) => req("POST", "/api/proxy/check", { proxy }),
  trust: (id) => req("POST", `/api/profiles/${id}/trust`),
  tls: (id) => req("POST", `/api/profiles/${id}/tls`),
  // DNS leak check: do name lookups escape the proxy to your real ISP?
  dns: (id) => req("POST", `/api/profiles/${id}/dns`),
  // Auto-adjust: align the profile to what its browser actually presents.
  align: (id) => req("POST", `/api/profiles/${id}/align`),
  // Automation: open the profile with a CDP endpoint your scripts can attach to.
  // (Detach with stop(id) — the attached browser closes when the session ends.)
  attach: (id, headless) => req("POST", `/api/profiles/${id}/attach`, { headless }),
  warmup: (id, minutes, preset) => req("POST", `/api/profiles/${id}/warmup`, { minutes, preset }),
  bulkUpdate: (ids, patch) => req("POST", "/api/profiles/bulk", { ids, patch }),
  // Bulk create at scale: save a chunk of generated profiles in one request.
  batchCreate: (profiles) => req("POST", "/api/profiles/batch", { profiles }),
  // Import profiles exported from GoLogin / AdsPower / Multilogin.
  importProfiles: (text) => req("POST", "/api/profiles/import", { text }),
  // Proxy pool: import, list, test and assign proxies across profiles.
  listProxies: () => req("GET", "/api/proxies"),
  addProxies: (text) => req("POST", "/api/proxies", { text }),
  deleteProxy: (id) => req("DELETE", `/api/proxies/${id}`),
  testProxy: (id) => req("POST", `/api/proxies/${id}/test`),
  assignProxies: (profileIds, proxyIds) => req("POST", "/api/proxies/assign", { profileIds, proxyIds }),
  // Scheduled warm-up: recurring, unattended aging of a profile's session.
  listSchedules: () => req("GET", "/api/schedules"),
  addSchedule: (s) => req("POST", "/api/schedules", s),
  updateSchedule: (id, patch) => req("PUT", `/api/schedules/${id}`, patch),
  deleteSchedule: (id) => req("DELETE", `/api/schedules/${id}`),
  // Session health: expired/expiring cookies and which logins are still live.
  // Opens the profile headlessly, so it's slow like the cookie/trust calls.
  sessionCheck: (id) => req("POST", `/api/profiles/${id}/session`),
  // Duplicate a profile as a template: same settings, a fresh coherent fingerprint.
  duplicate: (id) => req("POST", `/api/profiles/${id}/duplicate`),
  // Per-profile activity log (launches, warm-ups, trust runs, …), newest first.
  activity: (id) => req("GET", `/api/profiles/${id}/activity`),
  // Session history: snapshots saved when a session ends; restore rolls back.
  history: (id) => req("GET", `/api/profiles/${id}/history`),
  saveSnapshot: (id) => req("POST", `/api/profiles/${id}/history`),
  restoreSnapshot: (id, sid) => req("POST", `/api/profiles/${id}/history/${encodeURIComponent(sid)}/restore`),
  // Health overview: coherence, proxy, cached trust grade and schedule per profile.
  health: () => req("GET", "/api/profiles/health"),
  // Fingerprint collisions: which profiles look like the same device.
  collisions: () => req("GET", "/api/profiles/collisions"),
};
