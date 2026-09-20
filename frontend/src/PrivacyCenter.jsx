/**
 * Phase 39 Session 4 — Privacy Control Center.
 * Route: /privacy (listener-accessible). Carries a prominent DRAFT
 * watermark per locked directive (legal sign-off arrives later).
 */
import React, { useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { ShieldCheck, Download, Trash2, Lock, MapPin, Loader2, Target } from "lucide-react";

const API = process.env.REACT_APP_BACKEND_URL || "";

const LEVELS = [
  { n: 0, name: "Off",                    desc: "No location data captured beyond your signup city." },
  { n: 1, name: "City only",          desc: "Use your signup city for location-flavored greetings only." },
  { n: 2, name: "Session foreground", desc: "Foreground geolocation during active radio sessions. Ephemeral." },
  { n: 3, name: "Travel history",  desc: "Persistent travel pattern learning for frequent places + routes." },
];


export default function PrivacyCenter() {
  const [level, setLevel] = useState(0);
  const [audit, setAudit] = useState([]);
  const [eventsCount, setEventsCount] = useState(0);
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = async () => {
    try {
      const c = await axios.get(`${API}/privacy/consent`, { withCredentials: true });
      setLevel(c.data.level);
      const a = await axios.get(`${API}/privacy/audit_log`, { withCredentials: true });
      setAudit(a.data.entries || []);
      const x = await axios.get(`${API}/privacy/export`, { withCredentials: true });
      setEventsCount((x.data.travel_events || []).length);
    } catch (e) { /* silent */ }
  };
  useEffect(() => { refresh(); }, []);

  const setConsent = async (n) => {
    if (busy) return;
    setBusy(true);
    try {
      await axios.post(`${API}/privacy/consent`,
                                      { level: n }, { withCredentials: true });
      toast.success(`Consent set to level ${n} — ${LEVELS[n].name}`);
      await refresh();
    } catch (e) {
      toast.error(e.response?.data?.detail?.code === "consent_rate_limit"
                          ? "Too many consent changes — try again later."
                          : "Couldn't update consent.");
    } finally { setBusy(false); }
  };

  const exportData = async () => {
    try {
      const r = await axios.get(`${API}/privacy/export`, { withCredentials: true });
      const blob = new Blob([JSON.stringify(r.data, null, 2)],
                                              { type: "application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `bigfm_privacy_export_${Date.now()}.json`;
      a.click();
      toast.success("Privacy data exported.");
    } catch (e) { toast.error("Export failed."); }
  };

  const doDelete = async () => {
    if (confirm !== "DELETE_MY_DATA") {
      toast.error('Type "DELETE_MY_DATA" exactly to confirm.');
      return;
    }
    try {
      const r = await axios.post(`${API}/privacy/delete`,
                                                  { confirm }, { withCredentials: true });
      toast.success(`Account scheduled for deletion in ${r.data.recovery_window_days} days.`);
    } catch (e) { toast.error("Delete failed."); }
  };

  return (
    <div data-testid="privacy-center-page"
            style={{ maxWidth: 900, margin: "0 auto", padding: 24 }}>
      <div style={{ background: "rgba(245,158,11,0.1)",
                              border: "1px dashed #f59e0b",
                              padding: "8px 14px", borderRadius: 6,
                              color: "#f59e0b", fontSize: 12,
                              marginBottom: 18, textAlign: "center",
                              letterSpacing: 1, fontWeight: 700 }}
              data-testid="privacy-draft-watermark">
        DRAFT — pending legal sign-off
      </div>
      <h1 style={{ color: "#fff", fontSize: 26, fontWeight: 700,
                              margin: "0 0 6px",
                              display: "flex", alignItems: "center", gap: 10 }}>
        <ShieldCheck size={22} color="#10b981" /> Your FUUSIC Privacy
      </h1>
      <p style={{ color: "#9aa3af", fontSize: 13, margin: "0 0 24px" }}>
        Control what FUUSIC knows about your location.  All changes are logged.
      </p>

      <section data-testid="privacy-consent-section"
                      style={{ background: "#1f2937", borderRadius: 12,
                                  padding: 20, marginBottom: 20 }}>
        <h2 style={{ color: "#fff", fontSize: 16, margin: "0 0 12px" }}>
          Location Consent — currently <span style={{ color: "#10b981" }}>
              Level {level} ({LEVELS[level]?.name})
          </span>
        </h2>
        {LEVELS.map((lv) => (
          <label key={lv.n}
                        data-testid={`privacy-level-${lv.n}`}
                        style={{ display: "block", padding: "10px 12px",
                                    borderRadius: 6, marginBottom: 6,
                                    cursor: busy ? "wait" : "pointer",
                                    background: level === lv.n
                                                      ? "rgba(16,185,129,0.1)" : "transparent",
                                    border: level === lv.n
                                                      ? "1px solid #10b981"
                                                      : "1px solid rgba(255,255,255,0.06)" }}>
            <input type="radio" name="level" checked={level === lv.n}
                          disabled={busy}
                          onChange={() => setConsent(lv.n)}
                          style={{ marginRight: 8 }} />
            <strong style={{ color: "#fff" }}>{lv.n} — {lv.name}</strong>
            <div style={{ color: "#9aa3af", fontSize: 12, marginLeft: 22 }}>
              {lv.desc}
            </div>
          </label>
        ))}
      </section>

      <section style={{ background: "#1f2937", borderRadius: 12,
                                  padding: 20, marginBottom: 20 }}>
        <div style={{ display: "flex", justifyContent: "space-between",
                                  alignItems: "center" }}>
          <div>
            <h3 style={{ color: "#fff", fontSize: 14, margin: 0 }}>
              Travel Events Recorded</h3>
            <p style={{ color: "#9aa3af", fontSize: 12, margin: "4px 0 0" }}>
              {eventsCount} events in the last 90 days
            </p>
          </div>
          <button data-testid="privacy-export-btn" onClick={exportData}
                          style={{ background: "#3b82f6", color: "#fff", border: "none",
                                      padding: "8px 14px", borderRadius: 6, cursor: "pointer",
                                      display: "inline-flex", alignItems: "center", gap: 6 }}>
            <Download size={14} /> Export my data
          </button>
        </div>
      </section>

      {/* Phase J (M2) — location-share toggle. */}
      <LocationShareToggle />
      <RetargetingOptOutToggle />

      <section style={{ background: "#1f2937", borderRadius: 12,
                                  padding: 20, marginBottom: 20 }}>
        <h3 style={{ color: "#ef4444", fontSize: 14, margin: "0 0 8px",
                                display: "flex", alignItems: "center", gap: 6 }}>
          <Trash2 size={14} /> Delete my account
        </h3>
        <p style={{ color: "#9aa3af", fontSize: 12, margin: "0 0 10px" }}>
          Soft-deletes immediately.  30-day recovery window before hard delete.
          Type <code>DELETE_MY_DATA</code> to confirm.
        </p>
        <div style={{ display: "flex", gap: 8 }}>
          <input data-testid="privacy-delete-confirm"
                      type="text" value={confirm}
                      onChange={(e) => setConfirm(e.target.value)}
                      placeholder="DELETE_MY_DATA"
                      style={{ flex: 1, padding: "8px 12px",
                                  background: "#0b0b0b",
                                  border: "1px solid rgba(255,255,255,0.08)",
                                  borderRadius: 6, color: "#fff" }} />
          <button data-testid="privacy-delete-btn" onClick={doDelete}
                          style={{ background: "#ef4444", color: "#fff", border: "none",
                                      padding: "8px 14px", borderRadius: 6,
                                      cursor: "pointer" }}>
            Delete
          </button>
        </div>
      </section>

      <section data-testid="privacy-audit-section"
                      style={{ background: "#1f2937", borderRadius: 12,
                                  padding: 20 }}>
        <h3 style={{ color: "#fff", fontSize: 14, margin: "0 0 10px",
                                display: "flex", alignItems: "center", gap: 6 }}>
          <Lock size={14} /> Audit Log
        </h3>
        <div style={{ maxHeight: 240, overflowY: "auto",
                                fontFamily: "monospace", fontSize: 11,
                                color: "#9aa3af" }}>
          {audit.slice(0, 50).map((e, i) => (
            <div key={i} data-testid={`privacy-audit-row-${i}`}
                      style={{ padding: "4px 0", borderTop: "1px solid rgba(255,255,255,0.04)" }}>
              <span style={{ color: "#10b981" }}>{e.action}</span>
              {" · "}{e.timestamp?.slice(0, 19)}
              {e.action === "consent_change" &&
                ` · ${e.prev_level} → ${e.new_level}`}
            </div>
          ))}
          {audit.length === 0 && (
            <div style={{ fontStyle: "italic", padding: 12 }}>
              No events yet.</div>
          )}
        </div>
      </section>
    </div>
  );
}


// Phase J (M2) — location-share toggle for the Location Boost ad flow.
function LocationShareToggle() {
  const [state, setState] = useState({ has_location: null, lat: null, lng: null });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  useEffect(() => {
    let alive = true;
    axios.get(`${API}/api/user/location`, { withCredentials: true })
      .then((r) => { if (alive) setState(r.data); })
      .catch(() => { if (alive) setState({ has_location: false, lat: null, lng: null }); });
    return () => { alive = false; };
  }, []);

  const share = () => {
    if (!navigator.geolocation) {
      setErr("Your browser doesn't support geolocation."); return;
    }
    setBusy(true); setErr(null);
    navigator.geolocation.getCurrentPosition(async (pos) => {
      try {
        const { latitude, longitude, accuracy } = pos.coords;
        await axios.post(`${API}/api/user/location/ping`,
          { lat: latitude, lng: longitude, accuracy_meters: accuracy,
            source: "browser" },
          { withCredentials: true });
        setState({ has_location: true, lat: latitude, lng: longitude });
        toast.success("Location shared — local offers unlocked.");
      } catch (e) {
        setErr(e?.response?.data?.detail?.code || e.message);
      } finally { setBusy(false); }
    }, (e) => {
      setErr(`Geolocation denied: ${e.message}`);
      setBusy(false);
    }, { timeout: 10000, maximumAge: 60000 });
  };

  const stop = async () => {
    if (!window.confirm(
        "Stop sharing your location? You can re-enable later — but existing " +
        "location-boost ads won't reach you until you do.")) return;
    setBusy(true); setErr(null);
    try {
      await axios.delete(`${API}/api/user/location`, { withCredentials: true });
      setState({ has_location: false, lat: null, lng: null });
      toast.info("Location sharing turned off.");
    } catch (e) {
      setErr(e?.response?.data?.detail?.code || e.message);
    } finally { setBusy(false); }
  };

  return (
    <section style={{ background: "#1f2937", borderRadius: 12,
                                        padding: 20, marginBottom: 20 }}
                    data-testid="privacy-location-share">
      <h3 style={{ color: "#fff", fontSize: 14, margin: "0 0 8px",
                                display: "flex", alignItems: "center", gap: 6 }}>
        <MapPin size={14} /> Share my location for personalised offers
      </h3>
      <p style={{ color: "#9aa3af", fontSize: 12, margin: "0 0 12px" }}>
        FUUSIC uses your live location ONLY to show geofenced offers from
        nearby advertisers. Auto-expires after 60 min unless refreshed.
      </p>
      {state.has_location ? (
        <div style={{ display: "flex", justifyContent: "space-between",
                                    alignItems: "center", gap: 10 }}>
          <div style={{ color: "#10b981", fontSize: 12, fontFamily: "monospace" }}
                      data-testid="privacy-location-current">
            Sharing: {Number(state.lat).toFixed(4)}, {Number(state.lng).toFixed(4)}
          </div>
          <button onClick={stop} disabled={busy}
                          data-testid="privacy-location-stop"
                          style={{ background: "#ef4444", color: "#fff", border: "none",
                                      padding: "8px 14px", borderRadius: 6, cursor: "pointer",
                                      display: "inline-flex", alignItems: "center", gap: 6 }}>
            {busy && <Loader2 size={12} className="animate-spin" />} Stop sharing
          </button>
        </div>
      ) : (
        <button onClick={share} disabled={busy}
                        data-testid="privacy-location-share-btn"
                        style={{ background: "#3b82f6", color: "#fff", border: "none",
                                    padding: "8px 14px", borderRadius: 6, cursor: "pointer",
                                    display: "inline-flex", alignItems: "center", gap: 6 }}>
          {busy ? <Loader2 size={12} className="animate-spin" /> : <MapPin size={14} />}
          Share my location
        </button>
      )}
      {err && <div style={{ color: "#ef4444", fontSize: 11, marginTop: 6 }}
                                data-testid="privacy-location-error">{err}</div>}
    </section>
  );
}


// Phase M (M6) — retargeting opt-out toggle.  When opt-out=true the
// server drops the user from all audience_members rows and refuses to
// return retargeting candidates for them thereafter.
function RetargetingOptOutToggle() {
  const [optOut, setOptOut] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  useEffect(() => {
    let alive = true;
    axios.get(`${API}/api/user/retargeting/opt-out`, { withCredentials: true })
      .then((r) => { if (alive) setOptOut(!!r.data?.retargeting_opt_out); })
      .catch(() => { if (alive) setOptOut(false); });
    return () => { alive = false; };
  }, []);

  const flip = async () => {
    setBusy(true); setErr(null);
    try {
      const { data } = await axios.post(
        `${API}/api/user/retargeting/opt-out`,
        { opt_out: !optOut }, { withCredentials: true });
      setOptOut(!!data?.retargeting_opt_out);
      toast.info(data?.retargeting_opt_out
        ? "Retargeting off — you won't be added to audience segments."
        : "Retargeting re-enabled.");
    } catch (e) {
      setErr(e?.response?.data?.detail?.code || e.message);
    } finally { setBusy(false); }
  };

  return (
    <section style={{ background: "#1f2937", borderRadius: 12,
                                        padding: 20, marginBottom: 20 }}
                    data-testid="privacy-retargeting-opt-out">
      <h3 style={{ color: "#fff", fontSize: 14, margin: "0 0 8px",
                                display: "flex", alignItems: "center", gap: 6 }}>
        <Target size={14} /> Retargeting audiences
      </h3>
      <p style={{ color: "#9aa3af", fontSize: 12, margin: "0 0 12px" }}>
        Advertisers can define audience segments based on your past
        activity (coupons saved, podcasts finished, etc).  Opt out to
        remove yourself from ALL segments — advertisers only ever see
        aggregate counts, never individual user IDs.
      </p>
      <button onClick={flip} disabled={busy || optOut === null}
                        data-testid={optOut ? "privacy-retargeting-opt-in-btn"
                                                    : "privacy-retargeting-opt-out-btn"}
                        style={{ background: optOut ? "#10b981" : "#ef4444",
                                    color: "#fff", border: "none",
                                    padding: "8px 14px", borderRadius: 6, cursor: "pointer",
                                    display: "inline-flex", alignItems: "center", gap: 6 }}>
        {busy && <Loader2 size={12} className="animate-spin" />}
        {optOut ? "Re-enable retargeting" : "Opt out of retargeting"}
      </button>
      {err && <div style={{ color: "#ef4444", fontSize: 11, marginTop: 6 }}
                                data-testid="privacy-retargeting-error">{err}</div>}
    </section>
  );
}
