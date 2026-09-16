import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, getToken, onUnauthorized, setToken } from "../lib/api";

const AuthCtx = createContext(null);
export const useAuth = () => useContext(AuthCtx);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(false);
  const logout = useCallback(() => { setToken(null); setUser(null); }, []);
  useEffect(() => onUnauthorized(logout), [logout]);
  useEffect(() => {
    if (!getToken()) { setReady(true); return; }
    api("/auth/me").then(setUser).catch(() => setToken(null)).finally(() => setReady(true));
  }, []);
  const accept = ({ token, user }) => { setToken(token); setUser(user); };
  const value = {
    user, ready, logout,
    login: async (email, password) => accept(await api("/auth/login", { method: "POST", body: { email, password } })),
    register: async (name, email, password) => accept(await api("/auth/register", { method: "POST", body: { name, email, password } })),
    demo: async () => accept(await api("/auth/demo", { method: "POST" })),
  };
  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>;
}
