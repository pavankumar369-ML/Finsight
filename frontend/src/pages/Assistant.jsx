import { Fragment, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { ArrowUp, Eraser, ShieldCheck, Sparkles, CornerDownRight } from "lucide-react";
import clsx from "clsx";
import { api } from "../lib/api";
import { useApi } from "../lib/hooks";
import { Button, Card, ErrorState, PageHeader, Pill, Skeleton } from "../components/ui";
import { ms } from "../lib/format";
import { useToast } from "../components/Toast";

const PROMPT_GROUPS = [
  { title: "Spending", items: ["How much did I spend this month?", "How much did I spend on food last month?", "How much on Swiggy?", "Where does most of my money go?"] },
  { title: "Budgets & bills", items: ["Am I over any budget?", "How much can I spend per day?", "What bills are coming up?", "Biggest purchase this month"] },
  { title: "Planning", items: ["How much will I spend next month?", "How are my goals?", "How much am I saving each month?", "Compare this month with last month"] },
  { title: "Insights", items: ["Which spending is increasing?", "Do I spend more on weekends?", "Anything unusual in my spending?", "How can I save more?"] },
];

/* tiny, safe renderer: **bold** and "- " bullets only */
function Rich({ text }) {
  const inline = (line) => line.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") ? <strong key={i} className="font-semibold text-text">{part.slice(2, -2)}</strong> : <Fragment key={i}>{part}</Fragment>);
  const blocks = [];
  let list = [];
  text.split("\n").forEach((raw, i) => {
    const line = raw.trim();
    if (/^[-•*]\s+/.test(line)) { list.push(line.replace(/^[-•*]\s+/, "")); return; }
    if (list.length) { blocks.push(<ul key={`l${i}`} className="my-1.5 space-y-1 pl-4">{list.map((l, k) => <li key={k} className="list-disc marker:text-faint">{inline(l)}</li>)}</ul>); list = []; }
    if (line) blocks.push(<p key={i}>{inline(line)}</p>);
  });
  if (list.length) blocks.push(<ul key="lend" className="my-1.5 space-y-1 pl-4">{list.map((l, k) => <li key={k} className="list-disc marker:text-faint">{inline(l)}</li>)}</ul>);
  return <div className="space-y-1.5">{blocks}</div>;
}

export default function Assistant() {
  const toast = useToast();
  const { data, error, loading, reload, setData } = useApi("/assistant/history");
  const [input, setInput] = useState("");
  const [thinking, setThinking] = useState(false);
  const [followups, setFollowups] = useState([]);
  const scroller = useRef(null);
  const box = useRef(null);
  const messages = data?.messages ?? [];

  useEffect(() => {
    const el = scroller.current;
    if (!el) return;
    // conversation: follow the newest message; empty state: stay at the top so the heading is visible
    el.scrollTo({ top: messages.length || thinking ? el.scrollHeight : 0, behavior: "smooth" });
  }, [messages.length, thinking, followups.length]);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 140) + "px";
  }, [input]);

  async function send(text) {
    const q = (text ?? input).trim();
    if (!q || thinking) return;
    setInput("");
    setFollowups([]);
    const temp = { id: `t${Date.now()}`, role: "user", content: q };
    setData((d) => ({ ...d, messages: [...(d?.messages ?? []), temp] }));
    setThinking(true);
    try {
      const r = await api("/assistant/chat", { method: "POST", body: { message: q } });
      setData((d) => ({ ...d, messages: [...d.messages.filter((m) => m.id !== temp.id), r.user, r.assistant] }));
      setFollowups(r.suggestions || []);
    } catch (e) {
      setData((d) => ({ ...d, messages: d.messages.filter((m) => m.id !== temp.id) }));
      setInput(q);
      toast(e.message, { tone: "bad" });
    } finally {
      setThinking(false);
      box.current?.focus();
    }
  }
  async function clear() {
    try { await api("/assistant/history", { method: "DELETE" }); setFollowups([]); reload(); toast("Conversation cleared.", { tone: "info" }); }
    catch (e) { toast(e.message, { tone: "bad" }); }
  }

  return (
    <>
      <PageHeader title="Assistant" subtitle="Ask about your spending, budgets, bills and goals. Answers come from your own transactions."
        actions={<>
          {data && <Pill tone="good" className="h-8 px-3" ><ShieldCheck size={13} />Private · runs locally</Pill>}
          {messages.length > 0 && <Button variant="secondary" icon={Eraser} onClick={clear}>Clear</Button>}
        </>} />

      <Card className="flex h-[calc(100dvh-240px)] min-h-[460px] flex-col overflow-hidden lg:h-[calc(100dvh-210px)]">
        <div ref={scroller} className="flex-1 overflow-y-auto px-4 py-6 sm:px-8">
          {error ? <ErrorState error={error} onRetry={reload} /> : loading && !data ? (
            <div className="space-y-4">{[0, 1, 2].map((i) => <Skeleton key={i} className={clsx("h-14", i % 2 ? "ml-auto w-1/2" : "w-2/3")} />)}</div>
          ) : messages.length === 0 && !thinking ? (
            <div className="mx-auto flex min-h-full max-w-2xl flex-col items-center justify-center py-2 text-center">
              <motion.span initial={{ scale: 0.6, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} transition={{ type: "spring", stiffness: 260, damping: 18 }}
                className="grid h-14 w-14 place-items-center rounded-2xl bg-accent-soft text-accent"><Sparkles size={26} /></motion.span>
              <h2 className="display mt-4 text-2xl font-semibold">What would you like to know?</h2>
              <p className="mt-1 max-w-lg text-sm text-muted">
                FinSight's own NLP model understands {data?.intents ?? 20}+ kinds of questions ({data?.intent_accuracy ?? "—"}% accurate on unseen wording)
                and answers from your transactions. Nothing is sent to any outside service.
              </p>
              <div className="mt-6 grid w-full gap-4 text-left sm:grid-cols-2">
                {PROMPT_GROUPS.map((g, gi) => (
                  <div key={g.title}>
                    <p className="mb-1.5 px-1 text-[11px] font-semibold uppercase tracking-wider text-faint">{g.title}</p>
                    <div className="space-y-1.5">
                      {g.items.map((p, i) => (
                        <motion.button key={p} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 + (gi * 4 + i) * 0.025 }}
                          onClick={() => send(p)} className="block w-full rounded-xl border border-line-soft bg-surface-2 px-3.5 py-2.5 text-left text-[13.5px] transition-colors hover:border-line hover:bg-raised">
                          {p}
                        </motion.button>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="mx-auto max-w-3xl space-y-5">
              <AnimatePresence initial={false}>
                {messages.map((m) => (
                  <motion.div key={m.id} layout="position" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
                    className={clsx("flex gap-3", m.role === "user" && "justify-end")}>
                    {m.role === "assistant" && <span className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-xl bg-accent-soft text-accent"><Sparkles size={15} /></span>}
                    <div className={clsx("max-w-[85%] text-[14.5px] leading-relaxed", m.role === "user"
                      ? "rounded-2xl rounded-br-md bg-accent px-4 py-2.5 font-medium text-accent-ink"
                      : "rounded-2xl rounded-tl-md border border-line-soft bg-surface-2 px-4 py-3 text-muted")}>
                      {m.role === "assistant" ? <Rich text={m.content} /> : m.content}
                      {m.role === "assistant" && m.ms !== null && (
                        <p className="mt-2 flex items-center gap-1.5 text-[11px] text-faint">
                          <ShieldCheck size={11} />{m.intent || "Answer"} · {ms(m.ms)}
                        </p>
                      )}
                    </div>
                  </motion.div>
                ))}
              </AnimatePresence>
              {!thinking && followups.length > 0 && messages.length > 0 && (
                <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="flex flex-wrap items-center gap-1.5 pl-11">
                  <CornerDownRight size={14} className="text-faint" />
                  {followups.map((f) => (
                    <button key={f} onClick={() => send(f)}
                      className="rounded-full border border-line-soft bg-surface-2 px-3 py-1.5 text-[12.5px] text-muted transition-colors hover:border-accent hover:text-text">{f}</button>
                  ))}
                </motion.div>
              )}
              {thinking && (
                <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex gap-3" aria-live="polite" aria-label="Assistant is thinking">
                  <span className="grid h-8 w-8 place-items-center rounded-xl bg-accent-soft text-accent"><Sparkles size={15} /></span>
                  <div className="flex items-center gap-1 rounded-2xl rounded-tl-md border border-line-soft bg-surface-2 px-4 py-3.5">
                    {[0, 1, 2].map((i) => <motion.span key={i} className="h-1.5 w-1.5 rounded-full bg-muted" animate={{ y: [0, -4, 0], opacity: [0.4, 1, 0.4] }} transition={{ repeat: Infinity, duration: 0.9, delay: i * 0.15 }} />)}
                  </div>
                </motion.div>
              )}
            </div>
          )}
        </div>

        <form onSubmit={(e) => { e.preventDefault(); send(); }} className="border-t border-line-soft bg-surface p-3 sm:p-4">
          <div className="mx-auto flex max-w-3xl items-end gap-2 rounded-2xl border border-line bg-surface-2 p-1.5 pl-4 transition-colors focus-within:border-accent">
            <textarea ref={box} rows={1} value={input} onChange={(e) => setInput(e.target.value)} maxLength={1000}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
              placeholder="Ask about your money…" aria-label="Message"
              className="chat-input max-h-[140px] flex-1 resize-none bg-transparent py-2 text-[15px] text-text placeholder:text-faint focus:outline-none focus-visible:outline-none" />
            <motion.button whileTap={{ scale: 0.9 }} type="submit" disabled={!input.trim() || thinking} aria-label="Send"
              className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-accent text-accent-ink transition-opacity disabled:opacity-40">
              <ArrowUp size={18} strokeWidth={2.5} />
            </motion.button>
          </div>
          <p className="mx-auto mt-1.5 max-w-3xl px-1 text-[11px] text-faint">Enter to send, Shift + Enter for a new line. Answers are computed from your data on FinSight's server. Not financial advice.</p>
        </form>
      </Card>
    </>
  );
}
