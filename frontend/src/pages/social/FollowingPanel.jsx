// FUUSIC Social V2 — Following management panel.
// Unified view of everyone/everything the user follows, grouped by type,
// with search, type filters, unfollow, and "view profile". Reachable both as
// a slide-over (from the header FOLLOWING stat) and as the /social/following route.
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import {
  X, Search, Loader2, Users, Radio, Store, Moon, Sparkles, Mic2, UserMinus,
} from "lucide-react";
import { Avatar } from "./SocialV2";

const BACKEND = process.env.REACT_APP_BACKEND_URL || "";
const social = axios.create({ baseURL: `${BACKEND}/api/social`, withCredentials: true });
const root = axios.create({ baseURL: `${BACKEND}/api`, withCredentials: true });

const FILTERS = [
  { key: "all", label: "All", icon: Sparkles },
  { key: "people", label: "People", icon: Users },
  { key: "creators", label: "Creators", icon: Mic2 },
  { key: "advisors", label: "Advisors", icon: Moon },
  { key: "businesses", label: "Businesses", icon: Store },
  { key: "stations", label: "Stations", icon: Radio },
  { key: "clubs", label: "Clubs", icon: Users },
];

const fireEvent = (event, extra = {}) =>
  social.post("/feed-events", { event, ...extra }).catch(() => {});

