import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import Header from "../components/Header";
import AQIBigCard from "../components/AQIBigCard";
import PollutantGrid from "../components/PollutantGrid";
import TrendChart from "../components/TrendChart";
import ForecastStrip from "../components/ForecastStrip";
import MLPredictionCard from "../components/MLPredictionCard";
import HealthTips from "../components/HealthTips";
import SearchStations from "../components/SearchStations";
import { useAuth } from "../contexts/AuthContext";
import { api } from "../api/client";
import { useAutoRefresh, formatUpdatedTime } from "../hooks/useAutoRefresh";
import { ArrowsClockwise, Megaphone } from "@phosphor-icons/react";

const ADVISORY_STYLES = {
  good: { label: "Good", accent: "#10B981", badge: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300" },
  satisfactory: { label: "Satisfactory", accent: "#84CC16", badge: "border-lime-500/40 bg-lime-500/10 text-lime-300" },
  moderate: { label: "Moderate", accent: "#F59E0B", badge: "border-amber-500/40 bg-amber-500/10 text-amber-300" },
  poor: { label: "Poor", accent: "#F97316", badge: "border-orange-500/40 bg-orange-500/10 text-orange-300" },
  very_poor: { label: "Very Poor", accent: "#EF4444", badge: "border-red-500/40 bg-red-500/10 text-red-300" },
  severe: { label: "Severe", accent: "#7F1D1D", badge: "border-red-700/60 bg-red-900/25 text-red-300" },
};

export default function StudentDashboard() {
  const { user } = useAuth();
  const nav = useNavigate();
  const [stationId, setStationId] = useState(user?.home_station_id || "thapar-campus");
  const [station, setStation] = useState(null);
  const [current, setCurrent] = useState(null);
  const [tips, setTips] = useState([]);
  const [history, setHistory] = useState([]);
  const [forecast, setForecast] = useState([]);
  const [advisories, setAdvisories] = useState([]);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [refreshTick, setRefreshTick] = useState(0);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (id, silent = false) => {
    if (!silent) setLoading(true);
    try {
      const [s, h, f, adv] = await Promise.all([
        api.get(`/stations/${id}`),
        api.get(`/stations/${id}/history`),
        api.get(`/stations/${id}/forecast`),
        api.get("/advisories").catch(() => ({ data: { advisories: [] } })),
      ]);
      const cur = s.data.current;
      if (cur?.node_id) {
        api.get(`/nodes/${cur.node_id}/status`).catch(() => {});
      }
      setStation(s.data.station);
      setCurrent(cur);
      setTips(s.data.health_tips);
      setHistory(h.data.history);
      setForecast(f.data.forecast);
      setAdvisories(adv.data.advisories || []);
      setLastUpdated(new Date());
      setRefreshTick((t) => t + 1);
    } finally {
      if (!silent) setLoading(false);
    }
  }, []);

  useEffect(() => { load(stationId, false); }, [stationId, load]);

  const silentRefresh = useCallback(() => load(stationId, true), [stationId, load]);
  useAutoRefresh(silentRefresh, 60000);

  const activeAdvisories = advisories
    .filter((a) => !a.station_ids || a.station_ids.length === 0 || a.station_ids.includes(stationId))
    .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
    .slice(0, 3);

  return (
    <div className="min-h-screen">
      <Header />
      <main className="max-w-[1400px] mx-auto px-6 lg:px-10 py-10 scroll-mt-20">
        <div className="flex flex-wrap items-end justify-between gap-6 mb-8">
          <div>
            <div className="text-[10px] uppercase tracking-[0.3em] text-[#94A3B8] mb-2">Welcome back · {user?.name}</div>
            <h1 className="font-display text-3xl lg:text-4xl font-bold tracking-tight">Your air report</h1>
            <p className="text-sm text-[#94A3B8] mt-2 max-w-xl">
              Currently viewing readings from <span className="text-[#93C5FD]">{station?.name || "…"}</span>. Search any location below to compare.
            </p>
          </div>
          <div className="flex items-center gap-3">
            {lastUpdated && (
              <span data-testid="last-updated-indicator" className="text-[11px] font-mono text-[#64748B]">
                Updated {formatUpdatedTime(lastUpdated)}
              </span>
            )}
            <button
              data-testid="refresh-button"
              onClick={() => load(stationId, false)}
              className="h-10 px-4 border border-[#1E293B] hover:border-[#3B82F6] hover:bg-[#111827] transition-all flex items-center gap-2 text-xs uppercase tracking-[0.18em]"
            >
              <ArrowsClockwise size={14} /> Refresh
            </button>
          </div>
        </div>

        <div className="mb-8">
          <SearchStations onSelect={(s) => setStationId(s.id)} />
        </div>

        {loading || !current || !station ? (
          <SkeletonBlock />
        ) : (
          <div className="space-y-6">
            {activeAdvisories.length > 0 && (
              <section data-testid="student-advisories" className="space-y-3">
                <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.3em] text-[#94A3B8]">
                  <Megaphone size={13} className="text-[#93C5FD]" />
                  Active Advisories ({activeAdvisories.length})
                </div>
                <div className="space-y-2">
                  {activeAdvisories.map((a) => {
                    const style = ADVISORY_STYLES[a.severity] || ADVISORY_STYLES.moderate;
                    return (
                      <div
                        key={a.id}
                        data-testid={`student-advisory-${a.id}`}
                        className="relative border border-[#1E293B] bg-[#111827] px-5 py-4 pl-6"
                      >
                        <div className="absolute top-0 bottom-0 left-0 w-1" style={{ backgroundColor: style.accent }} />
                        <div className="flex flex-wrap items-center justify-between gap-2 mb-1">
                          <div className="font-display font-semibold text-sm text-[#F8FAFC]">{a.title}</div>
                          <div className="flex items-center gap-2">
                            <span className={`text-[9px] font-mono uppercase tracking-wider px-2 py-0.5 border ${style.badge}`}>
                              {style.label}
                            </span>
                            <span className="text-[10px] font-mono text-[#64748B]">
                              {new Date(a.created_at).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                            </span>
                          </div>
                        </div>
                        <p className="text-xs text-[#94A3B8] leading-relaxed">{a.message}</p>
                      </div>
                    );
                  })}
                </div>
              </section>
            )}

            <AQIBigCard station={station} reading={current} />

            <div className="grid lg:grid-cols-3 gap-6">
              <div className="lg:col-span-2 space-y-6">
                <TrendChart data={history} title="24-hour AQI trend (rolling 24-h avg)" dataKey="aqi" xKey="timestamp" />
                <PollutantGrid reading={current} />
              </div>
              <div className="space-y-6">
                <MLPredictionCard stationId={station.id} currentAqi={current.aqi} refreshKey={refreshTick} />
                <HealthTips tips={tips} category={current.category} />
                <button
                  data-testid="view-detail-button"
                  onClick={() => nav(`/location/${station.id}`)}
                  className="w-full h-12 border border-[#1E293B] hover:border-[#3B82F6] hover:bg-[#111827] transition-all text-xs uppercase tracking-[0.18em] text-[#94A3B8]"
                >
                  Open full station profile →
                </button>
              </div>
            </div>

            <ForecastStrip forecast={forecast} />
          </div>
        )}
      </main>
    </div>
  );
}

function SkeletonBlock() {
  return (
    <div className="space-y-4 animate-pulse">
      <div className="h-72 border border-[#1E293B] bg-[#111827]/40" />
      <div className="grid lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 h-64 border border-[#1E293B] bg-[#111827]/40" />
        <div className="h-64 border border-[#1E293B] bg-[#111827]/40" />
      </div>
    </div>
  );
}
