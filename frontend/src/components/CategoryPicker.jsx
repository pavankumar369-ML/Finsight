import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Check, ChevronDown } from "lucide-react";
import clsx from "clsx";
import { EXPENSE, INCOME, catMeta } from "../lib/categories";

export default function CategoryPicker({ value, type, onChange, corrected }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return;
    const close = (e) => { if (!ref.current?.contains(e.target)) setOpen(false); };
    const esc = (e) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", esc); };
  }, [open]);
  const { color } = catMeta(value);
  const list = type === "income" ? INCOME : EXPENSE;
  return (
    <div ref={ref} className="relative inline-block">
      <button type="button" onClick={() => setOpen((o) => !o)} aria-haspopup="listbox" aria-expanded={open}
        className="group inline-flex items-center gap-1.5 rounded-full border border-transparent py-1 pl-2 pr-1.5 text-[12px] font-semibold transition-colors hover:border-line"
        style={{ background: `${color}1A`, color }}>
        <span className="h-1.5 w-1.5 rounded-full" style={{ background: color }} />
        {value}
        {corrected && <Check size={12} aria-label="Corrected by you" />}
        <ChevronDown size={13} className="opacity-50 transition-opacity group-hover:opacity-100" />
      </button>
      <AnimatePresence>
        {open && (
          <motion.ul role="listbox" initial={{ opacity: 0, y: -4, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: -4, scale: 0.97 }}
            transition={{ duration: 0.14 }}
            className="absolute left-0 top-full z-40 mt-1.5 max-h-72 w-48 origin-top-left overflow-auto rounded-2xl border border-line bg-surface p-1.5 shadow-2xl">
            {list.map((c) => (
              <li key={c}>
                <button type="button" role="option" aria-selected={c === value} onClick={() => { setOpen(false); if (c !== value) onChange(c); }}
                  className={clsx("flex w-full items-center gap-2.5 rounded-xl px-2.5 py-1.5 text-left text-[13px] hover:bg-surface-2", c === value && "font-semibold")}>
                  <span className="h-2 w-2 rounded-full" style={{ background: catMeta(c).color }} />
                  <span className="flex-1">{c}</span>
                  {c === value && <Check size={14} className="text-accent" />}
                </button>
              </li>
            ))}
          </motion.ul>
        )}
      </AnimatePresence>
    </div>
  );
}
