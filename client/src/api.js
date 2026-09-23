// HW4 Part 1: thin fetch wrapper for the FastAPI backend (code/db_routes.py).
//
// credentials: "include" is required on every call so the browser sends/stores
// the HttpOnly session cookie set at /api/hw4/auth/login, even though the API
// runs on a different port (8619) than the Vite dev server (5173).
const API_BASE = "http://localhost:8619";

async function apiFetch(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });

  let data = null;
  const text = await res.text();
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }

  if (!res.ok) {
    const message = (data && data.detail) || `Request failed with status ${res.status}`;
    const error = new Error(message);
    error.status = res.status;
    throw error;
  }
  return data;
}

export const api = {
  register: (name, email, password) =>
    apiFetch("/api/hw4/auth/register", {
      method: "POST",
      body: JSON.stringify({ name, email, password }),
    }),

  login: (email, password) =>
    apiFetch("/api/hw4/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  logout: () => apiFetch("/api/hw4/auth/logout", { method: "POST" }),

  me: () => apiFetch("/api/hw4/auth/me"),

  // Uses the eager-loaded /records-fixed endpoint (single JOIN query),
  // not the naive /records endpoint -- that one is intentionally N+1 for
  // the HW4 Part 3 benchmark and would lazy-load related data for every
  // row. Also caps the page size: the seed data has 5000 rows and this is
  // a UI list view, not a bulk export.
  listRecords: (limit = 50) => apiFetch(`/api/hw4/records-fixed?limit=${limit}`),

  createRecord: (productName, brandName) =>
    apiFetch("/api/hw4/records", {
      method: "POST",
      body: JSON.stringify({ product_name: productName, brand_name: brandName }),
    }),

  updateRecord: (id, productName, brandName) =>
    apiFetch(`/api/hw4/records/${id}`, {
      method: "PUT",
      body: JSON.stringify({ product_name: productName, brand_name: brandName }),
    }),

  deleteRecord: (id) => apiFetch(`/api/hw4/records/${id}`, { method: "DELETE" }),
};