export function FollowingPanel({ onClose }) {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("all");
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try { const r = await social.get("/following"); setData(r.data); }
    catch (_) { /* soft */ } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); fireEvent("following_page_view"); }, [load]);

  const groups = useMemo(() => {
    if (!data) return [];
    const map = {
      people: ["People", data.people], creators: ["Creators", data.creators],
      advisors: ["Advisors", data.advisors], businesses: ["Businesses", data.businesses],
      stations: ["Stations", data.stations], clubs: ["Clubs", data.clubs],
    };
    const keys = filter === "all" ? Object.keys(map) : [filter];
    const ql = q.trim().toLowerCase();
    return keys.map((k) => {
      const [label, items] = map[k];
      const filtered = (items || []).filter(
        (it) => !ql || (it.name || "").toLowerCase().includes(ql));
      return { key: k, label, items: filtered };
    }).filter((g) => g.items.length > 0);
  }, [data, filter, q]);

  const unfollow = async (kind, item) => {
    const id = item.user_id || item.business_id || item.station_id || item.club_slug;
    setBusy(id);
    try {
      if (kind === "people" || kind === "creators" || kind === "advisors")
        await social.delete(`/follow/${item.user_id}`);
      else if (kind === "businesses")
        await root.post(`/business/${item.business_id}/unfollow`);
      else if (kind === "stations")
        await root.post(`/stations/${item.station_id}/unfollow`);
      else if (kind === "clubs")
        await social.post(`/clubs/${item.club_slug}/leave`);
      fireEvent("following_unfollow", { item_id: id, item_type: kind });
      toast.success("Unfollowed");
      await load();
    } catch (_) { toast.error("Couldn't unfollow"); }
    finally { setBusy(null); }
  };

  const openProfile = (kind, item) => {
    fireEvent("following_profile_open", { item_type: kind });
    if (kind === "stations" && item.slug) navigate(`/r/${item.slug}`);
    else if (kind === "businesses" && item.business_id) navigate(`/business/${item.business_id}`);
    else if (kind === "clubs") navigate("/social/dreams");
  };

  const total = data?.count || 0;
  return (
    <div className="fixed inset-0 z-[70] flex justify-end bg-black/70 backdrop-blur-sm"
         onClick={onClose} data-testid="following-panel">
      <div className="w-full sm:max-w-md h-full overflow-hidden flex flex-col border-l border-white/10"
           style={{ background: "linear-gradient(180deg,#0d0a24,#0a0a14)" }}
           onClick={(e) => e.stopPropagation()}>
        <div className="p-5 pb-3 border-b border-white/10">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-xl font-black">People you follow</h2>
              <p className="text-xs text-slate-400 mt-0.5">{total} following</p>
            </div>
            <button type="button" onClick={onClose} data-testid="following-close"
                    className="w-9 h-9 grid place-items-center rounded-full bg-white/10 hover:bg-white/20">
              <X size={18} />
            </button>
          </div>
          <div className="mt-3 flex items-center gap-2 rounded-full bg-white/[0.05] border border-white/10 px-3">
            <Search size={15} className="text-slate-400" />
            <input value={q} onChange={(e) => setQ(e.target.value)} data-testid="following-search"
                   placeholder="Search who you follow…"
                   className="flex-1 bg-transparent py-2.5 text-sm outline-none" />
          </div>
          <div className="mt-3 flex gap-1.5 overflow-x-auto no-scrollbar" data-testid="following-filters">
            {FILTERS.map((f) => {
              const active = filter === f.key;
              return (
                <button key={f.key} type="button"
                        onClick={() => { setFilter(f.key); fireEvent("following_filter", { meta: { filter: f.key } }); }}
                        data-testid={`following-filter-${f.key}`}
                        className={`flex-shrink-0 inline-flex items-center gap-1.5 px-3 h-9 rounded-full text-xs font-bold transition
                          ${active ? "text-white" : "text-slate-400 bg-white/[0.04]"}`}
                        style={active ? { background: "linear-gradient(135deg,#a855f7,#ec4899)" } : undefined}>
                  <f.icon size={13} /> {f.label}
                </button>
              );
            })}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto no-scrollbar p-4 space-y-6" data-testid="following-list">
          {loading ? (
            <div className="flex justify-center py-20"><Loader2 className="animate-spin text-purple-400" /></div>
          ) : groups.length === 0 ? (
            <EmptyFollowing navigate={navigate} onClose={onClose} />
          ) : groups.map((g) => (
            <div key={g.key}>
              <div className="text-[11px] font-black uppercase tracking-[0.18em] text-slate-400 mb-2">
                {g.label} · {g.items.length}
              </div>
              <div className="space-y-2">
                {g.items.map((it) => {
                  const id = it.user_id || it.business_id || it.station_id || it.club_slug;
                  return (
                    <div key={id} data-testid={`following-item-${id}`}
                         className="flex items-center gap-3 rounded-2xl p-3 bg-white/[0.04] border border-white/10">
                      <button type="button" onClick={() => openProfile(g.key, it)} className="shrink-0">
                        <Avatar name={it.name} url={it.avatar_url} size={44} />
                      </button>
                      <div className="min-w-0 flex-1" onClick={() => openProfile(g.key, it)}>
                        <div className="text-sm font-bold truncate">{it.name}</div>
                        <div className="text-[11px] text-slate-400 truncate capitalize">
                          {it.category || it.type}
                        </div>
                      </div>
                      <button type="button" onClick={() => unfollow(g.key, it)}
                              disabled={busy === id} data-testid={`following-unfollow-${id}`}
                              className="inline-flex items-center gap-1.5 h-9 px-3 rounded-full text-xs font-bold bg-white/10 hover:bg-white/20 disabled:opacity-60">
                        {busy === id ? <Loader2 size={13} className="animate-spin" />
                          : <UserMinus size={13} />} Unfollow
                      </button>
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function EmptyFollowing({ navigate, onClose }) {
  const go = (path) => { onClose?.(); navigate(path); };
  return (
    <div className="rounded-3xl border border-white/10 bg-white/[0.03] p-8 text-center"
         data-testid="following-empty">
      <span className="inline-grid place-items-center w-16 h-16 rounded-2xl mb-4"
            style={{ background: "linear-gradient(135deg,#a855f7,#ec4899)" }}>
        <Users size={28} className="text-white" />
      </span>
      <h3 className="text-xl font-black">Build your FUUSIC feed</h3>
      <p className="text-slate-400 mt-2 text-sm">
        Follow people, businesses, creators and clubs you care about to fill your wall.
      </p>
      <div className="mt-4 flex flex-col gap-2">
        <button type="button" onClick={() => go("/social?tab=friends")} data-testid="following-find-people"
                className="h-11 rounded-full font-bold text-white"
                style={{ background: "linear-gradient(135deg,#a855f7,#ec4899)" }}>Find people</button>
        <button type="button" onClick={() => go("/social/dreams")}
                className="h-11 rounded-full font-bold bg-white/10">Explore clubs</button>
        <button type="button" onClick={() => go("/community")}
                className="h-11 rounded-full font-bold bg-white/10">Discover stations</button>
      </div>
    </div>
  );
}

export default FollowingPanel;
