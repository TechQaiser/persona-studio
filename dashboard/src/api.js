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

const BASE = import.meta.env.VITE_API_URL || "http://localhost:8787";

async function req(method, path, body) {
  const res = await fetch(BASE + path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`${method} ${path} → ${res.status}`);
  return res.status === 204 ? null : res.json();
}

export const api = {
  async health() {
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
  list: () => req("GET", "/api/profiles"),
  create: (p) => req("POST", "/api/profiles", p),
  update: (p) => req("PUT", `/api/profiles/${p.id}`, p),
  remove: (id) => req("DELETE", `/api/profiles/${id}`),
  launch: (id) => req("POST", `/api/profiles/${id}/launch`),
  stop: (id) => req("POST", `/api/profiles/${id}/stop`),
};
