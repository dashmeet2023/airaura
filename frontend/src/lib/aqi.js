export function categoryForAqi(aqi) {
  if (aqi <= 50) return { label: "Good", color: "#10B981", code: "good", text: "text-emerald-400", bg: "bg-emerald-500/10", border: "border-emerald-500/40" };
  if (aqi <= 100) return { label: "Satisfactory", color: "#84CC16", code: "satisfactory", text: "text-lime-400", bg: "bg-lime-500/10", border: "border-lime-500/40" };
  if (aqi <= 200) return { label: "Moderate", color: "#F59E0B", code: "moderate", text: "text-amber-400", bg: "bg-amber-500/10", border: "border-amber-500/40" };
  if (aqi <= 300) return { label: "Poor", color: "#F97316", code: "poor", text: "text-orange-400", bg: "bg-orange-500/10", border: "border-orange-500/40" };
  if (aqi <= 400) return { label: "Very Poor", color: "#EF4444", code: "very_poor", text: "text-red-400", bg: "bg-red-500/10", border: "border-red-500/40" };
  return { label: "Severe", color: "#7F1D1D", code: "severe", text: "text-red-500", bg: "bg-red-900/20", border: "border-red-700/60" };
}

export const AQI_SCALE = [
  { range: "0–50", label: "Good", color: "#10B981", code: "good" },
  { range: "51–100", label: "Satisfactory", color: "#84CC16", code: "satisfactory" },
  { range: "101–200", label: "Moderate", color: "#F59E0B", code: "moderate" },
  { range: "201–300", label: "Poor", color: "#F97316", code: "poor" },
  { range: "301–400", label: "Very Poor", color: "#EF4444", code: "very_poor" },
  { range: "401–500", label: "Severe", color: "#7F1D1D", code: "severe" },
];
