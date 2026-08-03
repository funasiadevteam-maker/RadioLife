/**
 * Phase 39 Session 6 — /places UI (the mandatory carryover from S5).
 * DRAFT watermark + map placeholder + place cards with confirm/reject/hide.
 */
import React, { useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { MapPin, Check, X, EyeOff, RefreshCw } from "lucide-react";
import BannerAdSlot from "@/components/BannerAdSlot";

const API = process.env.REACT_APP_BACKEND_URL || "";


export default function PlacesAndRoutes() {
  const [places, setPlaces]    = useState([]);
  const [consent, setConsent] = useState(0);
  const [busy, setBusy]          = useState(false);
  const [loading, setLoading] = useState(true);

  const refresh = async () => {
    setLoading(true);
    try {
      const c = await axios.get(`${API}/privacy/consent`, { withCredentials: true });
      setConsent(c.data.level || 0);
      if (c.data.level >= 3) {
        const p = await axios.get(`${API}/places/frequent`, { withCredentials: true });
        setPlaces(p.data.places || []);
      }
    } catch (e) { /* silent */ }
    setLoading(false);
  };
  useEffect(() => { refresh(); }, []);

  const detect = async () => {
    setBusy(true);
    try {
      const r = await axios.post(`${API}/places/frequent/refresh`, {}, { withCredentials: true });
      toast.success(`Detected ${r.data.clusters_found} place(s)`);
      await refresh();
    } catch (e) { toast.error("Detection failed."); }
    setBusy(false);
  };

  const act = async (pid, action, payload = {}) => {
    try {
      await axios.post(`${API}/places/frequent/${pid}/${action}`, payload, { withCredentials: true });
      toast.success(action === "hide" ? "Hidden" : action === "confirm" ? "Confirmed" : "Updated");
      await refresh();
    } catch (e) { toast.error("Action failed."); }
  };

  return (
    <div data-testid="places-page" style={{ maxWidth: 900, margin: "0 auto", padding: 24 }}>
      <div data-testid="places-draft-watermark"
            style={{ background: "rgba(245,158,11,0.1)", border: "1px dashed #f59e0b",
                      padding: "8px 14px", borderRadius: 6, color: "#f59e0b",
                      fontSize: 12, textAlign: "center", letterSpacing: 1,
                      fontWeight: 700, marginBottom: 18 }}>
        DRAFT — pending legal sign-off
      </div>
      <header style={{ display: "flex", justifyContent: "space-between",
                                  alignItems: "center", marginBottom: 18 }}>
        <h1 style={{ color: "#fff", fontSize: 22, fontWeight: 700, margin: 0,
                                display: "flex", alignItems: "center", gap: 8 }}>
          <MapPin size={20} color="#3b82f6" /> Your Frequent Places
        </h1>
        {consent >= 3 && (
          <button data-testid="places-refresh-btn" onClick={detect} disabled={busy}
                          style={{ background: "#3b82f6", color: "#fff", border: "none",
                                      padding: "8px 14px", borderRadius: 6,
                                      display: "inline-flex", alignItems: "center", gap: 6,
                                      cursor: busy ? "wait" : "pointer", opacity: busy ? 0.6 : 1 }}>
            <RefreshCw size={14} className={busy ? "animate-spin" : ""} />
            {busy ? "Detecting…" : "Refresh detection"}
          </button>
        )}
      </header>

      {loading ? (
        <div style={{ color: "#9aa3af", padding: 24 }}>Loading…</div>
      ) : consent < 3 ? (
        <div data-testid="places-empty-consent"
              style={{ background: "#1f2937", borderRadius: 12, padding: 28, textAlign: "center" }}>
          <p style={{ color: "#9aa3af", margin: "0 0 12px" }}>
            Enable Travel History to see your places.
          </p>
          <a href="/privacy" data-testid="places-enable-cta"
              style={{ display: "inline-block", background: "#10b981", color: "#0b0b0b",
                          padding: "8px 16px", borderRadius: 6, textDecoration: "none",
                          fontWeight: 600 }}>
            Go to Privacy Settings →
          </a>
        </div>
      ) : places.length === 0 ? (
        <div data-testid="places-empty-no-data"
              style={{ background: "#1f2937", borderRadius: 12, padding: 28,
                          textAlign: "center", color: "#9aa3af" }}>
          We're still learning your patterns — check back in a few days.
        </div>
      ) : (
        <div data-testid="places-list" style={{ display: "grid", gap: 12 }}>
          {places.map((p) => (
            <div key={p.place_id} data-testid={`places-card-${p.place_id}`}
                    style={{ background: "#1f2937", borderRadius: 12, padding: 16 }}>
              <div style={{ display: "flex", justifyContent: "space-between",
                                      alignItems: "center", marginBottom: 8 }}>
                <div>
                  <div style={{ color: "#fff", fontSize: 16, fontWeight: 600 }}>
                    {p.label || "Detected place"}
                    {p.user_confirmed === true && (
                      <span data-testid={`places-confirmed-badge-${p.place_id}`}
                                  style={{ marginLeft: 8, fontSize: 11, color: "#10b981" }}>
                        ✓ Confirmed
                      </span>
                    )}
                  </div>
                  <div style={{ color: "#9aa3af", fontSize: 12 }}>
                    {p.category || "place"} · {p.visit_count} visits ·
                    last seen {p.last_seen?.slice(0, 10) || "—"}
                  </div>
                </div>
                <div style={{ display: "flex", gap: 6 }}>
                  <button data-testid={`places-confirm-${p.place_id}`}
                                  onClick={() => act(p.place_id, "confirm", { confirmed: true })}
                                  style={btn("#10b981")}>
                    <Check size={12} /> Yes
                  </button>
                  <button data-testid={`places-reject-${p.place_id}`}
                                  onClick={() => act(p.place_id, "confirm", { confirmed: false })}
                                  style={btn("#9aa3af")}>
                    <X size={12} /> No
                  </button>
                  <button data-testid={`places-hide-${p.place_id}`}
                                  onClick={() => act(p.place_id, "hide")}
                                  style={btn("#ef4444")}>
                    <EyeOff size={12} /> Hide
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}


function btn(color) {
  return { background: "transparent", color, border: `1px solid ${color}`,
                  padding: "4px 10px", borderRadius: 4, fontSize: 12,
                  cursor: "pointer", display: "inline-flex", alignItems: "center", gap: 4 };
}
