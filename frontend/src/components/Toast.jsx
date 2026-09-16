import { createContext, useCallback, useContext, useState } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "motion/react";
import { CheckCircle2, AlertTriangle, Info } from "lucide-react";

const ToastCtx = createContext(() => {});
export const useToast = () => useContext(ToastCtx);

export function ToastProvider({ children }) {
  const [items, setItems] = useState([]);
  const push = useCallback((message, { tone = "good", action, duration = 3800 } = {}) => {
    const id = Math.random().toString(36).slice(2);
    setItems((s) => [...s.slice(-3), { id, message, tone, action }]);
    setTimeout(() => setItems((s) => s.filter((t) => t.id !== id)), duration);
  }, []);
  const icons = { good: CheckCircle2, bad: AlertTriangle, info: Info };
  const colors = { good: "text-mint", bad: "text-coral", info: "text-sky" };
  return (
    <ToastCtx.Provider value={push}>
      {children}
      {createPortal(<div aria-live="polite" className="pointer-events-none fixed bottom-20 left-1/2 z-[70] flex w-[min(92vw,420px)] -translate-x-1/2 flex-col gap-2 lg:bottom-6">
        <AnimatePresence initial={false}>
          {items.map((t) => {
            const Icon = icons[t.tone] ?? Info;
            return (
              <motion.div key={t.id} layout initial={{ opacity: 0, y: 16, scale: 0.96 }} animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: 8, scale: 0.96 }} transition={{ type: "spring", stiffness: 500, damping: 36 }}
                className="pointer-events-auto flex items-center gap-3 rounded-2xl border border-line bg-raised px-4 py-3 text-sm shadow-2xl">
                <Icon size={18} className={colors[t.tone]} />
                <span className="flex-1 text-text">{t.message}</span>
                {t.action && (
                  <button className="font-semibold text-accent hover:underline" onClick={() => { t.action.onClick(); setItems((s) => s.filter((x) => x.id !== t.id)); }}>
                    {t.action.label}
                  </button>
                )}
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>, document.body)}
    </ToastCtx.Provider>
  );
}
