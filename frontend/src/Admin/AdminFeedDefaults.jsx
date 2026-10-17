/** Admin — Feed Defaults.
 *
 *  Route: /admin/feed-defaults
 *  Sets the DEFAULT feed frequency mode per actor category (people, stations,
 *  businesses, …). A listener's own explicit per-entity choice always wins; these
 *  defaults decide how a freshly-followed account behaves until the user tunes it.
 *
 *  GET  /api/social/feed-preferences/defaults   (admin)
 *  PUT  /api/social/feed-preferences/defaults   (admin)  { defaults: {cat: mode} }
 */
import React, { useEffect, useState, useCallback } from "react";
import axios from "axios";
import { Toaster, toast } from "sonner";
import {
  SlidersHorizontal, Loader2, Save, Rss, Sparkles, Zap, BellOff,
} from "lucide-react";
import AdminSubNav from "@/AdminSubNav";
import { API } from "@/AuthContext";

const CATS = [
  { key: "person", label: "People you follow", desc: "Listeners & public profiles" },
  { key: "friend", label: "Friends", desc: "Accepted mutual connections" },
  { key: "station", label: "Radio stations", desc: "Community & flagship stations" },
  { key: "business", label: "Businesses & venues", desc: "Merchant pages" },
  { key: "creator", label: "Creators", desc: "Podcast & show creators" },
  { key: "advisor", label: "Advisors", desc: "Tarot / advisory profiles" },
  { key: "club", label: "Dream clubs", desc: "Community clubs" },
];

const MODES = [
  { key: "all_updates", label: "All Updates", Icon: Rss },
  { key: "daily_highlights", label: "Daily Highlights", Icon: Sparkles },
  { key: "live_only", label: "Live Only", Icon: Zap },
  { key: "mute", label: "Mute", Icon: BellOff },
];

const ACCENT = "#a855f7";

export default function AdminFeedDefaults() {
  const [defaults, setDefaults] = useState({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/social/feed-preferences/defaults`,
        { withCredentials: true });
      setDefaults(r.data?.defaults || {});
      setDirty(false);
    } catch (e) {
      toast.error("Couldn't load feed defaults");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const pick = (cat, mode) => {
    if (defaults[cat] === mode) return;
    setDefaults((d) => ({ ...d, [cat]: mode }));
    setDirty(true);
  };

  const save = async () => {
    setSaving(true);
    try {
      const r = await axios.put(`${API}/social/feed-preferences/defaults`,
        { defaults }, { withCredentials: true });
      setDefaults(r.data?.defaults || defaults);
      setDirty(false);
      toast.success("Feed defaults saved");
    } catch (e) {
      toast.error("Save failed — try again");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div data-testid="admin-feed-defaults-page"
         style={{ display: "flex", minHeight: "100vh", background: "#070710" }}>
      <Toaster richColors position="top-right" />
      <AdminSubNav />
      <main style={{ flex: 1, padding: "28px 32px", color: "#cbd5e1", overflowY: "auto" }}>
        <header style={{ display: "flex", justifyContent: "space-between",
                         alignItems: "center", marginBottom: 8 }}>
          <h1 style={{ display: "inline-flex", alignItems: "center", gap: 10,
                       color: "#fff", margin: 0, fontSize: 22 }}>
            <SlidersHorizontal size={20} color={ACCENT} /> Feed Defaults
          </h1>
          <button onClick={save} disabled={!dirty || saving}
                  data-testid="admin-feed-defaults-save"
                  style={{ display: "inline-flex", alignItems: "center", gap: 8,
                           padding: "9px 16px", borderRadius: 10, border: "none",
                           fontWeight: 700, fontSize: 13,
                           cursor: (!dirty || saving) ? "default" : "pointer",
                           opacity: (!dirty || saving) ? 0.5 : 1,
                           background: ACCENT, color: "#fff" }}>
            {saving ? <Loader2 size={15} className="spin" /> : <Save size={15} />}
            Save changes
          </button>
        </header>
        <p style={{ margin: "0 0 22px", fontSize: 13, color: "#8b8b9a", maxWidth: 640 }}>
          How a freshly-followed account shows up in a listener's feed by default.
          A listener's own per-account choice (via My Feed Preferences) always wins —
          these only set the starting point for new follows.
        </p>

        {loading ? (
          <div data-testid="admin-feed-defaults-loading"
               style={{ display: "flex", alignItems: "center", gap: 10, color: "#8b8b9a" }}>
            <Loader2 size={16} className="spin" /> Loading…
          </div>
        ) : (
          <div style={{ display: "grid", gap: 10, maxWidth: 820 }}>
            {CATS.map((c) => {
              const cur = defaults[c.key];
              return (
                <div key={c.key} data-testid={`admin-feed-default-row-${c.key}`}
                     style={{ background: "#0f0f17", border: "1px solid #25252f",
                              borderRadius: 14, padding: "14px 16px",
                              display: "flex", alignItems: "center", gap: 16,
                              flexWrap: "wrap" }}>
                  <div style={{ minWidth: 190, flex: "1 1 190px" }}>
                    <div style={{ color: "#fff", fontWeight: 700, fontSize: 14 }}>{c.label}</div>
                    <div style={{ color: "#6b6b7a", fontSize: 12 }}>{c.desc}</div>
                  </div>
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    {MODES.map((m) => {
                      const active = cur === m.key;
                      return (
                        <button key={m.key} onClick={() => pick(c.key, m.key)}
                                data-testid={`admin-feed-default-${c.key}-${m.key}`}
                                style={{ display: "inline-flex", alignItems: "center", gap: 6,
                                         padding: "8px 12px", borderRadius: 10, fontSize: 12.5,
                                         fontWeight: 700, cursor: "pointer",
                                         border: active ? `1px solid ${ACCENT}` : "1px solid #25252f",
                                         background: active ? "rgba(168,85,247,0.16)" : "transparent",
                                         color: active ? "#e9d5ff" : "#9b9bab" }}>
                          <m.Icon size={14} color={active ? ACCENT : "#6b6b7a"} />
                          {m.label}
                        </button>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </main>
    </div>
  );
}
