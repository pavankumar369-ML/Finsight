const inr = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
export const money = (v, { sign = false } = {}) => {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const s = `₹${inr.format(Math.abs(Math.round(v)))}`;
  if (sign) return v < 0 ? `−${s}` : `+${s}`;
  return v < 0 ? `−${s}` : s;
};
export const compact = (v) => {
  const a = Math.abs(v);
  if (a >= 1e7) return `₹${(v / 1e7).toFixed(1)}Cr`;
  if (a >= 1e5) return `₹${(v / 1e5).toFixed(1)}L`;
  if (a >= 1e3) return `₹${(v / 1e3).toFixed(a >= 1e4 ? 0 : 1)}k`;
  return `₹${Math.round(v)}`;
};
export const pct = (v, d = 0) => (v === null || v === undefined ? "—" : `${Number(v).toFixed(d)}%`);
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const MONTHS_LONG = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
export const monthLabel = (mk, long = false) => {
  if (!mk) return "";
  const [y, m] = mk.split("-").map(Number);
  return long ? `${MONTHS_LONG[m - 1]} ${y}` : MONTHS[m - 1];
};
export const monthName = (mk) => (mk ? MONTHS_LONG[Number(mk.split("-")[1]) - 1] : "");
export const dateLabel = (iso) => {
  const d = new Date(iso + "T00:00:00");
  return `${d.getDate()} ${MONTHS[d.getMonth()]}`;
};
export const todayISO = () => {
  const d = new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
};
export const ms = (v) => (v === null || v === undefined ? "—" : v < 1 ? `${v.toFixed(2)} ms` : v < 1000 ? `${v.toFixed(v < 10 ? 1 : 0)} ms` : `${(v / 1000).toFixed(2)} s`);
export const duration = (s) => {
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
  return h ? `${h}h ${m}m` : m ? `${m}m ${s % 60}s` : `${s}s`;
};
