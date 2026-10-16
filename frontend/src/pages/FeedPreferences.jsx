// Settings → My Feed Preferences. Per-followed-entity frequency control that
// mirrors the server-side modes applied in services/social_feed.build_feed:
//   All Updates · Daily Highlights · Live Only · Mute
// Backed by GET/PUT /api/social/feed-preferences.
import { useEffect, useState, useCallback, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import {
  ArrowLeft, Loader2, Rss, Sparkles, Zap, BellOff, Users, Building2, Radio as RadioIcon,
} from "lucide-react";
import { sfTokens, initials } from "@/design_v2/socialfeed/sfTheme";
import { useThemeStore } from "@/theme/useTheme";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

export const FEED_MODES = [
  { key: "all_updates", label: "All", full: "All Updates", Icon: Rss, desc: "Every post, as it happens" },
  { key: "daily_highlights", label: "Daily", full: "Daily Highlights", Icon: Sparkles, desc: "Grouped into one daily digest" },
  { key: "live_only", label: "Live", full: "Live Only", Icon: Zap, desc: "Only when they go live" },
  { key: "mute", label: "Mute", full: "Mute", Icon: BellOff, desc: "Hidden from your feed (still followed)" },
];

const GROUPS = [
  { key: "people", type: "person", title: "People", Icon: Users },
  { key: "stations", type: "station", title: "Stations", Icon: RadioIcon },
  { key: "businesses", type: "business", title: "Businesses", Icon: Building2 },
];

export default function FeedPreferences() {
  const nav = useNavigate();
  const appearance = useThemeStore((s) => s.theme);
  const t = sfTokens(appearance);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/social/feed-preferences`, { withCredentials: true });
      setData(r.data || {});
    } catch (_e) {
      setData({ people: [], stations: [], businesses: [] });
    } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const total = useMemo(
    () => GROUPS.reduce((n, g) => n + (data?.[g.key]?.length || 0), 0), [data]);

  const setMode = async (groupKey, type, entity, mode) => {
    if (entity.frequency_mode === mode) return;
    const id = entity.actor_id;
    setSaving(`${type}:${id}`);
    setData((d) => ({
      ...d,
      [groupKey]: (d[groupKey] || []).map((e) =>
        e.actor_id === id ? { ...e, frequency_mode: mode, explicitly_set: true } : e),
    }));
    try {
      await axios.put(`${API}/social/feed-preferences/${type}/${id}`,
        { frequency_mode: mode }, { withCredentials: true });
      const m = FEED_MODES.find((x) => x.key === mode);
      toast.success(`${entity.name} · ${m?.full || mode}`);
    } catch (_e) {
      toast.error("Couldn't update — try again");
      load();
    } finally { setSaving(null); }
  };

  return (
    <div data-testid="feed-prefs-root"
      style={{ minHeight: "100vh", background: t.canvas, color: t.text }}>
      <div style={{ maxWidth: 680, margin: "0 auto", padding: "16px 14px 60px" }}>
        <button onClick={() => nav(-1)} data-testid="feed-prefs-back" className="sf-press"
          style={{ display: "inline-flex", alignItems: "center", gap: 6, background: "none",
                   border: "none", color: t.text2, cursor: "pointer", fontSize: 14, fontWeight: 700, marginBottom: 14 }}>
          <ArrowLeft size={17} /> Back
        </button>

        <div style={{ display: "flex", alignItems: "center", gap: 8, color: t.accent, fontSize: 11, fontWeight: 900, letterSpacing: ".08em", textTransform: "uppercase" }}>
          <Sparkles size={13} /> My Feed Preferences
        </div>
        <h1 style={{ margin: "6px 0 4px", fontSize: 26, fontWeight: 900, color: t.text }}>Control your feed</h1>
        <p style={{ margin: 0, fontSize: 14, color: t.muted, maxWidth: 520, lineHeight: 1.5 }}>
          Choose how often each thing you follow shows up. Your choices always win over the
          smart ranking — set an account to Mute and it stays followed but off your feed.
        </p>

        {loading ? (
          <div data-testid="feed-prefs-loading" style={{ display: "grid", placeItems: "center", padding: "60px 0" }}>
            <Loader2 size={22} className="sf-spin" color={t.accent} />
          </div>
        ) : total === 0 ? (
          <div data-testid="feed-prefs-empty"
            style={{ marginTop: 28, textAlign: "center", padding: "40px 20px", border: `1px solid ${t.border}`, borderRadius: 18, background: t.card }}>
            <Users size={28} color={t.accent} />
            <div style={{ fontWeight: 900, fontSize: 17, color: t.text, marginTop: 10 }}>Nothing to tune yet</div>
            <div style={{ fontSize: 13.5, color: t.muted, marginTop: 4, maxWidth: 340, marginInline: "auto" }}>
              Follow people, stations and businesses, then come back to fine-tune how much you see from each.
            </div>
            <button onClick={() => nav("/social")} data-testid="feed-prefs-find" className="sf-press"
              style={{ marginTop: 16, padding: "10px 20px", borderRadius: 999, border: "none", cursor: "pointer", color: "#fff", background: t.accentGrad, fontWeight: 800, fontSize: 13.5 }}>
              Find people to follow
            </button>
          </div>
        ) : (
          <div style={{ marginTop: 20, display: "flex", flexDirection: "column", gap: 22 }}>
            {GROUPS.map((g) => {
              const items = data?.[g.key] || [];
              if (!items.length) return null;
              return (
                <section key={g.key} data-testid={`feed-prefs-group-${g.key}`}>
                  <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 10 }}>
                    <g.Icon size={15} color={t.accent} />
                    <span style={{ fontSize: 11.5, fontWeight: 900, letterSpacing: ".08em", textTransform: "uppercase", color: t.text2 }}>
                      {g.title} · {items.length}
                    </span>
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                    {items.map((e) => (
                      <EntityCard key={e.actor_id} t={t} entity={e} groupKey={g.key} type={g.type}
                        saving={saving === `${g.type}:${e.actor_id}`} onSet={setMode} />
                    ))}
                  </div>
                </section>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

function EntityCard({ t, entity, groupKey, type, saving, onSet }) {
  const mode = entity.frequency_mode || "all_updates";
  return (
    <div data-testid={`feed-prefs-row-${type}-${entity.actor_id}`}
      style={{ background: t.card, border: `1px solid ${t.border}`, borderRadius: 16, padding: 12, boxShadow: t.shadow }}>
      <div style={{ display: "flex", alignItems: "center", gap: 11, marginBottom: 11 }}>
        {entity.avatar_url ? (
          <img src={entity.avatar_url} alt="" loading="lazy"
            style={{ width: 42, height: 42, borderRadius: 999, objectFit: "cover", flexShrink: 0 }} />
        ) : (
          <span style={{ width: 42, height: 42, borderRadius: 999, flexShrink: 0, display: "grid", placeItems: "center", color: "#fff", fontWeight: 800, background: t.accentGrad }}>
            {initials(entity.name)}
          </span>
        )}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontWeight: 800, fontSize: 14.5, color: t.text, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {entity.name}
          </div>
          <div style={{ fontSize: 11.5, color: t.muted }}>
            {FEED_MODES.find((m) => m.key === mode)?.desc}
            {!entity.explicitly_set && <span style={{ color: t.accent, fontWeight: 700 }}> · default</span>}
          </div>
        </div>
        {saving && <Loader2 size={16} className="sf-spin" color={t.accent} />}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 6 }}>
        {FEED_MODES.map((m) => {
          const active = m.key === mode;
          return (
            <button key={m.key} onClick={() => onSet(groupKey, type, entity, m.key)}
              data-testid={`feed-prefs-mode-${type}-${entity.actor_id}-${m.key}`} className="sf-press"
              title={m.full}
              style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 4,
                       padding: "9px 4px", borderRadius: 11, cursor: "pointer",
                       border: `1px solid ${active ? t.accent : t.border}`,
                       background: active ? t.accentSoft : "transparent",
                       color: active ? t.accent : t.text2, fontWeight: 800, fontSize: 11.5 }}>
              <m.Icon size={16} />
              {m.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
