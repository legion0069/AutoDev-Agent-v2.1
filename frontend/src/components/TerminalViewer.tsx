import { useEffect, useRef } from "react";
import { Circle } from "lucide-react";
import { useLogs } from "../hooks/useLogs";

export function TerminalViewer() {
  const { logs, connected } = useLogs();
  const bottomRef = useRef<HTMLDivElement>(null);
  useEffect(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }), [logs.length]);

  return (
    <section className="overflow-hidden rounded-2xl border border-line bg-[#080c14]">
      <div className="flex h-12 items-center justify-between border-b border-line px-4">
        <div className="flex items-center gap-2"><span className="size-2 rounded-full bg-rose-400/80" /><span className="size-2 rounded-full bg-amber-300/80" /><span className="size-2 rounded-full bg-mint/80" /><span className="ml-2 text-xs font-medium text-slate-400">Live execution stream</span></div>
        <div className="flex items-center gap-1.5 text-[11px] text-slate-500"><Circle className={`size-2 fill-current ${connected ? "text-mint" : "text-slate-600"}`} />{connected ? "Live" : "Reconnecting"}</div>
      </div>
      <div className="h-[min(56vh,520px)] min-h-64 overflow-y-auto px-4 py-3 font-mono text-xs">
        {logs.length === 0 ? <p className="py-8 text-center text-slate-600">Waiting for execution events…</p> : logs.map((log) => (
          <div key={log.event_id} className="flex gap-3 py-1.5 leading-5">
            <span className="shrink-0 text-slate-600">{new Date(log.timestamp).toLocaleTimeString([], { hour12: false })}</span>
            <span className={`min-w-0 ${log.level === "error" ? "text-rose-300" : log.level === "warning" ? "text-amber-300" : "text-emerald-200"}`}>{log.message}</span>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </section>
  );
}
