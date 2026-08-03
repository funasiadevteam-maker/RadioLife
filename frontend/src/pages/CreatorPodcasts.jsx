/** Phase B — Creator's podcasts dashboard (`/creator/podcasts`).
 *
 *  A focused view of the current user's podcast channels — reuses the
 *  existing /creator flow (Creator.jsx) for CRUD but provides a
 *  clean per-podcast overview with episode counts + subscriber counts
 *  + status chips + deep links into the existing episode manager.
 */
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { Loader2, BookHeadphones, Plus, Settings2, BarChart3 } from "lucide-react";
import { API, useAuth } from "@/AuthContext";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";

export default function CreatorPodcasts() {
  const { user } = useAuth();
  const [creator, setCreator] = useState(null);
  const [channels, setChannels] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    if (!user) { setLoading(false); return; }
    setLoading(true);
    try {
      const me = await axios.get(`${API}/podcasts/creators/me`,
        { withCredentials: true });
      const cre = me.data?.creator || null;
      setCreator(cre);
      if (cre?.application_status === "approved") {
        const r = await axios.get(
          `${API}/podcasts/creators/${cre.id}/channels`,
          { withCredentials: true });
        setChannels(r.data?.channels || []);
      } else { setChannels([]); }
    } catch (_) { setCreator(null); setChannels([]); }
    finally { setLoading(false); }
  }, [user]);
  useEffect(() => { load(); }, [load]);

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-950 text-white p-8
                                    flex items-center justify-center"
                data-testid="creator-podcasts-loading">
        <Loader2 className="w-6 h-6 animate-spin text-violet-400" />
      </div>
    );
  }
  if (!user) {
    return (
      <div className="min-h-screen bg-slate-950 text-white p-8 text-center"
                data-testid="creator-podcasts-unauth">
        <div className="text-sm text-white/60">Sign in to manage podcasts.</div>
        <Link to="/login" className="text-violet-400 underline text-sm mt-3
                          inline-block">Sign in</Link>
      </div>
    );
  }
  if (!creator || creator.application_status !== "approved") {
    return (
      <div className="min-h-screen bg-slate-950 text-white p-8 max-w-3xl
                                    mx-auto"
                data-testid="creator-podcasts-not-creator">
        <h1 className="text-2xl font-bold">My Podcasts</h1>
        <div className="mt-6 p-6 rounded-2xl border border-white/10
                                        bg-white/[0.03]">
          <div className="text-sm text-white/70">
            You don&apos;t have an approved creator profile yet.
          </div>
          <Link to="/creator" className="mt-4 inline-flex items-center gap-2
                                                                px-4 h-10 rounded-full bg-violet-500
                                                                text-white text-sm font-semibold
                                                                hover:bg-violet-400"
                        data-testid="creator-podcasts-apply-cta">
            Go to Creator Studio →
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-950 text-white pb-24"
              data-testid="creator-podcasts-page">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 py-8">
        <div className="flex items-center justify-between gap-3
                                        flex-wrap">
          <div>
            <div className="text-[10px] uppercase tracking-widest
                                            font-mono text-violet-400">Creator</div>
            <h1 className="text-3xl font-black tracking-tight mt-0.5"
                    data-testid="creator-podcasts-title">
              My Podcasts
            </h1>
            <p className="text-sm text-white/60 mt-1">
              {channels.length} channel{channels.length === 1 ? "" : "s"} ·
              signed in as {creator.display_name}
            </p>
          </div>
          <Link to="/creator" data-testid="creator-podcasts-new-cta"
                    className="inline-flex items-center gap-1.5 px-4 h-10
                                          rounded-full bg-violet-500 text-white
                                          text-sm font-semibold hover:bg-violet-400">
            <Plus size={14} /> New Podcast
          </Link>
        </div>

        {channels.length === 0 ? (
          <div className="mt-8 p-8 rounded-2xl border border-white/10
                                          bg-white/[0.03] text-center"
                      data-testid="creator-podcasts-empty">
            <BookHeadphones size={40} className="text-violet-400 mx-auto
                                                              mb-3" />
            <div className="text-sm text-white/70 mb-3">
              You haven&apos;t created a podcast yet.
            </div>
            <Link to="/creator" className="text-violet-400 underline text-sm">
              Create your first podcast →
            </Link>
          </div>
        ) : (
          <ul className="mt-8 grid grid-cols-1 md:grid-cols-2 gap-4"
                    data-testid="creator-podcasts-list">
            {channels.map((c) => {
              const status = c.approval_status || "draft";
              const active = c.active !== false;
              const statusColor = status === "approved" && active
                ? "text-emerald-400"
                : status === "pending" ? "text-amber-400"
                : status === "rejected" ? "text-red-400"
                : "text-slate-400";
              return (
                <li key={c.id}
                        className="p-4 rounded-2xl bg-white/[0.03]
                                                border border-white/[0.08] flex gap-4"
                        data-testid={`creator-podcast-card-${c.id}`}>
                  <div className="w-20 h-20 rounded-xl flex-shrink-0
                                                  overflow-hidden bg-violet-900/40
                                                  flex items-center justify-center">
                    {c.cover_image_url ? (
                      <img src={c.cover_image_url} alt={c.title}
                                  className="w-full h-full object-cover" />
                    ) : (
                      <BookHeadphones size={28} className="text-violet-300" />
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-bold truncate"
                                data-testid={`creator-podcast-title-${c.id}`}>
                      {c.title}
                    </div>
                    <div className={`text-[10px] uppercase tracking-widest
                                                      font-mono mt-0.5 ${statusColor}`}
                                data-testid={`creator-podcast-status-${c.id}`}>
                      {status}
                    </div>
                    <div className="mt-2 flex items-center gap-3 text-xs
                                                    text-white/60">
                      <span data-testid={`creator-podcast-episodes-${c.id}`}>
                        {c.episode_count || 0} ep
                      </span>
                      <span>·</span>
                      <span data-testid={`creator-podcast-subs-${c.id}`}>
                        {c.follower_count || 0} subs
                      </span>
                    </div>
                    <div className="mt-3 flex gap-2">
                      <Link to={`/podcasts/${c.id}`}
                                  className="text-[11px] px-2 h-7 inline-flex
                                                            items-center gap-1 rounded-full
                                                            bg-violet-500/20 text-violet-300
                                                            border border-violet-500/30"
                                  data-testid={`creator-podcast-view-${c.id}`}>
                        View
                      </Link>
                      <Link to={`/creator/channels/${c.id}/settings`}
                                  className="text-[11px] px-2 h-7 inline-flex
                                                            items-center gap-1 rounded-full
                                                            bg-white/10 text-white/80
                                                            border border-white/10"
                                  data-testid={`creator-podcast-manage-${c.id}`}>
                        <Settings2 size={11} /> Manage
                      </Link>
                      <Link to={`/creator`}
                                  className="text-[11px] px-2 h-7 inline-flex
                                                            items-center gap-1 rounded-full
                                                            bg-white/10 text-white/80
                                                            border border-white/10"
                                  data-testid={`creator-podcast-analytics-${c.id}`}>
                        <BarChart3 size={11} /> Analytics
                      </Link>
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        )}

        {/* Callout — creator flow lives at /creator */}
        <div className="mt-10 p-4 rounded-xl border border-white/10
                                        bg-white/[0.03] text-xs text-white/60"
                    data-testid="creator-podcasts-help">
          Need to upload an episode, edit metadata, or import an RSS feed?
          Head to <Link to="/creator" className="text-violet-400 underline">
          Creator Studio</Link> where the full episode manager lives.
        </div>
      </div>
    </div>
  );
}
