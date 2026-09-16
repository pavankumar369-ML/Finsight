import { useState } from "react";
import { motion } from "motion/react";
import { Bar, BarChart, CartesianGrid, Line, LineChart, Tooltip, XAxis, YAxis } from "recharts";
import { AlertOctagon, AlertTriangle, CheckCircle2, TrendingUp } from "lucide-react";
import clsx from "clsx";
import { useApi, useTokens } from "../lib/hooks";
import { Card, CardHeader, ChartTooltip, CountUp, Empty, ErrorState, PageHeader, Pill, Skeleton } from "../components/ui";
import { ChartBox } from "../components/ui";
import { CategoryIcon, catMeta } from "../lib/categories";
import { compact, dateLabel, money, monthLabel, monthName } from "../lib/format";

export default function Insights() {
  const { data, error, reload } = useApi("/insights");
  if (error) return <Card><ErrorState error={error} onRetry={reload} /></Card>;
  const fc = data?.forecast;
  const enough = fc && fc.history.length >= 1;
  return (
    <>
      <PageHeader title="Insights" subtitle="What the forecasting and anomaly models see in your history, and what to do about it." />
      {data && !enough ? (
        <Card><Empty icon={TrendingUp} title="Insights need at least one full month" body="Forecasts use completed months. Import older statements to see them now." /></Card>
      ) : (
        <div className="grid grid-cols-12 gap-4 lg:gap-5">
          <ForecastCard fc={fc} className="col-span-12 xl:col-span-7" />
          <TipsCard tips={data?.tips} className="col-span-12 xl:col-span-5" />
          <TrendCard hist={data?.category_history} className="col-span-12 lg:col-span-7" />
          <RuleCard rule={data?.rule_50_30_20} className="col-span-12 lg:col-span-5" />
          <AnomalyList list={data?.anomalies} className="col-span-12" />
        </div>
      )}
    </>
  );
}

function ForecastCard({ fc, className }) {
  const t = useTokens();
  if (!fc) return <Card className={clsx("h-[420px] p-6", className)}><Skeleton className="h-10 w-1/2" /><Skeleton className="mt-6 h-72" /></Card>;
  const rows = fc.categories.slice(0, 8).map((c) => ({ ...c, change: c.last ? ((c.forecast - c.last) / c.last) * 100 : null }));
  const last = fc.history.at(-1)?.total ?? 0;
  const diff = last ? ((fc.total - last) / last) * 100 : 0;
  return (
    <Card className={className}>
      <CardHeader title={`${monthName(fc.month)} forecast`} hint="Holt-Winters exponential smoothing per category. Unusual spends are left out so one-offs don't skew it."
        action={fc.backtest_mape !== null && <Pill tone="info" className="whitespace-nowrap">Backtest error {fc.backtest_mape}%</Pill>} />
      <div className="px-5 pt-4 sm:px-6">
        <p className="display text-[2.4rem] font-semibold leading-none"><CountUp value={fc.total} format={money} /></p>
        <p className="mt-1.5 text-[13px] text-muted">
          expected spend, <span className={clsx("font-semibold", diff > 0 ? "text-coral" : "text-mint")}>{diff > 0 ? "up" : "down"} {Math.abs(diff).toFixed(1)}%</span> from {monthName(fc.history.at(-1)?.month)}
        </p>
      </div>
      <div className="h-[280px] px-2 pb-4 pt-2">
        <ChartBox>
          <BarChart data={rows} layout="vertical" margin={{ left: 8, right: 20, top: 8 }} barGap={2}>
            <CartesianGrid horizontal={false} stroke={t.linesoft} />
            <XAxis type="number" tickFormatter={compact} axisLine={false} tickLine={false} />
            <YAxis type="category" dataKey="category" width={96} axisLine={false} tickLine={false} tick={{ fill: t.muted, fontSize: 12 }} />
            <Tooltip content={<ChartTooltip formatter={(v) => money(v)} />} />
            <Bar dataKey="last" name={`${monthName(fc.history.at(-1)?.month)} actual`} fill={t.raised} radius={[0, 4, 4, 0]} maxBarSize={10} />
            <Bar dataKey="forecast" name="Forecast" fill={t.accent} radius={[0, 4, 4, 0]} maxBarSize={10} />
          </BarChart>
        </ChartBox>
      </div>
    </Card>
  );
}

