import { useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { CalendarDays, Plus, Target, Trash2 } from "lucide-react";
import clsx from "clsx";
import { api } from "../lib/api";
import { useApi } from "../lib/hooks";
import { Button, Card, CountUp, Empty, ErrorState, Field, IconButton, Input, PageHeader, Pill, Ring, Skeleton } from "../components/ui";
import Modal from "../components/Modal";
import { money } from "../lib/format";
import { useToast } from "../components/Toast";

const EMOJI = ["🎯", "🛟", "💻", "🏖️", "🏍️", "🎓", "🏠", "💍", "📱", "✈️"];
const STATUS = { "on-track": ["good", "On track"], behind: ["warn", "Behind schedule"], overdue: ["bad", "Past deadline"], done: ["good", "Reached"], "no-deadline": ["neutral", "No deadline"] };
const monthYear = (iso) => new Date(iso + "T00:00:00").toLocaleDateString("en-IN", { month: "short", year: "numeric" });

export default function Goals() {
  const { data, error, loading, reload } = useApi("/goals");
  const [creating, setCreating] = useState(false);
  if (error) return <Card><ErrorState error={error} onRetry={reload} /></Card>;
  const goals = data?.goals ?? [];
  return (
    <>
      <PageHeader title="Goals" subtitle="Set something to save for. FinSight splits your average monthly savings across active goals to estimate when you'll get there."
        actions={<Button icon={Plus} onClick={() => setCreating(true)}>New goal</Button>} />
      {data && goals.length > 0 && (
        <Card className="mb-5 flex flex-col gap-6 p-5 sm:flex-row sm:items-center sm:p-6">
          <Ring value={data.total_saved} max={data.total_target || 1} size={96} stroke={9} color="var(--mint)">
            <span className="display num text-lg font-semibold">{Math.round((data.total_saved / (data.total_target || 1)) * 100)}%</span>
          </Ring>
          <div className="grid flex-1 gap-5 sm:grid-cols-3">
            <div><p className="text-[13px] text-muted">Saved across goals</p><p className="display mt-1 text-3xl font-semibold"><CountUp value={data.total_saved} format={money} /></p></div>
            <div><p className="text-[13px] text-muted">Still to go</p><p className="display mt-1 text-3xl font-semibold"><CountUp value={Math.max(data.total_target - data.total_saved, 0)} format={money} /></p></div>
            <div><p className="text-[13px] text-muted">You save on average</p>
              <p className={clsx("display mt-1 text-3xl font-semibold", data.monthly_savings < 0 && "text-coral")}><CountUp value={data.monthly_savings} format={money} /><span className="text-base text-faint"> /month</span></p>
              <p className="text-[12px] text-faint">last 3 complete months</p></div>
          </div>
        </Card>
      )}
      {loading && !data ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-72 rounded-[20px]" />)}</div>
      ) : goals.length === 0 ? (
        <Card><Empty icon={Target} title="No goals yet" body="An emergency fund, a laptop, a trip. Add a target and FinSight tracks progress and estimates a finish date."
          action={<Button icon={Plus} onClick={() => setCreating(true)}>Create a goal</Button>} /></Card>
      ) : (
        <motion.div layout className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          <AnimatePresence>{goals.map((g) => <GoalCard key={g.id} g={g} onChanged={reload} />)}</AnimatePresence>
        </motion.div>
      )}
      <NewGoal open={creating} onClose={() => setCreating(false)} onSaved={reload} />
    </>
  );
}

