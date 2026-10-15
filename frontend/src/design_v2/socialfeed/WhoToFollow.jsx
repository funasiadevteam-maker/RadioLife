// FUUSIC Social — "Who to Follow" interest-based suggestions.
// Shows People / Creators / Stations / Businesses / Clubs / Advisors with a
// plain-language reason, plus Follow / Not Interested / Hide. Theme-aware.
import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import {
  UserPlus, Check, X, Loader2, Sparkles, Radio, Store, Users, Moon, Mic2,
} from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

const TYPE_ICON = {
  person: Users, creator: Mic2, advisor: Moon, station: Radio,
  business: Store, club: Users,
};

const followUrl = (s) => {
  switch (s.actor_type) {
    case "station": return `${API}/stations/${s.actor_id}/follow`;
    case "business": return `${API}/business/${s.actor_id}/follow`;
    case "club": return `${API}/social/clubs/${s.actor_id}/join`;
    default: return `${API}/social/follow/${s.actor_id}`;
  }
};

export default function WhoToFollow({ t, onFollowed, limit = 10 }) {
  const [items, setItems] = useState(null);
  const [state, setState] = useState({}); // id -> "following" | "busy"

  const load = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/social/who-to-follow`,
        { params: { limit }, withCredentials: true });
      setItems(r.data?.items || []);
    } catch (_e) { setItems([]); }
  }, [limit]);
  useEffect(() => { load(); }, [load]);

  const key = (s) => `${s.actor_type}:${s.actor_id}`;

  const follow = async (s) => {
    const k = key(s);
    setState((p) => ({ ...p, [k]: "busy" }));
    try {
      await axios.post(followUrl(s), {}, { withCredentials: true });
      setState((p) => ({ ...p, [k]: "following" }));
      onFollowed && onFollowed(s);
      setTimeout(() => setItems((prev) => (prev || []).filter((x) => key(x) !== k)), 900);
    } catch (_e) { setState((p) => ({ ...p, [k]: undefined })); }
  };

  const dismiss = async (s, action) => {
    const k = key(s);
    setItems((prev) => (prev || []).filter((x) => key(x) !== k));
    axios.post(`${API}/social/suggestions/dismiss`,
      { actor_type: s.actor_type, actor_id: s.actor_id, action },
      { withCredentials: true }).catch(() => {});
  };

  if (items && items.length === 0) return null;

  return (
    <div data-testid="who-to-follow" style={{ background: t.card, border: `1px solid ${t.border}`, borderRadius: 18, boxShadow: t.shadow, padding: 14 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 10 }}>
        <Sparkles size={16} color={t.accent} />
        <span style={{ fontWeight: 900, fontSize: 15, color: t.text }}>Who to Follow</span>
      </div>
      {!items ? (
        <div style={{ display: "flex", gap: 10 }}>
          {[0, 1, 2].map((i) => (
            <div key={i} style={{ flex: "0 0 200px", height: 150, borderRadius: 14, background: t.chip }} />
          ))}
        </div>
      ) : (
        <div style={{ display: "flex", gap: 10, overflowX: "auto", paddingBottom: 4 }} className="no-scrollbar">
          {items.map((s) => {
            const k = key(s);
            const st = state[k];
            const Icon = TYPE_ICON[s.actor_type] || Users;
            return (
              <div key={k} data-testid={`wtf-card-${s.actor_type}-${s.actor_id}`}
                style={{ flex: "0 0 210px", position: "relative", borderRadius: 14, border: `1px solid ${t.border}`, background: t.cardAlt, padding: 14, display: "flex", flexDirection: "column", alignItems: "center", textAlign: "center" }}>
                <button onClick={() => dismiss(s, "hide")} data-testid={`wtf-hide-${s.actor_id}`} title="Hide suggestion"
                  style={{ position: "absolute", top: 8, right: 8, width: 24, height: 24, borderRadius: 999, border: "none", cursor: "pointer", background: t.chip, color: t.muted, display: "grid", placeItems: "center" }}>
                  <X size={13} />
                </button>
                <span style={{ width: 56, height: 56, borderRadius: 999, overflow: "hidden", background: t.chip, display: "grid", placeItems: "center", marginBottom: 8 }}>
                  {s.avatar_url
                    ? <img src={s.avatar_url} alt="" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                    : <Icon size={24} color={t.accent} />}
                </span>
                <div style={{ fontWeight: 800, fontSize: 13.5, color: t.text, width: "100%", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{s.name}</div>
                <div style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 10.5, color: t.muted, margin: "3px 0" }}>
                  <Icon size={11} /> <span style={{ textTransform: "capitalize" }}>{s.category || s.actor_type}</span>
                </div>
                <div style={{ fontSize: 11, color: t.accent, fontWeight: 700, background: t.accentSoft, borderRadius: 999, padding: "3px 9px", marginBottom: 10, maxWidth: "100%", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                  {s.reason}
                </div>
                <button onClick={() => follow(s)} disabled={st === "busy" || st === "following"}
                  data-testid={`wtf-follow-${s.actor_id}`}
                  style={{ width: "100%", display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 6, padding: "8px", borderRadius: 999, border: "none", cursor: "pointer", fontWeight: 800, fontSize: 13, color: "#fff", background: st === "following" ? "#22c55e" : t.accentGrad, opacity: st === "busy" ? 0.7 : 1 }}>
                  {st === "busy" ? <Loader2 size={14} className="sf-spin" />
                    : st === "following" ? <><Check size={14} /> Following</>
                    : <><UserPlus size={14} /> Follow</>}
                </button>
                <button onClick={() => dismiss(s, "not_interested")} data-testid={`wtf-notinterested-${s.actor_id}`}
                  style={{ marginTop: 6, background: "none", border: "none", cursor: "pointer", color: t.muted, fontSize: 11, fontWeight: 600 }}>
                  Not interested
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
