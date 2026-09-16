import { Component } from "react";
import { AlertTriangle } from "lucide-react";

export default class PageBoundary extends Component {
  state = { error: null };
  static getDerivedStateFromError(error) { return { error }; }
  componentDidCatch(error, info) { console.error("Page crashed:", error, info); }
  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="flex flex-col items-center gap-3 rounded-[20px] border border-line-soft bg-surface px-6 py-16 text-center">
        <span className="grid h-12 w-12 place-items-center rounded-2xl bg-coral-soft text-coral"><AlertTriangle size={22} /></span>
        <p className="display text-xl font-semibold">This page hit an error</p>
        <p className="max-w-md text-sm text-muted">{String(this.state.error?.message || this.state.error)}</p>
        <button className="mt-2 h-10 rounded-xl bg-accent px-4 text-sm font-semibold text-accent-ink" onClick={() => this.setState({ error: null })}>Try again</button>
      </div>
    );
  }
}
