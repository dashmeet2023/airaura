import { useCallback, useEffect, useState } from "react";
import Header from "../components/Header";
import { api, formatApiError } from "../api/client";
import { useAutoRefresh, formatUpdatedTime } from "../hooks/useAutoRefresh";
import { Megaphone, Trash } from "@phosphor-icons/react";

const EMPTY_FORM = {
  title: "",
  message: "",
  severity: "moderate",
  station_ids: [],
  expires_at: "",
};

const SEVERITIES = [
  { id: "good", label: "Good", color: "#10B981" },
  { id: "satisfactory", label: "Satisfactory", color: "#84CC16" },
  { id: "moderate", label: "Moderate", color: "#F59E0B" },
  { id: "poor", label: "Poor", color: "#F97316" },
  { id: "very_poor", label: "Very Poor", color: "#EF4444" },
  { id: "severe", label: "Severe", color: "#7F1D1D", textColor: "#F87171" },
];

export default function PCBAdvisories() {
  const [advisories, setAdvisories] = useState([]);
  const [stations, setStations] = useState([]);
  const [form, setForm] = useState(EMPTY_FORM);
  const [err, setErr] = useState("");
  const [feedErr, setFeedErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirmDeleteId, setConfirmDeleteId] = useState(null);
  const [deletingId, setDeletingId] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);

  const load = useCallback(async () => {
    const [advRes, stRes] = await Promise.all([
      api.get("/advisories"),
      api.get("/stations"),
    ]);
    setAdvisories(advRes.data.advisories || []);
    setStations(stRes.data.stations || []);
    setLastUpdated(new Date());
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useAutoRefresh(load, 60000);

  const toggleStation = (id) => {
    setForm((f) => ({
      ...f,
      station_ids: f.station_ids.includes(id) ? f.station_ids.filter((x) => x !== id) : [...f.station_ids, id],
    }));
  };

  const submit = async (e) => {
    e.preventDefault();
    setErr(""); setBusy(true);
    try {
      const payload = {
        title: form.title,
        message: form.message,
        severity: form.severity,
        station_ids: form.station_ids,
      };
      if (form.expires_at) {
        const expDate = new Date(form.expires_at);
        if (Number.isNaN(expDate.getTime())) {
          setErr("Invalid expiry date/time");
          return;
        }
        payload.expires_at = expDate.toISOString();
      }
      await api.post("/advisories", payload);
      setForm(EMPTY_FORM);
      await load();
    } catch (e) {
      setErr(formatApiError(e));
    } finally {
      setBusy(false);
    }
  };

  const handleDelete = async (id) => {
    setFeedErr("");
    setDeletingId(id);
    try {
      await api.delete(`/advisories/${id}`);
      setConfirmDeleteId(null);
      setAdvisories((prev) => prev.filter((item) => item.id !== id));
      await load();
    } catch (e) {
      setFeedErr(formatApiError(e));
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="min-h-screen">
      <Header />
      <main className="max-w-[1400px] mx-auto px-6 lg:px-10 py-10">
        <div className="flex flex-wrap items-end justify-between gap-4 mb-8">
          <div>
            <div className="text-[10px] uppercase tracking-[0.3em] text-[#94A3B8] mb-2">PPCB · Public Communications</div>
            <h1 className="font-display text-3xl lg:text-4xl font-bold tracking-tight">Advisories</h1>
            <p className="text-sm text-[#94A3B8] mt-2">Broadcast official air-quality advisories to citizens of affected zones.</p>
          </div>
          {lastUpdated && (
            <span data-testid="last-updated-indicator" className="text-[11px] font-mono text-[#64748B]">
              Updated {formatUpdatedTime(lastUpdated)}
            </span>
          )}
        </div>

        <div className="grid lg:grid-cols-5 gap-6">
          {/* COMPOSER */}
          <form onSubmit={submit} className="lg:col-span-2 border border-[#1E293B] bg-[#111827] p-6 space-y-4" data-testid="advisory-composer">
            <div className="text-[10px] uppercase tracking-[0.3em] text-[#94A3B8]">Compose new advisory</div>
            <input
              data-testid="advisory-title"
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
              placeholder="Title (e.g. Severe smog warning – Ludhiana)"
              required
              className="w-full h-11 px-4 bg-[#0B1120] border border-[#1E293B] focus:border-[#3B82F6] outline-none text-sm transition-colors"
            />
            <textarea
              data-testid="advisory-message"
              value={form.message}
              onChange={(e) => setForm({ ...form, message: e.target.value })}
              placeholder="Public message…"
              rows={5}
              required
              className="w-full px-4 py-3 bg-[#0B1120] border border-[#1E293B] focus:border-[#3B82F6] outline-none text-sm transition-colors resize-none"
            />
            <div>
              <div className="text-[10px] uppercase tracking-[0.2em] text-[#94A3B8] mb-2">Severity</div>
              <div className="flex flex-wrap gap-2">
                {SEVERITIES.map((s) => (
                  <button
                    key={s.id}
                    type="button"
                    data-testid={`severity-${s.id}`}
                    onClick={() => setForm({ ...form, severity: s.id })}
                    className={`text-[10px] uppercase tracking-[0.18em] px-3 py-1.5 border transition-colors ${
                      form.severity === s.id ? "bg-[#1E293B] text-white" : "text-[#94A3B8] hover:text-white"
                    }`}
                    style={{ borderColor: form.severity === s.id ? s.color : "#1E293B", color: form.severity === s.id ? (s.textColor || s.color) : undefined }}
                  >
                    {s.label}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <div className="flex items-center justify-between mb-2">
                <label htmlFor="advisory-expires-at" className="text-[10px] uppercase tracking-[0.2em] text-[#94A3B8]">
                  Expires at (optional · default 48 h)
                </label>
                {form.expires_at && (
                  <button
                    type="button"
                    data-testid="advisory-expires-clear"
                    onClick={() => setForm({ ...form, expires_at: "" })}
                    className="text-[10px] uppercase tracking-[0.15em] text-[#64748B] hover:text-white transition-colors"
                  >
                    Reset to 48 h
                  </button>
                )}
              </div>
              <input
                id="advisory-expires-at"
                data-testid="advisory-expires-at"
                type="datetime-local"
                value={form.expires_at}
                onChange={(e) => setForm({ ...form, expires_at: e.target.value })}
                className="w-full h-11 px-4 bg-[#0B1120] border border-[#1E293B] focus:border-[#3B82F6] outline-none text-sm text-[#F8FAFC] [color-scheme:dark] transition-colors"
              />
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-[0.2em] text-[#94A3B8] mb-2">Target stations ({form.station_ids.length})</div>
              <div className="max-h-48 overflow-auto border border-[#1E293B] divide-y divide-[#1E293B]">
                {stations.map((s) => (
                  <label key={s.id} className="flex items-center gap-3 px-3 py-2 hover:bg-[#1E293B]/50 transition-colors cursor-pointer">
                    <input
                      data-testid={`advisory-station-${s.id}`}
                      type="checkbox"
                      checked={form.station_ids.includes(s.id)}
                      onChange={() => toggleStation(s.id)}
                      className="accent-[#3B82F6]"
                    />
                    <div className="flex-1 text-sm">{s.name}</div>
                    <div className="text-[10px] font-mono text-[#64748B]">{s.current.aqi}</div>
                  </label>
                ))}
              </div>
            </div>
            {err && <div data-testid="advisory-error" className="border border-red-500/40 bg-red-500/10 text-red-300 text-xs p-3 font-mono">{err}</div>}
            <button data-testid="advisory-submit" disabled={busy} className="w-full h-11 bg-[#3B82F6] hover:bg-[#2563EB] disabled:opacity-50 text-sm uppercase tracking-[0.18em] transition-colors flex items-center justify-center gap-2">
              <Megaphone size={14} /> {busy ? "Broadcasting…" : "Publish advisory"}
            </button>
          </form>

          {/* FEED */}
          <div className="lg:col-span-3 space-y-4" data-testid="advisory-feed">
            {feedErr && (
              <div data-testid="advisory-feed-error" className="border border-red-500/40 bg-red-500/10 text-red-300 text-xs p-3 font-mono">
                {feedErr}
              </div>
            )}
            {advisories.length === 0 && (
              <div className="border border-[#1E293B] bg-[#111827] p-10 text-center text-sm text-[#64748B]">No advisories yet.</div>
            )}
            {advisories.map((a) => {
              const sev = SEVERITIES.find((s) => s.id === a.severity) || SEVERITIES[1];
              const expDate = a.expires_at ? new Date(a.expires_at) : null;
              const hasValidExp = Boolean(expDate && !Number.isNaN(expDate.getTime()));
              const isExpired = hasValidExp && expDate.getTime() <= Date.now();
              const confirming = confirmDeleteId === a.id;
              return (
                <div
                  key={a.id}
                  className={`border border-[#1E293B] bg-[#111827] p-6 relative ${isExpired ? "opacity-70" : ""}`}
                  data-testid={`advisory-${a.id}`}
                >
                  <div className="absolute top-0 left-0 bottom-0 w-1" style={{ backgroundColor: sev.color }} />
                  <div className="flex flex-wrap items-center justify-between gap-3 mb-2">
                    <h3 className="font-display text-lg font-bold tracking-tight">{a.title}</h3>
                    <div className="flex items-center gap-3">
                      {isExpired && (
                        <span
                          data-testid={`advisory-expired-${a.id}`}
                          className="text-[10px] font-mono uppercase tracking-[0.18em] px-2 py-0.5 border border-[#334155] bg-[#1E293B]/60 text-[#94A3B8]"
                        >
                          Expired
                        </span>
                      )}
                      <span className="text-[10px] uppercase tracking-[0.2em]" style={{ color: sev.textColor || sev.color }}>
                        {sev.label}
                      </span>
                      {!confirming ? (
                        <button
                          type="button"
                          data-testid={`advisory-delete-${a.id}`}
                          onClick={() => setConfirmDeleteId(a.id)}
                          title="Delete advisory"
                          className="text-[10px] uppercase tracking-[0.18em] px-2.5 py-1 border border-[#1E293B] text-[#94A3B8] hover:text-red-300 hover:border-red-500/50 transition-colors flex items-center gap-1"
                        >
                          <Trash size={12} /> Delete
                        </button>
                      ) : (
                        <div className="flex items-center gap-1.5" data-testid={`advisory-delete-confirm-box-${a.id}`}>
                          <button
                            type="button"
                            data-testid={`advisory-delete-confirm-${a.id}`}
                            disabled={deletingId === a.id}
                            onClick={() => handleDelete(a.id)}
                            className="text-[10px] uppercase tracking-[0.18em] px-2.5 py-1 border border-red-500/60 bg-red-500/15 text-red-300 hover:bg-red-500/25 disabled:opacity-50 transition-colors"
                          >
                            {deletingId === a.id ? "Deleting…" : "Confirm delete"}
                          </button>
                          <button
                            type="button"
                            data-testid={`advisory-delete-cancel-${a.id}`}
                            disabled={deletingId === a.id}
                            onClick={() => setConfirmDeleteId(null)}
                            className="text-[10px] uppercase tracking-[0.18em] px-2 py-1 border border-[#1E293B] text-[#94A3B8] hover:text-white transition-colors"
                          >
                            Cancel
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                  <p className="text-sm text-[#94A3B8] leading-relaxed">{a.message}</p>
                  <div className="mt-4 flex flex-wrap items-center justify-between gap-2 text-[10px] font-mono uppercase tracking-widest text-[#64748B]">
                    <div>{a.author_name}</div>
                    <div className="flex flex-wrap items-center gap-3">
                      <span>Published {new Date(a.created_at).toLocaleString()}</span>
                      {hasValidExp && (
                        <span data-testid={`advisory-expires-label-${a.id}`}>
                          {isExpired ? "Expired" : "Expires"} {expDate.toLocaleString()}
                        </span>
                      )}
                    </div>
                  </div>
                  {a.station_ids?.length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-1">
                      {a.station_ids.map((sid) => (
                        <span key={sid} className="text-[10px] font-mono px-2 py-0.5 border border-[#1E293B] text-[#94A3B8]">{sid}</span>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </main>
    </div>
  );
}
