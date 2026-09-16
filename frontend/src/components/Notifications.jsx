import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AnimatePresence, motion } from "motion/react";
import { AlertOctagon, AlertTriangle, Bell, CalendarClock, PartyPopper } from "lucide-react";
import clsx from "clsx";
import { useApi } from "../lib/hooks";

const KEY = "fs-seen-notes";
const readSeen = () => { try { return new Set(JSON.parse(localStorage.getItem(KEY) || "[]")); } catch { return new Set(); } };
const ICON = { bad: AlertOctagon, warn: AlertTriangle, info: CalendarClock, good: PartyPopper };
const TONE = { bad: "bg-coral-soft text-coral", warn: "bg-accent-soft text-accent", info: "bg-surface-2 text-sky", good: "bg-mint-soft text-mint" };

export default function Notifications({ align = "right" }) {
  const { data } = useApi("/notifications", { interval: 60000 });
  const [open, setOpen] = useState(false);
  const [seen, setSeen] = useState(readSeen);
  const ref = useRef(null);
  const navigate = useNavigate();
  const items = data?.items ?? [];
  const unread = items.filter((n) => !seen.has(n.id)).length;

  useEffect(() => {
    if (!open) return;
    const close = (e) => { if (!ref.current?.contains(e.target)) setOpen(false); };
    const esc = (e) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", close); document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", esc); };
  }, [open]);

  const markAll = () => {
    const next = new Set([...seen, ...items.map((n) => n.id)]);
    setSeen(next);
    localStorage.setItem(KEY, JSON.stringify([...next].slice(-300)));
  };

  return (
    <div ref={ref} className="relative">
      <motion.button whileTap={{ scale: 0.9 }} onClick={() => setOpen((o) => !o)} aria-label={`Notifications${unread ? `, ${unread} unread` : ""}`}
        className="relative grid h-9 w-9 place-items-center rounded-xl text-muted transition-colors hover:bg-surface-2 hover:text-text">
        <motion.span animate={unread ? { rotate: [0, -14, 12, -8, 0] } : {}} transition={{ duration: 0.6, delay: 0.4 }}><Bell size={17} /></motion.span>
        <AnimatePresence>
          {unread > 0 && (
            <motion.span initial={{ scale: 0 }} animate={{ scale: 1 }} exit={{ scale: 0 }}
              className="num absolute -right-0.5 -top-0.5 grid h-[18px] min-w-[18px] place-items-center rounded-full bg-coral px-1 text-[10px] font-bold text-white">
              {unread > 9 ? "9+" : unread}
            </motion.span>
          )}
        </AnimatePresence>
      </motion.button>
      <AnimatePresence>
        {open && (
          <motion.div initial={{ opacity: 0, y: -6, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: -6, scale: 0.97 }}
            transition={{ duration: 0.16 }}
            className={clsx("absolute top-full z-50 mt-2 w-[min(92vw,380px)] overflow-hidden rounded-2xl border border-line bg-surface shadow-2xl",
              align === "right" ? "right-0 origin-top-right" : "left-0 origin-top-left")}>
            <div className="flex items-center justify-between border-b border-line-soft px-4 py-3">
              <p className="display font-semibold">Notifications</p>
              {unread > 0 && <button onClick={markAll} className="text-[12px] font-semibold text-accent hover:underline">Mark all as read</button>}
            </div>
            {items.length === 0 ? (
              <p className="px-4 py-8 text-center text-sm text-muted">You're all caught up.</p>
            ) : (
              <ul className="max-h-[420px] overflow-auto p-1.5">
                {items.map((n) => {
                  const Icon = ICON[n.tone] ?? Bell;
                  const isNew = !seen.has(n.id);
                  return (
                    <li key={n.id}>
                      <button onClick={() => { const s = new Set(seen).add(n.id); setSeen(s); localStorage.setItem(KEY, JSON.stringify([...s])); setOpen(false); navigate(n.link); }}
                        className="flex w-full gap-3 rounded-xl px-2.5 py-2.5 text-left hover:bg-surface-2">
                        <span className={clsx("grid h-8 w-8 shrink-0 place-items-center rounded-lg", TONE[n.tone])}><Icon size={15} /></span>
                        <span className="min-w-0 flex-1">
                          <span className={clsx("block text-[13px] leading-snug", isNew ? "font-semibold text-text" : "text-muted")}>{n.title}</span>
                          <span className="block text-[12px] text-faint">{n.body}</span>
                        </span>
                        {isNew && <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-accent" />}
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
