import { useEffect, useState } from "react";
import { categoryForAqi } from "../lib/aqi";
import { api, formatApiError } from "../api/client";
import { Brain, TrendUp, TrendDown, Minus } from "@phosphor-icons/react";

export default function MLPredictionCard({ stationId, currentAqi }) {
  const [state, setState] = useState({ loading: true, data: null, error: null });

  useEffect(() => {
    if (!stationId) return;
    let cancelled = false;
    setState({ loading: true, data: null, error: null });
    api
      .get(`/stations/${stationId}/predict`)
      .then((res) => {
        if (!cancelled) setState({ loading: false, data: res.data, error: null });
      })
      .catch((err) => {
        if (!cancelled) setState({ loading: false, data: null, error: formatApiError(err) });
      });
    return () => {
      cancelled = true;
    };
  }, [stationId]);

  if (state.loading) {
    return (
      <div
        className="border border-[#1E293B] bg-[#111827] p-6 h-40 animate-pulse"
        data-testid="ml-prediction-card"
      />
    );
  }

  if (state.error || !state.data) {
    const notDeployed = state.error?.toLowerCase().includes("not deployed");
    return (
      <div className="border border-[#1E293B] bg-[#111827] p-6" data-testid="ml-prediction-card">
        <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.3em] text-[#94A3B8] mb-3">
          <Brain size={14} /> ML Model Prediction
        </div>
        <p className="text-xs text-[#64748B] leading-relaxed">
          {notDeployed
            ? "Model not deployed yet — drop the exported model file into backend/ml/model/."
            : "Prediction unavailable right now."}
        </p>
      </div>
    );
  }

  if (state.data.status === "warming_up") {
    const daysAvail = state.data.days_available ?? 0;
    const daysNeeded = state.data.days_needed ?? 8;
    const pct = Math.min(100, Math.max(0, (daysAvail / daysNeeded) * 100));
    return (
      <div className="border border-[#1E293B] bg-[#111827] p-6" data-testid="ml-prediction-card">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.3em] text-[#94A3B8]">
            <Brain size={14} /> ML Model Prediction
          </div>
          <span className="text-[9px] font-mono uppercase tracking-wider px-2 py-0.5 border border-amber-500/40 bg-amber-500/10 text-amber-300">
            Warming up
          </span>
        </div>
        <div data-testid="ml-warming-up" className="font-display font-semibold text-base text-[#E2E8F0] mb-3">
          Collecting data: {daysAvail}/{daysNeeded} days
        </div>
        <div className="h-1.5 bg-[#1E293B] mb-3">
          <div className="h-full bg-amber-400 transition-all duration-500" style={{ width: `${pct}%` }} />
        </div>
        <p className="text-[10px] text-[#64748B] leading-relaxed">
          Uses PM2.5/PM10 daily averages from the sensor. At least {daysNeeded} days are needed to compute 7-day lag and rolling features.
        </p>
      </div>
    );
  }

  const { predicted_aqi, category, model, inputs, simulated } = state.data;
  const cat = categoryForAqi(predicted_aqi);
  const delta = typeof currentAqi === "number" ? predicted_aqi - currentAqi : null;
  const DeltaIcon = delta == null || delta === 0 ? Minus : delta > 0 ? TrendUp : TrendDown;

  return (
    <div className="border border-[#1E293B] bg-[#111827] p-6" data-testid="ml-prediction-card">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.3em] text-[#94A3B8]">
          <Brain size={14} /> ML Model Prediction
        </div>
        <div className="text-[9px] font-mono text-[#64748B] uppercase">{model?.replace(/_/g, " ")}</div>
      </div>

      <div className="flex items-end gap-4">
        <div
          className="font-display font-bold text-5xl tracking-tighter leading-none"
          style={{ color: cat.color }}
          data-testid="ml-prediction-value"
        >
          {predicted_aqi}
        </div>
        <div className="pb-1">
          <div
            className={`inline-block px-2.5 py-0.5 border ${cat.border} ${cat.bg} ${cat.text} text-[10px] uppercase tracking-[0.15em] font-medium`}
          >
            {category?.label || cat.label}
          </div>
          {delta !== null && (
            <div className="flex items-center gap-1 text-[10px] font-mono text-[#94A3B8] mt-2">
              <DeltaIcon size={11} />
              {delta === 0 ? "matches live reading" : `${delta > 0 ? "+" : ""}${delta} vs live reading`}
            </div>
          )}
        </div>
      </div>

      {inputs && (
        <div className="flex gap-4 mt-4 pt-4 border-t border-[#1E293B]" data-testid="ml-prediction-inputs">
          <div>
            <div className="text-[9px] uppercase tracking-[0.2em] text-[#64748B]">PM2.5 used</div>
            <div className="text-sm font-mono text-[#E2E8F0] mt-0.5">{inputs.pm25} µg/m³</div>
          </div>
          <div>
            <div className="text-[9px] uppercase tracking-[0.2em] text-[#64748B]">PM10 used</div>
            <div className="text-sm font-mono text-[#E2E8F0] mt-0.5">{inputs.pm10} µg/m³</div>
          </div>
        </div>
      )}

      <p className="text-[10px] text-[#64748B] mt-4 leading-relaxed">
        XGBoost trained on CPCB station history — uses PM2.5/PM10 daily averages from the sensor (plus their 7-day trend).
        {simulated ? " Currently using simulated daily baseline." : ""}
      </p>
    </div>
  );
}
