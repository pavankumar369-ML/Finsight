import { useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import Modal from "./Modal";
import { Button, Field, Input } from "./ui";
import { api } from "../lib/api";
import { useToast } from "./Toast";

export default function ChangePassword({ open, onClose }) {
  const toast = useToast();
  const blank = { current: "", next: "", confirm: "" };
  const [f, setF] = useState(blank);
  const [show, setShow] = useState(false);
  const [errors, setErrors] = useState({});
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.value }));
  const close = () => { setF(blank); setErrors({}); setShow(false); onClose(); };

  async function submit(e) {
    e.preventDefault();
    const errs = {};
    if (!f.current) errs.current = "Enter your current password.";
    if (f.next.length < 6) errs.next = "Use at least 6 characters.";
    else if (f.next === f.current) errs.next = "Choose something different from your current password.";
    if (f.confirm !== f.next) errs.confirm = "The two new passwords don't match.";
    setErrors(errs);
    if (Object.keys(errs).length) return;
    setBusy(true);
    try {
      await api("/auth/change-password", { method: "POST", body: { current_password: f.current, new_password: f.next } });
      toast("Password changed. Use the new one next time you sign in.");
      close();
    } catch (err) {
      if (err.status === 400) setErrors({ current: err.message });
      else toast(err.message, { tone: "bad" });
    } finally { setBusy(false); }
  }

  const type = show ? "text" : "password";
  return (
    <Modal open={open} onClose={close} title="Change password" subtitle="You'll stay signed in on this device." width={420}>
      <form onSubmit={submit} className="space-y-4" noValidate>
        <Field label="Current password" error={errors.current}>
          <Input type={type} value={f.current} onChange={set("current")} autoComplete="current-password" />
        </Field>
        <Field label="New password" error={errors.next} hint="At least 6 characters.">
          <Input type={type} value={f.next} onChange={set("next")} autoComplete="new-password" />
        </Field>
        <Field label="Confirm new password" error={errors.confirm}>
          <Input type={type} value={f.confirm} onChange={set("confirm")} autoComplete="new-password" />
        </Field>
        <button type="button" onClick={() => setShow((s) => !s)} className="flex items-center gap-1.5 text-[13px] font-semibold text-muted hover:text-text">
          {show ? <EyeOff size={15} /> : <Eye size={15} />}{show ? "Hide passwords" : "Show passwords"}
        </button>
        <div className="flex justify-end gap-2 pt-1">
          <Button type="button" variant="ghost" onClick={close}>Cancel</Button>
          <Button type="submit" loading={busy}>Update password</Button>
        </div>
      </form>
    </Modal>
  );
}
