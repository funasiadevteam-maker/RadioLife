/** Phase B — Podcast detail page (Legacy dark).
 *
 *  Route: /podcasts/:podcast_id
 *  Shows: cover, description, subscribe button, episode list newest-first,
 *  play buttons that push into usePlayerStore.podcastEpisode.
 */
import { useCallback, useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import axios from "axios";
import { Play, Pause, Loader2, BookHeadphones, Rss,
                  CheckCircle2, ChevronLeft } from "lucide-react";
import { API, useAuth } from "@/AuthContext";
import { usePlayerStore } from "@/store/usePlayerStore";
import { toast } from "sonner";
import SafeImage from "@/components/SafeImage";

function _fmtDuration(sec) {
  if (!sec || !Number.isFinite(sec)) return "";
  const s = Math.round(sec);
  const m = Math.floor(s / 60);
  const h = Math.floor(m / 60);
  if (h > 0) return `${h}h ${m % 60}m`;
  return `${m}m ${s % 60}s`;
}

function _fmtDate(iso) {
  if (!iso) return "";
  try { return new Date(iso).toLocaleDateString(undefined,
    { year: "numeric", month: "short", day: "numeric" }); }
  catch (_) { return ""; }
}

export default function PodcastDetail() {
  const { podcast_id: podcastId } = useParams();
  const { user } = useAuth();
  const [ch, setCh] = useState(null);
  const [eps, setEps] = useState([]);
  const [loading, setLoading] = useState(true);
  const [subscribed, setSubscribed] = useState(false);
  const [subBusy, setSubBusy] = useState(false);
  const setPodcastEpisode = usePlayerStore((s) => s.setPodcastEpisode);
  const currentEpisode = usePlayerStore((s) => s.podcastEpisode);
  const podcastPlaying = usePlayerStore((s) => s.podcastPlaying);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [chR, epsR] = await Promise.all([
        axios.get(`${API}/podcasts/channels/${podcastId}`),
        axios.get(`${API}/podcasts/channels/${podcastId}/episodes?limit=100`),
      ]);
      // Server returns {channel, episodes, followers} — unwrap.
      setCh(chR.data?.channel || chR.data);
      setEps(epsR.data?.items || []);
    } catch (_e) {
      setCh(null); setEps([]);
    } finally { setLoading(false); }
  }, [podcastId]);
  useEffect(() => { load(); }, [load]);

  // Check subscription state (auth users only).
  useEffect(() => {
    if (!user) { setSubscribed(false); return; }
    (async () => {
      try {
        const r = await axios.get(`${API}/podcasts/me/subscriptions`,
          { withCredentials: true });
        setSubscribed((r.data?.items || [])
          .some((c) => c.id === podcastId));
      } catch (_) { setSubscribed(false); }
    })();
  }, [user, podcastId]);

  const toggleSubscribe = async () => {
    if (!user) {
      toast.info("Sign in to subscribe.");
      return;
    }
    setSubBusy(true);
    try {
      if (subscribed) {
        await axios.post(
          `${API}/podcasts/channels/${podcastId}/unfollow`, {},
          { withCredentials: true });
        setSubscribed(false);
        toast.success("Unsubscribed");
      } else {
        await axios.post(
          `${API}/podcasts/channels/${podcastId}/follow`, {},
          { withCredentials: true });
        setSubscribed(true);
        toast.success("Subscribed — episodes will show up in your feed.");
      }
    } catch (_e) {
      toast.error("Could not update subscription");
    } finally { setSubBusy(false); }
  };

  const play = (ep) => {
    setPodcastEpisode({
      episode_id:              ep.id,
      podcast_id:              ep.channel_id,
      title:                        ep.title,
      cover_image_url:      ep.cover_image_url || ch?.cover_image_url,
      audio_url:                `${API}/podcasts/episodes/${ep.id}/audio.mp3`,
      duration_seconds:  ep.duration_seconds,
      podcast_title:        ch?.title,
      podcast_slug:          ch?.slug,
    });
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-950 text-white p-8
                                    flex items-center justify-center"
                data-testid="podcast-detail-loading">
        <Loader2 className="w-6 h-6 animate-spin text-violet-400" />
      </div>
    );
  }
  if (!ch) {
    return (
      <div className="min-h-screen bg-slate-950 text-white p-8"
                data-testid="podcast-detail-not-found">
        <Link to="/podcasts" className="text-violet-400
                          inline-flex items-center gap-1">
          <ChevronLeft size={14} /> Back to podcasts
        </Link>
        <div className="mt-8 text-center text-white/60">
          Podcast not found.
        </div>
      </div>
    );
  }

  const cover = ch.cover_image_url;

  return (
    <div className="min-h-screen bg-slate-950 text-white pb-24"
              data-testid="podcast-detail-page"
              data-podcast-id={podcastId}>
      <div className="max-w-6xl xl:max-w-[1200px] mx-auto px-4 sm:px-6 py-6">
        <Link to="/podcasts" className="text-violet-400 text-xs
                        inline-flex items-center gap-1 hover:text-violet-300"
                    data-testid="podcast-detail-back">
          <ChevronLeft size={12} /> All podcasts
        </Link>

        {/* Hero */}
        <div className="mt-4 flex flex-col sm:flex-row gap-6">
          <div className="w-40 h-40 rounded-2xl overflow-hidden
                                          flex-shrink-0 bg-gradient-to-br
                                          from-violet-600/60 to-pink-600/60
                                          flex items-center justify-center">
            <SafeImage src={cover} alt={ch.title}
                                        fallbackKind="podcast"
                                        fallbackText={ch.title}
                                        className="w-full h-full object-cover"
                                        data-testid="podcast-detail-cover" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-[10px] uppercase tracking-widest
                                            font-mono text-violet-400 mb-1"
                        data-testid="podcast-detail-category">
              {ch.category || "podcast"}
              {ch.language ? ` · ${String(ch.language).toUpperCase()}` : ""}
            </div>
            <h1 className="text-3xl font-black tracking-tight"
                    data-testid="podcast-detail-title">{ch.title}</h1>
            <p className="mt-3 text-sm text-white/70 whitespace-pre-line"
                data-testid="podcast-detail-description">
              {ch.description || "No description yet."}
            </p>
            <div className="mt-4 flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={toggleSubscribe}
                disabled={subBusy}
                data-testid="podcast-detail-subscribe"
                data-subscribed={subscribed ? "true" : "false"}
                className={[
                  "px-4 h-9 rounded-full text-sm font-semibold",
                  "inline-flex items-center gap-1.5 transition",
                  subscribed
                    ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                    : "bg-violet-500 text-white hover:bg-violet-400",
                ].join(" ")}>
                {subBusy
                  ? <Loader2 size={14} className="animate-spin" />
                  : (subscribed
                        ? <><CheckCircle2 size={14} /> Subscribed</>
                        : <>Subscribe</>)}
              </button>
              <span className="text-xs text-white/50"
                          data-testid="podcast-detail-follower-count">
                {ch.follower_count || 0} subscribers
              </span>
              {ch.rss_enabled && (
                <a href={`${API}/../podcasts/${ch.slug}/rss.xml`}
                    target="_blank" rel="noopener noreferrer"
                    className="text-xs inline-flex items-center gap-1
                                              text-orange-400 hover:text-orange-300"
                    data-testid="podcast-detail-rss">
                  <Rss size={11} /> RSS
                </a>
              )}
            </div>
          </div>
        </div>

        {/* Episodes */}
        <section className="mt-10" data-testid="podcast-detail-episodes">
          <div className="text-xs uppercase tracking-widest font-mono
                                          text-white/40 mb-3">
            {eps.length} episode{eps.length === 1 ? "" : "s"}
          </div>
          {eps.length === 0 ? (
            <div className="p-8 rounded-xl border border-white/10
                                            bg-white/[0.03] text-center text-white/60"
                        data-testid="podcast-detail-empty-episodes">
              No episodes yet.
            </div>
          ) : (
            <ul className="divide-y divide-white/[0.06]">
              {eps.map((ep) => {
                const isCurrent = currentEpisode?.episode_id === ep.id;
                const isPlayingThis = isCurrent && podcastPlaying;
                return (
                  <li key={ep.id}
                          className="py-3 flex items-center gap-3
                                                  hover:bg-white/[0.03] px-2 -mx-2
                                                  rounded-lg transition"
                          data-testid={`podcast-episode-row-${ep.id}`}>
                    <button
                      type="button"
                      onClick={() => (isPlayingThis
                            ? window.dispatchEvent(
                                    new CustomEvent("bigfm:player:toggle"))
                            : play(ep))}
                      className={[
                        "w-10 h-10 rounded-full flex-shrink-0",
                        "flex items-center justify-center transition",
                        isCurrent
                          ? "bg-violet-500 text-white"
                          : "bg-white/10 text-white hover:bg-violet-500",
                      ].join(" ")}
                      data-testid={`podcast-episode-play-${ep.id}`}
                      aria-label={isPlayingThis ? "Pause" : "Play"}>
                      {isPlayingThis
                        ? <Pause size={16} />
                        : <Play size={16} className="ml-0.5" />}
                    </button>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-semibold truncate"
                                  data-testid={`podcast-episode-title-${ep.id}`}>
                        {ep.title || `Episode ${ep.episode_number}`}
                      </div>
                      <div className="text-[11px] text-white/50 mt-0.5
                                                      flex items-center gap-2">
                        <span>{_fmtDate(ep.published_at)}</span>
                        {ep.duration_seconds ? (
                          <>
                            <span>·</span>
                            <span>{_fmtDuration(ep.duration_seconds)}</span>
                          </>) : null}
                        {ep.explicit_flag && (
                          <span className="text-red-400
                                                                  border border-red-400/40
                                                                  rounded px-1 text-[9px]">E</span>
                        )}
                      </div>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
