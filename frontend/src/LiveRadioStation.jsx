/** Phase 42-A — Live Radio Station Detail page.
 *
 *  `/live-radio/station/:id` — favicon, tags, country/language, big Play
 *  button (routed through the global player store), Similar AI-Curated
 *  suggestion, and the Phase 42-C Claim CTA.
 *
 *  Phase 42-B2 hotfix — Play no longer spawns a self-contained <audio>
 *  element on this page.  togglePlay() now hands off to
 *  usePlayerStore.setImportedStation(), which the global
 *  <ImportedStreamBridge /> picks up and uses to (a) fire the
 *  pre-roll overlay when applicable and (b) drive the single global
 *  audio element.  This guarantees direct-load (shared URL) plays
 *  behave the same as Discover/Browse-tile plays.
 */
import React, { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import {
  Play, Pause, ArrowLeft, ExternalLink, Globe2, Radio as RadioIcon,
  Sparkles, MapPin, Languages, Tag, Award, AlertCircle, ShieldCheck,
  Image as ImageIcon, Upload, Trash2,
} from "lucide-react";
import { API } from "@/AuthContext";
import { usePlayerStore } from "@/store/usePlayerStore";
// Phase 42-D3 — heart toggle on the detail header.
import { FavoriteHeart } from "@/components/FavoriteControls";
// Phase 42-E2.2 — Universal share button on station detail.
import ShareButton from "@/components/ShareButton";
// Phase 42-E2.4 — OG meta for station shares.
import OGMeta from "@/components/OGMeta";
// Phase FUN.1.1 — Flagship "you might also like" carousel.
import FlagshipStrip from "@/components/FlagshipStrip";
// P0 mixed-content fix — rewrite http:// stream URLs through the proxy.
import { toPlayableStreamUrl } from "@/utils/streamUrl";
// Phase AD.11 — station_detail + now_playing banner zones.
import BannerZoneSlot from "@/components/BannerZoneSlot";
// Phase AD.8 — Daily code claim widget inside the Now Playing surface.
import DailyCodeWidget from "@/components/DailyCodeWidget";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";
function resolveImg(u) {
  if (!u) return null;
  return u.startsWith("http") ? u : `${BACKEND_URL}${u}`;
}

export default function LiveRadioStation() {
  const { id } = useParams();
  const navigate = useNavigate();
  // P0 (2026-07-27, 3rd attempt) — the bottom-bar Play button navigates
  // here with `?autoplay=1` when the user taps play with no station
  // selected.  We read the flag and fire togglePlay() the moment the
  // station has loaded so audio starts within a couple of seconds of
  // the tap (which browsers count as the user gesture).
  const [searchParams] = useSearchParams();
  const autoplayHint = searchParams.get("autoplay") === "1";
  const autoplayFiredRef = useRef(false);
  const clickFiredRef = useRef(false);

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);
  const [streamErr, setStreamErr] = useState(null);
  const [toggling, setToggling] = useState(false);
  const [artBusy, setArtBusy] = useState(false);

  // Phase 42-B2 hotfix — route Play through the unified player store so
  // the global ImportedStreamBridge can drive playback AND fire the
  // pre-roll overlay.  Direct-load (shared URL) plays now match the
  // Discover/Browse-tile behaviour.
  const importedStation = usePlayerStore((s) => s.importedStation);
  const importedPlaying = usePlayerStore((s) => s.importedPlaying);
  const setImportedStation = usePlayerStore((s) => s.setImportedStation);
  const setImportedPlaying = usePlayerStore((s) => s.setImportedPlaying);

  const isThisStationActive = importedStation?.id === id;
  const playing = isThisStationActive && importedPlaying;

  useEffect(() => {
    let cancelled = false;
    setLoading(true); setErr(null); setData(null);
    setStreamErr(null);
    clickFiredRef.current = false;
    (async () => {
      try {
        const r = await axios.get(`${API}/live-radio/stations/${id}`);
        if (cancelled) return;
        setData(r.data);
        // On-demand: generate AI art the first time an imported station
        // with only a placeholder is opened, then refresh to show it.
        const st = r.data?.station;
        if (id.startsWith("imp_") && st && !st.has_custom_art) {
          axios.post(`${API}/imported-stations/${id}/artwork/ensure`).catch(() => {});
          setTimeout(async () => {
            if (cancelled) return;
            try {
              const r2 = await axios.get(`${API}/live-radio/stations/${id}`);
              if (!cancelled) setData(r2.data);
            } catch (_e) { /* ignore */ }
          }, 16000);
        }
      } catch (e) {
        if (cancelled) return;
        setErr(e.response?.data?.detail?.code || "load_failed");
      } finally { if (!cancelled) setLoading(false); }
    })();
    return () => { cancelled = true; };
  }, [id]);

  const fireClickPing = async () => {
    if (clickFiredRef.current) return;
    clickFiredRef.current = true;
    try {
      await axios.post(`${API}/live-radio/click/${id}`);
    } catch (_e) { /* swallow — fire-and-forget */ }
  };

  // Phase 42-B2 hotfix — togglePlay now goes through the global player
  // store.  This guarantees the ImportedStreamBridge picks up the
  // station, fires the pre-roll overlay, and drives the single global
  // <audio> element (no more dueling-audio bug from a per-page tag).
  //
  // Phase Π+4.1 (2026-07-25) — the previous version awaited
  // `POST /api/radio/play/${id}` BEFORE `setImportedStation`, which
  // meant the play HTTP request landed in the network queue BEFORE
  // the bridge's useEffect could dispatch the pre-roll request —
  // inverting the tester's required order.
  //
  // Fix: use `s.stream_url` from the station-detail GET (which already
  // returns `s.get("url_resolved") or s.get("url")`, the exact same
  // shape the /radio/play endpoint would have returned).  The bridge's
  // pre-roll POST is now the FIRST server-side call after Play.
  // `fireClickPing()` still handles the click record + RadioBrowser
  // ping, and it's already fire-and-forget so it can't race the
  // pre-roll HTTP order.
  const togglePlay = async () => {
    if (toggling) return;
    const s = data?.station;
    if (!s || s.source === "bigfm_ai") return;
    // Pause-if-this-station-is-active.
    if (isThisStationActive) {
      setImportedPlaying(!playing);
      return;
    }
    if (!s.stream_url) {
      setStreamErr("Stream unavailable — try again in a moment.");
      return;
    }
    setToggling(true);
    setStreamErr(null);
    try {
      // Set the station FIRST — this triggers ImportedStreamBridge's
      // pre-roll-request useEffect on the next microtask.  The bridge
      // is the SINGLE owner of the pre-roll gate, so we do NOT
      // duplicate the request here.
      setImportedStation({
        id,
        name: s.name,
        stream_url: toPlayableStreamUrl(s.stream_url),
        favicon: s.favicon,
        country: s.country,
        language: s.language,
        source: "imported",
      });
      // Fire-and-forget click ping (analytics + RadioBrowser credit).
      fireClickPing();
    } catch (e) {
      setStreamErr("Stream unavailable — try again in a moment.");
    } finally {
      setToggling(false);
    }
  };

  // Phase 42-C — wire the inert toast to the real claim wizard.
  const onClaim = () => {
    navigate(`/claim/station/${id}`);
  };

  // Owner/admin artwork tools (imported stations).
  const refetchStation = async () => {
    try {
      const r = await axios.get(`${API}/live-radio/stations/${id}`);
      setData(r.data);
    } catch (_e) { /* ignore */ }
  };
  const genArt = async () => {
    setArtBusy(true);
    try {
      await axios.post(`${API}/imported-stations/${id}/artwork/generate`, {}, { withCredentials: true });
      for (let i = 0; i < 12; i++) {
        await new Promise((r) => setTimeout(r, 6000));
        const st = await axios.get(`${API}/imported-stations/${id}/artwork/status`);
        if (["complete", "failed", "idle"].includes(st.data?.status)) break;
      }
      await refetchStation();
      toast.success("Artwork updated");
    } catch (e) {
      toast.error(e.response?.status === 429 ? "Hourly limit reached — try later." : "Couldn't generate artwork.");
    } finally { setArtBusy(false); }
  };
  const uploadArt = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setArtBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      await axios.post(`${API}/imported-stations/${id}/artwork/upload`, fd, { withCredentials: true });
      await refetchStation();
      toast.success("Logo uploaded");
    } catch (_e) {
      toast.error("Upload failed — use a JPG/PNG/WebP under 5 MB.");
    } finally { setArtBusy(false); e.target.value = ""; }
  };
  const clearArt = async () => {
    setArtBusy(true);
    try {
      await axios.post(`${API}/imported-stations/${id}/artwork/clear`, {}, { withCredentials: true });
      await refetchStation();
      toast.success("Reset to default");
    } catch (_e) { /* ignore */ } finally { setArtBusy(false); }
  };

  // P0 · 3rd attempt — auto-play when the URL carries `?autoplay=1`
  // (bottom-bar Play button + station-rail item clicks land here).  We
  // wait for the station to load, guard against double-fire via a ref,
  // and route through the existing togglePlay() so the ImportedStreamBridge's
  // pre-roll gate runs exactly as it does for manual clicks.
  useEffect(() => {
    if (!autoplayHint) return;
    if (autoplayFiredRef.current) return;
    if (!data?.station) return;
    if (data.station.source === "bigfm_ai") return;
    if (isThisStationActive && playing) return;
    autoplayFiredRef.current = true;
    // One-tick delay so the bridge + store subscriptions settle first.
    const t = setTimeout(() => { togglePlay(); }, 250);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoplayHint, data?.station]);

  if (loading) {
    return (
      <div data-testid="live-radio-station-loading"
           className="text-white max-w-[920px] mx-auto px-5 pt-10 pb-24">
        <div className="h-6 w-40 bg-white/[0.06] rounded mb-4 animate-pulse" />
        <div className="flex gap-6">
          <div className="w-48 h-48 bg-white/[0.06] rounded-xl animate-pulse" />
          <div className="flex-grow space-y-2">
            <div className="h-8 w-2/3 bg-white/[0.06] rounded animate-pulse" />
            <div className="h-4 w-1/2 bg-white/[0.06] rounded animate-pulse" />
            <div className="h-12 w-32 bg-white/[0.06] rounded-full mt-4 animate-pulse" />
          </div>
        </div>
      </div>
    );
  }

  if (err || !data) {
    return (
      <div data-testid="live-radio-station-error"
           className="text-white max-w-[920px] mx-auto px-5 pt-10 pb-24">
        <Link to="/radio"
              data-testid="live-radio-station-back"
              className="inline-flex items-center gap-1 text-xs
                         text-white/50 hover:text-white mb-6">
          <ArrowLeft size={12} /> Back to Radio
        </Link>
        <div className="text-center py-16">
          <AlertCircle size={32} className="mx-auto mb-3 text-white/30" />
          <div className="text-sm text-white/60">
            {err === "station_not_found"
              ? "We couldn't find that station."
              : "Something went wrong loading this station."}
          </div>
          <Link to="/radio"
                className="text-xs text-cyan-300 hover:text-cyan-200 mt-3
                           inline-block">
            Browse all stations →
          </Link>
        </div>
      </div>
    );
  }

  const s = data.station;
  const isAI = s.source === "bigfm_ai";
  const cats = data.categories || [];

  return (
    <div data-testid="live-radio-station-page"
         data-station-id={id}
         data-station-source={s.source}
         className="text-white max-w-[920px] mx-auto px-5 pt-6 pb-24">
      {/* Phase 42-E2.4 — OG meta keyed off the live station entity. */}
      <OGMeta
        entityType="station"
        entityId={s.slug || s.id || id}
        title={`${s.name} on RadioLife`}
        description={s.tagline || s.description
                            || `Listen to ${s.name} live on RadioLife.`} />
      <Link to="/radio"
            data-testid="live-radio-station-back"
            className="inline-flex items-center gap-1 text-xs
                       text-white/50 hover:text-white mb-6">
        <ArrowLeft size={12} /> Back to Radio
      </Link>

      <div className="flex flex-col md:flex-row gap-6 md:gap-8 mb-10">
        {/* Cover */}
        <div className="relative w-48 h-48 md:w-56 md:h-56 rounded-xl
                        overflow-hidden bg-bg-elevated flex items-center
                        justify-center flex-shrink-0 mx-auto md:mx-0">
          {s.favicon ? (
            <img src={resolveImg(s.favicon)} alt=""
                 onError={(e) => { e.currentTarget.style.display = "none"; }}
                 className="w-full h-full object-cover" />
          ) : null}
          <RadioIcon size={48} className="text-white/30 absolute" />
          {isAI && (
            <span className="absolute top-2 left-2 text-[10px] uppercase
                             tracking-widest font-mono px-2 py-1
                             rounded bg-cyan-400/20 text-cyan-300
                             border border-cyan-400/30"
                  data-testid="live-radio-station-badge-ai">
              AI-Curated
            </span>
          )}
          {/* Phase 42-D3 — favorite toggle on station detail. */}
          <div className="absolute top-2 right-2 z-10">
            <FavoriteHeart
              stationId={s.id}
              stationType={isAI ? "bigfm" : "imported"}
              station={{
                name: s.name, favicon: s.favicon,
                thumbnail_url: s.favicon,
                country: s.country, language: s.language,
              }}
              size={16} />
          </div>
        </div>

        {/* Header info */}
        <div className="flex-grow min-w-0">
          <div className="text-xs font-mono uppercase tracking-widest
                          text-cyan-400/80 mb-1">
            {isAI ? "RadioLife AI Channel" : "Live Radio Station"}
          </div>
          <h1 className="text-3xl sm:text-4xl font-bold tracking-tight
                         leading-tight mb-3"
              data-testid="live-radio-station-name">
            {s.name}
            {s.claim_badge_visible && (
              <span data-testid="live-radio-station-claim-badge"
                    className="ml-3 inline-flex items-center gap-1 px-2.5
                               h-7 align-middle rounded-full
                               bg-emerald-400/15 border border-emerald-400/30
                               text-emerald-300 text-xs font-mono">
                <ShieldCheck size={12} /> Claimed by owner
              </span>
            )}
          </h1>
          {s.owner_overrides?.description && (
            <p data-testid="live-radio-station-owner-description"
               className="text-sm text-white/70 mb-4 max-w-prose">
              {s.owner_overrides.description}
            </p>
          )}
          <div className="flex flex-wrap gap-x-4 gap-y-1.5 text-sm
                          text-white/60 mb-5">
            {s.country && (
              <span className="inline-flex items-center gap-1.5">
                <MapPin size={12} /> {s.country}
                {s.country_code ? ` (${s.country_code})` : ""}
              </span>
            )}
            {s.language && (
              <span className="inline-flex items-center gap-1.5">
                <Languages size={12} /> <span className="capitalize">{s.language}</span>
              </span>
            )}
            {s.bitrate != null && (
              <span className="inline-flex items-center gap-1.5">
                <RadioIcon size={12} /> {s.bitrate} kbps
                {s.codec ? ` · ${s.codec}` : ""}
              </span>
            )}
            {s.votes != null && (
              <span className="inline-flex items-center gap-1.5">
                <Award size={12} /> {s.votes} votes
              </span>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={isAI
                ? () => navigate(`/radio?channel=${encodeURIComponent(s.id)}`)
                : togglePlay}
              disabled={!isAI && !s.stream_url}
              data-testid="live-radio-station-play"
              data-playing={playing}
              className="inline-flex items-center gap-2 px-5 h-11
                         rounded-full bg-cyan-400 text-slate-900
                         font-semibold text-sm hover:bg-cyan-300
                         disabled:opacity-40 disabled:cursor-not-allowed
                         transition-colors">
              {isAI
                ? <><Sparkles size={14} /> Open in Radio</>
                : playing
                  ? <><Pause size={14} /> Pause</>
                  : <><Play size={14} /> Play live</>}
            </button>
            {!isAI && !s.claim_badge_visible && (
              <button
                type="button"
                onClick={onClaim}
                data-testid="live-radio-station-claim"
                className="inline-flex items-center gap-2 px-4 h-11
                           rounded-full bg-white/[0.06] hover:bg-white/[0.12]
                           border border-white/[0.10] text-sm
                           text-white/80 hover:text-white transition-colors">
                <Award size={13} /> Claim this station
              </button>
            )}
            {!isAI && s.claim_badge_visible && (
              <span data-testid="live-radio-station-already-claimed-chip"
                    className="inline-flex items-center gap-1.5 px-3 h-11
                               rounded-full bg-emerald-400/[0.06]
                               border border-emerald-400/30
                               text-emerald-200 text-xs">
                <ShieldCheck size={13} /> Verified · operated by owner
              </span>
            )}
            {s.homepage && (
              <a href={s.homepage}
                 target="_blank" rel="noopener noreferrer"
                 data-testid="live-radio-station-homepage"
                 className="inline-flex items-center gap-1.5 text-xs
                            text-white/40 hover:text-white/70
                            underline-offset-4 hover:underline">
                <ExternalLink size={11} /> Visit site
              </a>
            )}
            {/* Phase 42-E2.2 — share this station */}
            <ShareButton
              featureType="station"
              contentId={s.id}
              title={`${s.name} on RadioLife`}
              text={`I'm tuned to ${s.name} on RadioLife. Listen with me:`} />
          </div>

          {/* Phase 42-B2 hotfix — local <audio> removed.  The global
              <ImportedStreamBridge /> now owns playback after
              togglePlay() routes the station into the player store. */}
          {streamErr && (
            <div data-testid="live-radio-station-stream-error"
                 className="mt-3 px-3 py-2 rounded-lg text-xs
                            bg-amber-500/10 border border-amber-500/30
                            text-amber-200 inline-flex items-center gap-2">
              <AlertCircle size={12} /> {streamErr}
            </div>
          )}
        </div>
      </div>

      {/* Owner/admin artwork tools — imported stations only. */}
      {data?.viewer_is_owner && !isAI && (
        <section data-testid="owner-artwork-manager"
                 className="mb-8 rounded-xl border border-white/[0.10] bg-white/[0.03] p-4">
          <div className="text-xs uppercase tracking-widest text-white/50 font-mono mb-3 inline-flex items-center gap-1.5">
            <ImageIcon size={12} /> Station artwork · owner tools
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="button" data-testid="owner-art-generate" onClick={genArt} disabled={artBusy}
                    className="inline-flex items-center gap-2 px-4 h-10 rounded-full bg-cyan-400 text-slate-900 font-semibold text-sm disabled:opacity-40">
              <Sparkles size={14} /> {artBusy ? "Working…" : "Generate AI artwork"}
            </button>
            <label data-testid="owner-art-upload"
                   className="inline-flex items-center gap-2 px-4 h-10 rounded-full bg-white/[0.06] border border-white/[0.10] text-sm text-white/80 cursor-pointer hover:bg-white/[0.12]">
              <Upload size={14} /> Upload logo
              <input type="file" accept="image/png,image/jpeg,image/webp" className="hidden" onChange={uploadArt} disabled={artBusy} />
            </label>
            <button type="button" data-testid="owner-art-clear" onClick={clearArt} disabled={artBusy}
                    className="inline-flex items-center gap-2 px-4 h-10 rounded-full bg-white/[0.06] border border-white/[0.10] text-sm text-white/60 hover:text-white/90">
              <Trash2 size={14} /> Reset
            </button>
          </div>
          <div className="text-[11px] text-white/40 mt-2">
            AI art is generated from your station name &amp; genre. Upload your own logo to override it.
          </div>
        </section>
      )}

      {/* Phase AD.11 — station_detail banner slot (leaderboard). */}
      <BannerZoneSlot zone="station_detail" />

      {/* Phase AD.8 — Daily code claim widget. */}
      <DailyCodeWidget />

      {/* Tags */}
      {s.tags_json && s.tags_json.length > 0 && (
        <section data-testid="live-radio-station-tags" className="mb-8">
          <div className="text-xs uppercase tracking-widest text-white/40
                          font-mono mb-2 inline-flex items-center gap-1.5">
            <Tag size={11} /> Tags
          </div>
          <div className="flex flex-wrap gap-1.5">
            {s.tags_json.slice(0, 20).map((t) => (
              <span key={t}
                    data-testid={`live-radio-station-tag-${t}`}
                    className="text-xs px-2 py-1 rounded-full
                               bg-white/[0.05] border border-white/[0.08]
                               text-white/70">
                {t}
              </span>
            ))}
          </div>
        </section>
      )}

      {/* Categories assigned */}
      {cats.length > 0 && (
        <section data-testid="live-radio-station-categories"
                 className="mb-8">
          <div className="text-xs uppercase tracking-widest text-white/40
                          font-mono mb-2">
            RadioLife categories
          </div>
          <div className="flex flex-wrap gap-2">
            {cats.map((c) => (
              <Link
                key={c.category}
                to={`/radio/browse?category=${c.category}`}
                data-testid={`live-radio-station-cat-${c.category}`}
                className="text-xs px-3 h-7 inline-flex items-center
                           rounded-full bg-cyan-400/10 hover:bg-cyan-400/20
                           border border-cyan-400/20 text-cyan-200
                           transition-colors">
                <span className="capitalize">{c.category}</span>
                <span className="ml-1.5 text-[10px] text-cyan-300/60
                                 font-mono">
                  {Math.round(c.confidence_score * 100)}%
                </span>
              </Link>
            ))}
          </div>
        </section>
      )}

      {/* Similar AI suggestion */}
      {data.similar_ai_channel && (
        <section data-testid="live-radio-station-similar-ai"
                 className="mb-8 p-4 rounded-xl bg-cyan-400/[0.06]
                            border border-cyan-400/20">
          <div className="text-xs uppercase tracking-widest text-cyan-300
                          font-mono mb-3 inline-flex items-center gap-1.5">
            <Sparkles size={11} /> You might like a RadioLife AI channel
          </div>
          <button
            type="button"
            onClick={() => navigate(
              `/radio?channel=${encodeURIComponent(data.similar_ai_channel.id)}`)}
            data-testid="live-radio-station-similar-ai-card"
            className="flex items-center gap-4 w-full text-left
                       hover:bg-white/[0.04] rounded-lg p-2 -m-2
                       transition-colors">
            <div className="w-16 h-16 rounded-lg bg-gradient-to-br
                            from-cyan-500/30 to-cyan-700/30
                            flex items-center justify-center
                            flex-shrink-0">
              <Sparkles size={24} className="text-cyan-300" />
            </div>
            <div className="flex-grow min-w-0">
              <div className="text-sm font-semibold text-white">
                {data.similar_ai_channel.name}
              </div>
              <div className="text-xs text-white/50 mt-0.5">
                Personalized to your taste · AI-curated · Mood-aware
              </div>
            </div>
            <div className="text-xs text-cyan-300 font-medium
                            whitespace-nowrap">
              Open →
            </div>
          </button>
        </section>
      )}

      {/* Phase FUN.1.1 — Flagship stations "you might also like" strip.
            Region-aware — backend pins user's region first. */}
      <FlagshipStrip
        limit={6}
        title="Flagship stations you might also like"
        testId="nowplaying-flagship-strip" />

      {/* Phase AD.11 — now_playing banner (320×180 compact). */}
      <div className="mt-8 flex justify-center">
        <BannerZoneSlot zone="now_playing" />
      </div>
    </div>
  );
}
