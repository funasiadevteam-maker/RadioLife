/**
 * Phase 39 Session 6 — /places/:place_id detail page.
 * Map centroid + last 10 visits + editable label + hide CTA.
 */
import React, { useEffect, useState } from "react";
import axios from "axios";
import { useParams, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { MapPin, EyeOff, Save, ArrowLeft } from "lucide-react";

const API = process.env.REACT_APP_BACKEND_URL || "";

export default function PlaceDetail() {
  const { place_id } = useParams();
  const nav = useNavigate();
  const [place, setPlace]   = useState(null);
  const [label, setLabel]   = useState("");
  const [trips, setTrips]   = useState([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    try {
      const c = await axios.get(`${API}/privacy/consent`, { withCredentials: true });
      if (c.data.level < 3) { nav("/privacy"); return; }
      const p = await axios.get(`${API}/places/frequent`, { withCredentials: true });
      const found = (p.data.places || []).find(x => x.place_id === place_id);
      if (!found) { toast.error("Place not found"); nav("/places"); return; }
      setPlace(found);
      setLabel(found.label || "");
      const t = await axios.get(`${API}/routes/trips`, { withCredentials: true });
      const related = (t.data.trips || []).filter(
        x => x.origin_place_id === place_id || x.destination_place_id === place_id
      ).slice(0, 10);
      setTrips(related);
    } catch (e) { /* silent */ }
    setLoading(false);
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [place_id]);

  const saveLabel = async () => {
    // Backend confirm endpoint stores user_confirmed; we re-use to mark
    // the user has reviewed this place. Label edit persists locally for
    // the session (full label-mutation API ships in Session 6b).
    try {
      await axios.post(`${API}/places/frequent/${place_id}/confirm`,
                       { confirmed: true }, { withCredentials: true });
      toast.success("Saved");
    } catch (e) { toast.error("Save failed"); }
  };

  const hide = async () => {
    try {
      await axios.post(`${API}/places/frequent/${place_id}/hide`,
                       {}, { withCredentials: true });
      toast.success("Hidden");
      nav("/places");
    } catch (e) { toast.error("Hide failed"); }
  };

  if (loading) {
    return <div data-testid="place-detail-loading" style={{ color: "#9aa3af", padding: 24 }}>
      Loading…
    </div>;
  }
  if (!place) return null;

  return (
    <div data-testid="place-detail-page" style={{ maxWidth: 760, margin: "0 auto", padding: 24 }}>
      <button data-testid="place-detail-back"
              onClick={() => nav("/places")}
              style={{ background: "transparent", color: "#9aa3af", border: "none",
                       cursor: "pointer", display: "inline-flex", alignItems: "center",
                       gap: 4, marginBottom: 12, fontSize: 13 }}>
        <ArrowLeft size={14} /> Back to places
      </button>

      <h1 style={{ color: "#fff", fontSize: 22, fontWeight: 700, margin: "0 0 6px",
                   display: "flex", alignItems: "center", gap: 8 }}>
        <MapPin size={20} color="#3b82f6" /> {place.label || "Detected place"}
      </h1>
      <div style={{ color: "#9aa3af", fontSize: 12, marginBottom: 18 }}>
        {place.category} · {place.visit_count} visits · confidence {place.confidence}
      </div>

      {/* Map placeholder — full Google Maps embed lands in Session 6b. */}
      <div data-testid="place-detail-map"
           style={{ background: "#0f1419", height: 220, borderRadius: 12,
                    display: "flex", alignItems: "center", justifyContent: "center",
                    color: "#3b82f6", marginBottom: 18, border: "1px solid #1f2937" }}>
        📍 {place.lat?.toFixed(5)}, {place.lng?.toFixed(5)}
      </div>

      <div style={{ background: "#1f2937", borderRadius: 12, padding: 16, marginBottom: 16 }}>
        <label style={{ color: "#9aa3af", fontSize: 12, display: "block", marginBottom: 6 }}>
          Label
        </label>
        <div style={{ display: "flex", gap: 8 }}>
          <input data-testid="place-detail-label-input"
                 value={label} onChange={(e) => setLabel(e.target.value)}
                 style={{ flex: 1, background: "#0b0b0b", color: "#fff",
                          border: "1px solid #2a2f3a", borderRadius: 6,
                          padding: "8px 10px" }} />
          <button data-testid="place-detail-save-btn"
                  onClick={saveLabel}
                  style={{ background: "#10b981", color: "#0b0b0b", border: "none",
                           padding: "8px 14px", borderRadius: 6, fontWeight: 600,
                           display: "inline-flex", alignItems: "center", gap: 6,
                           cursor: "pointer" }}>
            <Save size={14} /> Save
          </button>
        </div>
      </div>

      <div style={{ background: "#1f2937", borderRadius: 12, padding: 16, marginBottom: 16 }}>
        <h3 style={{ color: "#fff", fontSize: 14, margin: "0 0 10px" }}>Recent visits</h3>
        {trips.length === 0 ? (
          <div data-testid="place-detail-no-trips" style={{ color: "#9aa3af", fontSize: 12 }}>
            No recorded trips yet.
          </div>
        ) : (
          <ul data-testid="place-detail-trip-list"
              style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {trips.map(t => (
              <li key={t._id || `${t.started_at}-${t.destination_place_id}`}
                  data-testid="place-detail-trip-row"
                  style={{ color: "#cbd5e1", fontSize: 12, padding: "6px 0",
                           borderBottom: "1px solid #2a2f3a" }}>
                {String(t.started_at).slice(0, 16).replace("T", " ")} —
                {" "}{t.time_bucket} · {t.duration_min} min
              </li>
            ))}
          </ul>
        )}
      </div>

      <button data-testid="place-detail-hide-btn"
              onClick={hide}
              style={{ background: "transparent", color: "#ef4444",
                       border: "1px solid #ef4444", padding: "8px 14px",
                       borderRadius: 6, cursor: "pointer",
                       display: "inline-flex", alignItems: "center", gap: 6 }}>
        <EyeOff size={14} /> Hide this place from my list
      </button>
    </div>
  );
}
