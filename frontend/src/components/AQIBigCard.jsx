import { categoryForAqi } from "../lib/aqi";
import { Drop, Thermometer, CloudFog, Wind, Warning } from "@phosphor-icons/react";

function getNodeChipMeta(reading) {
  if (reading?.simulated === false && reading?.node_status === "warming_up") {
    return {
      label: "Warming up",
      cls: "border-amber-500/40 bg-amber-500/10 text-amber-300",
      dot: "bg-amber-400 animate-pulse",
    };
  }
  if (reading?.simulated === false) {
    return {
      label: "Live sensor",
      cls: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
      dot: "bg-emerald-400 animate-pulse",
    };
  }
  if (reading?.node_status === "offline") {
    return {
      label: "Offline",
      cls: "border-slate-600/60 bg-slate-800/70 text-slate-300",
      dot: "bg-slate-400",
    };
  }
  return {
    label: "Simulated data",
    cls: "border-[#334155] bg-[#0B1120] text-[#94A3B8]",
    dot: "bg-[#64748B]",
  };
}

export default function AQIBigCard({ station, reading }) {
  const cat = categoryForAqi(reading.aqi);
  const chip = getNodeChipMeta(reading);

  return (
    <div data-testid="aqi-big-card" className="relative border border-[#1E293B] bg-[#111827] overflow-hidden">
      <div className={`absolute inset-0 ${cat.bg} pointer-events-none`} />
      <div className="absolute top-0 left-0 right-0 h-1" style={{ backgroundColor: cat.color }} />
      <div className="relative p-8 lg:p-10 grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="lg:col-span-2">
          <div className="flex flex-wrap items-center gap-2 mb-2">
            <div className="text-[10px] tracking-[0.3em] uppercase text-[#94A3B8]">Live AQI Reading</div>
            <span
              data-testid="node-status-chip"
              className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 border text-[10px] font-mono uppercase tracking-wider ${chip.cls}`}
            >
              <span className={`w-1.5 h-1.5 rounded-full ${chip.dot}`} />
              {chip.label}
            </span>
            {reading.rh_warning && (
              <span
                data-testid="rh-warning-badge"
                className="inline-flex items-center gap-1.5 px-2.5 py-0.5 border border-yellow-500/50 bg-yellow-500/15 text-yellow-300 text-[10px] font-mono tracking-wider"
              >
                <Warning size={12} weight="fill" />
                High humidity — PM may read high
              </span>
            )}
          </div>
          <h2 className="font-display text-2xl font-bold tracking-tight" data-testid="station-name">{station.name}</h2>
          <div className="text-xs font-mono text-[#64748B] mt-1">{station.city} · {station.state} · {station.lat?.toFixed(3)}, {station.lng?.toFixed(3)}</div>

          <div className="mt-8 flex items-end gap-6">
            <div>
              <div className="font-display font-bold text-7xl lg:text-8xl tracking-tighter leading-none" style={{ color: cat.color }} data-testid="aqi-value">
                {reading.aqi}
              </div>
              <div className="text-xs font-mono uppercase tracking-[0.2em] text-[#64748B] mt-2">
                CPCB AQI{reading.dominant_pollutant ? ` · ${reading.dominant_pollutant}` : ""}
              </div>
            </div>
            <div className="pb-3">
              <div className={`inline-block px-3 py-1 border ${cat.border} ${cat.bg} ${cat.text} text-xs uppercase tracking-[0.2em] font-medium`} data-testid="aqi-category">
                {cat.label}
              </div>
              <div className="text-xs font-mono text-[#94A3B8] mt-2 max-w-xs">
                Updated {new Date(reading.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
              </div>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-px bg-[#1E293B] border border-[#1E293B]">
          <MetricTile icon={CloudFog} label="PM2.5" value={reading.pm25} unit="µg/m³" />
          <MetricTile icon={Wind} label="PM10" value={reading.pm10} unit="µg/m³" />
          <MetricTile icon={Thermometer} label="Temp" value={reading.temperature} unit="°C" />
          <MetricTile icon={Drop} label="Humidity" value={reading.humidity} unit="%" />
        </div>
      </div>
    </div>
  );
}

function MetricTile({ icon: Icon, label, value, unit }) {
  return (
    <div className="bg-[#0B1120] p-4 flex flex-col gap-2" data-testid={`metric-${label.toLowerCase()}`}>
      <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-[0.2em] text-[#64748B]">
        <Icon size={12} /> {label}
      </div>
      <div className="font-display font-bold text-2xl">{value}</div>
      <div className="text-[10px] font-mono text-[#64748B]">{unit}</div>
    </div>
  );
}
