import { useMemo, useState } from "react";
import { motion } from "motion/react";
import { Bar, BarChart, CartesianGrid, Cell, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from "recharts";
import { BrainCircuit, FlaskConical, Minus, TrendingDown, TrendingUp } from "lucide-react";
import clsx from "clsx";
import { useApi, useTokens } from "../lib/hooks";
import { Card, CardHeader, ChartBox, ChartTooltip, CountUp, Pill, Skeleton } from "./ui";
import { catMeta } from "../lib/categories";
import { compact, money } from "../lib/format";

const SEG_COLORS = ["var(--sky)", "var(--mint)", "var(--violet)", "var(--coral)"];

export default function MLInsights() {
  const { data } = useApi("/ml-insights");
  if (data && !data.segments && !data.what_if) return null;
  return (
    <section className="mt-10">
      <div className="mb-4 flex items-start gap-3">
        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-accent-soft text-accent"><BrainCircuit size={20} /></span>
        <div>
          <h2 className="display text-2xl font-semibold">Machine learning insights</h2>
          <p className="max-w-[70ch] text-[14px] text-muted">Patterns found with K-Means clustering, linear regression with significance tests, and variance decomposition on your own transactions.</p>
        </div>
      </div>
      <div className="grid grid-cols-12 gap-4 lg:gap-5">
        <Segments seg={data?.segments} className="col-span-12 xl:col-span-7" />
        <WhatIf base={data?.what_if} goals={data?.goals ?? []} className="col-span-12 xl:col-span-5" />
        <Trends tr={data?.trends} className="col-span-12 lg:col-span-4" />
        <Drivers list={data?.drivers} className="col-span-12 md:col-span-6 lg:col-span-4" />
        <Weekday wk={data?.weekday} className="col-span-12 md:col-span-6 lg:col-span-4" />
      </div>
    </section>
  );
}

function Segments({ seg, className }) {
  const t = useTokens();
  const [active, setActive] = useState(null);
  if (seg === undefined) return <Skeleton className={clsx("h-[440px] rounded-[20px]", className)} />;
  if (!seg) return <Card className={clsx("p-6 text-sm text-muted", className)}>Spending segments appear after about 40 everyday transactions.</Card>;
  const colors = [t.sky, t.mint, t.violet, t.coral];
  return (
    <Card className={className}>
      <CardHeader title="Your spending segments" hint={`K-Means grouped ${seg.n} everyday spends by amount, weekday and time of month.`}
        action={<Pill tone="info" className="whitespace-nowrap">k = {seg.k} · silhouette {seg.silhouette}</Pill>} />
      <div className="h-[240px] px-2 pt-4">
        <ChartBox>
          <ScatterChart margin={{ right: 16, left: 0, top: 6 }}>
            <CartesianGrid stroke={t.linesoft} />
            <XAxis type="number" dataKey="x" domain={[1, 31]} ticks={[1, 8, 15, 22, 29]} name="Day of month" axisLine={false} tickLine={false} tickFormatter={(v) => `Day ${v}`} />
            <YAxis type="number" dataKey="y" scale="log" domain={["auto", "auto"]} tickFormatter={compact} axisLine={false} tickLine={false} width={48} allowDataOverflow />
            <ZAxis range={[28, 28]} />
            <Tooltip cursor={{ strokeDasharray: "3 3" }} content={({ active: a, payload }) => a && payload?.length ? (
              <div className="rounded-xl border border-line bg-surface px-3 py-2 text-[12px] shadow-card">
                <p className="font-semibold">{payload[0].payload.label}</p>
                <p className="text-muted">{money(payload[0].payload.y)} · day {payload[0].payload.x}</p>
                <p style={{ color: colors[payload[0].payload.segment] }}>{seg.groups[payload[0].payload.segment].name}</p>
              </div>) : null} />
            {seg.groups.map((g, i) => (
              <Scatter key={i} data={seg.points.filter((p) => p.segment === i)} fill={colors[i]}
                fillOpacity={active === null || active === i ? 0.85 : 0.12} isAnimationActive={false} />
            ))}
          </ScatterChart>
        </ChartBox>
      </div>
      <ul className="grid gap-2 px-5 pb-5 pt-3 sm:grid-cols-2 sm:px-6">
        {seg.groups.map((g, i) => (
          <li key={i}>
            <button onMouseEnter={() => setActive(i)} onMouseLeave={() => setActive(null)} onFocus={() => setActive(i)} onBlur={() => setActive(null)}
              className={clsx("w-full rounded-2xl border p-3 text-left transition-colors", active === i ? "border-line bg-raised" : "border-line-soft bg-surface-2")}>
              <span className="flex items-center gap-2 text-[13px] font-semibold leading-snug"><span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: SEG_COLORS[i] }} />{g.name}</span>
              <span className="mt-1.5 flex items-baseline justify-between gap-2 text-[12px] text-muted">
                <span>{g.count} spends · median {money(g.median)}</span><span className="num font-semibold text-text">{g.share}%</span>
              </span>
              <span className="mt-1.5 block h-1.5 overflow-hidden rounded-full bg-line-soft">
                <motion.span className="block h-full rounded-full" style={{ background: SEG_COLORS[i] }} initial={{ width: 0 }} animate={{ width: `${g.share}%` }} transition={{ duration: 0.8, delay: i * 0.08 }} />
              </span>
              <span className="mt-1 block truncate text-[11px] text-faint">Mostly {g.top_categories.join(", ")}</span>
            </button>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function WhatIf({ base, goals, className }) {
  const cats = useMemo(() => base ? Object.entries(base.categories).filter(([c, v]) => !["Rent", "Bills", "Education"].includes(c) && v > 200).slice(0, 5) : [], [base]);
  const [cuts, setCuts] = useState({});
  if (base === undefined) return <Skeleton className={clsx("h-[440px] rounded-[20px]", className)} />;
  if (!base) return null;
  const saved = cats.reduce((s, [c, v]) => s + v * ((cuts[c] ?? 0) / 100), 0);
  const newSavings = base.savings + saved;
  const perGoal = goals.length ? newSavings / goals.length : 0;
  const oldPerGoal = goals.length ? base.savings / goals.length : 0;
  const months = (rem, per) => (per > 0 ? Math.ceil(rem / per) : null);
  return (
    <Card className={className}>
      <CardHeader title="What if I cut back?" hint={`Based on your average of the last ${base.months.length} complete months.`}
        action={<FlaskConical size={18} className="text-faint" />} />
      <div className="px-5 pt-4 sm:px-6">
        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-2xl bg-surface-2 p-3">
            <p className="text-[12px] text-muted">Monthly savings</p>
            <p className={clsx("display text-2xl font-semibold", newSavings < 0 && "text-coral")}><CountUp value={newSavings} format={money} duration={0.4} /></p>
            <p className="text-[12px] text-faint">now {money(base.savings)}</p>
          </div>
          <div className="rounded-2xl bg-surface-2 p-3">
            <p className="text-[12px] text-muted">Extra in a year</p>
            <p className="display text-2xl font-semibold text-mint"><CountUp value={saved * 12} format={money} duration={0.4} /></p>
            <p className="text-[12px] text-faint">{money(saved)} a month</p>
          </div>
        </div>
        <div className="mt-5 space-y-4">
          {cats.map(([c, v]) => {
            const pct = cuts[c] ?? 0;
            return (
              <label key={c} className="block">
                <span className="flex items-baseline justify-between text-[13px]">
                  <span className="font-semibold">{c} <span className="font-normal text-faint">· {money(v)}/mo</span></span>
                  <span className="num font-semibold" style={{ color: pct ? catMeta(c).color : "var(--faint)" }}>{pct ? `−${pct}% (${money(v * pct / 100)})` : "no change"}</span>
                </span>
                <input type="range" min="0" max="50" step="5" value={pct} onChange={(e) => setCuts((x) => ({ ...x, [c]: Number(e.target.value) }))}
                  className="mt-1.5 w-full cursor-pointer" style={{ accentColor: catMeta(c).color }} aria-label={`Cut ${c} by percent`} />
              </label>
            );
          })}
        </div>
      </div>
      {goals.length > 0 && (
        <div className="mt-4 border-t border-line-soft px-5 py-4 sm:px-6">
          <p className="mb-2 text-[13px] font-semibold text-muted">Goal finish, splitting savings evenly</p>
          <ul className="space-y-1.5 text-[13px]">
            {goals.slice(0, 3).map((g) => {
              const before = months(g.remaining, oldPerGoal), after = months(g.remaining, perGoal);
              return (
                <li key={g.name} className="flex items-center justify-between gap-2">
                  <span className="truncate">{g.emoji} {g.name}</span>
                  <span className="num whitespace-nowrap">
                    {after === null ? <span className="text-coral">not reachable</span> : <><span className="font-semibold">{after} mo</span>{before !== null && after < before && <span className="text-mint"> ({before - after} sooner)</span>}</>}
                  </span>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </Card>
  );
}

function Spark({ values, color }) {
  const w = 72, h = 26;
  const min = Math.min(...values), max = Math.max(...values);
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * w},${h - 2 - ((v - min) / (max - min || 1)) * (h - 4)}`).join(" ");
  return <svg width={w} height={h} aria-hidden="true"><polyline points={pts} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>;
}

function Trends({ tr, className }) {
  if (!tr) return <Skeleton className={clsx("h-[380px] rounded-[20px]", className)} />;
  const items = tr.items.slice(0, 6);
  const icon = { rising: TrendingUp, falling: TrendingDown, stable: Minus };
  return (
    <Card className={className}>
      <CardHeader title="Trend detection" hint={`Linear regression over ${tr.months} months. A trend counts only if p < 0.1.`} />
      {tr.months < 4 ? <p className="px-6 pb-6 pt-4 text-sm text-muted">Needs at least 4 complete months.</p> : (
        <ul className="px-5 pb-5 pt-3 sm:px-6">
          {items.map((x) => {
            const Icon = icon[x.direction];
            const tone = x.direction === "rising" ? "text-coral" : x.direction === "falling" ? "text-mint" : "text-faint";
            return (
              <li key={x.category} className="flex items-center gap-3 border-b border-line-soft py-2.5 last:border-0">
                <span className={clsx("grid h-8 w-8 place-items-center rounded-lg bg-surface-2", tone)}><Icon size={16} /></span>
                <div className="min-w-0 flex-1">
                  <p className="text-[13px] font-semibold">{x.category}</p>
                  <p className="text-[11px] text-faint">{x.direction === "stable" ? "no clear trend" : `${x.pct_per_month > 0 ? "+" : ""}${x.pct_per_month}% a month`} · p {x.p_value ?? "—"} · R² {x.r2 ?? "—"}</p>
                </div>
                <Spark values={x.series} color={catMeta(x.category).color} />
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}

function Drivers({ list, className }) {
  if (!list) return <Skeleton className={clsx("h-[380px] rounded-[20px]", className)} />;
  const top = list.filter((d) => d.share > 0).slice(0, 6);
  const max = Math.max(...top.map((d) => d.share), 1);
  return (
    <Card className={className}>
      <CardHeader title="What makes months differ" hint="Share of the month-to-month swing in total spend explained by each category." />
      {top.length === 0 ? <p className="px-6 pb-6 pt-4 text-sm text-muted">Needs at least 3 complete months.</p> : (
        <div className="space-y-3 px-5 pb-5 pt-4 sm:px-6">
          {top.map((d, i) => (
            <div key={d.category}>
              <div className="flex justify-between text-[13px]"><span>{d.category}</span><span className="num font-semibold">{d.share}%</span></div>
              <div className="mt-1 h-2 overflow-hidden rounded-full bg-raised">
                <motion.div className="h-full rounded-full" style={{ background: catMeta(d.category).color }} initial={{ width: 0 }} animate={{ width: `${(d.share / max) * 100}%` }} transition={{ delay: i * 0.05, duration: 0.7 }} />
              </div>
            </div>
          ))}
          <p className="pt-1 text-[12px] text-faint">Steadying {top[0].category.toLowerCase()} spending would make your months most predictable.</p>
        </div>
      )}
    </Card>
  );
}

function Weekday({ wk, className }) {
  const t = useTokens();
  if (wk === undefined) return <Skeleton className={clsx("h-[380px] rounded-[20px]", className)} />;
  if (!wk) return <Card className={clsx("p-6 text-sm text-muted", className)}>Weekly rhythm needs more everyday transactions.</Card>;
  return (
    <Card className={className}>
      <CardHeader title="Weekly rhythm" hint="Average everyday spend per weekday"
        action={wk.weekend_premium_pct !== null && <Pill tone={wk.weekend_premium_pct > 15 ? "warn" : "neutral"}>Weekends {wk.weekend_premium_pct > 0 ? "+" : ""}{wk.weekend_premium_pct}%</Pill>} />
      <div className="h-[230px] px-2 pb-2 pt-4">
        <ChartBox>
          <BarChart data={wk.days} margin={{ right: 12 }}>
            <CartesianGrid vertical={false} stroke={t.linesoft} />
            <XAxis dataKey="day" axisLine={false} tickLine={false} />
            <YAxis tickFormatter={compact} axisLine={false} tickLine={false} width={44} />
            <Tooltip content={<ChartTooltip formatter={(v) => money(v)} />} />
            <Bar dataKey="avg" name="Average" radius={[6, 6, 2, 2]}>
              {wk.days.map((d) => <Cell key={d.day} fill={d.day === wk.busiest ? t.accent : ["Sat", "Sun"].includes(d.day) ? t.violet : t.sky} />)}
            </Bar>
          </BarChart>
        </ChartBox>
      </div>
      <p className="px-6 pb-5 text-[12px] text-faint">{wk.busiest} is your biggest spending day.</p>
    </Card>
  );
}
