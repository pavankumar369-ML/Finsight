import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { AnimatePresence, motion } from "motion/react";
import { AlertOctagon, ChevronLeft, ChevronRight, Download, Pencil, Plus, Search, SearchX, Trash2, Upload, X } from "lucide-react";
import clsx from "clsx";
import { api, apiUrl, dataChanged, getToken } from "../lib/api";
import { useApi, useDebounced } from "../lib/hooks";
import { Button, Card, Empty, ErrorState, IconButton, Input, PageHeader, Segmented, Select, Skeleton } from "../components/ui";
import CategoryPicker from "../components/CategoryPicker";
import { CategoryIcon, EXPENSE, INCOME } from "../lib/categories";
import { dateLabel, money, monthLabel } from "../lib/format";
import { useActions } from "../components/Layout";
import { useToast } from "../components/Toast";

const SIZE = 20;

function lastMonths(n) {
  const out = [], d = new Date();
  d.setDate(1);
  for (let i = 0; i < n; i++) { out.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`); d.setMonth(d.getMonth() - 1); }
  return out;
}

function Confidence({ value, corrected }) {
  if (corrected) return <span className="text-[11px] font-semibold text-sky">Set by you</span>;
  const bars = Math.max(1, Math.round(value * 4));
  const tone = value >= 0.8 ? "bg-mint" : value >= 0.6 ? "bg-accent" : "bg-coral";
  return (
    <span className="inline-flex items-end gap-[3px]" title={`Model confidence ${Math.round(value * 100)}%`} aria-label={`Model confidence ${Math.round(value * 100)} percent`}>
      {[1, 2, 3, 4].map((b) => <span key={b} className={clsx("w-[3px] rounded-full", b <= bars ? tone : "bg-line")} style={{ height: 4 + b * 3 }} />)}
    </span>
  );
}

export default function Transactions() {
  const [params, setParams] = useSearchParams();
  const actions = useActions();
  const toast = useToast();
  const [q, setQ] = useState(params.get("q") ?? "");
  const dq = useDebounced(q, 300);
  const type = params.get("type") ?? "";
  const category = params.get("category") ?? "";
  const month = params.get("month") ?? "";
  const anomaly = params.get("anomaly") === "1";
  const page = Number(params.get("page") ?? 1);
  const [hidden, setHidden] = useState(new Set());
  const timers = useRef({});

  const update = (patch) => {
    const next = new URLSearchParams(params);
    Object.entries({ page: "", ...patch }).forEach(([k, v]) => (v ? next.set(k, v) : next.delete(k)));
    setParams(next, { replace: true });
  };
  useEffect(() => { if (dq !== (params.get("q") ?? "")) update({ q: dq }); }, [dq]); // eslint-disable-line

  const path = useMemo(() => {
    const s = new URLSearchParams({ page, size: SIZE });
    if (dq) s.set("q", dq);
    if (type) s.set("type", type);
    if (category) s.set("category", category);
    if (month) s.set("month", month);
    if (anomaly) s.set("anomaly", "true");
    return `/transactions?${s}`;
  }, [dq, type, category, month, anomaly, page]);
  const { data, error, loading, reload } = useApi(path);
  const items = (data?.items ?? []).filter((t) => !hidden.has(t.id));
  const pages = data ? Math.max(1, Math.ceil(data.total / SIZE)) : 1;
  const filtered = dq || type || category || month || anomaly;

  const [exporting, setExporting] = useState(false);
  async function exportCsv() {
    setExporting(true);
    try {
      const qs = path.split("?")[1].replace(/(^|&)(page|size)=[^&]*/g, "");
      const res = await fetch(apiUrl(`/transactions/export?${qs}`), { headers: { Authorization: `Bearer ${getToken()}` } });
      if (!res.ok) throw new Error("Export failed. Try again.");
      const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(await res.blob()), download: `finsight-transactions.csv` });
      a.click(); URL.revokeObjectURL(a.href);
      toast(`Exported ${data?.total ?? ""} transactions.`);
    } catch (e) { toast(e.message, { tone: "bad" }); } finally { setExporting(false); }
  }

  async function recategorise(t, cat) {
    try {
      await api(`/transactions/${t.id}`, { method: "PATCH", body: { category: cat } });
      toast(`Moved to ${cat}. Retrain on the Metrics page to teach the model.`);
      reload(); dataChanged();
    } catch (e) { toast(e.message, { tone: "bad" }); }
  }
  function remove(t) {
    setHidden((h) => new Set(h).add(t.id));
    timers.current[t.id] = setTimeout(async () => {
      try { await api(`/transactions/${t.id}`, { method: "DELETE" }); dataChanged(); }
      catch (e) { toast(e.message, { tone: "bad" }); }
      finally { setHidden((h) => { const n = new Set(h); n.delete(t.id); return n; }); }
    }, 4000);
    toast("Transaction deleted.", {
      tone: "info", duration: 4000,
      action: { label: "Undo", onClick: () => { clearTimeout(timers.current[t.id]); setHidden((h) => { const n = new Set(h); n.delete(t.id); return n; }); } },
    });
  }

  return (
    <>
      <PageHeader title="Transactions" subtitle="Every category here was predicted by the model. Click a category to correct it."
        actions={<><Button variant="secondary" icon={Download} loading={exporting} onClick={exportCsv}>Export</Button><Button variant="secondary" icon={Upload} onClick={actions.importCsv}>Import</Button><Button icon={Plus} onClick={actions.addTxn}>Add</Button></>} />

      <Card className="mb-4 p-3 sm:p-4">
        <div className="flex flex-col gap-3 xl:flex-row xl:items-center">
          <div className="xl:w-72"><Input icon={Search} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search description or category" aria-label="Search transactions" /></div>
          <Segmented value={type} onChange={(v) => update({ type: v, category: "" })} options={[{ value: "", label: "All" }, { value: "expense", label: "Spent" }, { value: "income", label: "Income" }]} />
          <div className="flex flex-1 flex-wrap gap-2">
            <Select value={category} onChange={(e) => update({ category: e.target.value })} aria-label="Category">
              <option value="">All categories</option>
              {(type === "income" ? INCOME : type === "expense" ? EXPENSE : [...EXPENSE, ...INCOME]).map((c) => <option key={c}>{c}</option>)}
            </Select>
            <Select value={month} onChange={(e) => update({ month: e.target.value })} aria-label="Month">
              <option value="">Any month</option>
              {lastMonths(12).map((m) => <option key={m} value={m}>{monthLabel(m, true)}</option>)}
            </Select>
            <button onClick={() => update({ anomaly: anomaly ? "" : "1" })} aria-pressed={anomaly}
              className={clsx("inline-flex h-10 items-center gap-2 rounded-xl border px-3 text-sm font-semibold transition-colors",
                anomaly ? "border-coral bg-coral-soft text-coral" : "border-line bg-surface-2 text-muted hover:text-text")}>
              <AlertOctagon size={15} />Unusual only
            </button>
            {filtered && <Button variant="ghost" icon={X} onClick={() => { setQ(""); setParams({}, { replace: true }); }}>Clear</Button>}
          </div>
        </div>
      </Card>

      <div className="mb-3 flex flex-wrap items-center gap-x-5 gap-y-1 px-1 text-[13px] text-muted">
        {data && <>
          <span><span className="num font-semibold text-text">{data.total}</span> transactions</span>
          <span>Spent <span className="num font-semibold text-coral">{money(data.expense)}</span></span>
          <span>Income <span className="num font-semibold text-mint">{money(data.income)}</span></span>
        </>}
      </div>

      <Card className="overflow-visible">
        {error ? <ErrorState error={error} onRetry={reload} /> : loading && !data ? (
          <div className="space-y-2 p-5">{Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-12" />)}</div>
        ) : items.length === 0 ? (
          filtered ? <Empty icon={SearchX} title="No transactions match" body="Try a different search or clear the filters." />
            : <Empty icon={Upload} title="No transactions yet" body="Import a bank statement or add your first one." action={<Button icon={Upload} onClick={actions.importCsv}>Import CSV</Button>} />
        ) : (
          <>
            <div className="hidden grid-cols-[88px_minmax(0,1fr)_170px_70px_120px_80px] gap-3 border-b border-line-soft px-6 py-3 text-[12px] font-semibold text-faint md:grid">
              <span>Date</span><span>Description</span><span>Category</span><span>Model</span><span className="text-right">Amount</span><span />
            </div>
            <ul className={clsx(loading && "opacity-60 transition-opacity")}>
              <AnimatePresence initial={false}>
                {items.map((t) => (
                  <motion.li key={t.id} layout="position" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0, height: 0 }}
                    className="group border-b border-line-soft last:border-0">
                    <div className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 px-4 py-3 md:grid-cols-[88px_minmax(0,1fr)_170px_70px_120px_80px] md:px-6">
                      <span className="num hidden text-[13px] text-muted md:block">{dateLabel(t.date)}</span>
                      <button className="md:hidden" onClick={() => actions.editTxn(t)} aria-label={`Edit ${t.description}`}><CategoryIcon category={t.category} size={34} /></button>
                      <div className="min-w-0">
                        <p className="flex items-center gap-2 truncate text-[14px] font-semibold">
                          <span className="truncate">{t.description}</span>
                          {t.is_anomaly && <span title={t.anomaly_reason} className="inline-flex shrink-0 items-center gap-1 rounded-full bg-coral-soft px-1.5 py-0.5 text-[11px] font-semibold text-coral"><AlertOctagon size={11} />Unusual</span>}
                        </p>
                        {t.is_anomaly && <p className="hidden text-[12px] text-coral md:block">{t.anomaly_reason}</p>}
                        <div className="mt-1 flex items-center gap-2 md:hidden">
                          <CategoryPicker value={t.category} type={t.type} corrected={t.user_corrected} onChange={(c) => recategorise(t, c)} />
                          <span className="text-[12px] text-faint">{dateLabel(t.date)}</span>
                        </div>
                      </div>
                      <span className="hidden md:block"><CategoryPicker value={t.category} type={t.type} corrected={t.user_corrected} onChange={(c) => recategorise(t, c)} /></span>
                      <span className="hidden md:block">{t.type === "expense" ? <Confidence value={t.confidence} corrected={t.user_corrected} /> : <span className="text-[11px] text-faint">—</span>}</span>
                      <button onClick={() => actions.editTxn(t)} tabIndex={-1} className={clsx("num text-right font-semibold md:pointer-events-none", t.type === "income" ? "text-mint" : "text-text")}>{t.type === "income" ? "+" : "−"}{money(t.amount)}</button>
                      <div className="hidden justify-end gap-0.5 opacity-0 transition-opacity focus-within:opacity-100 group-hover:opacity-100 md:flex">
                        <IconButton icon={Pencil} label="Edit" className="h-8 w-8" onClick={() => actions.editTxn(t)} />
                        <IconButton icon={Trash2} label="Delete" className="h-8 w-8 hover:text-coral" onClick={() => remove(t)} />
                      </div>
                    </div>
                  </motion.li>
                ))}
              </AnimatePresence>
            </ul>
          </>
        )}
      </Card>

      {data && pages > 1 && (
        <div className="mt-4 flex items-center justify-between gap-3 px-1">
          <span className="num text-[13px] text-muted">Page {page} of {pages}</span>
          <div className="flex gap-2">
            <Button variant="secondary" size="sm" icon={ChevronLeft} disabled={page <= 1} onClick={() => update({ page: String(page - 1) })}>Previous</Button>
            <Button variant="secondary" size="sm" disabled={page >= pages} onClick={() => update({ page: String(page + 1) })}>Next<ChevronRight size={16} /></Button>
          </div>
        </div>
      )}
    </>
  );
}
