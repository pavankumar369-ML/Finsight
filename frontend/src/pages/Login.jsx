import { useState } from "react";
import { motion } from "motion/react";
import { Navigate } from "react-router-dom";
import { Sparkles } from "lucide-react";
import { useAuth } from "../components/Auth";
import { Button, Field, Input, Segmented } from "../components/ui";
import Logo from "../components/Logo";

export default function Login() {
  const auth = useAuth();
  const [mode, setMode] = useState("signin");
  const [form, setForm] = useState({ name: "", email: "", password: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  if (auth.user) return <Navigate to="/" replace />;
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  async function run(kind, fn) {
    setBusy(kind); setError("");
    try { await fn(); } catch (e) { setError(e.message); } finally { setBusy(""); }
  }
  const submit = (e) => {
    e.preventDefault();
    if (mode === "signup" && form.name.trim().length < 2) return setError("Enter your name.");
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(form.email)) return setError("Enter a valid email address.");
    if (form.password.length < 6) return setError("Password needs at least 6 characters.");
    run("form", () => mode === "signin" ? auth.login(form.email, form.password) : auth.register(form.name, form.email, form.password));
  };

  return (
    <div className="grain grid min-h-full lg:grid-cols-[1.15fr_1fr]">
      <section className="relative hidden flex-col justify-between overflow-hidden border-r border-line-soft bg-surface px-14 py-12 lg:flex">
        <Logo />
        <div className="relative">
          <h1 className="display max-w-[14ch] text-[3.6rem] font-semibold leading-[0.98]">Know where your money went, and where it’s heading.</h1>
          <p className="mt-6 max-w-[46ch] text-[16px] leading-relaxed text-muted">
            Upload a bank statement and FinSight sorts every UPI payment into categories, forecasts next month and flags spends that don’t look like you.
          </p>
          <PacePreview />
        </div>
        <p className="text-[13px] text-faint">
          Designed & built by Pavan Kumar · © 2026 FinSight · {" "}
          <a href="https://github.com/pavankumar369-ML" target="_blank" rel="noopener noreferrer"
             className="font-semibold text-muted underline-offset-4 hover:text-accent hover:underline">GitHub</a>
          {" "}·{" "}
          <a href="https://www.linkedin.com/in/pindiprolu-phani-pavan-kumar-236280385" target="_blank" rel="noopener noreferrer"
             className="font-semibold text-muted underline-offset-4 hover:text-accent hover:underline">LinkedIn</a>
        </p>
      </section>

      <section className="flex items-center justify-center px-5 py-10">
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }} className="w-full max-w-[400px]">
          <Logo className="mb-10 lg:hidden" />
          <h2 className="display text-3xl font-semibold">{mode === "signin" ? "Welcome back" : "Create your account"}</h2>
          <p className="mt-1.5 text-muted">{mode === "signin" ? "Sign in to see this month’s picture." : "It takes under a minute."}</p>

          <Button size="lg" variant="secondary" icon={Sparkles} className="mt-7 w-full" loading={busy === "demo"} onClick={() => run("demo", auth.demo)}>
            Explore with 6 months of demo data
          </Button>
          <div className="my-6 flex items-center gap-3 text-[12px] text-faint"><span className="h-px flex-1 bg-line" />or use your email<span className="h-px flex-1 bg-line" /></div>

          <Segmented value={mode} onChange={(m) => { setMode(m); setError(""); }} className="mb-5 w-full [&>button]:flex-1"
            options={[{ value: "signin", label: "Sign in" }, { value: "signup", label: "Create account" }]} />
          <form onSubmit={submit} className="space-y-4" noValidate>
            {mode === "signup" && <Field label="Name"><Input value={form.name} onChange={set("name")} autoComplete="name" /></Field>}
            <Field label="Email"><Input type="email" value={form.email} onChange={set("email")} autoComplete="email" /></Field>
            <Field label="Password"><Input type="password" value={form.password} onChange={set("password")} autoComplete={mode === "signin" ? "current-password" : "new-password"} /></Field>
            {error && <motion.p initial={{ opacity: 0, x: -4 }} animate={{ opacity: 1, x: 0 }} role="alert" className="rounded-xl bg-coral-soft px-3 py-2 text-[13px] text-coral">{error}</motion.p>}
            <Button type="submit" size="lg" className="w-full" loading={busy === "form"}>{mode === "signin" ? "Sign in" : "Create account"}</Button>
          </form>
        </motion.div>
      </section>
    </div>
  );
}

function PacePreview() {
  return (
    <div className="mt-12 max-w-[520px] rounded-[20px] border border-line bg-bg/60 p-5">
      <div className="flex items-baseline justify-between text-[13px]">
        <span className="text-muted">This month</span><span className="num text-muted">day 15 of 30</span>
      </div>
      <p className="display mt-1 text-2xl font-semibold">60% of budget used</p>
      <div className="relative mt-4 h-3 rounded-full bg-raised">
        <motion.div className="absolute inset-y-0 left-0 rounded-full bg-accent" initial={{ width: 0 }} animate={{ width: "60%" }} transition={{ delay: 0.5, duration: 1.2, ease: [0.16, 1, 0.3, 1] }} />
        <motion.div className="absolute -top-1.5 h-6 w-0.5 rounded bg-text" initial={{ left: 0, opacity: 0 }} animate={{ left: "50%", opacity: 1 }} transition={{ delay: 0.3, duration: 1 }} />
      </div>
      <p className="mt-3 text-[13px] text-muted">Spending is ahead of the calendar by 10 points.</p>
    </div>
  );
}