function GoalCard({ g, onChanged }) {
  const toast = useToast();
  const [amount, setAmount] = useState("");
  const [busy, setBusy] = useState(false);
  const [tone, label] = STATUS[g.status];
  const done = g.status === "done";

  async function add(v) {
    const n = Number(v);
    if (!n) return toast("Enter an amount to add.", { tone: "bad" });
    setBusy(true);
    try {
      const r = await api(`/goals/${g.id}/contribute`, { method: "POST", body: { amount: n } });
      setAmount("");
      toast(r.completed && !done ? `${g.emoji} ${g.name} reached. Well done!` : `${n > 0 ? "Added" : "Withdrew"} ${money(Math.abs(n))} ${n > 0 ? "to" : "from"} ${g.name}.`);
      onChanged();
    } catch (e) { toast(e.message, { tone: "bad" }); } finally { setBusy(false); }
  }
  async function remove() {
    try { await api(`/goals/${g.id}`, { method: "DELETE" }); toast(`${g.name} removed.`, { tone: "info" }); onChanged(); }
    catch (e) { toast(e.message, { tone: "bad" }); }
  }

  let plan;
  if (done) plan = "Target reached. Move the money somewhere safe or set a bigger goal.";
  else if (g.required_monthly !== null) plan = <>Needs <b className="num text-text">{money(g.required_monthly)}</b>/month to hit the {monthYear(g.deadline)} deadline. At your current pace you’d finish {g.projected_date ? monthYear(g.projected_date) : "later"}.</>;
  else if (g.projected_date) plan = <>At about <b className="num text-text">{money(g.suggested_monthly)}</b>/month you’ll get there by <b className="text-text">{monthYear(g.projected_date)}</b>.</>;
  else plan = "Your recent months didn't leave savings, so there's no finish estimate yet.";

  return (
    <motion.div layout initial={{ opacity: 0, scale: 0.97 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.95 }}>
      <Card className={clsx("group flex h-full flex-col p-5", done && "ring-1 ring-mint/40")}>
        <div className="flex items-start gap-3">
          <motion.span whileHover={{ rotate: [0, -10, 10, 0] }} className="grid h-12 w-12 place-items-center rounded-2xl bg-surface-2 text-2xl">{g.emoji}</motion.span>
          <div className="min-w-0 flex-1">
            <p className="truncate font-semibold">{g.name}</p>
            <div className="mt-1 flex flex-wrap items-center gap-1.5">
              <Pill tone={tone}>{label}</Pill>
              {g.deadline && <span className="inline-flex items-center gap-1 text-[12px] text-faint"><CalendarDays size={12} />{monthYear(g.deadline)}</span>}
            </div>
          </div>
          <IconButton icon={Trash2} label={`Remove ${g.name}`} onClick={remove} className="h-8 w-8 opacity-0 transition-opacity hover:text-coral focus:opacity-100 group-hover:opacity-100" />
        </div>
        <div className="mt-5 flex items-center gap-5">
          <Ring value={g.progress * 100} size={92} stroke={9} color={done ? "var(--mint)" : "var(--accent)"}>
            <span className="display num text-lg font-semibold">{Math.round(g.progress * 100)}%</span>
          </Ring>
          <div className="min-w-0">
            <p className="display text-[1.6rem] font-semibold leading-none"><CountUp value={g.saved} format={money} /></p>
            <p className="num mt-1 text-sm text-muted">of {money(g.target)}</p>
            {!done && <p className="num mt-0.5 text-[12px] text-faint">{money(g.remaining)} to go</p>}
          </div>
        </div>
        <p className="mt-4 flex-1 text-[13px] leading-relaxed text-muted">{plan}</p>
        {!done && (
          <div className="mt-4 border-t border-line-soft pt-4">
            <div className="flex flex-wrap gap-1.5">
              {[500, 1000, 5000].map((v) => (
                <motion.button key={v} whileTap={{ scale: 0.92 }} disabled={busy} onClick={() => add(v)}
                  className="num rounded-lg border border-line-soft bg-surface-2 px-2.5 py-1 text-[12px] font-semibold text-muted hover:border-line hover:text-text">+{money(v)}</motion.button>
              ))}
            </div>
            <form className="mt-2 flex gap-2" onSubmit={(e) => { e.preventDefault(); add(amount); }}>
              <Input type="number" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="Custom amount" className="num h-9" aria-label={`Amount to add to ${g.name}`} />
              <Button size="sm" className="h-9" loading={busy} type="submit">Add</Button>
            </form>
          </div>
        )}
      </Card>
    </motion.div>
  );
}

function NewGoal({ open, onClose, onSaved }) {
  const toast = useToast();
  const blank = { name: "", target: "", saved: "", deadline: "", emoji: "🎯" };
  const [f, setF] = useState(blank);
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.value }));
  async function submit(e) {
    e.preventDefault();
    if (f.name.trim().length < 2) return toast("Give the goal a name.", { tone: "bad" });
    if (!(Number(f.target) > 0)) return toast("Enter a target amount above zero.", { tone: "bad" });
    setBusy(true);
    try {
      await api("/goals", { method: "POST", body: { name: f.name.trim(), target: Number(f.target), saved: Number(f.saved) || 0, emoji: f.emoji, deadline: f.deadline || null } });
      toast(`${f.emoji} ${f.name.trim()} created.`); setF(blank); onSaved(); onClose();
    } catch (err) { toast(err.message, { tone: "bad" }); } finally { setBusy(false); }
  }
  return (
    <Modal open={open} onClose={onClose} title="New goal" subtitle="What are you saving for?" width={460}>
      <form onSubmit={submit} className="space-y-4">
        <div className="flex flex-wrap gap-1.5" role="radiogroup" aria-label="Icon">
          {EMOJI.map((e) => (
            <button type="button" key={e} role="radio" aria-checked={f.emoji === e} onClick={() => setF((x) => ({ ...x, emoji: e }))}
              className={clsx("grid h-10 w-10 place-items-center rounded-xl text-xl transition-all", f.emoji === e ? "scale-110 bg-accent-soft ring-2 ring-accent" : "bg-surface-2 hover:bg-raised")}>{e}</button>
          ))}
        </div>
        <Field label="Name"><Input value={f.name} onChange={set("name")} placeholder="Emergency fund" maxLength={60} /></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Target (₹)"><Input type="number" min="1" value={f.target} onChange={set("target")} placeholder="100000" className="num" /></Field>
          <Field label="Already saved (₹)"><Input type="number" min="0" value={f.saved} onChange={set("saved")} placeholder="0" className="num" /></Field>
        </div>
        <Field label="Deadline" hint="Optional. Adds a monthly amount you need to save."><Input type="date" value={f.deadline} onChange={set("deadline")} /></Field>
        <div className="flex justify-end gap-2"><Button type="button" variant="ghost" onClick={onClose}>Cancel</Button><Button type="submit" loading={busy}>Create goal</Button></div>
      </form>
    </Modal>
  );
}
