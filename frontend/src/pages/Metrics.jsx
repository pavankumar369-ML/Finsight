import { useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Line, LineChart, Tooltip, XAxis, YAxis, ReferenceLine } from "recharts";
import { BrainCircuit, CheckCircle2, Clock, Gauge, Pause, Play, RefreshCw, Rocket, XCircle, CircleDashed, Users, UserCheck, LogIn, UserPlus, Repeat2, Activity, ShieldCheck, Eye, Lock } from "lucide-react";
import clsx from "clsx";
import { api, dataChanged } from "../lib/api";
import { useApi, useTokens } from "../lib/hooks";
import { Button, Card, CardHeader, ChartTooltip, CountUp, ErrorState, PageHeader, Pill, Ring, Segmented, Skeleton } from "../components/ui";
import { ChartBox } from "../components/ui";
import { duration, ms } from "../lib/format";
import { catMeta } from "../lib/categories";
import { useToast } from "../components/Toast";
import { useAuth } from "../components/Auth";

const clock = (t) => new Date(t).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });

export default function Metrics() {
  const { user } = useAuth();
  const admin = !!user?.is_admin;
  const [paused, setPaused] = useState(false);
  const [windowS, setWindowS] = useState("300");
  const live = useApi(`/metrics/live?window=${windowS}`, { interval: 2000, paused });
  const models = useApi("/metrics/models", { interval: 10000, paused });
  const [load, setLoad] = useState(null);

  return (
    <>
      <PageHeader title="Metrics"
        subtitle="Measured from the running system: every API call is timed by middleware, and model scores come from held-out test data. The page refreshes every two seconds."
        actions={<>
          <span className={clsx("inline-flex h-10 items-center gap-2 rounded-xl border border-line-soft px-3 text-[13px] font-semibold", paused ? "text-faint" : "text-mint")}>
            <span className={clsx("relative h-2 w-2 rounded-full", paused ? "bg-faint" : "live-dot bg-mint")} />{paused ? "Paused" : "Live"}
          </span>
          {admin ? <Pill tone="warn" className="h-10 px-3"><ShieldCheck size={14} />Admin</Pill>
            : <Pill className="h-10 px-3" ><Eye size={14} />Read-only view</Pill>}
          <Button variant="secondary" icon={paused ? Play : Pause} onClick={() => setPaused((p) => !p)}>{paused ? "Resume" : "Pause"}</Button>
          {admin && <LoadTest onDone={(r) => { setLoad(r); live.reload(); }} />}
        </>} />

      <ReviewCard live={live.data} models={models.data} load={load} />

      {admin && <UsersSection paused={paused} />}

      <div className="mb-3 mt-9 flex flex-wrap items-end justify-between gap-3">
        <div><h2 className="display text-2xl font-semibold">API performance</h2><p className="text-[14px] text-muted">Every request except this page's own polling.</p></div>
        <Segmented value={windowS} onChange={setWindowS} options={[{ value: "300", label: "5 min" }, { value: "900", label: "15 min" }, { value: "3600", label: "1 hour" }]} />
      </div>
      {live.error ? <Card><ErrorState error={live.error} onRetry={live.reload} /></Card> : <ApiSection d={live.data} load={load} />}

      <div className="mb-3 mt-9"><h2 className="display text-2xl font-semibold">Models</h2><p className="text-[14px] text-muted">Categoriser quality, what it's unsure about, and the offline benchmarks behind the forecaster and anomaly detector.</p></div>
      {models.error ? <Card><ErrorState error={models.error} onRetry={models.reload} /></Card> : <ModelSection m={models.data} onRetrained={models.reload} admin={admin} />}
    </>
  );
}

