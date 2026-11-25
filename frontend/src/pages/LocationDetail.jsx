import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import Header from "../components/Header";
import AQIBigCard from "../components/AQIBigCard";
import PollutantGrid from "../components/PollutantGrid";
import TrendChart from "../components/TrendChart";
import ForecastStrip from "../components/ForecastStrip";
import MLPredictionCard from "../components/MLPredictionCard";
import HealthTips from "../components/HealthTips";
import { api } from "../api/client";
import { useAutoRefresh, formatUpdatedTime } from "../hooks/useAutoRefresh";
import { CaretLeft } from "@phosphor-icons/react";

export default function LocationDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const [data, setData] = useState(null);
  const [history, setHistory] = useState([]);
  const [forecast, setForecast] = useState([]);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [refreshTick, setRefreshTick] = useState(0);

  const load = useCallback(async () => {
    const [s, h, f] = await Promise.all([
      api.get(`/stations/${id}`),
      api.get(`/stations/${id}/history`),
      api.get(`/stations/${id}/forecast`),
    ]);
    if (s.data.current?.node_id) {
      api.get(`/nodes/${s.data.current.node_id}/status`).catch(() => {});
    }
    setData(s.data);
    setHistory(h.data.history);
    setForecast(f.data.forecast);
    setLastUpdated(new Date());
    setRefreshTick((t) => t + 1);
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  useAutoRefresh(load, 60000);

  return (
    <div className="min-h-screen">
      <Header />
      <main className="max-w-[1400px] mx-auto px-6 lg:px-10 py-10 scroll-mt-20">
        <div className="flex flex-wrap items-center justify-between gap-4 mb-6">
          <button onClick={() => nav(-1)} data-testid="back-button" className="inline-flex items-center gap-1 text-xs uppercase tracking-[0.18em] text-[#94A3B8] hover:text-white transition-colors">
            <CaretLeft size={14} /> Back
          </button>
          {lastUpdated && (
            <span data-testid="last-updated-indicator" className="text-[11px] font-mono text-[#64748B]">
              Updated {formatUpdatedTime(lastUpdated)}
            </span>
          )}
        </div>
        {data ? (
          <div className="space-y-6">
            <AQIBigCard station={data.station} reading={data.current} />
            <div className="grid lg:grid-cols-3 gap-6">
              <div className="lg:col-span-2 space-y-6">
                <TrendChart data={history} title="24-hour AQI trend (rolling 24-h avg)" />
                <PollutantGrid reading={data.current} />
              </div>
              <div className="space-y-6">
                <MLPredictionCard stationId={data.station.id} currentAqi={data.current.aqi} refreshKey={refreshTick} />
                <HealthTips tips={data.health_tips} category={data.current.category} />
              </div>
            </div>
            <ForecastStrip forecast={forecast} />
          </div>
        ) : (
          <div className="text-[#64748B] font-mono text-sm">Loading station…</div>
        )}
      </main>
    </div>
  );
}
