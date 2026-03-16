export const BASE = import.meta.env.VITE_API_URL ?? "/kms/api";

export function friendlyError(e: any): string {
  const msg: string = e?.message ?? String(e ?? "");
  if (msg.includes("401")) {
    return "Your session has expired — please log in again. If the problem persists, contact IT support.";
  }
  if (msg.includes("403")) {
    return "You don't have permission for this action. Contact an admin to adjust your role. If the problem persists, contact IT support.";
  }
  if (msg.includes("404")) {
    return "Item not found — it may have been deleted or moved. If unexpected, contact IT support.";
  }
  if (msg.includes("503")) {
    return "The AI service is currently unavailable. Check that Ollama is running and try again.";
  }
  if (msg.includes("500")) {
    return "The server encountered an error. Try again in a moment. If the problem persists, contact IT support.";
  }
  if (/failed to fetch|networkerror|network error/i.test(msg)) {
    return "Could not reach the server. Check your network connection and try again. If the problem persists, contact IT support.";
  }
  if (msg) {
    return `${msg} — if the problem persists, contact IT support.`;
  }
  return "An unexpected error occurred. Try again. If the problem persists, contact IT support.";
}

async function request(path: string, options: RequestInit = {}) {
  const token = localStorage.getItem("token");
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });
  if (!res.ok) {
    if (res.status === 401) {
      localStorage.removeItem("token");
      localStorage.removeItem("role");
      localStorage.removeItem("email");
      window.location.replace("/kms/login");
    }
    let detail = `${res.status} ${res.statusText}`;
    try {
      const err = await res.json();
      if (err.detail) detail = `${res.status}: ${err.detail}`;
    } catch {}
    throw new Error(detail);
  }
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  login: async (email: string, password: string) => {
    const r = await fetch(`${BASE}/auth/jwt/login`, {
      method: "POST",
      body: new URLSearchParams({ username: email, password }),
    });
    const data = await r.json();
    if (data.access_token) {
      localStorage.setItem("token", data.access_token);
      // Fetch role and store it
      const me = await fetch(`${BASE}/users/me`, {
        headers: { Authorization: `Bearer ${data.access_token}` },
      }).then(r => r.json());
      localStorage.setItem("role", me.role ?? "reader");
      localStorage.setItem("email", me.email ?? "");
    }
    return data;
  },

  register: (email: string, password: string, role: string) =>
    fetch(`${BASE}/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password, role }),
    }).then(r => {
      if (!r.ok) return r.json().then(d => { throw d; });
      return r.json();
    }),

  getDoc: (path: string) => request(`/docs/${path}`),
  createDoc: (data: object) => request("/docs", { method: "POST", body: JSON.stringify(data) }),
  updateDoc: (path: string, data: object) => request(`/docs/${path}`, { method: "PUT", body: JSON.stringify(data) }),
  deleteDoc: (path: string) => request(`/docs/${path}`, { method: "DELETE" }),
  listDocs: () => request("/docs"),
  getFolders: () => request("/docs/folders"),
  ingest: (message: string) => request("/ingest", { method: "POST", body: JSON.stringify({ message }) }),
  search: (q: string, mode = "keyword") => request(`/search?q=${encodeURIComponent(q)}&mode=${mode}`),
  reviewQueue: () => request("/review/queue"),
  markReviewed: (id: number) => request(`/review/${id}/mark-reviewed`, { method: "POST" }),
  getMe: () => request("/users/me"),
  getSettings: () => request("/admin/settings"),
  updateSetting: (key: string, value: string) => request(`/admin/settings/${key}`, { method: "PATCH", body: JSON.stringify({ value }) }),
  listUsers: () => request("/admin/users"),
  changeRole: (id: string, role: string) => request(`/admin/users/${id}/role`, { method: "PATCH", body: JSON.stringify({ role }) }),
  resetPassword: (id: string, password: string) => request(`/admin/users/${id}/reset-password`, { method: "POST", body: JSON.stringify({ password }) }),
  deleteUser: (id: string) => request(`/admin/users/${id}`, { method: "DELETE" }),
  listVersions: (path: string) => request(`/versions/${path}`),
  restoreVersion: (path: string, versionId: number) => request(`/versions/${path}/restore/${versionId}`, { method: "POST" }),
  listComments: (path: string) => request(`/comments/${path}`),
  addComment: (path: string, body: string) => request(`/comments/${path}`, { method: "POST", body: JSON.stringify({ body }) }),
  deleteComment: (id: number) => request(`/comments/${id}`, { method: "DELETE" }),
};
