import { useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Check, PiggyBank, Plus, Trash2, X } from "lucide-react";
import clsx from "clsx";
import { api, dataChanged } from "../lib/api";
import { useApi } from "../lib/hooks";
import { Button, Card, CountUp, Empty, ErrorState, Field, IconButton, Input, PageHeader, Pill, Select, Skeleton } from "../components/ui";
import Modal from "../components/Modal";
import { CategoryIcon, catMeta } from "../lib/categories";
import { money } from "../lib/format";
import { useToast } from "../components/Toast";

const STATUS = {
  "on-track": { tone: "good", label: "On track" },
  "at-risk": { tone: "warn", label: "May go over" },
  over: { tone: "bad", label: "Over budget" },
};

export default function Budgets() {
  const { data, error, loading, reload } = useApi("/budgets");
  const [adding, setAdding] = useState(false);
  if (error) return <Card><ErrorState error={error} onRetry={reload} /></Card>;
  const list = data?.budgets ?? [];
  const totalLimit = list.reduce((s, b) => s + b.limit, 0);
  const totalSpent = list.reduce((s, b) => s + b.spent, 0);
  const risky = list.filter((b) => b.status !== "on-track").length;

  return (
    <>
      <PageHeader title="Budgets" subtitle="Projections blend your pace this month with the forecast model, so one early big spend doesn't trigger a false alarm."
        actions={<Button icon={Plus} onClick={() => setAdding(true)} disabled={data && data.available_categories.length === 0}>New budget</Button>} />

      {data && list.length > 0 && (
        <Card className="mb-5 grid gap-5 p-5 sm:grid-cols-3 sm:p-6">
          <div><p className="text-[13px] text-muted">Spent against budgets</p>
            <p className="display mt-1 text-3xl font-semibold"><CountUp value={totalSpent} format={money} /><span className="text-lg text-faint"> / {money(totalLimit)}</span></p></div>
          <div><p className="text-[13px] text-muted">Left for the month</p>
            <p className={clsx("display mt-1 text-3xl font-semibold", totalLimit - totalSpent < 0 && "text-coral")}><CountUp value={totalLimit - totalSpent} format={money} /></p>
            <p className="text-[12px] text-faint">about {money(Math.max(totalLimit - totalSpent, 0) / Math.max(data.days - data.day + 1, 1))} a day for {data.days - data.day + 1} days</p></div>
          <div><p className="text-[13px] text-muted">Needing attention</p>
            <p className="display mt-1 text-3xl font-semibold"><span className={risky ? "text-accent" : "text-mint"}>{risky}</span><span className="text-lg text-faint"> of {list.length}</span></p></div>
        </Card>
      )}

      {loading && !data ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">{[0, 1, 2, 3, 4, 5].map((i) => <Skeleton key={i} className="h-44 rounded-[20px]" />)}</div>
      ) : list.length === 0 ? (
        <Card><Empty icon={PiggyBank} title="No budgets yet" body="Set a monthly limit for a category and FinSight warns you before you cross it."
          action={<Button icon={Plus} onClick={() => setAdding(true)}>Create a budget</Button>} /></Card>
      ) : (
        <motion.div layout className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          <AnimatePresence>{list.map((b) => <BudgetCard key={b.id} b={b} day={data.day} days={data.days} onChanged={reload} />)}</AnimatePresence>
        </motion.div>
      )}

      {data?.unbudgeted?.length > 0 && (
        <Card className="mt-5 p-5 sm:p-6">
          <h2 className="display text-lg font-semibold">Spending without a budget</h2>
          <p className="text-[13px] text-muted">These categories have spend this month but no limit.</p>
          <div className="mt-4 flex flex-wrap gap-2">
            {data.unbudgeted.map((u) => (
              <span key={u.category} className="inline-flex items-center gap-2 rounded-xl bg-surface-2 py-1.5 pl-1.5 pr-3 text-[13px]">
                <CategoryIcon category={u.category} size={26} />{u.category}<span className="num font-semibold">{money(u.spent)}</span>
              </span>
            ))}
          </div>
        </Card>
      )}
      <NewBudget open={adding} onClose={() => setAdding(false)} options={data?.available_categories ?? []} onSaved={reload} />
    </>
  );
}

