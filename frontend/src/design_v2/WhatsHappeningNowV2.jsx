import React from "react";
import { useNavigate } from "react-router-dom";
import { Users, Radio, Sparkles, ChevronRight, Bell } from "lucide-react";
import { fireV2Event } from "./analytics";

// Bridge from brand → Social. Real friend / live activity (never fabricated).
// `data` = payload from GET /api/social/home. Honest empty state when quiet.
export default function WhatsHappeningNowV2({ title = "What's Happening Now", data }) {
  const navigate = useNavigate();
  const happening = data?.happening_now || {};
  const friends = Array.isArray(data?.friends_now) ? data.friends_now : [];
  const rooms = Array.isArray(data?.suggested_rooms) ? data.suggested_rooms : [];
  const requests = Number(data?.counts?.friend_requests || 0);

  const friendsOnline = Number(happening.friends_online || friends.length || 0);
  const liveExp = Number(happening.live_experiences || rooms.length || 0);

  const open = (to, meta) => {
    fireV2Event("home_whats_happening_click", { meta });
    navigate(to);
  };

  const hasActivity = friends.length > 0 || rooms.length > 0
    || friendsOnline > 0 || liveExp > 0 || requests > 0;

  // Empty state — invite into Social instead of showing fake counts.
  if (!hasActivity) {
    return (
      <section data-testid="nlv2-whats-happening">
        <div className="mb-4">
          <h2 className="text-xl font-bold">{title}</h2>
        </div>
        <button
          type="button"
          onClick={() => open("/social", "empty")}
          data-testid="nlv2-happening-empty"
          className="w-full nlv2-glass-strong nlv2-card-hover rounded-3xl p-6 text-left flex items-center gap-4 relative overflow-hidden">
          <div className="absolute -right-8 -top-8 w-40 h-40 rounded-full"
            style={{ background: "rgba(45,212,191,0.18)", filter: "blur(30px)" }} />
          <div className="w-14 h-14 rounded-2xl grid place-items-center shrink-0"
            style={{ background: "linear-gradient(135deg,#14b8a6,#22c55e)" }}>
            <Users size={24} color="#fff" />
          </div>
          <div className="min-w-0 flex-1 relative z-10">
            <div className="text-lg font-black">Discover Social</div>
            <div className="text-sm text-[#aab4d0] mt-1">
              Listen together, join clubs and share Moments with friends.
            </div>
          </div>
          <div className="inline-flex items-center gap-1 text-sm font-bold text-white/85 shrink-0">
            Explore <ChevronRight size={16} />
          </div>
        </button>
      </section>
    );
  }

  const stats = [
    friendsOnline > 0 && { k: "friends", label: `${friendsOnline} friend${friendsOnline === 1 ? "" : "s"} active`, color: "#5eead4" },
    liveExp > 0 && { k: "live", label: `${liveExp} live now`, color: "#fca5a5" },
    requests > 0 && { k: "req", label: `${requests} request${requests === 1 ? "" : "s"}`, color: "#c4b5fd" },
  ].filter(Boolean);

  return (
    <section data-testid="nlv2-whats-happening">
      <div className="flex items-center justify-between gap-3 mb-4">
        <h2 className="text-xl font-bold">{title}</h2>
        <button type="button" onClick={() => open("/social", "see-all")}
          data-testid="nlv2-happening-seeall"
          className="text-sm font-semibold text-[#c084fc] hover:text-white inline-flex items-center gap-1">
          Open Social <ChevronRight size={15} />
        </button>
      </div>

      {stats.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-4" data-testid="nlv2-happening-stats">
          {stats.map((s) => (
            <span key={s.k} className="inline-flex items-center gap-1.5 text-[12px] font-bold px-3 h-8 rounded-full nlv2-glass"
              style={{ color: s.color }}>
              <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: s.color }} />
              {s.label}
            </span>
          ))}
        </div>
      )}

      <div className="flex gap-3 overflow-x-auto nlv2-scroll pb-2">
        {requests > 0 && (
          <button type="button" onClick={() => open("/social", "requests")}
            data-testid="nlv2-happening-requests"
            className="shrink-0 w-[220px] text-left nlv2-glass-strong nlv2-card-hover rounded-2xl p-4">
            <div className="w-10 h-10 rounded-xl grid place-items-center mb-3" style={{ background: "linear-gradient(135deg,#8b5cf6,#6366f1)" }}>
              <Bell size={18} color="#fff" />
            </div>
            <div className="text-[10px] font-mono uppercase tracking-widest text-[#c4b5fd]">Friend requests</div>
            <div className="text-sm font-bold mt-0.5">{requests} waiting to connect</div>
            <div className="mt-2 text-[12px] font-bold text-white/80 inline-flex items-center gap-1">Review <ChevronRight size={13} /></div>
          </button>
        )}

        {friends.slice(0, 6).map((f, i) => (
          <button type="button" key={(f.user_id || "f") + i}
            onClick={() => open(f.room_id ? `/social/room/${f.room_id}` : "/social", "friend")}
            data-testid={`nlv2-happening-friend-${i}`}
            className="shrink-0 w-[220px] text-left nlv2-glass-strong nlv2-card-hover rounded-2xl p-4">
            <div className="flex items-center gap-2 mb-3">
              {f.avatar_url
                ? <img src={f.avatar_url} alt="" className="w-10 h-10 rounded-full object-cover" />
                : <span className="w-10 h-10 rounded-full grid place-items-center text-white font-black" style={{ background: "linear-gradient(135deg,#14b8a6,#22c55e)" }}>{(f.name || "?").slice(0, 1).toUpperCase()}</span>}
              <span className="inline-flex items-center gap-1 text-[10px] font-black px-2 py-0.5 rounded-full" style={{ background: "rgba(45,212,191,0.18)", color: "#5eead4" }}>
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" /> LISTENING
              </span>
            </div>
            <div className="text-sm font-bold truncate">{f.name || "A friend"}</div>
            <div className="text-[12px] text-[#97a3c2] truncate">{f.context ? `to ${f.context}` : "in a listening room"}</div>
            <div className="mt-2 text-[12px] font-bold text-white/80 inline-flex items-center gap-1">Join <ChevronRight size={13} /></div>
          </button>
        ))}

        {friends.length === 0 && rooms.slice(0, 6).map((r, i) => (
          <button type="button" key={(r.id || r._id || "r") + i}
            onClick={() => open(`/social/room/${r.id || r._id}`, "room")}
            data-testid={`nlv2-happening-room-${i}`}
            className="shrink-0 w-[220px] text-left nlv2-glass-strong nlv2-card-hover rounded-2xl p-4">
            <div className="w-10 h-10 rounded-xl grid place-items-center mb-3" style={{ background: "linear-gradient(135deg,#f43f5e,#a855f7)" }}>
              <Radio size={18} color="#fff" />
            </div>
            <div className="text-[10px] font-mono uppercase tracking-widest text-[#fca5a5]">Live room</div>
            <div className="text-sm font-bold mt-0.5 truncate">{r.title || (r.content && r.content.name) || "Listening room"}</div>
            <div className="mt-2 text-[12px] font-bold text-white/80 inline-flex items-center gap-1">Join <ChevronRight size={13} /></div>
          </button>
        ))}

        <button type="button" onClick={() => open("/social", "discover")}
          data-testid="nlv2-happening-more"
          className="shrink-0 w-[180px] text-left nlv2-glass nlv2-card-hover rounded-2xl p-4 grid content-center">
          <Sparkles size={20} className="text-[#c084fc] mb-2" />
          <div className="text-sm font-bold">More in Social</div>
          <div className="text-[12px] text-[#97a3c2] mt-0.5">Moments, Clubs & Together</div>
        </button>
      </div>
    </section>
  );
}
