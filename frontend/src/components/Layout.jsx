import { createContext, useContext, useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { motion } from "motion/react";
import PageBoundary from "./PageBoundary";
import { LayoutDashboard, ListOrdered, PiggyBank, Lightbulb, Activity, Plus, Moon, Sun, LogOut, Upload, Target, Sparkles, LayoutGrid } from "lucide-react";
import Notifications from "./Notifications";
import Modal from "./Modal";
import clsx from "clsx";
import { useAuth } from "./Auth";
import { Button, IconButton } from "./ui";
import AddTransaction from "./AddTransaction";
import ImportCsv from "./ImportCsv";
import Logo from "./Logo";

const NAV = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/transactions", label: "Transactions", icon: ListOrdered },
  { to: "/assistant", label: "Assistant", icon: Sparkles },
  { to: "/budgets", label: "Budgets", icon: PiggyBank },
  { to: "/goals", label: "Goals", icon: Target },
  { to: "/insights", label: "Insights", icon: Lightbulb },
  { to: "/metrics", label: "Metrics", icon: Activity },
];

const ActionsCtx = createContext(null);
export const useActions = () => useContext(ActionsCtx);

function ThemeToggle() {
  const [theme, setTheme] = useState(() => document.documentElement.dataset.theme || "dark");
  useEffect(() => { document.documentElement.dataset.theme = theme; localStorage.setItem("fs-theme", theme); }, [theme]);
  const dark = theme === "dark";
  return (
    <IconButton label={dark ? "Switch to light theme" : "Switch to dark theme"} onClick={() => setTheme(dark ? "light" : "dark")}
      icon={dark ? Sun : Moon} />
  );
}

