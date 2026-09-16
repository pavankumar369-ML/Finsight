import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "motion/react";
import { X } from "lucide-react";

export default function Modal({ open, onClose, title, subtitle, children, width = 520 }) {
  const panel = useRef(null);
  useEffect(() => {
    if (!open) return;
    const prev = document.activeElement;
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    setTimeout(() => panel.current?.querySelector("input, select, textarea, button:not([data-close])")?.focus(), 60);
    return () => { document.removeEventListener("keydown", onKey); document.body.style.overflow = ""; prev?.focus?.(); };
  }, [open, onClose]);
  return createPortal(
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center sm:p-6">
          <motion.div className="absolute inset-0 bg-[#060812]/70 backdrop-blur-[3px]" onClick={onClose}
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} />
          <motion.div ref={panel} role="dialog" aria-modal="true" aria-label={title}
            className="relative max-h-[92vh] w-full overflow-y-auto rounded-t-[24px] border border-line bg-surface shadow-2xl sm:rounded-[24px]"
            style={{ maxWidth: width }}
            initial={{ opacity: 0, y: 40, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 24, scale: 0.98 }}
            transition={{ type: "spring", stiffness: 420, damping: 34 }}>
            <div className="sticky top-0 z-10 flex items-start justify-between gap-4 border-b border-line-soft bg-surface px-6 pb-4 pt-5">
              <div>
                <h2 className="display text-xl font-semibold">{title}</h2>
                {subtitle && <p className="mt-0.5 text-[13px] text-muted">{subtitle}</p>}
              </div>
              <button data-close onClick={onClose} aria-label="Close" className="grid h-9 w-9 place-items-center rounded-xl text-muted hover:bg-surface-2 hover:text-text">
                <X size={18} />
              </button>
            </div>
            <div className="px-6 py-5">{children}</div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
