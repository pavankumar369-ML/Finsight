const TOKEN_KEY = "fs-token";
export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const setToken = (t) => (t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY));

export class ApiError extends Error {
  constructor(message, status) { super(message); this.status = status; }
}

const listeners = new Set();
export const onUnauthorized = (fn) => (listeners.add(fn), () => listeners.delete(fn));

export async function api(path, { method = "GET", body, form } = {}) {
  const headers = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  let res;
  try {
    res = await fetch(`/api${path}`, { method, headers, body: form ?? (body !== undefined ? JSON.stringify(body) : undefined) });
  } catch {
    throw new ApiError("Can't reach the FinSight server. Check that the backend is running on port 8000.", 0);
  }
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    if (res.status === 401 && token) listeners.forEach((fn) => fn());
    let msg = data?.detail;
    if (Array.isArray(msg)) msg = msg.map((d) => `${d.loc?.slice(-1)[0]}: ${d.msg}`).join(", ");
    throw new ApiError(msg || `Request failed (${res.status}).`, res.status);
  }
  return data;
}

/* tiny pub/sub so any page can refetch after a mutation elsewhere */
const dataSubs = new Set();
export const onDataChanged = (fn) => (dataSubs.add(fn), () => dataSubs.delete(fn));
export const dataChanged = () => dataSubs.forEach((fn) => fn());
