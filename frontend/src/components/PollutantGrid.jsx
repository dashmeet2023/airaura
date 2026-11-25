export default function PollutantGrid({ reading }) {
  const isNode = reading?.simulated === false;
  const isOffline = reading?.node_status === "offline";
  const pmStale = Boolean(reading?.pm_stale);

  if (isNode) {
    const gasLabel = `Gas (${reading.gas_sensor || "Sensor"})`;
    const gasAlarm = Boolean(reading.gas_alarm);
    const hasMv = reading.gas_mv !== null && reading.gas_mv !== undefined;
    const items = [
      { key: "pm1", label: "PM 1", value: reading.pm1, unit: "µg/m³", max: 150, stale: pmStale },
      { key: "pm25", label: "PM 2.5", value: reading.pm25, unit: "µg/m³", max: 250, stale: pmStale },
      { key: "pm10", label: "PM 10", value: reading.pm10, unit: "µg/m³", max: 430, stale: pmStale },
      {
        key: "gas",
        label: gasLabel,
        isGas: true,
        gasAlarm,
        gasMv: hasMv ? reading.gas_mv : null,
        gasAlarmFrac: reading.gas_alarm_frac,
      },
      { key: "temperature", label: "Temperature", value: reading.temperature, unit: "°C", max: 50, neutral: true },
      { key: "humidity", label: "Humidity", value: reading.humidity, unit: "%", max: 100, neutral: true },
    ];

    return (
      <div data-testid="pollutant-grid" className="border border-[#1E293B] bg-[#111827] p-6">
        <div className="flex flex-wrap items-center justify-between gap-2 mb-5">
          <div className="text-[10px] uppercase tracking-[0.3em] text-[#94A3B8]">Sensor Telemetry</div>
          {pmStale && (
            <span
              data-testid="pm-stale-note"
              className="text-[10px] font-mono px-2 py-0.5 border border-amber-500/40 bg-amber-500/10 text-amber-300"
            >
              PM sensor not responding
            </span>
          )}
        </div>
        <div className={`grid grid-cols-2 md:grid-cols-3 gap-x-8 gap-y-5 ${isOffline ? "opacity-60" : ""}`}>
          {items.map((it) => {
            if (it.isGas) {
              const pillCls = it.gasAlarm
                ? "border-red-500/50 bg-red-500/15 text-red-300"
                : "border-emerald-500/40 bg-emerald-500/10 text-emerald-300";
              const barColor = it.gasAlarm ? "#EF4444" : "#10B981";
              const mvPct = it.gasMv !== null ? Math.min(100, Math.max(0, (it.gasMv / 3300) * 100)) : (it.gasAlarm ? 100 : 12);
              return (
                <div key={it.key} data-testid="pollutant-gas">
                  <div className="flex items-baseline justify-between gap-2 mb-2">
                    <span className="text-xs uppercase tracking-wider text-[#94A3B8]">{it.label}</span>
                    <span className="font-mono text-[10px] text-[#64748B]">{it.gasMv !== null ? "mV" : "status"}</span>
                  </div>
                  <div className="flex flex-wrap items-center gap-2 mb-2">
                    <span
                      data-testid="gas-status-pill"
                      className={`text-[10px] font-mono uppercase tracking-wider px-2 py-0.5 border ${pillCls}`}
                    >
                      {it.gasAlarm ? "Smoke/gas detected" : "Normal"}
                    </span>
                    {it.gasMv !== null && (
                      <span data-testid="gas-mv-value" className="font-display font-bold text-lg">
                        {it.gasMv} mV
                      </span>
                    )}
                  </div>
                  <div className="h-1 bg-[#1E293B] relative">
                    <div className="h-full transition-all duration-500" style={{ width: `${mvPct}%`, backgroundColor: isOffline ? "#64748B" : barColor }} />
                  </div>
                </div>
              );
            }

            const hasVal = typeof it.value === "number";
            const val = hasVal ? it.value : 0;
            const pct = Math.min(100, Math.max(0, (val / it.max) * 100));
            const color = isOffline || it.neutral
              ? "#94A3B8"
              : pct > 80 ? "#EF4444" : pct > 55 ? "#F97316" : pct > 30 ? "#F59E0B" : "#10B981";
            return (
              <div key={it.key} data-testid={`pollutant-${it.key}`}>
                <div className="flex items-baseline justify-between gap-2 mb-2">
                  <span className="text-xs uppercase tracking-wider text-[#94A3B8]">{it.label}</span>
                  <span className="font-mono text-[10px] text-[#64748B]">{it.unit}</span>
                </div>
                <div className="flex items-baseline gap-2 mb-2">
                  <div className={`font-display font-bold text-xl ${isOffline ? "text-slate-400" : ""}`}>
                    {hasVal ? it.value : "—"}
                  </div>
                  {it.stale && (
                    <span className="text-[9px] font-mono text-amber-300">PM sensor not responding</span>
                  )}
                </div>
                <div className="h-1 bg-[#1E293B] relative">
                  <div className="h-full transition-all duration-500" style={{ width: `${hasVal ? pct : 0}%`, backgroundColor: color }} />
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  const simItems = [
    { key: "pm25", label: "PM 2.5", value: reading.pm25, unit: "µg/m³", max: 250 },
    { key: "pm10", label: "PM 10", value: reading.pm10, unit: "µg/m³", max: 430 },
    { key: "no2", label: "NO₂", value: reading.no2, unit: "µg/m³", note: "simulated", max: 200 },
    { key: "so2", label: "SO₂", value: reading.so2, unit: "µg/m³", note: "simulated", max: 80 },
    { key: "o3", label: "O₃", value: reading.o3, unit: "µg/m³", note: "simulated", max: 180 },
    { key: "co2", label: "CO₂", value: reading.co2, unit: "ppm", note: "simulated", max: 1500 },
  ];

  return (
    <div data-testid="pollutant-grid" className="border border-[#1E293B] bg-[#111827] p-6">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-5">
        <div className="text-[10px] uppercase tracking-[0.3em] text-[#94A3B8]">Pollutant Concentrations</div>
        <span
          data-testid="pollutant-simulated-badge"
          className="text-[9px] font-mono uppercase tracking-widest px-2 py-0.5 border border-[#334155] bg-[#0B1120] text-[#94A3B8]"
        >
          simulated
        </span>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-x-8 gap-y-5">
        {simItems.map((it) => {
          const val = typeof it.value === "number" ? it.value : 0;
          const pct = Math.min(100, Math.max(0, (val / it.max) * 100));
          const color = pct > 80 ? "#EF4444" : pct > 55 ? "#F97316" : pct > 30 ? "#F59E0B" : "#10B981";
          return (
            <div key={it.key} data-testid={`pollutant-${it.key}`}>
              <div className="flex items-baseline justify-between gap-2 mb-2">
                <span className="text-xs uppercase tracking-wider text-[#94A3B8]">{it.label}</span>
                <span className="font-mono text-[10px] text-[#64748B]">{it.unit}</span>
              </div>
              <div className="flex items-baseline gap-2 mb-2">
                <div className="font-display font-bold text-xl">{it.value ?? "—"}</div>
                {it.note && (
                  <span className="text-[9px] font-mono uppercase tracking-wider text-[#64748B] border border-[#1E293B] px-1.5 py-0.5">
                    {it.note}
                  </span>
                )}
              </div>
              <div className="h-1 bg-[#1E293B] relative">
                <div className="h-full transition-all duration-500" style={{ width: `${pct}%`, backgroundColor: color }} />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
