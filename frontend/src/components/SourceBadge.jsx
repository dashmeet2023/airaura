export default function SourceBadge({ current }) {
  if (current?.node_status === "offline") {
    return (
      <span className="text-[9px] font-mono uppercase tracking-wider px-1.5 py-0.5 border border-slate-600/60 bg-slate-800/70 text-slate-300 shrink-0">
        Offline
      </span>
    );
  }
  if (current?.simulated === false && current?.node_status === "warming_up") {
    return (
      <span className="text-[9px] font-mono uppercase tracking-wider px-1.5 py-0.5 border border-amber-500/40 bg-amber-500/10 text-amber-300 shrink-0">
        Warming up
      </span>
    );
  }
  if (current?.simulated === false) {
    return (
      <span className="text-[9px] font-mono uppercase tracking-wider px-1.5 py-0.5 border border-emerald-500/40 bg-emerald-500/10 text-emerald-300 shrink-0">
        Live sensor
      </span>
    );
  }
  return (
    <span className="text-[9px] font-mono uppercase tracking-wider px-1.5 py-0.5 border border-[#334155] text-[#64748B] shrink-0">
      Simulated
    </span>
  );
}