function BudgetCard({ b, day, days, onChanged }) {
  const toast = useToast();
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(String(b.limit));
  const [busy, setBusy] = useState(false);
  const s = STATUS[b.status];
  const color = b.status === "over" ? "var(--coral)" : b.status === "at-risk" ? "var(--accent)" : catMeta(b.category).color;
  const spentPct = Math.min(b.spent / b.limit, 1) * 100;
  const projPct = Math.min(b.projected / b.limit, 1) * 100;

  async function save() {
    const v = Number(value);
    if (!v || v <= 0) return toast("Enter a limit above zero.", { tone: "bad" });
    setBusy(true);
    try { await api("/budgets", { method: "PUT", body: { category: b.category, monthly_limit: v } }); setEditing(false); onChanged(); dataChanged(); toast(`${b.category} budget set to ${money(v)}.`); }
    catch (e) { toast(e.message, { tone: "bad" }); } finally { setBusy(false); }
  }
  async function remove() {
    try { await api(`/budgets/${b.id}`, { method: "DELETE" }); onChanged(); dataChanged(); toast(`${b.category} budget removed.`, { tone: "info" }); }
    catch (e) { toast(e.message, { tone: "bad" }); }
  }

  return (
    <motion.div layout initial={{ opacity: 0, scale: 0.97 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.95 }}>
      <Card className="group h-full p-5">
        <div className="flex items-start gap-3">
          <CategoryIcon category={b.category} size={40} />
          <div className="min-w-0 flex-1">
            <p className="font-semibold">{b.category}</p>
            <Pill tone={s.tone} className="mt-1">{s.label}</Pill>
          </div>
          <IconButton icon={Trash2} label={`Remove ${b.category} budget`} onClick={remove} className="h-8 w-8 opacity-0 transition-opacity hover:text-coral focus:opacity-100 group-hover:opacity-100" />
        </div>
        <div className="mt-5 flex items-baseline justify-between gap-2">
          <p className="display text-[1.7rem] font-semibold leading-none"><CountUp value={b.spent} format={money} /></p>
          <AnimatePresence mode="wait" initial={false}>
            {editing ? (
              <motion.form key="e" initial={{ opacity: 0, x: 6 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }} className="flex items-center gap-1"
                onSubmit={(e) => { e.preventDefault(); save(); }}>
                <Input autoFocus type="number" min="1" value={value} onChange={(e) => setValue(e.target.value)} className="num h-8 w-24 text-right" aria-label="Monthly limit" />
                <IconButton icon={Check} label="Save limit" type="submit" disabled={busy} className="h-8 w-8 text-mint" />
                <IconButton icon={X} label="Cancel" type="button" onClick={() => { setEditing(false); setValue(String(b.limit)); }} className="h-8 w-8" />
              </motion.form>
            ) : (
              <motion.button key="v" initial={{ opacity: 0 }} animate={{ opacity: 1 }} onClick={() => setEditing(true)}
                className="num rounded-lg px-1.5 py-0.5 text-sm text-muted underline decoration-line decoration-dashed underline-offset-4 hover:text-text" title="Edit limit">
                of {money(b.limit)}
              </motion.button>
            )}
          </AnimatePresence>
        </div>
        <div className="relative mt-3 h-2.5 rounded-full bg-raised">
          <motion.div className="hatch absolute inset-y-0 left-0 rounded-full" style={{ color }} initial={{ width: 0 }} animate={{ width: `${projPct}%` }} transition={{ duration: 1.1, ease: [0.16, 1, 0.3, 1] }} />
          <motion.div className="absolute inset-y-0 left-0 rounded-full" style={{ background: color }} initial={{ width: 0 }} animate={{ width: `${spentPct}%` }} transition={{ duration: 0.9, ease: [0.16, 1, 0.3, 1] }} />
          <div className="absolute -top-1 bottom-[-4px] w-0.5 rounded bg-text/70" style={{ left: `${(day / days) * 100}%` }} title="Today" />
        </div>
        <div className="mt-3 flex justify-between text-[12px] text-muted">
          <span>{b.remaining >= 0 ? <>{money(b.remaining)} left · {money(b.daily_allowance)}/day</> : <span className="text-coral">{money(-b.remaining)} over</span>}</span>
          <span>month-end ~<span className="num font-semibold text-text">{money(b.projected)}</span></span>
        </div>
      </Card>
    </motion.div>
  );
}

function NewBudget({ open, onClose, options, onSaved }) {
  const toast = useToast();
  const [category, setCategory] = useState("");
  const [limit, setLimit] = useState("");
  const [busy, setBusy] = useState(false);
  const cat = category || options[0] || "";
  async function submit(e) {
    e.preventDefault();
    const v = Number(limit);
    if (!v || v <= 0) return toast("Enter a monthly limit above zero.", { tone: "bad" });
    setBusy(true);
    try { await api("/budgets", { method: "PUT", body: { category: cat, monthly_limit: v } }); toast(`${cat} budget created.`); onSaved(); dataChanged(); onClose(); setLimit(""); setCategory(""); }
    catch (err) { toast(err.message, { tone: "bad" }); } finally { setBusy(false); }
  }
  return (
    <Modal open={open} onClose={onClose} title="New budget" subtitle="A monthly limit for one category." width={420}>
      <form onSubmit={submit} className="space-y-4">
        <Field label="Category"><Select value={cat} onChange={(e) => setCategory(e.target.value)} className="w-full">{options.map((c) => <option key={c}>{c}</option>)}</Select></Field>
        <Field label="Monthly limit (₹)"><Input type="number" min="1" value={limit} onChange={(e) => setLimit(e.target.value)} placeholder="5000" className="num" /></Field>
        <div className="flex justify-end gap-2"><Button type="button" variant="ghost" onClick={onClose}>Cancel</Button><Button type="submit" loading={busy}>Create budget</Button></div>
      </form>
    </Modal>
  );
}
