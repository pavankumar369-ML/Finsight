import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Sparkles, Trash2 } from "lucide-react";
import clsx from "clsx";
import Modal from "./Modal";
import { Button, Field, Input, Segmented, Select } from "./ui";
import { api, dataChanged } from "../lib/api";
import { useDebounced } from "../lib/hooks";
import { CategoryIcon, EXPENSE, INCOME, catMeta } from "../lib/categories";
import { todayISO } from "../lib/format";
import { useToast } from "./Toast";

export default function AddTransaction({ open, onClose, editing }) {
  const toast = useToast();
  const [form, setForm] = useState(blank());
  const [picked, setPicked] = useState(null);         // category the user chose explicitly
  const [suggestion, setSuggestion] = useState(null);
  const [thinking, setThinking] = useState(false);
  const [errors, setErrors] = useState({});
  const [saving, setSaving] = useState(false);
  const desc = useDebounced(form.description, 280);

  function blank() { return { description: "", amount: "", date: todayISO(), type: "expense" }; }

  useEffect(() => {
    if (!open) return;
    if (editing) {
      setForm({ description: editing.description, amount: String(editing.amount), date: editing.date, type: editing.type });
      setPicked(editing.category);
    } else { setForm(blank()); setPicked(null); }
    setSuggestion(null); setErrors({});
  }, [open, editing]);

  useEffect(() => {
    if (!open || form.type !== "expense" || desc.trim().length < 3) { setSuggestion(null); return; }
    let live = true;
    setThinking(true);
    api("/categorize/suggest", { method: "POST", body: { description: desc } })
      .then((s) => live && setSuggestion(s)).catch(() => {}).finally(() => live && setThinking(false));
    return () => { live = false; };
  }, [desc, form.type, open]);

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const category = picked ?? (form.type === "expense" ? suggestion?.category : "Other income");

  async function submit(e) {
    e.preventDefault();
    const errs = {};
    if (form.description.trim().length < 2) errs.description = "Describe the transaction, like “UPI/SWIGGY”.";
    const amt = Number(form.amount);
    if (!amt || amt <= 0) errs.amount = "Enter an amount above zero.";
    if (!form.date) errs.date = "Pick a date.";
    setErrors(errs);
    if (Object.keys(errs).length) return;
    setSaving(true);
    try {
      const body = { description: form.description.trim(), amount: amt, date: form.date, type: form.type };
      if (picked) body.category = picked;
      let t;
      if (editing) {
        t = await api(`/transactions/${editing.id}`, { method: "PATCH", body: { ...body, category: picked ?? category } });
        toast("Transaction updated.");
      } else {
        t = await api("/transactions", { method: "POST", body });
        toast(t.is_anomaly ? `Added. This looks unusual: ${t.anomaly_reason}.` : `Added to ${t.category}.`, { tone: t.is_anomaly ? "info" : "good" });
      }
      dataChanged();
      onClose();
    } catch (err) {
      toast(err.message, { tone: "bad" });
    } finally { setSaving(false); }
  }

  async function remove() {
    setSaving("del");
    try { await api(`/transactions/${editing.id}`, { method: "DELETE" }); toast("Transaction deleted.", { tone: "info" }); dataChanged(); onClose(); }
    catch (err) { toast(err.message, { tone: "bad" }); } finally { setSaving(false); }
  }

  const options = form.type === "expense" ? EXPENSE : INCOME;
  return (
    <Modal open={open} onClose={onClose} title={editing ? "Edit transaction" : "Add transaction"}
      subtitle={editing ? "Changing the category teaches the model." : "Type a description and FinSight suggests the category."}>
      <form onSubmit={submit} className="space-y-4" noValidate>
        <Segmented value={form.type} onChange={(v) => { setForm((f) => ({ ...f, type: v })); setPicked(null); }}
          options={[{ value: "expense", label: "Expense" }, { value: "income", label: "Income" }]} />
        <Field label="Description" error={errors.description}>
          <Input value={form.description} onChange={set("description")} placeholder="e.g. UPI/ZOMATO/VELLORE" autoComplete="off" maxLength={200} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Amount (₹)" error={errors.amount}>
            <Input value={form.amount} onChange={set("amount")} inputMode="decimal" type="number" min="0" step="0.01" placeholder="0" className="num" />
          </Field>
          <Field label="Date" error={errors.date}>
            <Input type="date" value={form.date} onChange={set("date")} max={todayISO()} />
          </Field>
        </div>

        {form.type === "expense" && (
          <div className="rounded-2xl border border-line-soft bg-surface-2 p-4">
            <div className="mb-3 flex items-center gap-2 text-[13px] font-semibold text-muted">
              <Sparkles size={15} className={clsx("text-accent", thinking && "animate-pulse")} />
              {picked ? "You picked a category" : suggestion ? "Suggested category" : "Category suggestion appears as you type"}
            </div>
            <AnimatePresence mode="popLayout">
              {suggestion && !picked && (
                <motion.div key="s" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="space-y-2">
                  {suggestion.top.map((c, i) => (
                    <button type="button" key={c.category} onClick={() => setPicked(c.category)}
                      className={clsx("group flex w-full items-center gap-3 rounded-xl px-2 py-1.5 text-left transition-colors hover:bg-raised", i === 0 && "bg-raised/60")}>
                      <CategoryIcon category={c.category} size={28} />
                      <span className="w-28 text-sm font-semibold">{c.category}</span>
                      <span className="relative h-1.5 flex-1 overflow-hidden rounded-full bg-line-soft">
                        <motion.span className="absolute inset-y-0 left-0 rounded-full" style={{ background: catMeta(c.category).color }}
                          initial={{ width: 0 }} animate={{ width: `${Math.max(c.p * 100, 2)}%` }} transition={{ type: "spring", stiffness: 140, damping: 22 }} />
                      </span>
                      <span className="num w-11 text-right text-[12px] text-muted">{Math.round(c.p * 100)}%</span>
                    </button>
                  ))}
                  <p className="pt-1 text-[12px] text-faint">
                    {suggestion.confidence < 0.6 ? "Not very sure about this one. Tap the right category to help it learn." : `Model answered in ${suggestion.inference_ms} ms.`}
                  </p>
                </motion.div>
              )}
            </AnimatePresence>
            <div className="mt-3 flex items-center gap-2">
              <span className="text-[12px] text-faint">{picked ? "Category" : "Or choose"}</span>
              <Select value={picked ?? ""} onChange={(e) => setPicked(e.target.value || null)} className="h-9 flex-1">
                <option value="">{suggestion ? `Use suggestion (${suggestion.category})` : "Let FinSight decide"}</option>
                {options.map((c) => <option key={c}>{c}</option>)}
              </Select>
            </div>
          </div>
        )}
        {form.type === "income" && (
          <Field label="Category">
            <Select value={picked ?? "Other income"} onChange={(e) => setPicked(e.target.value)} className="w-full">
              {INCOME.map((c) => <option key={c}>{c}</option>)}
            </Select>
          </Field>
        )}
        <div className="flex justify-end gap-2 pt-1">
          {editing && <Button type="button" variant="ghost" icon={Trash2} className="mr-auto text-coral hover:text-coral" loading={saving === "del"} onClick={remove}>Delete</Button>}
          <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
          <Button type="submit" loading={saving === true}>{editing ? "Save changes" : "Add transaction"}</Button>
        </div>
      </form>
    </Modal>
  );
}
