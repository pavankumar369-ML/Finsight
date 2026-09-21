import { useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { FileUp, FileSpreadsheet, Download, AlertTriangle, Lock } from "lucide-react";
import clsx from "clsx";
import Modal from "./Modal";
import { Button, CountUp } from "./ui";
import { api, apiUrl, dataChanged } from "../lib/api";
import { CategoryIcon, catMeta } from "../lib/categories";
import { useToast } from "./Toast";

export default function ImportCsv({ open, onClose }) {
  const toast = useToast();
  const input = useRef(null);
  const [file, setFile] = useState(null);
  const [drag, setDrag] = useState(false);
  const [busy, setBusy] = useState(false);
  const [password, setPassword] = useState("");
  const [locked, setLocked] = useState("");      // server message when a PDF needs a password
  const isPdf = file?.name?.toLowerCase().endsWith(".pdf");
  const [result, setResult] = useState(null);

  const close = () => { onClose(); setTimeout(() => { setFile(null); setResult(null); setPassword(""); setLocked(""); }, 250); };
  const pick = (f) => {
    if (!f) return;
    if (!/\.(csv|xlsx|xls|xlsm|pdf)$/i.test(f.name)) return toast("Choose a .csv, .xlsx, .xls or .pdf statement from your bank.", { tone: "bad" });
    setLocked(""); setPassword("");
    setFile(f); setResult(null);
  };
  async function upload() {
    setBusy(true);
    try {
      const form = new FormData();
      form.append("file", file);
      if (isPdf && password) form.append("password", password);
      const r = await api("/transactions/import", { method: "POST", form });
      setResult(r); setLocked(""); setPassword("");
      dataChanged();
    } catch (e) {
      if (e.status === 423) setLocked(e.message);
      else toast(e.message, { tone: "bad" });
    } finally { setBusy(false); }
  }
  async function sample() {
    const res = await fetch(apiUrl("/transactions/sample-csv"));
    const blob = await res.blob();
    const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: "finsight-sample.csv" });
    a.click(); URL.revokeObjectURL(a.href);
  }
  const breakdown = result ? Object.entries(result.breakdown).sort((a, b) => b[1] - a[1]) : [];
  const maxB = breakdown[0]?.[1] ?? 1;

  return (
    <Modal open={open} onClose={close} title="Import bank statement" subtitle="CSV, Excel or PDF. Bank headers, Dr/Cr markers, Nil values and amounts written in words are handled automatically." width={560}>
      <AnimatePresence mode="wait">
        {!result ? (
          <motion.div key="pick" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="space-y-4">
            <button type="button" onClick={() => input.current?.click()}
              onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
              onDrop={(e) => { e.preventDefault(); setDrag(false); pick(e.dataTransfer.files?.[0]); }}
              className={clsx("flex w-full flex-col items-center gap-3 rounded-2xl border-2 border-dashed px-6 py-10 text-center transition-colors",
                drag ? "border-accent bg-accent-soft" : "border-line hover:border-faint hover:bg-surface-2")}>
              <motion.span animate={{ y: drag ? -4 : 0 }} className="grid h-12 w-12 place-items-center rounded-2xl bg-surface-2 text-accent">
                {file ? <FileSpreadsheet size={22} /> : <FileUp size={22} />}
              </motion.span>
              {file ? (
                <span><span className="block font-semibold">{file.name}</span><span className="text-[13px] text-muted">{(file.size / 1024).toFixed(1)} KB · ready to import</span></span>
              ) : (
                <span><span className="block font-semibold">Drop your statement here</span><span className="text-[13px] text-muted">or click to choose a .csv, .xlsx, .xls or .pdf file (up to 5 MB)</span></span>
              )}
            </button>
            <input ref={input} type="file" accept=".csv,.xlsx,.xls,.xlsm,.pdf,application/pdf,text/csv,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" hidden onChange={(e) => pick(e.target.files?.[0])} />
            {isPdf && (
              <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} className="overflow-hidden">
                <label className="block">
                  <span className="mb-1.5 flex items-center gap-1.5 text-[13px] font-semibold text-muted"><Lock size={13} />PDF password {!locked && <span className="font-normal text-faint">(only if the statement is locked)</span>}</span>
                  <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="off"
                    onKeyDown={(e) => { if (e.key === "Enter" && file) upload(); }}
                    placeholder="Often your date of birth (DDMMYYYY) or customer ID"
                    className={clsx("h-10 w-full rounded-xl border bg-surface-2 px-3 text-sm text-text placeholder:text-faint focus:border-accent focus:outline-none", locked ? "border-accent" : "border-line")} />
                </label>
                {locked && <p className="mt-1.5 text-[12px] text-accent">{locked}</p>}
                <p className="mt-1.5 text-[12px] text-faint">Text-based e-statements work. Scanned paper statements can't be read.</p>
              </motion.div>
            )}
            <div className="flex flex-wrap items-center justify-between gap-2">
              <Button variant="ghost" size="sm" icon={Download} onClick={sample}>Download sample CSV</Button>
              <div className="flex gap-2">
                <Button variant="ghost" onClick={close}>Cancel</Button>
                <Button onClick={upload} disabled={!file} loading={busy}>Import and categorise</Button>
              </div>
            </div>
          </motion.div>
        ) : (
          <motion.div key="done" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="space-y-5">
            <div className="grid grid-cols-3 gap-3">
              {[["Imported", result.imported, "text-mint"], ["Duplicates skipped", result.duplicates, "text-muted"], ["Rows with errors", result.error_count, result.error_count ? "text-coral" : "text-muted"]].map(([l, v, c]) => (
                <div key={l} className="rounded-2xl bg-surface-2 p-3">
                  <CountUp value={v} className={clsx("display block text-3xl font-semibold", c)} />
                  <span className="text-[12px] text-muted">{l}</span>
                </div>
              ))}
            </div>
            {breakdown.length > 0 && (
              <div>
                <p className="mb-2 text-[13px] font-semibold text-muted">Sorted into categories in {result.elapsed_ms} ms</p>
                <div className="space-y-2">
                  {breakdown.map(([cat, n], i) => (
                    <div key={cat} className="flex items-center gap-3">
                      <CategoryIcon category={cat} size={26} />
                      <span className="w-28 text-sm">{cat}</span>
                      <span className="h-2 flex-1 overflow-hidden rounded-full bg-surface-2">
                        <motion.span className="block h-full rounded-full" style={{ background: catMeta(cat).color }}
                          initial={{ width: 0 }} animate={{ width: `${(n / maxB) * 100}%` }} transition={{ delay: 0.05 * i, duration: 0.6, ease: [0.16, 1, 0.3, 1] }} />
                      </span>
                      <span className="num w-8 text-right text-sm text-muted">{n}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {result.detected_columns && (
              <div className="rounded-2xl border border-line-soft p-3 text-[13px]">
                <p className="mb-2 font-semibold text-muted">
                  Read as {result.file_type}{result.header_row > 1 ? `, table found at row ${result.header_row}` : ""}
                  {result.amounts_from_words > 0 && <>, {result.amounts_from_words} amount{result.amounts_from_words > 1 ? "s" : ""} converted from words</>}
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {Object.entries(result.detected_columns).map(([k, v]) => (
                    <span key={k} className="rounded-lg bg-surface-2 px-2 py-1 text-[12px]"><span className="text-faint">{k}</span> ← <span className="font-semibold">{v}</span></span>
                  ))}
                </div>
              </div>
            )}
            {result.low_confidence > 0 && (
              <p className="flex gap-2 rounded-xl bg-accent-soft px-3 py-2 text-[13px] text-accent">
                <AlertTriangle size={16} className="mt-0.5 shrink-0" />
                {result.low_confidence} transaction{result.low_confidence > 1 ? "s were" : " was"} hard to categorise. Check them in the list and fix the category to improve the model.
              </p>
            )}
            {result.errors.length > 0 && (
              <details className="text-[13px] text-muted"><summary className="cursor-pointer">Show row errors</summary>
                <ul className="mt-2 list-disc pl-5">{result.errors.map((e) => <li key={e}>{e}</li>)}</ul>
              </details>
            )}
            <div className="flex justify-end gap-2">
              <Button variant="secondary" onClick={() => { setFile(null); setResult(null); }}>Import another</Button>
              <Button onClick={close}>Done</Button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </Modal>
  );
}
