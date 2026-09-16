import { cloneElement, forwardRef, useEffect, useId, useRef, useState } from "react";
import { animate, motion } from "motion/react";
import clsx from "clsx";
import { AlertTriangle, Loader2 } from "lucide-react";

export function Card({ className, children, as: As = "section", ...rest }) {
  return (
    <As className={clsx("relative rounded-[20px] border border-line-soft bg-surface shadow-card", className)} {...rest}>
      {children}
    </As>
  );
}

export function CardHeader({ title, hint, action, className }) {
  return (
    <div className={clsx("flex items-start justify-between gap-4 px-5 pt-5 sm:px-6 sm:pt-6", className)}>
      <div className="min-w-0">
        <h2 className="display text-[1.15rem] font-semibold leading-tight text-text">{title}</h2>
        {hint && <p className="mt-1 text-[13px] leading-snug text-muted">{hint}</p>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}

export const Button = forwardRef(function Button({ variant = "primary", size = "md", loading, icon: Icon, className, children, disabled, ...rest }, ref) {
  const base = "relative inline-flex select-none items-center justify-center gap-2 whitespace-nowrap rounded-xl font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-50";
  const sizes = { sm: "h-8 px-3 text-[13px]", md: "h-10 px-4 text-sm", lg: "h-12 px-5 text-[15px]" };
  const variants = {
    primary: "bg-accent text-accent-ink hover:brightness-110",
    secondary: "border border-line bg-surface-2 text-text hover:bg-raised",
    ghost: "text-muted hover:bg-surface-2 hover:text-text",
    danger: "bg-coral text-white hover:brightness-110",
  };
  return (
    <motion.button ref={ref} whileTap={{ scale: disabled || loading ? 1 : 0.96 }} transition={{ type: "spring", stiffness: 500, damping: 30 }}
      className={clsx(base, sizes[size], variants[variant], className)} disabled={disabled || loading} {...rest}>
      {loading ? <Loader2 size={16} className="animate-spin" /> : Icon && <Icon size={16} strokeWidth={2.2} />}
      {children}
    </motion.button>
  );
});

export function IconButton({ icon: Icon, label, className, ...rest }) {
  return (
    <motion.button whileTap={{ scale: 0.9 }} aria-label={label} title={label}
      className={clsx("grid h-9 w-9 place-items-center rounded-xl text-muted transition-colors hover:bg-surface-2 hover:text-text", className)} {...rest}>
      <Icon size={17} />
    </motion.button>
  );
}

export function Segmented({ value, onChange, options, size = "md", className }) {
  const id = useId();
  return (
    <div role="radiogroup" className={clsx("inline-flex rounded-xl border border-line-soft bg-surface-2 p-1", className)}>
      {options.map((o) => {
        const active = o.value === value;
        return (
          <button key={o.value} role="radio" aria-checked={active} onClick={() => onChange(o.value)} type="button"
            className={clsx("relative rounded-[9px] font-semibold transition-colors", size === "sm" ? "px-2.5 py-1 text-[12px]" : "px-3.5 py-1.5 text-[13px]",
              active ? "text-text" : "text-muted hover:text-text")}>
            {active && <motion.span layoutId={`seg-${id}`} className="absolute inset-0 rounded-[9px] border border-line bg-raised"
              transition={{ type: "spring", stiffness: 500, damping: 38 }} />}
            <span className="relative">{o.label}</span>
          </button>
        );
      })}
    </div>
  );
}

export const Input = forwardRef(function Input({ className, icon: Icon, ...rest }, ref) {
  return (
    <div className="relative">
      {Icon && <Icon size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-faint" />}
      <input ref={ref} className={clsx("h-10 w-full rounded-xl border border-line bg-surface-2 px-3 text-sm text-text placeholder:text-faint transition-colors focus:border-accent focus:outline-none",
        Icon && "pl-9", className)} {...rest} />
    </div>
  );
});

export function Select({ className, children, ...rest }) {
  return (
    <select className={clsx("h-10 cursor-pointer rounded-xl border border-line bg-surface-2 px-3 pr-8 text-sm text-text focus:border-accent focus:outline-none", className)} {...rest}>
      {children}
    </select>
  );
}

export function Field({ label, error, children, hint }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-[13px] font-semibold text-muted">{label}</span>
      {children}
      {error ? <span className="mt-1 block text-[12px] text-coral">{error}</span> : hint && <span className="mt-1 block text-[12px] text-faint">{hint}</span>}
    </label>
  );
}

export function Skeleton({ className }) { return <div className={clsx("skeleton", className)} />; }

export function ErrorState({ error, onRetry }) {
  return (
    <div className="flex flex-col items-center gap-3 px-6 py-10 text-center">
      <span className="grid h-11 w-11 place-items-center rounded-2xl bg-coral-soft text-coral"><AlertTriangle size={20} /></span>
      <p className="max-w-sm text-sm text-muted">{error?.message ?? "Something went wrong loading this."}</p>
      {onRetry && <Button variant="secondary" size="sm" onClick={onRetry}>Try again</Button>}
    </div>
  );
}

export function Empty({ icon: Icon, title, body, action }) {
  return (
    <div className="flex flex-col items-center gap-2 px-6 py-10 text-center">
      {Icon && <span className="mb-1 grid h-12 w-12 place-items-center rounded-2xl bg-surface-2 text-faint"><Icon size={22} /></span>}
      <p className="font-semibold text-text">{title}</p>
      {body && <p className="max-w-xs text-sm text-muted">{body}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

/* animates from the previously shown value to the new one */
export function CountUp({ value, format = (v) => Math.round(v).toLocaleString("en-IN"), duration = 0.9, className }) {
  const ref = useRef(null);
  const prev = useRef(0);
  const fmt = useRef(format);
  fmt.current = format;
  useEffect(() => {
    if (value === null || value === undefined) return;
    const node = ref.current;
    const from = prev.current;
    prev.current = value;
    const controls = animate(from, value, {
      duration, ease: [0.16, 1, 0.3, 1],
      onUpdate: (v) => { if (node) node.textContent = fmt.current(v); },
      onComplete: () => { if (node) node.textContent = fmt.current(value); },
    });
    return () => { controls.stop(); if (node) node.textContent = fmt.current(value); };
  }, [value, duration]);
  return <span ref={ref} className={clsx("num", className)}>{format(value ?? 0)}</span>;
}

/* Recharts' ResponsiveContainer can freeze an entry animation at a stale width.
   This waits for the container size to settle, then renders the chart at exact dimensions. */
export function ChartBox({ children }) {
  const ref = useRef(null);
  const [size, setSize] = useState(null);
  useEffect(() => {
    const el = ref.current;
    let t;
    const ro = new ResizeObserver(([entry]) => {
      clearTimeout(t);
      t = setTimeout(() => {
        const { width, height } = entry.contentRect;
        if (width > 0 && height > 0) setSize((s) => (s && Math.abs(s.w - width) < 2 && Math.abs(s.h - height) < 2 ? s : { w: Math.floor(width), h: Math.floor(height) }));
      }, 80);
    });
    ro.observe(el);
    return () => { ro.disconnect(); clearTimeout(t); };
  }, []);
  return <div ref={ref} className="h-full w-full">{size && cloneElement(children, { width: size.w, height: size.h })}</div>;
}

export function Pill({ tone = "neutral", children, className }) {
  const tones = {
    neutral: "bg-surface-2 text-muted border-line-soft",
    good: "bg-mint-soft text-mint border-transparent",
    warn: "bg-accent-soft text-accent border-transparent",
    bad: "bg-coral-soft text-coral border-transparent",
    info: "bg-surface-2 text-sky border-line-soft",
  };
  return <span className={clsx("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[12px] font-semibold", tones[tone], className)}>{children}</span>;
}

export function Ring({ value, max = 100, size = 120, stroke = 10, color = "var(--accent)", track = "var(--raised)", children }) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const frac = Math.max(0, Math.min(1, value / max));
  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={track} strokeWidth={stroke} />
        <motion.circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={stroke} strokeLinecap="round"
          strokeDasharray={c} initial={{ strokeDashoffset: c }} animate={{ strokeDashoffset: c * (1 - frac) }}
          transition={{ duration: 1.1, ease: [0.16, 1, 0.3, 1] }} />
      </svg>
      <div className="absolute inset-0 grid place-items-center">{children}</div>
    </div>
  );
}

export function ChartTooltip({ active, payload, label, formatter = (v) => v, labelFormatter = (l) => l }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-xl border border-line bg-surface px-3 py-2 text-[12px] shadow-card">
      <p className="mb-1 font-semibold text-text">{labelFormatter(label, payload)}</p>
      {payload.filter((p) => p.value !== null && p.value !== undefined).map((p) => (
        <div key={p.dataKey} className="flex items-center gap-2 text-muted">
          <span className="h-2 w-2 rounded-full" style={{ background: p.color || p.payload?.fill }} />
          <span>{p.name}</span>
          <span className="num ml-auto pl-3 font-semibold text-text">{formatter(p.value, p.dataKey)}</span>
        </div>
      ))}
    </div>
  );
}

export function useMediaQuery(q) {
  const [m, setM] = useState(() => window.matchMedia(q).matches);
  useEffect(() => {
    const mq = window.matchMedia(q);
    const fn = () => setM(mq.matches);
    mq.addEventListener("change", fn);
    return () => mq.removeEventListener("change", fn);
  }, [q]);
  return m;
}

export function PageHeader({ title, subtitle, actions }) {
  return (
    <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between lg:mb-8 lg:pr-24">
      <div>
        <h1 className="display text-[2rem] font-semibold leading-[1.05] sm:text-[2.5rem]">{title}</h1>
        {subtitle && <p className="mt-2 max-w-[62ch] text-[15px] text-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
