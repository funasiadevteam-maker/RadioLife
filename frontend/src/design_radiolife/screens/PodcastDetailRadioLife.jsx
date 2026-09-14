/** Phase B — RadioLife (light) variant of the podcast detail page.
 *
 *  Route match: /podcasts/:podcast_id when useDesignVariant() === "radiolife".
 *  Mounted by RadioLifeOverlay.
 */
import { useCallback, useEffect, useState } from "react";
import { useLocation, Link } from "react-router-dom";
import axios from "axios";
import { Play, Pause, Loader2, BookHeadphones, ChevronLeft,
                  CheckCircle2, Video } from "lucide-react";
import { API, useAuth } from "@/AuthContext";
import { usePlayerStore } from "@/store/usePlayerStore";
import { toast } from "sonner";
import SafeImage from "@/components/SafeImage";
import PipVideoPlayer, { useEpisodeVideo } from "@/components/PipVideoPlayer";

function _fmtDuration(sec) {
  if (!sec || !Number.isFinite(sec)) return "";
  const s = Math.round(sec);
  const m = Math.floor(s / 60);
  const h = Math.floor(m / 60);
  if (h > 0) return `${h}h ${m % 60}m`;
  return `${m}m`;
}

function _fmtDate(iso) {
  if (!iso) return "";
  try { return new Date(iso).toLocaleDateString(undefined,
    { year: "numeric", month: "short", day: "numeric" }); }
  catch (_) { return ""; }
}