/* ---------- document review card ---------- */
function ReviewCard({ live, models, load }) {
  const b = models?.benchmarks;
  const L = models?.latest;
  const dash = live?.dashboard_avg ?? load?.dashboardAvg ?? null;
  const modelsReady = models && live && models.ready && L && b?.forecast && b?.anomaly
  const rows = modelsReady ? [
    { name: "Categorisation accuracy", target: "≥ 90%", value: `${L.accuracy}%`, pass: L.accuracy >= 90, note: `${L.n_test} test samples` },
    { name: "Categorisation macro F1", target: "≥ 0.85", value: L.f1_macro.toFixed(3), pass: L.f1_macro >= 0.85 },
    { name: "Inference time per transaction", target: "< 50 ms", value: ms(models.inference_ms), pass: models.inference_ms < 50, note: "measured just now" },
    { name: "Forecast error (MAPE)", target: "≤ 20%", value: `${b.forecast.mape}%`, pass: b.forecast.mape <= 20, note: "4 held-out months" },
    { name: "Anomaly precision", target: "≥ 80%", value: `${b.anomaly.precision}%`, pass: b.anomaly.precision >= 80 },
    { name: "Anomaly recall", target: "≥ 75%", value: `${b.anomaly.recall}%`, pass: b.anomaly.recall >= 75 },
    { name: "CSV import, 500 rows", target: "< 3 s", value: ms(b.csv_500?.ms), pass: (b.csv_500?.ms ?? 1e9) < 3000 },
    { name: "Dashboard API response", target: "< 500 ms", value: dash !== null ? ms(dash) : "Open Overview", pass: dash === null ? null : dash < 500, note: dash !== null ? "live average" : "no calls in window yet" },
    (() => {
      const a = models.assistant;
      if (!a?.count) return { name: "AI assistant response", target: "< 5 s", value: "Ask it something", pass: null, note: "no replies measured yet" };
      return { name: "AI assistant response", target: "< 5 s", value: ms(a.avg_ms), pass: a.avg_ms < 5000,
        note: `${a.count} replies · local NLP, intent accuracy ${a.intent_accuracy}%` };
    })(),
  ] : null;
  const passed = rows?.filter((r) => r.pass).length;
  const measured = rows?.filter((r) => r.pass !== null).length;
  return (
    <Card className="overflow-hidden">
      <div className="flex flex-col gap-5 border-b border-line-soft p-5 sm:flex-row sm:items-center sm:p-6">
        <Ring value={passed ?? 0} max={measured || 1} size={84} stroke={8} color="var(--mint)">
          <span className="display num text-xl font-semibold">{rows ? `${passed}/${measured}` : "–"}</span>
        </Ring>
        <div className="flex-1">
          <h2 className="display text-[1.35rem] font-semibold">Results against the project document</h2>
          <p className="mt-1 max-w-[70ch] text-[14px] text-muted">Section 12 targets, checked against values this system is producing right now. Use this table in the review.</p>
        </div>
      </div>
      {!rows ? <div className="space-y-2 p-6">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-9" />)}</div> : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-[14px]">
            <thead><tr className="text-left text-[12px] text-faint"><th className="px-6 py-3 font-semibold">Parameter</th><th className="px-3 py-3 font-semibold">Target</th><th className="px-3 py-3 font-semibold">Measured</th><th className="px-6 py-3 text-right font-semibold">Status</th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.name} className="border-t border-line-soft">
                  <td className="px-6 py-3 font-semibold">{r.name}{r.note && <span className="ml-2 text-[12px] font-normal text-faint">{r.note}</span>}</td>
                  <td className="num px-3 py-3 text-muted">{r.target}</td>
                  <td className="num px-3 py-3 font-semibold"><motion.span key={r.value} initial={{ opacity: 0.3 }} animate={{ opacity: 1 }}>{r.value}</motion.span></td>
                  <td className="px-6 py-3 text-right">
                    {r.pass === null ? <Pill><CircleDashed size={12} />Pending</Pill> : r.pass ? <Pill tone="good"><CheckCircle2 size={12} />Meets target</Pill> : <Pill tone="bad"><XCircle size={12} />Below target</Pill>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

/* ---------- load test ---------- */
function LoadTest({ onDone }) {
  const toast = useToast();
  const [progress, setProgress] = useState(null);
  const running = progress !== null;
  async function run() {
    const targets = ["/dashboard", "/transactions?size=25", "/budgets", "/insights", "/meta"];
    const total = 60, conc = 6;
    const times = [], dash = [];
    let done = 0, failed = 0;
    setProgress(0);
    const one = async (i) => {
      const path = i % 7 === 6 ? null : targets[i % targets.length];
      const t0 = performance.now();
      try {
        if (path) await api(path);
        else await api("/categorize/suggest", { method: "POST", body: { description: "UPI/SWIGGY/VELLORE/12345" } });
        const dt = performance.now() - t0;
        times.push(dt);
        if (path === "/dashboard") dash.push(dt);
      } catch { failed++; }
      done++; setProgress(done / total);
    };
    for (let i = 0; i < total; i += conc) await Promise.all(Array.from({ length: Math.min(conc, total - i) }, (_, k) => one(i + k)));
    times.sort((a, b) => a - b);
    const r = {
      requests: total, failed, avg: times.reduce((s, v) => s + v, 0) / (times.length || 1),
      p95: times[Math.floor(times.length * 0.95)] ?? 0, dashboardAvg: dash.length ? dash.reduce((s, v) => s + v, 0) / dash.length : null,
    };
    setProgress(null);
    toast(`Load test done: ${total} requests, ${ms(r.avg)} average round trip${failed ? `, ${failed} failed` : ""}.`, { tone: failed ? "bad" : "good" });
    onDone(r);
  }
  return (
    <Button icon={Rocket} onClick={run} disabled={running} className="min-w-[152px] overflow-hidden">
      {running && <motion.span className="absolute inset-y-0 left-0 bg-black/15" animate={{ width: `${progress * 100}%` }} />}
      <span className="relative">{running ? `Running ${Math.round(progress * 100)}%` : "Run load test"}</span>
    </Button>
  );
}

/* ---------- API section ---------- */
function Kpi({ label, value, format, icon: Icon, tone, sub }) {
  return (
    <Card className="p-4 sm:p-5">
      <div className="flex items-center justify-between text-[13px] text-muted">{label}{Icon && <Icon size={15} className="text-faint" />}</div>
      <CountUp value={value ?? 0} format={format} duration={0.5} className={clsx("display mt-1.5 block text-[1.6rem] font-semibold leading-tight", tone)} />
      {sub && <p className="mt-0.5 text-[12px] text-faint">{sub}</p>}
    </Card>
  );
}

function ApiSection({ d, load }) {
  const t = useTokens();
  if (!d) return <div className="grid grid-cols-2 gap-4 lg:grid-cols-6">{[0, 1, 2, 3, 4, 5].map((i) => <Skeleton key={i} className="h-28 rounded-[20px]" />)}</div>;
  const series = d.series.map((s) => ({ ...s, rpm: (s.count / d.bucket_s) * 60 }));
  const maxP95 = Math.max(...(d.endpoints ?? []).map((e) => e.p95), 1);
  const totalStatus = Object.values(d.status).reduce((s, v) => s + v, 0) || 1;
  return (
    <div className="grid grid-cols-12 gap-4 lg:gap-5">
      <div className="col-span-12 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:gap-5 xl:grid-cols-6">
        <Kpi label="Median (p50)" value={d.p50} format={ms} icon={Gauge} />
        <Kpi label="p95 latency" value={d.p95} format={ms} tone={d.p95 > 500 ? "text-coral" : undefined} />
        <Kpi label="p99 latency" value={d.p99} format={ms} />
        <Kpi label="Requests / min" value={d.rpm} format={(v) => v.toFixed(1)} sub={`${d.requests} in window`} />
        <Kpi label="Server errors" value={d.error_rate} format={(v) => `${v.toFixed(1)}%`} tone={d.error_rate > 0 ? "text-coral" : "text-mint"} />
        <Kpi label="Uptime" value={d.uptime_s} format={(v) => duration(Math.round(v))} icon={Clock} sub={`${d.requests_all_time.toLocaleString("en-IN")} requests logged`} />
      </div>

      <Card className="col-span-12 xl:col-span-8">
        <CardHeader title="Latency" hint={`Server-side time per ${d.bucket_s}s bucket. Dashed line is the 500 ms target.`}
          action={load && <Pill tone="info">Last load test: {ms(load.avg)} avg, {ms(load.p95)} p95 round trip</Pill>} />
        <div className="h-[270px] px-2 pb-4 pt-4">
          <ChartBox>
            <AreaChart data={series} margin={{ right: 16 }}>
              <defs><linearGradient id="lat" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor={t.sky} stopOpacity={0.35} /><stop offset="1" stopColor={t.sky} stopOpacity={0} /></linearGradient></defs>
              <CartesianGrid vertical={false} stroke={t.linesoft} />
              <XAxis dataKey="t" tickFormatter={clock} axisLine={false} tickLine={false} minTickGap={60} />
              <YAxis tickFormatter={(v) => `${Math.round(v)}`} axisLine={false} tickLine={false} width={40} unit="" />
              <Tooltip content={<ChartTooltip formatter={(v) => ms(v)} labelFormatter={clock} />} />
              <ReferenceLine y={500} stroke={t.coral} strokeDasharray="4 4" strokeOpacity={0.6} ifOverflow="hidden" />
              <Area type="monotone" dataKey="p95" name="p95" stroke={t.violet} fill="none" strokeWidth={1.5} connectNulls isAnimationActive={false} dot={false} />
              <Area type="monotone" dataKey="avg" name="Average" stroke={t.sky} fill="url(#lat)" strokeWidth={2.5} connectNulls isAnimationActive={false} dot={false} />
            </AreaChart>
          </ChartBox>
        </div>
      </Card>

      <Card className="col-span-12 md:col-span-6 xl:col-span-4">
        <CardHeader title="Throughput" hint="Requests per minute" />
        <div className="h-[170px] px-2 pt-4">
          <ChartBox>
            <BarChart data={series}>
              <XAxis dataKey="t" hide /><YAxis hide />
              <Tooltip content={<ChartTooltip formatter={(v) => `${v.toFixed(0)} rpm`} labelFormatter={clock} />} />
              <Bar dataKey="rpm" name="Throughput" fill={t.accent} radius={[3, 3, 0, 0]} isAnimationActive={false} />
            </BarChart>
          </ChartBox>
        </div>
        <div className="px-5 pb-5 pt-3 sm:px-6">
          <p className="mb-2 text-[13px] text-muted">Status codes</p>
          <div className="flex h-2.5 overflow-hidden rounded-full bg-raised">
            {[["2xx", t.mint], ["3xx", t.sky], ["4xx", t.accent], ["5xx", t.coral]].map(([k, c]) => (
              <motion.span key={k} style={{ background: c }} animate={{ width: `${(d.status[k] / totalStatus) * 100}%` }} transition={{ duration: 0.5 }} />
            ))}
          </div>
          <div className="mt-2 flex flex-wrap gap-x-4 text-[12px] text-muted">
            {Object.entries(d.status).map(([k, v]) => <span key={k}><span className="num font-semibold text-text">{v}</span> {k}</span>)}
          </div>
        </div>
      </Card>

      {d.endpoints && <Card className="col-span-12 md:col-span-6 xl:col-span-12">
        <CardHeader title="Endpoints" hint="Busiest routes in the selected window" />
        {d.endpoints.length === 0 ? <p className="px-6 pb-6 pt-4 text-sm text-muted">No traffic yet. Browse the app or run the load test.</p> : (
          <div className="overflow-x-auto pb-3 pt-3">
            <table className="w-full min-w-[560px] text-[13px]">
              <thead><tr className="text-left text-[12px] text-faint"><th className="px-6 py-2 font-semibold">Route</th><th className="px-3 py-2 text-right font-semibold">Calls</th><th className="px-3 py-2 text-right font-semibold">Avg</th><th className="w-[34%] px-6 py-2 font-semibold">p95</th></tr></thead>
              <tbody>
                <AnimatePresence initial={false}>
                  {d.endpoints.map((e) => (
                    <motion.tr key={e.endpoint} layout initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="border-t border-line-soft">
                      <td className="px-6 py-2.5"><code className="text-[12px]"><span className="mr-2 font-semibold text-accent">{e.endpoint.split(" ")[0]}</span>{e.endpoint.split(" ")[1]}</code>{e.errors > 0 && <Pill tone="bad" className="ml-2">{e.errors} err</Pill>}</td>
                      <td className="num px-3 py-2.5 text-right">{e.count}</td>
                      <td className="num px-3 py-2.5 text-right text-muted">{ms(e.avg)}</td>
                      <td className="px-6 py-2.5">
                        <div className="flex items-center gap-3">
                          <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-raised">
                            <motion.div className="h-full rounded-full" style={{ background: e.p95 > 500 ? t.coral : t.sky }} animate={{ width: `${(e.p95 / maxP95) * 100}%` }} transition={{ duration: 0.5 }} />
                          </div>
                          <span className="num w-16 text-right">{ms(e.p95)}</span>
                        </div>
                      </td>
                    </motion.tr>
                  ))}
                </AnimatePresence>
              </tbody>
            </table>
          </div>
        )}
      </Card>}
    </div>
  );
}

/* ---------- Models section ---------- */
function ModelSection({ m, onRetrained, admin }) {
  const t = useTokens();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [hover, setHover] = useState(null);
  if (!m || !m.ready || !m.latest || !m.benchmarks?.forecast) {
    return (
      <Card className="p-10 text-center">
        <p className="display text-lg font-semibold">Warming up the models…</p>
        <p className="mx-auto mt-1.5 max-w-sm text-[13px] text-muted">
          FinSight trains its ML models and the assistant right after starting. This normally takes a few seconds
          {m && !m.ready ? " on a cold server it can take longer" : ""} — this refreshes automatically.
        </p>
        <div className="mx-auto mt-6 grid max-w-2xl gap-4 lg:grid-cols-2">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-56 rounded-[20px]" />)}</div>
      </Card>
    );
  }
  const L = m.latest;
  const labels = L.labels;
  const perClass = labels.map((c, i) => ({ category: c, f1: +(L.per_class_f1[i] * 100).toFixed(1) })).sort((a, b) => a.f1 - b.f1);
  const maxCell = Math.max(...L.confusion.flat().filter((_, k) => k % (labels.length + 1) !== 0), 1);
  const history = m.history.map((h, i) => ({ run: i + 1, accuracy: h.accuracy, f1: +(h.f1_macro * 100).toFixed(2), trigger: h.trigger, corrections: h.n_corrections }));

  async function retrain() {
    setBusy(true);
    try {
      const r = await api("/metrics/retrain", { method: "POST" });
      const delta = (r.accuracy - L.accuracy).toFixed(2);
      toast(`Retrained with ${r.n_corrections} corrections in ${Math.round(r.train_ms)} ms. Accuracy ${r.accuracy}% (${delta >= 0 ? "+" : ""}${delta}).`);
      onRetrained(); dataChanged();
    } catch (e) { toast(e.message, { tone: "bad" }); } finally { setBusy(false); }
  }

  return (
    <div className="grid grid-cols-12 gap-4 lg:gap-5">
      <Card className="col-span-12 lg:col-span-5">
        <CardHeader title="Transaction categoriser" hint="TF-IDF character n-grams with logistic regression" action={<Pill tone="info"><BrainCircuit size={12} />{L.trigger === "startup" ? "Trained at startup" : "Retrained"}</Pill>} />
        <div className="flex flex-wrap items-center justify-around gap-6 px-6 py-6">
          <Ring value={L.accuracy} size={132} stroke={11} color={t.mint}>
            <div className="text-center"><CountUp value={L.accuracy} format={(v) => `${v.toFixed(1)}%`} className="display block text-2xl font-semibold" /><span className="text-[12px] text-muted">accuracy</span></div>
          </Ring>
          <Ring value={L.f1_macro * 100} size={132} stroke={11} color={t.accent}>
            <div className="text-center"><CountUp value={L.f1_macro} format={(v) => v.toFixed(3)} className="display block text-2xl font-semibold" /><span className="text-[12px] text-muted">macro F1</span></div>
          </Ring>
        </div>
        <dl className="grid grid-cols-2 gap-px border-t border-line-soft bg-line-soft text-[13px] sm:grid-cols-4">
          {[["Train rows", L.n_train.toLocaleString("en-IN")], ["Test rows", L.n_test], ["Train time", ms(L.train_ms)], ["Per prediction", ms(m.inference_ms)]].map(([k, v]) => (
            <div key={k} className="bg-surface px-4 py-3"><dt className="text-faint">{k}</dt><dd className="num mt-0.5 font-semibold">{v}</dd></div>
          ))}
        </dl>
        <div className="flex flex-col gap-3 border-t border-line-soft p-5 sm:flex-row sm:items-center sm:px-6">
          <p className="flex-1 text-[13px] text-muted"><span className="num font-semibold text-text">{m.pending_corrections}</span> trusted category corrections (demo account excluded, max 50 per user). Retraining weights them into the training set.</p>
          {admin ? <Button variant="secondary" icon={RefreshCw} loading={busy} onClick={retrain}>Retrain now</Button>
            : <span className="flex items-center gap-1.5 text-[12px] text-faint"><Lock size={13} />Retraining is admin-only</span>}
        </div>
      </Card>

      <Card className="col-span-12 lg:col-span-7">
        <CardHeader title="Confusion matrix" hint="Rows are true categories, columns are predictions. Off-diagonal cells are mistakes." />
        <div className="overflow-x-auto px-5 pb-5 pt-4 sm:px-6">
          <div className="min-w-[520px]">
            <div className="grid gap-[3px]" style={{ gridTemplateColumns: `92px repeat(${labels.length}, minmax(0,1fr))` }} onMouseLeave={() => setHover(null)}>
              <span />
              {labels.map((c, j) => <span key={c} className={clsx("truncate pb-1 text-center text-[10px] font-semibold", hover?.[1] === j ? "text-text" : "text-faint")} title={c}>{c.slice(0, 4)}</span>)}
              {L.confusion.map((row, i) => (
                <FragmentRow key={labels[i]}>
                  <span className={clsx("truncate pr-2 text-right text-[11px] font-semibold leading-[26px]", hover?.[0] === i ? "text-text" : "text-muted")}>{labels[i]}</span>
                  {row.map((v, j) => {
                    const diag = i === j;
                    const rowSum = row.reduce((s, x) => s + x, 0) || 1;
                    const alpha = diag ? 0.25 + 0.75 * (v / rowSum) : Math.min(v / maxCell, 1);
                    return (
                      <div key={j} onMouseEnter={() => setHover([i, j])}
                        title={`${labels[i]} predicted as ${labels[j]}: ${v}`}
                        className={clsx("num grid h-[26px] place-items-center rounded-[5px] text-[10px] font-semibold transition-transform", hover?.[0] === i && hover?.[1] === j && "scale-110 ring-1 ring-text")}
                        style={{ background: v === 0 ? "var(--surface-2)" : diag ? `color-mix(in srgb, ${t.mint} ${alpha * 100}%, transparent)` : `color-mix(in srgb, ${t.coral} ${25 + alpha * 75}%, transparent)`,
                          color: v === 0 ? "var(--faint)" : "var(--text)" }}>
                        {v || ""}
                      </div>
                    );
                  })}
                </FragmentRow>
              ))}
            </div>
          </div>
        </div>
      </Card>

      <Card className="col-span-12 md:col-span-6 xl:col-span-4">
        <CardHeader title="F1 by category" hint="Weakest categories first" />
        <div className="space-y-2 px-5 pb-5 pt-4 sm:px-6">
          {perClass.map((c, i) => (
            <div key={c.category} className="flex items-center gap-3 text-[13px]">
              <span className="w-24 truncate">{c.category}</span>
              <div className="h-2 flex-1 overflow-hidden rounded-full bg-raised">
                <motion.div className="h-full rounded-full" style={{ background: catMeta(c.category).color }} initial={{ width: 0 }} animate={{ width: `${c.f1}%` }} transition={{ delay: i * 0.03, duration: 0.7 }} />
              </div>
              <span className="num w-11 text-right font-semibold">{c.f1}</span>
            </div>
          ))}
        </div>
      </Card>

      <Card className="col-span-12 md:col-span-6 xl:col-span-4">
        <CardHeader title="Prediction confidence" hint={`Your transactions · average ${m.avg_confidence ?? "—"}%`} />
        <div className="h-[260px] px-2 pb-4 pt-4">
          <ChartBox>
            <BarChart data={m.confidence_histogram} margin={{ right: 12 }}>
              <CartesianGrid vertical={false} stroke={t.linesoft} />
              <XAxis dataKey="bucket" axisLine={false} tickLine={false} interval={1} tick={{ fontSize: 10 }} />
              <YAxis axisLine={false} tickLine={false} width={34} allowDecimals={false} />
              <Tooltip content={<ChartTooltip formatter={(v) => `${v} transactions`} />} />
              <Bar dataKey="count" name="Transactions" radius={[4, 4, 0, 0]}>
                {m.confidence_histogram.map((_, i) => <Cell key={i} fill={i < 6 ? t.coral : i < 8 ? t.accent : t.mint} />)}
              </Bar>
            </BarChart>
          </ChartBox>
        </div>
      </Card>

      <Card className="col-span-12 xl:col-span-4">
        <CardHeader title="Training runs" hint="Accuracy and F1 across retrains" />
        <div className="h-[260px] px-2 pb-4 pt-4">
          <ChartBox>
            <LineChart data={history} margin={{ right: 16 }}>
              <CartesianGrid vertical={false} stroke={t.linesoft} />
              <XAxis dataKey="run" axisLine={false} tickLine={false} tickFormatter={(v) => `#${v}`} />
              <YAxis domain={["dataMin - 1", "dataMax + 1"]} axisLine={false} tickLine={false} width={40} tickFormatter={(v) => v.toFixed(0)} />
              <Tooltip content={<ChartTooltip formatter={(v) => `${v}%`} labelFormatter={(l, p) => `Run #${l} · ${p?.[0]?.payload.trigger} · ${p?.[0]?.payload.corrections} corrections`} />} />
              <Line dataKey="accuracy" name="Accuracy" stroke={t.mint} strokeWidth={2.5} dot={{ r: 3 }} type="monotone" />
              <Line dataKey="f1" name="Macro F1 ×100" stroke={t.accent} strokeWidth={2} dot={{ r: 3 }} type="monotone" />
            </LineChart>
          </ChartBox>
        </div>
      </Card>

      <Card className="col-span-12 lg:col-span-7">
        <CardHeader title="Forecaster benchmark" hint={`Holt-Winters trained on ${m.benchmarks.forecast.months - m.benchmarks.forecast.held_out} months, tested on the last ${m.benchmarks.forecast.held_out}.`}
          action={<Pill tone="good">MAPE {m.benchmarks.forecast.mape}%</Pill>} />
        <div className="h-[240px] px-2 pb-4 pt-4">
          <ChartBox>
            <LineChart data={m.benchmarks.forecast.labels.map((l, i) => ({ month: l, actual: m.benchmarks.forecast.actual[i], predicted: m.benchmarks.forecast.predicted[i] }))} margin={{ right: 20 }}>
              <CartesianGrid vertical={false} stroke={t.linesoft} />
              <XAxis dataKey="month" axisLine={false} tickLine={false} />
              <YAxis axisLine={false} tickLine={false} width={50} domain={["dataMin - 500", "dataMax + 500"]} tickFormatter={(v) => `₹${(v / 1000).toFixed(1)}k`} />
              <Tooltip content={<ChartTooltip formatter={(v) => `₹${v.toLocaleString("en-IN")}`} />} />
              <Line dataKey="actual" name="Actual" stroke={t.text} strokeWidth={2.5} dot={{ r: 4 }} />
              <Line dataKey="predicted" name="Predicted" stroke={t.accent} strokeWidth={2.5} strokeDasharray="6 4" dot={{ r: 4 }} />
            </LineChart>
          </ChartBox>
        </div>
        <p className="border-t border-line-soft px-6 py-3 text-[12px] text-faint">On your own data (6 months, no seasonality yet) the backtest error is {m.user.forecast_backtest_mape ?? "not available"}{m.user.forecast_backtest_mape ? "%" : ""}. It drops as more months are imported.</p>
      </Card>

      <Card className="col-span-12 lg:col-span-5">
        <CardHeader title="Anomaly detector benchmark" hint={`Isolation Forest on ${m.benchmarks.anomaly.samples} transactions with ${m.benchmarks.anomaly.injected} planted anomalies.`} />
        <div className="flex flex-wrap items-center justify-around gap-6 px-6 py-7">
          <Ring value={m.benchmarks.anomaly.precision} size={124} stroke={10} color={t.sky}>
            <div className="text-center"><span className="display num block text-2xl font-semibold">{m.benchmarks.anomaly.precision}%</span><span className="text-[12px] text-muted">precision</span></div>
          </Ring>
          <Ring value={m.benchmarks.anomaly.recall} size={124} stroke={10} color={t.violet}>
            <div className="text-center"><span className="display num block text-2xl font-semibold">{m.benchmarks.anomaly.recall}%</span><span className="text-[12px] text-muted">recall</span></div>
          </Ring>
        </div>
        <p className="border-t border-line-soft px-6 py-3 text-[12px] text-faint">Precision: of the flagged spends, how many were really planted anomalies. Recall: of the planted ones, how many were caught. Currently flagging {m.user.anomalies} of your {m.user.transactions} transactions.</p>
      </Card>
    </div>
  );
}

function FragmentRow({ children }) { return <>{children}</>; }


/* ---------- users ---------- */
function UsersSection({ paused }) {
  const t = useTokens();
  const { data: u, error, reload } = useApi("/metrics/users", { interval: 5000, paused });
  const day = (iso) => new Date(iso + "T00:00:00").toLocaleDateString("en-IN", { day: "numeric", month: "short" });
  return (
    <>
      <div className="mb-3 mt-9"><h2 className="display text-2xl font-semibold">Users</h2>
        <p className="text-[14px] text-muted">Who is using FinSight. Counts only; no one's personal details are shown.</p></div>
      {error ? <Card><ErrorState error={error} onRetry={reload} /></Card> : !u ? (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">{[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-28 rounded-[20px]" />)}</div>
      ) : (
        <div className="grid grid-cols-12 gap-4 lg:gap-5">
          <div className="col-span-12 grid grid-cols-2 gap-4 sm:grid-cols-4 lg:gap-5">
            <Card className="p-4 sm:p-5">
              <div className="flex items-center justify-between text-[13px] text-muted">Active now
                <span className="relative flex h-2 w-2"><span className={clsx("relative h-2 w-2 rounded-full bg-mint", !paused && "live-dot")} /></span></div>
              <CountUp value={u.active_now} duration={0.5} className="display mt-1.5 block text-[1.6rem] font-semibold leading-tight text-mint" />
              <p className="mt-0.5 text-[12px] text-faint">seen in the last {u.active_window_minutes} min</p>
            </Card>
            <Kpi label="Registered users" value={u.registered_users} format={(v) => Math.round(v).toLocaleString("en-IN")} icon={Users} sub={`${u.new_today} new today · demo excluded`} />
            <Kpi label="Activated users" value={u.activated_users} format={(v) => Math.round(v).toLocaleString("en-IN")} icon={UserCheck} sub="imported or added data" />
            <Kpi label="Returning users" value={u.returning_users} format={(v) => Math.round(v).toLocaleString("en-IN")} icon={Repeat2} sub="came back on another day" />
            <Kpi label="Active today" value={u.active_today} format={(v) => Math.round(v).toLocaleString("en-IN")} icon={Activity} sub={`${u.active_7d} in the last 7 days`} />
            <Kpi label="Sign-ins, all time" value={u.total_logins} format={(v) => Math.round(v).toLocaleString("en-IN")} icon={LogIn} sub={`${u.demo_sessions} were demo sessions`} />
            <Kpi label="Sign-ins today" value={u.logins_today} format={(v) => Math.round(v).toLocaleString("en-IN")} icon={UserPlus} />
          </div>
          <Card className="col-span-12">
            <CardHeader title="Sign-ins and new accounts" hint="Last 14 days"
              action={<div className="flex gap-3 text-[12px] text-muted"><span className="flex items-center gap-1.5"><i className="h-2 w-2 rounded-full bg-sky" />Sign-ins</span><span className="flex items-center gap-1.5"><i className="h-2 w-2 rounded-full bg-accent" />New accounts</span></div>} />
            <div className="h-[220px] px-2 pb-4 pt-4">
              <ChartBox>
                <BarChart data={u.series} margin={{ right: 16 }} barGap={3}>
                  <CartesianGrid vertical={false} stroke={t.linesoft} />
                  <XAxis dataKey="day" tickFormatter={day} axisLine={false} tickLine={false} minTickGap={16} />
                  <YAxis allowDecimals={false} axisLine={false} tickLine={false} width={34} />
                  <Tooltip content={<ChartTooltip labelFormatter={day} />} />
                  <Bar dataKey="logins" name="Sign-ins" fill={t.sky} radius={[5, 5, 1, 1]} maxBarSize={22} />
                  <Bar dataKey="signups" name="New accounts" fill={t.accent} radius={[5, 5, 1, 1]} maxBarSize={22} />
                </BarChart>
              </ChartBox>
            </div>
          </Card>
        </div>
      )}
    </>
  );
}