function TipsCard({ tips, className }) {
  const icon = { warn: AlertTriangle, info: TrendingUp, good: CheckCircle2 };
  const color = { warn: "text-accent bg-accent-soft", info: "text-sky bg-surface-2", good: "text-mint bg-mint-soft" };
  return (
    <Card className={className}>
      <CardHeader title="Worth doing" hint="Generated from your forecast, budgets and the 50/30/20 rule." />
      {!tips ? <div className="space-y-3 p-6">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-16" />)}</div> : tips.length === 0 ? <Empty title="Nothing needs attention" /> : (
        <ul className="space-y-2.5 px-5 pb-5 pt-4 sm:px-6">
          {tips.map((tip, i) => {
            const Icon = icon[tip.tone];
            return (
              <motion.li key={tip.title} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.06 }} className="flex gap-3 rounded-2xl border border-line-soft p-3">
                <span className={clsx("grid h-9 w-9 shrink-0 place-items-center rounded-xl", color[tip.tone])}><Icon size={17} /></span>
                <div><p className="text-[14px] font-semibold leading-snug">{tip.title}</p><p className="mt-0.5 text-[13px] text-muted">{tip.body}</p></div>
              </motion.li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}

function TrendCard({ hist, className }) {
  const t = useTokens();
  const cats = hist ? Object.entries(hist.series).sort((a, b) => b[1].reduce((s, v) => s + v, 0) - a[1].reduce((s, v) => s + v, 0)).map(([c]) => c) : [];
  const [sel, setSel] = useState(null);
  const active = sel ?? cats.filter((c) => c !== "Rent").slice(0, 3);
  const rows = hist?.months.map((m, i) => ({ month: m, ...Object.fromEntries(active.map((c) => [c, hist.series[c]?.[i] ?? 0])) })) ?? [];
  const toggle = (c) => setSel((s) => { const cur = s ?? active; return cur.includes(c) ? cur.filter((x) => x !== c) : [...cur, c].slice(-5); });
  return (
    <Card className={className}>
      <CardHeader title="Category trends" hint="Monthly spend over completed months. Pick up to five categories." />
      <div className="flex flex-wrap gap-1.5 px-5 pt-4 sm:px-6">
        {cats.map((c) => {
          const on = active.includes(c);
          return (
            <button key={c} onClick={() => toggle(c)} aria-pressed={on}
              className={clsx("inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[12px] font-semibold transition-colors", on ? "border-transparent text-text" : "border-line-soft text-faint hover:text-muted")}
              style={on ? { background: `${catMeta(c).color}26` } : undefined}>
              <span className="h-2 w-2 rounded-full" style={{ background: on ? catMeta(c).color : "var(--line)" }} />{c}
            </button>
          );
        })}
      </div>
      <div className="h-[260px] px-2 pb-4 pt-4">
        {!hist ? <Skeleton className="mx-4 h-full" /> : (
          <ChartBox>
            <LineChart data={rows} margin={{ right: 16, left: 0 }}>
              <CartesianGrid vertical={false} stroke={t.linesoft} />
              <XAxis dataKey="month" tickFormatter={(v) => monthLabel(v)} axisLine={false} tickLine={false} />
              <YAxis tickFormatter={compact} axisLine={false} tickLine={false} width={50} />
              <Tooltip content={<ChartTooltip formatter={(v) => money(v)} labelFormatter={(l) => monthLabel(l, true)} />} />
              {active.map((c) => <Line key={c} dataKey={c} name={c} stroke={catMeta(c).color} strokeWidth={2.5} dot={{ r: 3, strokeWidth: 0, fill: catMeta(c).color }} activeDot={{ r: 5 }} type="monotone" animationDuration={700} />)}
            </LineChart>
          </ChartBox>
        )}
      </div>
    </Card>
  );
}

function RuleCard({ rule, className }) {
  if (!rule) return <Card className={clsx("h-[340px] p-6", className)}><Skeleton className="h-full" /></Card>;
  const rows = [
    { key: "needs", label: "Needs", sub: "rent, bills, groceries, travel", ideal: 50, color: "var(--sky)" },
    { key: "wants", label: "Wants", sub: "food out, shopping, fun, transfers", ideal: 30, color: "var(--violet)" },
    { key: "savings", label: "Savings", sub: "what's left", ideal: 20, color: "var(--mint)" },
  ];
  return (
    <Card className={className}>
      <CardHeader title="50 / 30 / 20 check" hint={`Average of the last three months on ${money(rule.income)} income.`} />
      <div className="space-y-5 px-5 pb-6 pt-5 sm:px-6">
        {rows.map((r, i) => {
          const actual = rule.income ? (rule.actual[r.key] / rule.income) * 100 : 0;
          const good = r.key === "savings" ? actual >= r.ideal : actual <= r.ideal;
          return (
            <div key={r.key}>
              <div className="flex items-baseline justify-between">
                <p className="text-[14px] font-semibold">{r.label} <span className="font-normal text-faint">· {r.sub}</span></p>
                <p className="num text-[13px]"><span className={clsx("font-semibold", good ? "text-mint" : "text-coral")}>{actual.toFixed(0)}%</span><span className="text-faint"> / {r.ideal}%</span></p>
              </div>
              <div className="relative mt-2 h-3 rounded-full bg-raised">
                <motion.div className="absolute inset-y-0 left-0 rounded-full" style={{ background: r.color }} initial={{ width: 0 }}
                  animate={{ width: `${Math.max(0, Math.min(actual, 100))}%` }} transition={{ delay: i * 0.1, duration: 0.9, ease: [0.16, 1, 0.3, 1] }} />
                <div className="absolute -top-1 bottom-[-4px] w-0.5 rounded bg-text" style={{ left: `${r.ideal}%` }} title={`Target ${r.ideal}%`} />
              </div>
              <p className="num mt-1 text-[12px] text-faint">{money(rule.actual[r.key])} a month · target {money(rule.ideal[r.key])}</p>
            </div>
          );
        })}
      </div>
    </Card>
  );
}

function AnomalyList({ list, className }) {
  return (
    <Card className={className}>
      <CardHeader title="Flagged as unusual" hint="Isolation Forest over amount, category, weekday and size relative to your typical spend in that category." />
      {!list ? <Skeleton className="m-6 h-24" /> : list.length === 0 ? <Empty title="No unusual transactions" /> : (
        <div className="grid gap-3 px-5 pb-5 pt-4 sm:grid-cols-2 sm:px-6 xl:grid-cols-3">
          {list.map((t) => (
            <div key={t.id} className="flex items-center gap-3 rounded-2xl border border-line-soft bg-surface-2 p-3">
              <div className="relative"><CategoryIcon category={t.category} size={40} /><AlertOctagon size={14} className="absolute -right-1 -top-1 rounded-full bg-surface text-coral" /></div>
              <div className="min-w-0 flex-1"><p className="truncate text-[14px] font-semibold">{t.description}</p><p className="text-[12px] text-coral">{t.anomaly_reason}</p></div>
              <div className="text-right"><p className="num font-semibold">{money(t.amount)}</p><p className="text-[12px] text-faint">{dateLabel(t.date)}</p></div>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