export default function Layout() {
  const { user, logout } = useAuth();
  const location = useLocation();
  const [add, setAdd] = useState({ open: false, editing: null });
  const [importing, setImporting] = useState(false);
  const [more, setMore] = useState(false);
  const actions = { addTxn: () => setAdd({ open: true, editing: null }), editTxn: (t) => setAdd({ open: true, editing: t }), importCsv: () => setImporting(true) };

  useEffect(() => {
    const onKey = (e) => {
      if (e.target.closest("input, textarea, select, [contenteditable]") || e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key.toLowerCase() === "n") { e.preventDefault(); actions.addTxn(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []); // eslint-disable-line

  return (
    <ActionsCtx.Provider value={actions}>
      <div className="grain min-h-full">
        {/* sidebar */}
        <aside className="fixed inset-y-0 left-0 z-30 hidden w-[244px] flex-col border-r border-line-soft bg-surface/60 px-4 pb-4 pt-6 backdrop-blur lg:flex">
          <Logo className="px-2" />
          <nav className="mt-9 flex flex-col gap-1" aria-label="Main">
            {NAV.map(({ to, label, icon: Icon, end }) => (
              <NavLink key={to} to={to} end={end} className={({ isActive }) => clsx("relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-[14px] font-semibold transition-colors",
                isActive ? "text-text" : "text-muted hover:text-text")}>
                {({ isActive }) => (<>
                  {isActive && <motion.span layoutId="nav-active" className="absolute inset-0 rounded-xl bg-surface-2 ring-1 ring-line" transition={{ type: "spring", stiffness: 480, damping: 38 }} />}
                  {isActive && <motion.span layoutId="nav-bar" className="absolute left-0 top-2.5 bottom-2.5 w-[3px] rounded-full bg-accent" transition={{ type: "spring", stiffness: 480, damping: 38 }} />}
                  <Icon size={18} className="relative" />
                  <span className="relative">{label}</span>
                  {label === "Metrics" && <span className="live-dot relative ml-auto h-1.5 w-1.5 rounded-full bg-mint" />}
                </>)}
              </NavLink>
            ))}
          </nav>
          <div className="mt-6 space-y-2 px-1">
            <Button className="w-full" icon={Plus} onClick={actions.addTxn}>Add transaction</Button>
            <Button className="w-full" variant="secondary" icon={Upload} onClick={actions.importCsv}>Import statement</Button>
          </div>
          <div className="mt-auto flex items-center gap-3 rounded-2xl border border-line-soft bg-surface-2 p-3">
            <span className="display grid h-9 w-9 shrink-0 place-items-center rounded-full bg-accent text-[15px] font-bold text-accent-ink">
              {user?.name?.[0]?.toUpperCase()}
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold">{user?.name}</p>
              <p className="truncate text-[12px] text-faint">{user?.email}</p>
            </div>
            <IconButton icon={LogOut} label="Sign out" onClick={logout} className="h-8 w-8" />
          </div>
        </aside>

        {/* mobile top bar */}
        <header className="sticky top-0 z-30 flex items-center justify-between border-b border-line-soft bg-bg/85 px-4 py-3 backdrop-blur lg:hidden">
          <Logo compact />
          <div className="flex items-center gap-1">
            <Notifications />
            <ThemeToggle />
            <IconButton icon={Upload} label="Import statement" onClick={actions.importCsv} />
            <IconButton icon={LogOut} label="Sign out" onClick={logout} />
          </div>
        </header>

        <div className="relative z-10 lg:pl-[244px]">
          <div className="absolute right-6 top-6 z-20 hidden items-center gap-1 lg:flex"><Notifications /><ThemeToggle /></div>
          <main className="mx-auto max-w-[1320px] px-4 pb-28 pt-6 sm:px-6 lg:px-10 lg:pb-12 lg:pt-8">
            {/* Enter-only transition. An exit-wait (AnimatePresence mode="wait") around <Outlet/> could
                get stuck in dev/StrictMode and leave the page blank until a refresh. */}
            <motion.div key={location.pathname} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.22, ease: "easeOut" }}>
              <PageBoundary key={location.pathname}><Outlet /></PageBoundary>
            </motion.div>
          </main>
        </div>

        {/* mobile bottom nav */}
        <nav className="fixed inset-x-3 bottom-3 z-30 flex items-center justify-around rounded-2xl border border-line bg-surface/95 px-2 py-1.5 shadow-2xl backdrop-blur lg:hidden" aria-label="Main">
          {NAV.slice(0, 2).map((n) => <MobileLink key={n.to} {...n} />)}
          <motion.button whileTap={{ scale: 0.9 }} onClick={actions.addTxn} aria-label="Add transaction"
            className="grid h-11 w-11 place-items-center rounded-2xl bg-accent text-accent-ink"><Plus size={22} /></motion.button>
          <MobileLink {...NAV[2]} />
          <button onClick={() => setMore(true)} className={clsx("flex flex-col items-center gap-0.5 rounded-xl px-2 py-1 text-[10px] font-semibold",
            NAV.slice(3).some((n) => location.pathname.startsWith(n.to)) ? "text-accent" : "text-faint")}>
            <LayoutGrid size={19} />More
          </button>
        </nav>

        <AddTransaction open={add.open} editing={add.editing} onClose={() => setAdd({ open: false, editing: null })} />
        <ImportCsv open={importing} onClose={() => setImporting(false)} />
        <Modal open={more} onClose={() => setMore(false)} title="More" width={420}>
          <div className="grid grid-cols-2 gap-2">
            {NAV.slice(3).map(({ to, label, icon: Icon }) => (
              <NavLink key={to} to={to} onClick={() => setMore(false)} className={({ isActive }) => clsx("flex items-center gap-3 rounded-2xl border px-4 py-4 font-semibold",
                isActive ? "border-accent bg-accent-soft text-accent" : "border-line-soft bg-surface-2 text-text")}>
                <Icon size={19} />{label}
              </NavLink>
            ))}
          </div>
        </Modal>
      </div>
    </ActionsCtx.Provider>
  );
}

function MobileLink({ to, label, icon: Icon, end }) {
  return (
    <NavLink to={to} end={end} className={({ isActive }) => clsx("flex flex-col items-center gap-0.5 rounded-xl px-2 py-1 text-[10px] font-semibold", isActive ? "text-accent" : "text-faint")}>
      <Icon size={19} />{label}
    </NavLink>
  );
}
