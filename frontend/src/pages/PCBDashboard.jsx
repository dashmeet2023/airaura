import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import Header from "../components/Header";
import { api } from "../api/client";
import { categoryForAqi } from "../lib/aqi";
import { useAutoRefresh, formatUpdatedTime } from "../hooks/useAutoRefresh";
import { TrendUp, TrendDown, Buildings, ShieldWarning } from "@phosphor-icons/react";

export default function PCBDashboard() {
  const nav = useNavigate();
  const [data, setData] = useState(null);
  const [filter, setFilter] = useState("all");
  const [lastUpdated, setLastUpdated] = useState(null);

  const load = useCallback(async () => {
    const { data: overview } = await api.get("/overview");
    const nodeStations = (overview.stations || []).filter((s) => s.current?.node_id);
    await Promise.all(
      nodeStations.map((s) => api.get(`/nodes/${s.current.node_id}/status`).catch(() => {}))
    );
    setData(overview);
    setLastUpdated(new Date());
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useAutoRefresh(load, 60000);

  if (!data) {
    return (
      <div className="min-h-screen">
        <Header />
        <div className="max-w-[1400px] mx-auto px-6 py-10 text-[#64748B] font-mono">Loading regional overview…</div>
      </div>
    );
  }

  const { summary, hotspots, cleanest, stations } = data;
  const cat = categoryForAqi(summary.average_aqi);
  const liveCount = stations.filter(
    (s) => (s.simulated === false || s.source === "airaura-node" || s.current?.simulated === false) && s.current?.node_status !== "offline"
  ).length;
  const offlineCount = stations.filter((s) => s.current?.node_status === "offline").length;
  const simCount = stations.length - liveCount - offlineCount;
  const stationsSub = offlineCount > 0
    ? `${liveCount} live sensor · ${offlineCount} offline · ${simCount} simulated`
    : `${liveCount} live sensor${liveCount === 1 ? "" : "s"} · ${simCount} simulated`;
  const filtered = filter === "all" ? stations : stations.filter((s) => s.current.category.code === filter);

  return (
    <div className="min-h-screen">
      <Header />
      <main className="max-w-[1400px] mx-auto px-6 lg:px-10 py-10 scroll-mt-20">
        <div className="flex flex-wrap items-end justify-between gap-4 mb-10">
          <div>
            <div className="text-[10px] uppercase tracking-[0.3em] text-[#94A3B8] mb-2">PPCB · Regional Command</div>
            <h1 className="font-display text-3xl lg:text-4xl font-bold tracking-tight">Punjab Belt Overview</h1>
            <p className="text-sm text-[#94A3B8] mt-2">Real-time aggregate of {summary.total_stations} monitoring stations across the Punjab–Chandigarh–Delhi corridor.</p>
          </div>
          {lastUpdated && (
            <span data-testid="last-updated-indicator" className="text-[11px] font-mono text-[#64748B]">
              Updated {formatUpdatedTime(lastUpdated)}
            </span>
          )}
        </div>

        {/* KPI ROW */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-px bg-[#1E293B] border border-[#1E293B] mb-8">
          <KPI label="Regional Avg AQI" value={summary.average_aqi} accent={cat.color} sub={cat.label} testid="kpi-avg" />
          <KPI label="Active Stations" value={summary.total_stations} icon={Buildings} sub={stationsSub} testid="kpi-stations" />
          <KPI label="Poor to Severe Zones" value={(summary.buckets.severe || 0) + (summary.buckets.very_poor || 0) + (summary.buckets.poor || 0)} accent="#EF4444" icon={ShieldWarning} sub="needs action" testid="kpi-bad" />
          <KPI label="Clean Zones" value={(summary.buckets.good || 0) + (summary.buckets.satisfactory || 0)} accent="#10B981" sub="acceptable" testid="kpi-good" />
        </div>

        {/* HOTSPOTS & CLEANEST */}
        <div className="grid md:grid-cols-2 gap-6 mb-8">
          <RankList title="Pollution Hotspots" icon={TrendUp} accent="#EF4444" items={hotspots} testid="hotspots-list" onClick={(id) => nav(`/location/${id}`)} />
          <RankList title="Cleanest Stations" icon={TrendDown} accent="#10B981" items={cleanest} testid="cleanest-list" onClick={(id) => nav(`/location/${id}`)} />
        </div>

        {/* FILTER BAR */}
        <div className="flex flex-wrap items-center gap-2 mb-4">
          <span className="text-[10px] uppercase tracking-[0.3em] text-[#94A3B8] mr-2">Filter</span>
          {[
            { id: "all", label: `All (${stations.length})`, color: "#94A3B8" },
            { id: "good", label: `Good (${summary.buckets.good || 0})`, color: "#10B981" },
            { id: "satisfactory", label: `Satisfactory (${summary.buckets.satisfactory || 0})`, color: "#84CC16" },
            { id: "moderate", label: `Moderate (${summary.buckets.moderate || 0})`, color: "#F59E0B" },
            { id: "poor", label: `Poor (${summary.buckets.poor || 0})`, color: "#F97316" },
            { id: "very_poor", label: `Very Poor (${summary.buckets.very_poor || 0})`, color: "#EF4444" },
            { id: "severe", label: `Severe (${summary.buckets.severe || 0})`, color: "#7F1D1D", textColor: "#F87171" },
          ].map((f) => (
            <button
              key={f.id}
              data-testid={`filter-${f.id}`}
              onClick={() => setFilter(f.id)}
              className={`text-[10px] uppercase tracking-[0.18em] px-3 py-1.5 border transition-all ${
                filter === f.id
                  ? "border-[#3B82F6] bg-[#3B82F6]/10 text-white"
                  : "border-[#1E293B] text-[#94A3B8] hover:border-[#334155] hover:text-white"
              }`}
              style={filter === f.id ? { borderColor: f.color, color: f.textColor || f.color } : {}}
            >
              {f.label}
            </button>
          ))}
        </div>

        {/* STATION GRID */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-px bg-[#1E293B] border border-[#1E293B]" data-testid="station-grid">
          {filtered.map((s) => {
            const c = categoryForAqi(s.current.aqi);
            return (
              <button
                key={s.id}
                data-testid={`station-card-${s.id}`}
                onClick={() => nav(`/location/${s.id}`)}
                className="bg-[#0B1120] p-5 text-left hover:bg-[#111827] transition-colors group relative"
              >
                <div className="absolute top-0 left-0 right-0 h-0.5" style={{ backgroundColor: c.color }} />
                <div className="flex items-baseline justify-between gap-2 mb-3">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="text-[10px] uppercase tracking-[0.2em] text-[#64748B]">{s.type}</span>
                    <SourceBadge current={s.current} />
                  </div>
                  <div className={`text-[9px] uppercase tracking-wider px-1.5 py-0.5 border whitespace-nowrap ${c.border} ${c.text}`}>{c.label}</div>
                </div>
                <div className="font-display font-bold text-2xl group-hover:text-[#93C5FD] transition-colors">{s.name}</div>
                <div className="text-xs font-mono text-[#94A3B8] mt-1">{s.city}, {s.state}</div>
                <div className="mt-6 flex items-end justify-between">
                  <div>
                    <div className="font-display font-bold text-4xl" style={{ color: c.color }}>{s.current.aqi}</div>
                    <div className="text-[10px] font-mono uppercase text-[#64748B]">AQI</div>
                  </div>
                  <div className="text-right space-y-0.5 font-mono text-[10px] text-[#94A3B8]">
                    <div>PM2.5 · {s.current.pm25}</div>
                    <div>PM10 · {s.current.pm10}</div>
                    <div>T · {s.current.temperature}°C</div>
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      </main>
    </div>
  );
}

function SourceBadge({ current }) {
  if (current?.node_status === "offline") {
    return (
      <span className="text-[9px] font-mono uppercase tracking-wider px-1.5 py-0.5 border border-slate-600/60 bg-slate-800/70 text-slate-300">
        Offline
      </span>
    );
  }
  if (current?.simulated === false && current?.node_status === "warming_up") {
    return (
      <span className="text-[9px] font-mono uppercase tracking-wider px-1.5 py-0.5 border border-amber-500/40 bg-amber-500/10 text-amber-300">
        Warming up
      </span>
    );
  }
  if (current?.simulated === false) {
    return (
      <span className="text-[9px] font-mono uppercase tracking-wider px-1.5 py-0.5 border border-emerald-500/40 bg-emerald-500/10 text-emerald-300">
        Live sensor
      </span>
    );
  }
  return (
    <span className="text-[9px] font-mono uppercase tracking-wider px-1.5 py-0.5 border border-[#334155] text-[#64748B]">
      Simulated
    </span>
  );
}

function KPI({ label, value, sub, accent, icon: Icon, testid }) {
  return (
    <div className="bg-[#0B1120] p-6" data-testid={testid}>
      <div className="flex items-center justify-between mb-3">
        <div className="text-[10px] uppercase tracking-[0.3em] text-[#94A3B8]">{label}</div>
        {Icon && <Icon size={14} className="text-[#64748B]" />}
      </div>
      <div className="font-display font-bold text-4xl" style={{ color: accent || "#F8FAFC" }}>{value}</div>
      <div className="text-xs uppercase tracking-wider text-[#64748B] mt-2">{sub}</div>
    </div>
  );
}

function RankList({ title, icon: Icon, accent, items, testid, onClick }) {
  return (
    <div className="border border-[#1E293B] bg-[#111827]" data-testid={testid}>
      <div className="flex items-center justify-between p-5 border-b border-[#1E293B]">
        <div className="flex items-center gap-2">
          <Icon size={14} style={{ color: accent }} />
          <div className="text-[10px] uppercase tracking-[0.3em] text-[#94A3B8]">{title}</div>
        </div>
      </div>
      <div>
        {items.map((s, i) => {
          const c = categoryForAqi(s.current.aqi);
          return (
            <button
              key={s.id}
              onClick={() => onClick?.(s.id)}
              data-testid={`${testid}-item-${i}`}
              className="w-full text-left px-5 py-4 border-b border-[#1E293B] last:border-b-0 hover:bg-[#1E293B] transition-colors flex items-center gap-4"
            >
              <div className="font-mono text-[10px] text-[#64748B] w-6">0{i + 1}</div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <div className="font-display font-semibold truncate">{s.name}</div>
                  <SourceBadge current={s.current} />
                </div>
                <div className="text-[10px] font-mono uppercase text-[#64748B] tracking-widest">{s.city}</div>
              </div>
              <div className="font-display font-bold text-2xl" style={{ color: c.color }}>{s.current.aqi}</div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
