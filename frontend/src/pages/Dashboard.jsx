import { Link } from "react-router-dom";
import { motion } from "motion/react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, Tooltip, XAxis, YAxis } from "recharts";
import { AlertOctagon, ArrowDownRight, ArrowUpRight, ChevronRight, Plus, Upload, Wand2 } from "lucide-react";
import clsx from "clsx";
import { useApi, useTokens } from "../lib/hooks";
import { Card, CardHeader, ChartTooltip, CountUp, Empty, ErrorState, PageHeader, Pill, Ring, Skeleton, Button } from "../components/ui";
import { ChartBox } from "../components/ui";
import { compact, dateLabel, money, monthLabel, monthName, pct } from "../lib/format";
import { CategoryIcon, catMeta } from "../lib/categories";
import { useAuth } from "../components/Auth";
import { useActions } from "../components/Layout";

export default function Dashboard() {
  const { data, error, loading, reload } = useApi("/dashboard");
  const { user } = useAuth();
  const actions = useActions();
  if (error) return <Card><ErrorState error={error} onRetry={reload} /></Card>;
  const first = user?.name?.split(" ")[0];
  if (!loading && data?.counts.transactions === 0) {
    return (<>
      <PageHeader title={`Hi ${first}`} subtitle="Your overview fills in once there are transactions to look at." />
      <Card><Empty icon={Wand2} title="Start with a bank statement" body="Import a CSV and every row gets categorised automatically. You can also add transactions one at a time."
        action={<div className="flex gap-2"><Button icon={Upload} onClick={actions.importCsv}>Import CSV</Button><Button variant="secondary" icon={Plus} onClick={actions.addTxn}>Add one</Button></div>} /></Card>
    </>);
  }
  return (
    <>
      <PageHeader title={data ? `${monthName(data.today.slice(0, 7))}, so far` : "Overview"}
        subtitle={`Hi ${first}. Here’s how the month is going and what the models noticed.`} />
      <div className="grid grid-cols-12 gap-4 lg:gap-5">
        <PaceHero data={data} className="col-span-12 xl:col-span-8" />
        <HealthCard health={data?.health} className="col-span-12 md:col-span-6 xl:col-span-4" />
        <StatTiles data={data} className="col-span-12 md:col-span-6 xl:col-span-12" />
        <CashflowCard data={data} className="col-span-12 lg:col-span-7" />
        <CategoryCard data={data} className="col-span-12 lg:col-span-5" />
        <RecentCard data={data} className="col-span-12 lg:col-span-7" />
        <AnomalyCard data={data} className="col-span-12 lg:col-span-5" />
      </div>
    </>
  );
}

