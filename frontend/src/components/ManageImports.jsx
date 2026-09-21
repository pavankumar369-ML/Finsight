import { useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { AlertTriangle, FileSpreadsheet, FileText, Trash2, Undo2 } from "lucide-react";
import clsx from "clsx";
import Modal from "./Modal";
import { Button, Input, Skeleton } from "./ui";
import { api, dataChanged } from "../lib/api";
import { useApi } from "../lib/hooks";
import { useToast } from "./Toast";

const when = (iso) => new Date(iso).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });

export default function ManageImports({ open, onClose, isDemo }) {
  const toast = useToast();
  const { data, reload } = useApi(open ? "/imports" : null);
  const [confirming, setConfirming] = useState(null);   // batch id awaiting confirmation
  const [busy, setBusy] = useState(null);
  const [typed, setTyped] = useState("");

  async function undo(b) {
    setBusy(b.id);
    try {
      const r = await api(`/imports/${b.id}`, { method: "DELETE" });
      toast(`Removed ${r.deleted} transaction${r.deleted === 1 ? "" : "s"} from ${r.filename}.`, { tone: "info" });
      setConfirming(null); reload(); dataChanged();
    } catch (e) { toast(e.message, { tone: "bad" }); } finally { setBusy(null); }
  }
  async function deleteAll() {
    setBusy("all");
    try {
      const r = await api("/transactions/delete-all", { method: "POST", body: { confirm: typed } });
      toast(`Deleted all ${r.deleted} transactions. You're starting fresh.`, { tone: "info" });
      setTyped(""); reload(); dataChanged(); onClose();
    } catch (e) { toast(e.message, { tone: "bad" }); } finally { setBusy(null); }
  }

  const list = data?.imports ?? [];
  return (
    <Modal open={open} onClose={() => { setConfirming(null); setTyped(""); onClose(); }} title="Import history"
      subtitle="Every statement you import is kept as a batch, so a wrong file can be removed in one step." width={560}>
      {!data ? <div className="space-y-2">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-16" />)}</div> : list.length === 0 ? (
        <p className="rounded-2xl bg-surface-2 px-4 py-6 text-center text-sm text-muted">No imports yet. Files you import will appear here.</p>
      ) : (
        <ul className="space-y-2">
          <AnimatePresence initial={false}>
            {list.map((b) => {
              const Icon = b.file_type === "PDF" ? FileText : FileSpreadsheet;
              const gone = b.remaining === 0;
              return (
                <motion.li key={b.id} layout initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0, height: 0 }}
                  className="rounded-2xl border border-line-soft bg-surface-2 p-3">
                  <div className="flex items-center gap-3">
                    <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-surface text-accent"><Icon size={18} /></span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[14px] font-semibold">{b.filename}</p>
                      <p className="text-[12px] text-faint">
                        {when(b.created_at)} · {b.file_type} · <span className="num">{b.remaining}</span> of {b.imported} still in your list
                        {b.duplicates > 0 && <> · {b.duplicates} duplicates skipped</>}
                      </p>
                    </div>
                    {confirming !== b.id && (
                      <Button size="sm" variant="secondary" icon={Undo2} disabled={gone} onClick={() => setConfirming(b.id)}>Undo import</Button>
                    )}
                  </div>
                  {confirming === b.id && (
                    <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} className="mt-3 flex flex-wrap items-center justify-between gap-2 rounded-xl bg-coral-soft px-3 py-2">
                      <span className="text-[13px] text-coral">Remove all {b.remaining} transactions from this file? This can't be undone.</span>
                      <span className="flex gap-2">
                        <Button size="sm" variant="ghost" onClick={() => setConfirming(null)}>Keep</Button>
                        <Button size="sm" variant="danger" loading={busy === b.id} onClick={() => undo(b)}>Remove</Button>
                      </span>
                    </motion.div>
                  )}
                </motion.li>
              );
            })}
          </AnimatePresence>
        </ul>
      )}

      {!isDemo && (
        <div className="mt-6 rounded-2xl border border-coral/40 p-4">
          <p className="flex items-center gap-2 text-[14px] font-semibold text-coral"><AlertTriangle size={16} />Danger zone</p>
          <p className="mt-1 text-[13px] text-muted">Delete every transaction in your account (budgets and goals are kept). Type <b className="text-text">DELETE</b> to confirm.</p>
          <div className="mt-3 flex gap-2">
            <Input value={typed} onChange={(e) => setTyped(e.target.value)} placeholder="DELETE" aria-label="Type DELETE to confirm" className="h-9" />
            <Button size="sm" variant="danger" icon={Trash2} className={clsx("h-9", typed !== "DELETE" && "opacity-50")} disabled={typed !== "DELETE"} loading={busy === "all"} onClick={deleteAll}>
              Delete all
            </Button>
          </div>
        </div>
      )}
    </Modal>
  );
}
