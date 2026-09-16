import { useCallback, useEffect, useRef, useState } from "react";
import { api, onDataChanged } from "./api";

export function useApi(path, { interval, paused = false } = {}) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const alive = useRef(true);
  const load = useCallback(async () => {
    if (!path) return;
    try {
      const d = await api(path);
      if (alive.current) { setData(d); setError(null); }
    } catch (e) {
      if (alive.current) setError(e);
    } finally {
      if (alive.current) setLoading(false);
    }
  }, [path]);
  useEffect(() => { alive.current = true; setLoading(true); load(); return () => { alive.current = false; }; }, [load]);
  useEffect(() => onDataChanged(load), [load]);
  useEffect(() => {
    if (!interval || paused) return;
    const id = setInterval(load, interval);
    return () => clearInterval(id);
  }, [interval, paused, load]);
  return { data, error, loading, reload: load, setData };
}

export function useDebounced(value, delay = 250) {
  const [v, setV] = useState(value);
  useEffect(() => { const t = setTimeout(() => setV(value), delay); return () => clearTimeout(t); }, [value, delay]);
  return v;
}

/* Recharts can't read CSS variables inside SVG attributes, so resolve them per theme */
const KEYS = ["text", "muted", "faint", "line", "line-soft", "surface", "surface-2", "raised", "accent", "mint", "coral", "sky", "violet"];
function readTokens() {
  const s = getComputedStyle(document.documentElement);
  return Object.fromEntries(KEYS.map((k) => [k.replace("-", ""), s.getPropertyValue(`--${k}`).trim()]));
}
export function useTokens() {
  const [t, setT] = useState(readTokens);
  useEffect(() => {
    const obs = new MutationObserver(() => setT(readTokens()));
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => obs.disconnect();
  }, []);
  return t;
}
