/** Phase 41 P2 — News Preferences picker (account settings tile). */
import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { Newspaper, MapPin, Check, ArrowLeft } from "lucide-react";
import { API } from "@/AuthContext";

const CATEGORIES = [
  { id: "top",           label: "Top Headlines" },
  { id: "politics",      label: "Politics" },
  { id: "business",      label: "Business" },
  { id: "technology",    label: "Technology" },
  { id: "sports",        label: "Sports" },
  { id: "entertainment", label: "Entertainment" },
  { id: "world",         label: "World" },
  { id: "health",        label: "Health" },
  { id: "science",       label: "Science" },
];

export default function NewsPreferences() {
  const [selected, setSelected] = useState([]);
  const [localOn,  setLocalOn]  = useState(false);
  const [city,     setCity]     = useState(null);
  const [saving,   setSaving]   = useState(false);
  const [saved,    setSaved]    = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const r = await axios.get(`${API}/news/preferences`,
          { withCredentials: true });
        setSelected(r.data?.categories || []);
        setLocalOn(!!r.data?.local_enabled);
        setCity(r.data?.city || null);
      } catch (e) { /* silent */ }
    })();
  }, []);

  const toggle = (id) =>
    setSelected(prev => prev.includes(id)
      ? prev.filter(x => x !== id)
      : [...prev, id].slice(0, 8));

  const save = async () => {
    setSaving(true); setSaved(false);
    try {
      await axios.put(`${API}/news/preferences`,
        { categories: selected, local_enabled: localOn },
        { withCredentials: true });
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (e) { /* silent */ }
    setSaving(false);
  };

  return (
    <div data-testid="news-preferences-page"
         style={{ maxWidth: 720, margin: "0 auto", padding: 24, color: "#fff" }}>
      <Link to="/" data-testid="news-prefs-back"
            style={{ display: "inline-flex", alignItems: "center", gap: 6,
                     color: "#9aa3af", textDecoration: "none", fontSize: 13,
                     marginBottom: 18 }}>
        <ArrowLeft size={14} /> Back
      </Link>
      <h1 style={{ display: "flex", alignItems: "center", gap: 10,
                   fontSize: 26, fontWeight: 700, margin: "0 0 8px" }}>
        <Newspaper size={22} color="#00d9ff" /> News Interests
      </h1>
      <p style={{ color: "#9aa3af", fontSize: 14, marginBottom: 22 }}>
        Pick up to 8 topics — we'll filter your daily news feed and FUUSIC
        News Radio summaries to match.
      </p>

      <div data-testid="news-prefs-chips"
           style={{ display: "flex", flexWrap: "wrap", gap: 8,
                    marginBottom: 26 }}>
        {CATEGORIES.map(c => {
          const on = selected.includes(c.id);
          return (
            <button key={c.id}
                    data-testid={`news-pref-${c.id}`}
                    onClick={() => toggle(c.id)}
                    style={{ display: "inline-flex", alignItems: "center",
                             gap: 6,
                             background: on ? "#00d9ff" : "rgba(255,255,255,0.05)",
                             color: on ? "#0b0b0b" : "#cbd5e1",
                             border: "1px solid rgba(255,255,255,0.08)",
                             padding: "8px 14px", borderRadius: 18,
                             fontSize: 13, fontWeight: on ? 600 : 400,
                             cursor: "pointer" }}>
              {on && <Check size={13} />}
              {c.label}
            </button>
          );
        })}
      </div>

      <div data-testid="news-prefs-local"
           style={{ background: "rgba(255,255,255,0.03)",
                    border: "1px solid rgba(255,255,255,0.05)",
                    borderRadius: 12, padding: 16, marginBottom: 26,
                    display: "flex", alignItems: "center", gap: 14 }}>
        <MapPin size={20} color="#00d9ff" />
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 600, fontSize: 14 }}>Local news</div>
          <div style={{ color: "#9aa3af", fontSize: 12, marginTop: 2 }}>
            Surface headlines from {city || "your city"}.
          </div>
        </div>
        <button data-testid="news-prefs-local-toggle"
                onClick={() => setLocalOn(v => !v)}
                style={{ width: 44, height: 24, borderRadius: 14,
                         background: localOn ? "#00d9ff" : "rgba(255,255,255,0.1)",
                         border: "none", cursor: "pointer", position: "relative" }}>
          <span style={{ position: "absolute", top: 3, left: localOn ? 23 : 3,
                          width: 18, height: 18, borderRadius: "50%",
                          background: "#fff", transition: "left 0.15s" }} />
        </button>
      </div>

      <button data-testid="news-prefs-save"
              onClick={save} disabled={saving}
              style={{ background: "#00d9ff", color: "#0b0b0b",
                       border: "none", padding: "10px 18px", borderRadius: 8,
                       fontWeight: 600, cursor: "pointer",
                       opacity: saving ? 0.6 : 1 }}>
        {saving ? "Saving..." : saved ? "Saved ✓" : "Save preferences"}
      </button>
    </div>
  );
}
