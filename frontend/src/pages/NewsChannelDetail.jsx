// Phase R — Listener /news/channels/:id page (dual-design).
// Shows the channel meta + latest headlines pinned to the channel +
// upcoming schedule + recent bulletins with inline audio playback.
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import axios from "axios";
import { ArrowLeft, Play, Loader2, Clock, Calendar, Radio,
                 ExternalLink } from "lucide-react";
import { useDesignVariant } from "@/hooks/useDesignVariant";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

const SEGMENT_LABELS = {
  top_headlines: "Top headlines",
  breaking:      "Breaking",
  weather:       "Weather",
  traffic:       "Traffic",
  business:      "Business",
  sports:        "Sports",
  features:      "Features",
};

export default function NewsChannelDetail() {
  const { channel_id } = useParams();
  const variant = useDesignVariant();
  const light = variant === "radiolife";

  const [data, setData]     = useState(null);
  const [bulletins, setBs]  = useState([]);
  const [err, setErr]        = useState(null);
  const [busy, setBusy]      = useState(true);
  const [playing, setPlaying]= useState(null);   // bulletin_id currently in audio.

  useEffect(() => {
    let alive = true;
    (async () => {
      setBusy(true);
      setErr(null);
      try {
        const [ch, next] = await Promise.all([
          axios.get(`${API}/news/channels/${channel_id}`),
          axios.get(`${API}/news/bulletins/next?channel_id=${channel_id}`),
        ]);
        if (!alive) return;
        setData(ch.data);
        // Include the "next" live bulletin at top of the list if present.
        setBs(next.data?.bulletin ? [next.data.bulletin] : []);
      } catch (e) {
        if (alive) setErr(e?.response?.data?.detail?.code
                                        || e?.response?.data?.detail
                                        || e.message);
      } finally {
        if (alive) setBusy(false);
      }
    })();
    return () => { alive = false; };
  }, [channel_id]);

  const bg = light ? "bg-slate-50 text-slate-900" : "bg-slate-950 text-white";
  const cardBg = light ? "bg-white border-slate-200 shadow-sm"
                                    : "bg-slate-900/60 border-slate-800";

  if (busy) {
    return (
      <div className={`min-h-screen ${bg} p-8 flex items-center justify-center`}
                data-testid="news-channel-loading">
        <Loader2 className="w-6 h-6 animate-spin text-red-400" />
      </div>
    );
  }
  if (err || !data) {
    return (
      <div className={`min-h-screen ${bg} p-8 flex items-center justify-center`}
                data-testid="news-channel-error">
        <div className="text-center">
          <Radio className="w-10 h-10 text-red-500 mx-auto" />
          <div className="mt-3 font-bold text-lg">Channel unavailable</div>
          <div className="text-sm text-slate-400 mt-1">{String(err || "channel_not_found")}</div>
          <Link to="/news"
                    data-testid="news-channel-back-empty"
                    className="mt-4 inline-flex items-center gap-2 text-red-400 hover:underline">
            <ArrowLeft className="w-4 h-4" /> All news
          </Link>
        </div>
      </div>
    );
  }

  const ch = data.channel || {};
  const heads = data.latest_headlines || [];
  const schedule = data.upcoming_schedule || [];

  return (
    <div className={`min-h-screen ${bg}`} data-testid="news-channel-detail"
              data-variant={variant} data-channel-id={channel_id}>
      <div className="max-w-7xl xl:max-w-[1400px] mx-auto p-6 sm:p-8">
        <Link to="/news"
                    data-testid="news-channel-back"
                    className={`text-xs inline-flex items-center gap-1 mb-3 ${
                        light ? "text-slate-600 hover:text-slate-900"
                                : "text-slate-400 hover:text-white"}`}>
          <ArrowLeft className="w-3 h-3" /> All news
        </Link>

        {/* Channel header */}
        <div className="mb-6 flex items-start gap-4 flex-wrap">
          {ch.cover_image_url && (
            <img src={ch.cover_image_url} alt=""
                      className="w-24 h-24 rounded-2xl object-cover" />
          )}
          <div className="min-w-0 flex-1">
            <div className={`text-[10px] font-mono uppercase tracking-widest ${
                light ? "text-red-600" : "text-red-400"}`}>
              News channel · {ch.city || ch.region_code || "Global"}
            </div>
            <h1 className="mt-1 text-3xl md:text-4xl xl:text-5xl font-black tracking-tight">
              {ch.name}
            </h1>
            {ch.tagline && (
              <div className={`mt-1 text-sm ${light ? "text-slate-700" : "text-slate-300"}`}>
                {ch.tagline}
              </div>
            )}
            <div className="mt-1 text-[10px] font-mono text-slate-500">
              {ch.region_code || "Global"} · {ch.language} · {ch.live ? "LIVE" : "OFF-AIR"}
            </div>
          </div>
        </div>

        {/* Grid: main (bulletins + headlines) + sidebar (schedule) */}
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] xl:grid-cols-[1fr_360px] gap-6">
          {/* Left: bulletins + headlines */}
          <div className="min-w-0 space-y-6">
            {/* Bulletins */}
            <section data-testid="news-channel-bulletins">
              <div className="flex items-center gap-2 mb-3">
                <Play className={`w-4 h-4 ${light ? "text-red-600" : "text-red-400"}`} />
                <h2 className="text-sm font-bold uppercase tracking-widest font-mono
                                              text-slate-500">
                  Bulletins
                </h2>
              </div>
              {bulletins.length === 0 ? (
                <div className={`rounded-2xl border p-6 text-center ${cardBg}`}
                          data-testid="news-channel-bulletins-empty">
                  <div className="text-sm font-bold">No live bulletin yet.</div>
                  <div className={`text-xs mt-1 ${light ? "text-slate-600" : "text-slate-500"}`}>
                    Bulletins publish on the hour — check back shortly.
                  </div>
                </div>
              ) : (
                <div className="space-y-3">
                  {bulletins.map((b) => (
                    <div key={b.id}
                              data-testid={`news-channel-bulletin-${b.id}`}
                              className={`rounded-2xl border p-4 ${cardBg}`}>
                      <div className="flex items-center gap-2 mb-2">
                        <span className={`text-[10px] font-mono uppercase tracking-widest ${
                            light ? "text-red-600" : "text-red-400"} font-bold`}>
                          {b.bulletin_type?.replace(/_/g, " ") || "top of hour"}
                        </span>
                        <span className="text-[10px] font-mono text-slate-500">
                          · {b.duration_seconds || 0}s · {(b.headline_ids || []).length} headlines
                        </span>
                        {b.status === "live" && (
                          <span className="ml-auto text-[10px] font-bold text-emerald-400 uppercase tracking-widest">
                            Live
                          </span>
                        )}
                      </div>
                      {b.script_text && (
                        <div className={`text-xs ${light ? "text-slate-700" : "text-slate-300"} line-clamp-4`}>
                          {b.script_text}
                        </div>
                      )}
                      {b.audio_url ? (
                        <div className="mt-3">
                          <audio controls preload="none"
                                        src={b.audio_url}
                                        data-testid={`news-bulletin-audio-${b.id}`}
                                        onPlay={() => setPlaying(b.id)}
                                        onPause={() => setPlaying(null)}
                                        className="w-full">
                            Your browser does not support the audio element.
                          </audio>
                          {playing === b.id && (
                            <div className={`text-[10px] font-mono mt-1 ${
                                light ? "text-red-600" : "text-red-400"}`}>
                              Now playing on {ch.name}.
                            </div>
                          )}
                        </div>
                      ) : (
                        <div className={`mt-2 text-[10px] font-mono ${
                            light ? "text-slate-600" : "text-slate-500"}`}>
                          Audio unavailable · text-only bulletin.
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </section>

            {/* Latest headlines pinned to this channel's region */}
            <section data-testid="news-channel-latest">
              <div className="flex items-center gap-2 mb-3">
                <Radio className={`w-4 h-4 ${light ? "text-red-600" : "text-red-400"}`} />
                <h2 className="text-sm font-bold uppercase tracking-widest font-mono
                                              text-slate-500">
                  Latest headlines
                </h2>
              </div>
              {heads.length === 0 ? (
                <div className={`rounded-2xl border p-6 text-center text-sm ${cardBg}`}>
                  No live headlines in this region yet.
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {heads.map((h) => (
                    <div key={h.id}
                              data-testid={`news-channel-headline-${h.id}`}
                              className={`rounded-2xl border p-4 ${cardBg}`}>
                      <div className="flex items-center gap-2 mb-1">
                        <span className={`text-[10px] font-mono uppercase tracking-widest ${
                            light ? "text-red-600" : "text-red-400"}`}>
                          {h.category}
                        </span>
                        {h.is_breaking && (
                          <span className="text-[10px] font-mono uppercase tracking-widest text-red-400 font-bold">
                            · BREAKING
                          </span>
                        )}
                      </div>
                      <div className="text-sm font-bold line-clamp-2">{h.headline_text}</div>
                      {h.summary_text && (
                        <div className={`text-xs mt-1 ${
                            light ? "text-slate-600" : "text-slate-400"} line-clamp-3`}>
                          {h.summary_text}
                        </div>
                      )}
                      {h.source_url && (
                        <a href={h.source_url} target="_blank" rel="noreferrer"
                              className="mt-2 inline-flex items-center gap-1 text-[11px] hover:underline text-red-400">
                          <ExternalLink className="w-3 h-3" />
                          {h.source_name || "Source"}
                        </a>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </section>
          </div>

          {/* Right: upcoming schedule */}
          <aside data-testid="news-channel-schedule">
            <div className={`rounded-2xl border p-4 ${cardBg}`}>
              <div className="flex items-center gap-2 mb-3">
                <Calendar className={`w-4 h-4 ${light ? "text-red-600" : "text-red-400"}`} />
                <div className="text-[10px] font-mono uppercase tracking-widest text-slate-500 font-bold">
                  Upcoming schedule
                </div>
              </div>
              {schedule.length === 0 ? (
                <div className={`text-xs ${light ? "text-slate-600" : "text-slate-500"}`}>
                  No programming scheduled.
                </div>
              ) : (
                <div className="space-y-2">
                  {schedule.map((s, i) => (
                    <div key={i}
                              data-testid={`news-schedule-item-${i}`}
                              className="flex items-center gap-3 text-xs">
                      <Clock className={`w-3 h-3 ${
                          light ? "text-slate-500" : "text-slate-400"}`} />
                      <span className="font-mono text-slate-400 tabular-nums">
                        {String(s.hour_of_day).padStart(2, "0")}:00
                      </span>
                      <span className="flex-1 truncate">
                        {SEGMENT_LABELS[s.segment_type] || s.segment_type}
                      </span>
                      <span className="text-[10px] font-mono text-slate-500">
                        {s.duration_minutes}m
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}