function PaceHero({ data, className }) {
  const t = useTokens();
  if (!data) return <Card className={clsx("h-[380px] p-6", className)}><Skeleton className="h-8 w-2/3" /><Skeleton className="mt-6 h-4 w-full" /><Skeleton className="mt-8 h-48 w-full" /></Card>;
  const p = data.pace;
  const hasBudget = p.budget > 0;
  const used = hasBudget ? p.budget_progress : null;
  const gap = hasBudget ? Math.round((used - p.month_progress) * 100) : 0;
  const projPct = hasBudget ? Math.min(p.projected / p.budget, 1.25) : 0;
  const tone = !hasBudget ? "neutral" : gap > 8 ? "bad" : gap > 0 ? "warn" : "good";
  const toneColor = { bad: "var(--coral)", warn: "var(--accent)", good: "var(--mint)", neutral: "var(--sky)" }[tone];
  const headline = !hasBudget ? `${money(p.spent)} spent so far`
    : `${Math.round(used * 100)}% of your budget is gone, and ${Math.round(p.month_progress * 100)}% of the month`;
  const verdict = !hasBudget ? "Set budgets to see whether you're on pace."
    : gap > 0 ? `At this pace you'll finish near ${money(p.projected)}, which is ${money(p.projected - p.budget)} over your ${money(p.budget)} budget.`
      : `You're ${Math.abs(gap)} points behind the calendar. At this pace you'll finish near ${money(p.projected)}.`;

  return (
    <Card className={clsx("overflow-hidden", className)}>
      <div className="px-5 pt-5 sm:px-7 sm:pt-7">
        <div className="flex flex-wrap items-center gap-2">
          <Pill tone={tone}>{!hasBudget ? "No budgets yet" : gap > 8 ? "Spending too fast" : gap > 0 ? "Slightly ahead" : "On pace"}</Pill>
          <span className="num text-[13px] text-faint">Day {p.day} of {p.days}</span>
        </div>
        <h2 className="display mt-3 max-w-[30ch] text-[1.7rem] font-semibold leading-[1.1] sm:text-[2.1rem]">{headline}</h2>
        <p className="mt-2 max-w-[62ch] text-[14px] text-muted">{verdict}</p>

        {hasBudget && (
          <div className="mt-7" aria-label={`Budget used ${Math.round(used * 100)} percent, month elapsed ${Math.round(p.month_progress * 100)} percent`}>
            <div className="relative h-4 rounded-full bg-raised">
              <motion.div className="hatch absolute inset-y-0 left-0 rounded-full" style={{ color: toneColor }}
                initial={{ width: 0 }} animate={{ width: `${Math.min(projPct, 1) * 100}%` }} transition={{ delay: 0.4, duration: 1.4, ease: [0.16, 1, 0.3, 1] }} />
              <motion.div className="absolute inset-y-0 left-0 rounded-full" style={{ background: toneColor }}
                initial={{ width: 0 }} animate={{ width: `${Math.min(used, 1) * 100}%` }} transition={{ delay: 0.15, duration: 1.2, ease: [0.16, 1, 0.3, 1] }} />
              <motion.div className="absolute -top-2 bottom-[-8px] w-[3px] rounded-full bg-text" initial={{ left: "0%", opacity: 0 }}
                animate={{ left: `${p.month_progress * 100}%`, opacity: 1 }} transition={{ duration: 1, ease: [0.16, 1, 0.3, 1] }}>
                <span className="absolute -top-6 left-1/2 -translate-x-1/2 whitespace-nowrap text-[11px] font-semibold text-text">Today</span>
              </motion.div>
            </div>
            <div className="mt-2.5 flex flex-wrap justify-between gap-x-4 gap-y-1 text-[12px] text-muted">
              <span><span className="num font-semibold text-text">{money(p.spent)}</span> spent</span>
              <span className="flex items-center gap-1.5"><span className="hatch inline-block h-2.5 w-4 rounded-sm" style={{ color: toneColor }} />projected <span className="num font-semibold text-text">{money(p.projected)}</span></span>
              <span>budget <span className="num font-semibold text-text">{money(p.budget)}</span></span>
            </div>
          </div>
        )}
      </div>
      <div className="mt-4 h-[150px] sm:h-[170px]">
        <ChartBox>
          <AreaChart data={data.cumulative} margin={{ top: 10, right: 0, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="thisM" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor={t.accent} stopOpacity={0.35} /><stop offset="1" stopColor={t.accent} stopOpacity={0} /></linearGradient>
            </defs>
            <XAxis dataKey="day" hide />
            <YAxis hide domain={[0, "dataMax"]} />
            <Tooltip content={<ChartTooltip formatter={(v) => money(v)} labelFormatter={(l) => `Day ${l}`} />} />
            <Area type="monotone" dataKey="last" name="Last month" stroke={t.faint} strokeDasharray="4 4" fill="none" strokeWidth={1.5} dot={false} isAnimationActive={false} />
            <Area type="monotone" dataKey="this" name="This month" stroke={t.accent} fill="url(#thisM)" strokeWidth={2.5} dot={false} connectNulls={false} animationDuration={1200} />
          </AreaChart>
        </ChartBox>
      </div>
    </Card>
  );
}

function HealthCard({ health, className }) {
  const t = useTokens();
  if (!health) return <Card className={clsx("h-[380px] p-6", className)}><Skeleton className="mx-auto h-36 w-36 rounded-full" /><Skeleton className="mt-8 h-24" /></Card>;
  const color = health.score >= 70 ? t.mint : health.score >= 45 ? t.accent : t.coral;
  const word = health.score >= 70 ? "Healthy" : health.score >= 45 ? "Needs attention" : "At risk";
  return (
    <Card className={clsx("flex flex-col", className)}>
      <CardHeader title="Financial health" hint="Savings, budgets and how steady your spending is." />
      <div className="flex flex-1 flex-col items-center justify-center gap-6 px-6 pb-6 pt-4">
        <Ring value={health.score} size={148} stroke={12} color={color}>
          <div className="text-center">
            <CountUp value={health.score} className="display block text-[2.6rem] font-semibold leading-none" />
            <span className="text-[12px] font-semibold" style={{ color }}>{word}</span>
          </div>
        </Ring>
        <div className="w-full space-y-3">
          {health.parts.map((p, i) => (
            <div key={p.key}>
              <div className="mb-1 flex justify-between text-[13px]"><span className="text-muted">{p.label}</span><span className="num font-semibold">{p.points}<span className="text-faint">/{p.max}</span></span></div>
              <div className="h-1.5 overflow-hidden rounded-full bg-raised">
                <motion.div className="h-full rounded-full" style={{ background: color }} initial={{ width: 0 }}
                  animate={{ width: `${(p.points / p.max) * 100}%` }} transition={{ delay: 0.3 + i * 0.1, duration: 0.9, ease: [0.16, 1, 0.3, 1] }} />
              </div>
            </div>
          ))}
        </div>
      </div>
    </Card>
  );
}

function StatTiles({ data, className }) {
  const m = data?.month;
  const tiles = m ? [
    { label: "Income this month", value: m.income, color: "text-mint", note: m.prev_income ? `${money(m.prev_income)} last month` : "No income last month" },
    { label: "Spent this month", value: m.expense, color: "text-text", delta: m.expense_vs_same_day_last_month, note: "vs same day last month" },
    { label: "Saved so far", value: m.saved, color: m.saved >= 0 ? "text-text" : "text-coral", note: m.savings_rate !== null ? `${pct(m.savings_rate)} of income` : "Add income to see a rate" },
    { label: `Forecast for ${monthName(data.forecast.month)}`, value: data.forecast.total, color: "text-text", note: "Expected spend, Holt-Winters model" },
  ] : [];
  return (
    <div className={clsx("grid grid-cols-2 gap-4 lg:gap-5 xl:grid-cols-4", className)}>
      {!m && [0, 1, 2, 3].map((i) => <Card key={i} className="h-[118px] p-5"><Skeleton className="h-4 w-24" /><Skeleton className="mt-4 h-8 w-32" /></Card>)}
      {tiles.map((tile) => (
        <Card key={tile.label} className="p-4 sm:p-5">
          <p className="text-[13px] text-muted">{tile.label}</p>
          <CountUp value={tile.value} format={(v) => money(v)} className={clsx("display mt-1.5 block text-[1.55rem] font-semibold leading-tight sm:text-[1.9rem]", tile.color)} />
          <p className="mt-1 flex items-center gap-1 text-[12px] text-faint">
            {tile.delta !== undefined && tile.delta !== null && (
              <span className={clsx("inline-flex items-center font-semibold", tile.delta > 0 ? "text-coral" : "text-mint")}>
                {tile.delta > 0 ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}{Math.abs(tile.delta)}%
              </span>
            )}
            {tile.note}
          </p>
        </Card>
      ))}
    </div>
  );
}

function CashflowCard({ data, className }) {
  const t = useTokens();
  return (
    <Card className={className}>
      <CardHeader title="Money in and out" hint="Last six months" action={
        <div className="flex gap-3 text-[12px] text-muted"><span className="flex items-center gap-1.5"><i className="h-2 w-2 rounded-full bg-mint" />Income</span><span className="flex items-center gap-1.5"><i className="h-2 w-2 rounded-full bg-coral" />Spent</span></div>} />
      <div className="h-[260px] px-2 pb-4 pt-4">
        {!data ? <Skeleton className="mx-4 h-full" /> : (
          <ChartBox>
            <BarChart data={data.cashflow} barGap={4} margin={{ left: 0, right: 12 }}>
              <CartesianGrid vertical={false} stroke={t.linesoft} />
              <XAxis dataKey="month" tickFormatter={(v) => monthLabel(v)} axisLine={false} tickLine={false} />
              <YAxis tickFormatter={compact} axisLine={false} tickLine={false} width={52} />
              <Tooltip content={<ChartTooltip formatter={(v) => money(v)} labelFormatter={(l) => monthLabel(l, true)} />} />
              <Bar dataKey="income" name="Income" fill={t.mint} radius={[6, 6, 2, 2]} maxBarSize={26} />
              <Bar dataKey="expense" name="Spent" fill={t.coral} radius={[6, 6, 2, 2]} maxBarSize={26} />
            </BarChart>
          </ChartBox>
        )}
      </div>
    </Card>
  );
}

function CategoryCard({ data, className }) {
  const cats = data?.categories ?? [];
  const total = cats.reduce((s, c) => s + c.amount, 0);
  return (
    <Card className={className}>
      <CardHeader title="Where it went" hint="This month by category" />
      {!data ? <Skeleton className="m-6 h-52" /> : cats.length === 0 ? <Empty title="No spending yet this month" /> : (
        <div className="flex flex-col items-center gap-4 px-5 pb-5 pt-2 sm:flex-row sm:px-6">
          <div className="relative h-[190px] w-[190px] shrink-0">
            <ChartBox>
              <PieChart>
                <Pie data={cats} dataKey="amount" nameKey="category" innerRadius={62} outerRadius={90} paddingAngle={2} stroke="none" animationDuration={900}>
                  {cats.map((c) => <Cell key={c.category} fill={catMeta(c.category).color} />)}
                </Pie>
                <Tooltip content={<ChartTooltip formatter={(v) => money(v)} labelFormatter={(_, p) => p?.[0]?.name} />} />
              </PieChart>
            </ChartBox>
            <div className="pointer-events-none absolute inset-0 grid place-items-center text-center">
              <div><span className="num display block text-xl font-semibold">{compact(total)}</span><span className="text-[11px] text-faint">total</span></div>
            </div>
          </div>
          <ul className="w-full space-y-1.5">
            {cats.slice(0, 6).map((c) => (
              <li key={c.category}>
                <Link to={`/transactions?category=${encodeURIComponent(c.category)}`} className="flex items-center gap-2.5 rounded-lg px-1.5 py-1 text-[13px] hover:bg-surface-2">
                  <span className="h-2.5 w-2.5 rounded-full" style={{ background: catMeta(c.category).color }} />
                  <span className="flex-1">{c.category}</span>
                  <span className="num text-faint">{Math.round((c.amount / total) * 100)}%</span>
                  <span className="num w-[72px] text-right font-semibold">{money(c.amount)}</span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}

function TxnRow({ t }) {
  return (
    <li className="flex items-center gap-3 px-5 py-2.5 sm:px-6">
      <CategoryIcon category={t.category} />
      <div className="min-w-0 flex-1">
        <p className="truncate text-[14px] font-semibold">{t.description}</p>
        <p className="text-[12px] text-faint">{t.category} · {dateLabel(t.date)}</p>
      </div>
      <span className={clsx("num font-semibold", t.type === "income" ? "text-mint" : "text-text")}>{t.type === "income" ? "+" : "−"}{money(t.amount)}</span>
    </li>
  );
}

function RecentCard({ data, className }) {
  return (
    <Card className={className}>
      <CardHeader title="Recent activity" action={<Link to="/transactions" className="flex items-center gap-0.5 text-[13px] font-semibold text-accent hover:underline">All transactions<ChevronRight size={15} /></Link>} />
      {!data ? <div className="space-y-3 p-6">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-10" />)}</div> : (
        <ul className="py-3">{data.recent.map((t) => <TxnRow key={t.id} t={t} />)}</ul>
      )}
    </Card>
  );
}

function AnomalyCard({ data, className }) {
  const list = data?.anomalies ?? [];
  return (
    <Card className={className}>
      <CardHeader title="Unusual spends" hint="Isolation Forest flags payments that don’t match your usual pattern." />
      {!data ? <Skeleton className="m-6 h-40" /> : list.length === 0 ? (
        <Empty title="Nothing unusual" body="Spends that look out of character will show up here." />
      ) : (
        <ul className="space-y-2 px-5 pb-5 pt-3 sm:px-6">
          {list.map((t, i) => (
            <motion.li key={t.id} initial={{ opacity: 0, x: 8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.1 * i }}
              className="flex items-start gap-3 rounded-2xl border border-line-soft bg-surface-2 p-3">
              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-coral-soft text-coral"><AlertOctagon size={17} /></span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-[14px] font-semibold">{t.description}</p>
                <p className="text-[12px] text-coral">{t.anomaly_reason}</p>
              </div>
              <div className="text-right"><p className="num font-semibold">{money(t.amount)}</p><p className="text-[12px] text-faint">{dateLabel(t.date)}</p></div>
            </motion.li>
          ))}
          <Link to="/transactions?anomaly=1" className="block pt-1 text-center text-[13px] font-semibold text-accent hover:underline">Review flagged transactions</Link>
        </ul>
      )}
    </Card>
  );
}