export default function PodcastDetailRadioLife() {
  // Overlay is mounted outside <Routes>, so useParams() returns {}.
  // Parse the podcast id from the pathname directly.
  const { pathname } = useLocation();
  const podcastId = pathname.startsWith("/podcasts/")
    ? decodeURIComponent(pathname.slice("/podcasts/".length).split("/")[0])
    : "";
  const { user } = useAuth();
  const [ch, setCh] = useState(null);
  const [eps, setEps] = useState([]);
  const [loading, setLoading] = useState(true);
  const [subscribed, setSubscribed] = useState(false);
  const [subBusy, setSubBusy] = useState(false);
  const setPodcastEpisode = usePlayerStore((s) => s.setPodcastEpisode);
  const currentEpisode = usePlayerStore((s) => s.podcastEpisode);
  const podcastPlaying = usePlayerStore((s) => s.podcastPlaying);
  const { videoEp, setVideoEp, loadingId, open: openVideo } = useEpisodeVideo(API);

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
    } catch (_) { setCh(null); setEps([]); }
    finally { setLoading(false); }
  }, [podcastId]);
  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (!user) { setSubscribed(false); return; }
    axios.get(`${API}/podcasts/me/subscriptions`,
      { withCredentials: true })
      .then((r) => setSubscribed((r.data?.items || [])
        .some((c) => c.id === podcastId)))
      .catch(() => setSubscribed(false));
  }, [user, podcastId]);

  const toggleSubscribe = async () => {
    if (!user) { toast.info("Sign in to subscribe."); return; }
    setSubBusy(true);
    try {
      if (subscribed) {
        await axios.post(
          `${API}/podcasts/channels/${podcastId}/unfollow`, {},
          { withCredentials: true });
        setSubscribed(false); toast.success("Unsubscribed");
      } else {
        await axios.post(
          `${API}/podcasts/channels/${podcastId}/follow`, {},
          { withCredentials: true });
        setSubscribed(true); toast.success("Subscribed");
      }
    } catch (_) { toast.error("Could not update"); }
    finally { setSubBusy(false); }
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
      <div className="p-8 flex items-center justify-center"
                data-testid="rl-podcast-detail-loading">
        <Loader2 className="w-6 h-6 animate-spin text-violet-500" />
      </div>
    );
  }
  if (!ch) {
    return (
      <div className="p-6 text-center text-slate-500"
                data-testid="rl-podcast-detail-not-found">
        <Link to="/podcasts" className="text-violet-500 inline-flex
                          items-center gap-1 text-sm">
          <ChevronLeft size={12} /> Back
        </Link>
        <div className="mt-8">Podcast not found.</div>
      </div>
    );
  }

  return (
    <div className="px-4 pt-4 pb-6"
              data-testid="rl-podcast-detail-page"
              data-podcast-id={podcastId}>
      <Link to="/podcasts" className="text-violet-500 text-xs
                    inline-flex items-center gap-1"
                data-testid="rl-podcast-detail-back">
        <ChevronLeft size={12} /> All podcasts
      </Link>

      {/* Hero */}
      <div className="mt-4 flex gap-4">
        <div className="w-28 h-28 rounded-2xl overflow-hidden
                                        flex-shrink-0 bg-gradient-to-br from-violet-100
                                        to-pink-100 flex items-center justify-center">
          <SafeImage src={ch.cover_image_url} alt={ch.title}
                                        fallbackKind="podcast"
                                        fallbackText={ch.title}
                                        className="w-full h-full object-cover"
                                        data-testid="rl-podcast-detail-cover" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-[10px] uppercase tracking-widest font-mono
                                          text-violet-500 mb-1">
            {ch.category || "podcast"}
          </div>
          <h1 className="text-xl font-black tracking-tight text-slate-900"
                    data-testid="rl-podcast-detail-title">
            {ch.title}
          </h1>
          <div className="mt-2 text-xs text-slate-500"
                      data-testid="rl-podcast-detail-follower-count">
            {ch.follower_count || 0} subscribers
          </div>
        </div>
      </div>

      <p className="mt-4 text-sm text-slate-600 whitespace-pre-line"
              data-testid="rl-podcast-detail-description">
        {ch.description || "No description yet."}
      </p>

      <button
        type="button"
        onClick={toggleSubscribe}
        disabled={subBusy}
        data-testid="rl-podcast-detail-subscribe"
        data-subscribed={subscribed ? "true" : "false"}
        className={[
          "mt-4 px-4 h-10 rounded-full text-sm font-semibold w-full",
          "inline-flex items-center justify-center gap-1.5 transition",
          subscribed
            ? "bg-emerald-500/15 text-emerald-700 border border-emerald-500/40"
            : "bg-violet-500 text-white hover:bg-violet-400",
        ].join(" ")}>
        {subBusy
          ? <Loader2 size={14} className="animate-spin" />
          : (subscribed
                ? <><CheckCircle2 size={14} /> Subscribed</>
                : <>Subscribe</>)}
      </button>

      <section className="mt-8" data-testid="rl-podcast-detail-episodes">
        <div className="text-[11px] uppercase tracking-widest font-mono
                                        text-slate-400 mb-3">
          {eps.length} episode{eps.length === 1 ? "" : "s"}
        </div>
        {eps.length === 0 ? (
          <div className="p-6 rounded-xl border border-slate-200 bg-white
                                          text-center text-slate-500"
                      data-testid="rl-podcast-detail-empty-episodes">
            No episodes yet.
          </div>
        ) : (
          <ul className="divide-y divide-slate-100">
            {eps.map((ep) => {
              const isCurrent = currentEpisode?.episode_id === ep.id;
              const isPlayingThis = isCurrent && podcastPlaying;
              return (
                <li key={ep.id}
                        className="py-3 flex items-center gap-3"
                        data-testid={`rl-podcast-episode-row-${ep.id}`}>
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
                        : "bg-violet-100 text-violet-600",
                    ].join(" ")}
                    data-testid={`rl-podcast-episode-play-${ep.id}`}
                    aria-label={isPlayingThis ? "Pause" : "Play"}>
                    {isPlayingThis
                      ? <Pause size={16} />
                      : <Play size={16} className="ml-0.5" />}
                  </button>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-semibold text-slate-900
                                                    truncate"
                                data-testid={`rl-podcast-episode-title-${ep.id}`}>
                      {ep.title || `Episode ${ep.episode_number}`}
                    </div>
                    <div className="text-[11px] text-slate-500 mt-0.5">
                      {_fmtDate(ep.published_at)}
                      {ep.duration_seconds
                        ? ` · ${_fmtDuration(ep.duration_seconds)}` : ""}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => openVideo(ep, axios, () => toast("This episode is audio-only"))}
                    className="w-9 h-9 rounded-full flex-shrink-0 flex items-center
                                    justify-center bg-slate-100 text-slate-600
                                    hover:bg-violet-100 hover:text-violet-600 transition"
                    data-testid={`rl-podcast-episode-watch-${ep.id}`}
                    aria-label="Watch video (Picture-in-Picture)">
                    {loadingId === ep.id
                      ? <Loader2 size={15} className="animate-spin" />
                      : <Video size={15} />}
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </section>
      {videoEp && (
        <PipVideoPlayer videoUrl={videoEp.videoUrl} title={videoEp.title}
                        onClose={() => setVideoEp(null)} />
      )}
    </div>
  );
}
