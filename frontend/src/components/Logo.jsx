import clsx from "clsx";
export default function Logo({ className, compact }) {
  return (
    <div className={clsx("flex items-center gap-2.5", className)}>
      <svg width="32" height="32" viewBox="0 0 64 64" aria-hidden="true">
        <rect width="64" height="64" rx="16" fill="var(--surface-2)" stroke="var(--line)" />
        <path d="M14 44c8 0 10-24 18-24s10 14 18 14" fill="none" stroke="var(--accent)" strokeWidth="6" strokeLinecap="round" />
        <circle cx="50" cy="34" r="5" fill="var(--mint)" />
      </svg>
      <span className={clsx("display font-bold tracking-tight", compact ? "text-lg" : "text-[1.35rem]")}>FinSight</span>
    </div>
  );
}
