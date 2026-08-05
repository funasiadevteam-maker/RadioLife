/** Phase 41 Session 4.A — In-Store Business TV Display kiosk page.
 *
 * Route: `/tv/:slug` (UNAUTHENTICATED — no login required, lives
 * OUTSIDE the ProtectedRoute wrapper in App.js).
 *
 * Layout target: 1920×1080 (16:9). All sizing in `clamp()` units so
 * it scales gracefully up to 4K and down to a generic laptop.
 *
 *  ┌──────────────────────────────────────────────────────────────┐
 *  │ [logo] STATION NAME              [QR + "Listen on phone"]    │
 *  │  tagline · location                                          │
 *  │                                                              │
 *  │           ┌──────────────┐                                   │
 *  │           │  COVER ART   │   NOW PLAYING                     │
 *  │           │  (color tile)│   Track Title — Artist            │
 *  │           └──────────────┘   ▰▰▰▰▰▱▱▱▱▱▱▱▱▱▱▱ 1:34 / 3:00     │
 *  │                                                              │
 *  │ [announcement ticker scrolling →]                            │
 *  └──────────────────────────────────────────────────────────────┘
 *
 * Polls `/api/tv/{slug}` every `refresh_after_sec` (default 10s).
 * Visibility-aware: pauses while the tab is hidden.
 * Auto-fullscreen on first user click anywhere on the document
 * (browser API requires the user gesture).
 * Reserves every element's dimensions so the initial paint is
 * layout-shift safe.
 */
import React, { useEffect, useRef, useState, useMemo, useCallback } from "react";
import { useParams } from "react-router-dom";
import axios from "axios";
import QRCode from "react-qr-code";
import { Radio as RadioIcon, MapPin, Clock, Shield, Wifi } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const DEFAULT_REFRESH_SEC = 10;

function pad(n) { return n < 10 ? `0${n}` : `${n}`; }
function fmtMmSs(secs) {
  if (!secs || secs < 0) return "0:00";
  const m = Math.floor(secs / 60);
  const s = Math.floor(secs % 60);
  return `${m}:${pad(s)}`;
}

const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];
function todayKey() {
  return DAYS[(new Date().getDay() + 6) % 7];
}
function isOpenNow(profile) {
  if (!profile) return null;
  const row = (profile.hours || {})[todayKey()];
  if (!row || row.closed) return false;
  const o = row.open, c = row.close;
  if (!o || !c) return null;
  const [oh, om] = o.split(":").map((n) => parseInt(n, 10));
  const [ch, cm] = c.split(":").map((n) => parseInt(n, 10));
  if ([oh, om, ch, cm].some((n) => Number.isNaN(n))) return null;
  const now = new Date();
  const cur = now.getHours() * 60 + now.getMinutes();
  const openMin = oh * 60 + om, closeMin = ch * 60 + cm;
  if (closeMin <= openMin) return cur >= openMin || cur < closeMin;
  return openMin <= cur && cur < closeMin;
}

export default function StationTV() {
  const { slug } = useParams();
  const [state, setState] = useState(null);
  const [err, setErr]     = useState(null);
  const fullscreenRef     = useRef(false);

  const refreshSec = (state?.refresh_after_sec) || DEFAULT_REFRESH_SEC;

  const load = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/tv/${encodeURIComponent(slug)}`);
      setState(r.data);
      setErr(null);
    } catch (e) {
      const code = e.response?.data?.detail?.code;
      setErr(code || e.response?.status || "error");
    }
  }, [slug]);

  useEffect(() => {
    let cancelled = false;
    Promise.resolve().then(() => { if (!cancelled) load(); });
    return () => { cancelled = true; };
  }, [load]);

  // Polling loop — visibility-aware.
  useEffect(() => {
    let timer = null;
    const tickFn = () => {
      if (document.visibilityState === "visible") load();
    };
    timer = setInterval(tickFn, refreshSec * 1000);
    return () => { if (timer) clearInterval(timer); };
  }, [load, refreshSec]);

  // Auto-fullscreen on first user gesture.
  useEffect(() => {
    function onFirstClick() {
      if (fullscreenRef.current) return;
      try {
        const el = document.documentElement;
        if (el.requestFullscreen) el.requestFullscreen().catch(() => {});
        fullscreenRef.current = true;
      } catch { /* ignore */ }
    }
    document.addEventListener("click", onFirstClick, { once: true });
    return () => document.removeEventListener("click", onFirstClick);
  }, []);

  // Browser TAB color
  useEffect(() => {
    if (state?.station?.name) {
      document.title = `${state.station.name} · RadioLife TV`;
    } else {
      document.title = "RadioLife · TV Display";
    }
  }, [state?.station?.name]);

  if (err === "private_station") {
    return <ErrorScreen title="Private station" message="This station's TV display is not public." />;
  }
  if (err === "not_found" || err === 404) {
    return <ErrorScreen title="Station not found" message={`No station with slug "${slug}".`} />;
  }
  if (err) {
    return <ErrorScreen title="Unable to load TV display" message="Check your connection and try again." />;
  }

  return (
    <div data-testid="station-tv-page"
         data-slug={slug}
         data-page-type={state?.station?.page_type || ""}
         style={{
           minHeight: "100vh", width: "100%",
           background: state?.station?.cover_color
             ? `linear-gradient(135deg, ${state.station.cover_color}22, #050505 60%)`
             : "linear-gradient(135deg, #00d9ff22, #050505 60%)",
           color: "#fff",
           fontFamily: "Inter, system-ui, sans-serif",
           padding: "clamp(16px, 2.5vw, 40px)",
           display: "grid",
           gridTemplateRows: "auto 1fr auto",
           gap: "clamp(12px, 2vw, 32px)",
           overflow: "hidden",
         }}>
      <HeaderRow state={state} slug={slug} />
      <NowPlayingRow state={state} />
      <AnnouncementTicker items={state?.announcements} slug={slug} />
    </div>
  );
}

function HeaderRow({ state, slug }) {
  const st = state?.station;
  const bp = st?.business_profile || null;
  const isBusiness = st?.is_business;
  const openNow = useMemo(() => isOpenNow(bp), [bp]);
  return (
    <div style={{ display: "grid",
                   gridTemplateColumns: "1fr auto",
                   gap: "clamp(16px, 2vw, 40px)",
                   alignItems: "start" }}>
      <div data-testid="tv-station-header"
           style={{ display: "flex", alignItems: "center",
                     gap: "clamp(14px, 1.5vw, 28px)", minWidth: 0 }}>
        <div data-testid="tv-station-logo-wrap"
             style={{ width: "clamp(72px, 8vw, 132px)",
                       height: "clamp(72px, 8vw, 132px)",
                       borderRadius: "clamp(12px, 1vw, 24px)",
                       background: bp?.logo_url
                         ? `url(${bp.logo_url}) center/cover`
                         : (st?.cover_color
                              ? `${st.cover_color}33`
                              : "rgba(255,255,255,0.06)"),
                       border: "1px solid rgba(255,255,255,0.1)",
                       display: "flex", alignItems: "center",
                       justifyContent: "center", flexShrink: 0 }}>
          {!bp?.logo_url && (
            <RadioIcon size={36} color="rgba(255,255,255,0.45)" />
          )}
        </div>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: "clamp(11px, 0.85vw, 16px)",
                          fontFamily: "monospace", letterSpacing: 3,
                          color: "rgba(255,255,255,0.6)",
                          marginBottom: 8, textTransform: "uppercase" }}>
            {isBusiness ? "Live in-store on" : "Now streaming on"}
          </div>
          <h1 data-testid="tv-station-name"
              style={{ fontSize: "clamp(36px, 4.2vw, 84px)",
                        fontWeight: 800, lineHeight: 0.95, margin: 0,
                        overflow: "hidden", textOverflow: "ellipsis",
                        whiteSpace: "nowrap" }}>
            {st?.name || "Loading…"}
          </h1>
          <div style={{ display: "flex", alignItems: "center",
                          gap: "clamp(10px, 1vw, 18px)", flexWrap: "wrap",
                          marginTop: "clamp(10px, 1vw, 16px)",
                          fontSize: "clamp(13px, 1.05vw, 20px)",
                          color: "rgba(255,255,255,0.78)" }}>
            {st?.tagline && (
              <span data-testid="tv-station-tagline">{st.tagline}</span>
            )}
            {bp && (bp.address || bp.city) && (
              <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                <MapPin size={16} />
                {[bp.address, bp.city].filter(Boolean).join(", ")}
              </span>
            )}
            {bp?.verified && (
              <span data-testid="tv-verified-chip"
                    style={{ display: "inline-flex", alignItems: "center", gap: 4,
                              padding: "3px 12px", borderRadius: 999,
                              background: "rgba(0,217,255,0.18)",
                              color: "#00d9ff",
                              border: "1px solid rgba(0,217,255,0.5)",
                              fontWeight: 700, fontSize: "clamp(10px, 0.85vw, 14px)",
                              textTransform: "uppercase",
                              letterSpacing: "0.06em" }}>
                <Shield size={12} /> Verified
              </span>
            )}
            {openNow !== null && openNow !== undefined && (
              <span data-testid="tv-open-now-badge"
                    data-open={openNow ? "true" : "false"}
                    style={{ display: "inline-flex", alignItems: "center", gap: 4,
                              padding: "3px 12px", borderRadius: 999,
                              background: openNow ? "rgba(16,185,129,0.18)"
                                                  : "rgba(255,255,255,0.08)",
                              color: openNow ? "#10b981" : "rgba(255,255,255,0.55)",
                              border: `1px solid ${openNow ? "rgba(16,185,129,0.4)" : "rgba(255,255,255,0.08)"}`,
                              fontWeight: 700, fontSize: "clamp(10px, 0.85vw, 14px)",
                              textTransform: "uppercase",
                              letterSpacing: "0.06em" }}>
                <Clock size={12} />
                {openNow ? "Open now" : "Closed"}
              </span>
            )}
          </div>
        </div>
      </div>
      <QRPanel target={state?.qr_target_url || `${window.location.origin}/r/${slug}`} />
    </div>
  );
}

function QRPanel({ target }) {
  // Ensure absolute URL — backend may have returned just `/r/{slug}` if it
  // wasn't able to resolve a PUBLIC_BACKEND_URL at startup. We patch with
  // window.location.origin so the QR is always scannable.
  const absolute = useMemo(() => {
    if (!target) return "";
    if (/^https?:\/\//i.test(target)) return target;
    if (target.startsWith("/")) return `${window.location.origin}${target}`;
    return `${window.location.origin}/${target}`;
  }, [target]);
  return (
    <div data-testid="tv-qr-panel"
         data-qr-target={absolute}
         style={{ display: "flex", flexDirection: "column",
                   alignItems: "center", gap: 10,
                   padding: "clamp(10px, 1vw, 18px)",
                   borderRadius: "clamp(12px, 1vw, 22px)",
                   background: "rgba(255,255,255,0.06)",
                   border: "1px solid rgba(255,255,255,0.08)",
                   minWidth: "clamp(140px, 13vw, 220px)" }}>
      <div style={{ background: "#fff",
                     padding: "clamp(8px, 0.7vw, 16px)",
                     borderRadius: "clamp(8px, 0.6vw, 14px)",
                     lineHeight: 0 }}>
        {absolute ? (
          <QRCode value={absolute}
                  size={Math.round(Math.min(window.innerWidth, window.innerHeight) * 0.12) || 160}
                  bgColor="#ffffff" fgColor="#0b0b0b"
                  data-testid="tv-qr-code"
                  style={{ display: "block",
                            height: "clamp(120px, 11vw, 200px)",
                            width: "clamp(120px, 11vw, 200px)" }} />
        ) : null}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 6,
                     fontSize: "clamp(11px, 0.95vw, 16px)",
                     color: "rgba(255,255,255,0.85)",
                     fontWeight: 600, letterSpacing: "0.02em" }}>
        <Wifi size={13} /> Listen on your phone
      </div>
    </div>
  );
}

function NowPlayingRow({ state }) {
  const np = state?.now_playing;
  const [elapsed, setElapsed] = useState(0);
  // `duration` is the *displayed* track length. When the backend
  // seeds a track shorter than the 3-minute slot we still want a
  // pleasant moving progress bar, so we loop the elapsed counter
  // within `[0, duration)` for the entire slot.
  const duration = useMemo(() => {
    if (!np) return 0;
    const trackDur = Number(np.duration_sec) || 0;
    return trackDur > 0 ? trackDur : (np.slot_seconds || 180);
  }, [np]);
  const coverColor = np?.cover_color || "#00d9ff";

  useEffect(() => {
    if (!np) {
      Promise.resolve().then(() => setElapsed(0));
      return undefined;
    }
    const startedAt = np.started_at || 0;
    const slot      = np.slot_seconds || 180;
    let cancelled = false;
    const compute = () => {
      if (cancelled) return;
      const now = Math.floor(Date.now() / 1000);
      const sinceSlotStart = Math.max(0, Math.min(now - startedAt, slot));
      // Loop within the slot if the track is shorter so the bar
      // cycles continuously instead of saturating at 100%.
      const looped = duration > 0 ? sinceSlotStart % duration : 0;
      setElapsed(Math.min(looped, duration));
    };
    const initial = setTimeout(compute, 0);
    const t = setInterval(compute, 1000);
    return () => {
      cancelled = true;
      clearTimeout(initial);
      clearInterval(t);
    };
  }, [np, duration]);

  const progress = duration > 0 ? Math.min(elapsed / duration, 1) : 0;

  if (!np) {
    return (
      <div data-testid="tv-now-playing-empty"
           style={{ display: "grid", placeItems: "center",
                     padding: "clamp(24px, 4vw, 80px)" }}>
        <div style={{ textAlign: "center", maxWidth: 720 }}>
          <RadioIcon size={64} color="rgba(255,255,255,0.3)"
                       style={{ marginBottom: 18 }} />
          <div style={{ fontSize: "clamp(24px, 2.6vw, 48px)",
                          fontWeight: 700, marginBottom: 8 }}>
            Tuning in soon
          </div>
          <div style={{ fontSize: "clamp(14px, 1.2vw, 22px)",
                          color: "rgba(255,255,255,0.6)",
                          lineHeight: 1.5 }}>
            Scan the QR with your phone to start listening — this screen
            will light up automatically once the station goes live.
          </div>
        </div>
      </div>
    );
  }

  return (
    <div data-testid="tv-now-playing"
         style={{ display: "grid",
                   gridTemplateColumns: "auto 1fr",
                   gap: "clamp(20px, 3vw, 64px)",
                   alignItems: "center",
                   padding: "clamp(20px, 2.5vw, 56px)" }}>
      <div data-testid="tv-cover-art"
           aria-label="album art"
           style={{ width: "clamp(180px, 22vw, 420px)",
                     height: "clamp(180px, 22vw, 420px)",
                     borderRadius: "clamp(16px, 1.4vw, 28px)",
                     background: np.cover_image_url
                       ? `url(${np.cover_image_url}) center/cover`
                       : `linear-gradient(135deg, ${coverColor}, ${coverColor}66 60%, #050505)`,
                     border: "1px solid rgba(255,255,255,0.06)",
                     boxShadow: "0 30px 60px rgba(0,0,0,0.45)",
                     display: "flex", alignItems: "flex-end",
                     justifyContent: "flex-start",
                     padding: "clamp(12px, 1.2vw, 22px)" }}>
        <div style={{ fontFamily: "monospace",
                        fontSize: "clamp(10px, 0.85vw, 16px)",
                        letterSpacing: 3, opacity: 0.7,
                        textTransform: "uppercase" }}>
          NOW PLAYING
        </div>
      </div>
      <div style={{ minWidth: 0 }}>
        <div data-testid="tv-track-title"
             style={{ fontSize: "clamp(32px, 4vw, 72px)",
                       fontWeight: 800, lineHeight: 1.05,
                       marginBottom: "clamp(8px, 1vw, 16px)",
                       overflow: "hidden", textOverflow: "ellipsis",
                       whiteSpace: "nowrap" }}>
          {np.title || "Untitled"}
        </div>
        <div data-testid="tv-track-artist"
             style={{ fontSize: "clamp(18px, 1.8vw, 32px)",
                       color: "rgba(255,255,255,0.75)",
                       marginBottom: "clamp(20px, 2vw, 32px)",
                       overflow: "hidden", textOverflow: "ellipsis",
                       whiteSpace: "nowrap" }}>
          {np.artist || "Unknown artist"}
        </div>
        <div data-testid="tv-progress-bar"
             role="progressbar"
             aria-valuemin={0} aria-valuemax={100}
             aria-valuenow={Math.round(progress * 100)}
             style={{ width: "100%",
                       height: "clamp(8px, 0.6vw, 12px)",
                       borderRadius: 999,
                       background: "rgba(255,255,255,0.08)",
                       overflow: "hidden",
                       marginBottom: 10 }}>
          <div style={{ width: `${Math.round(progress * 100)}%`,
                          height: "100%",
                          background: coverColor,
                          transition: "width 1s linear" }} />
        </div>
        <div style={{ display: "flex", justifyContent: "space-between",
                        fontFamily: "monospace",
                        fontSize: "clamp(13px, 1vw, 18px)",
                        color: "rgba(255,255,255,0.55)" }}>
          <span data-testid="tv-elapsed">{fmtMmSs(elapsed)}</span>
          <span data-testid="tv-duration">{fmtMmSs(duration)}</span>
        </div>
      </div>
    </div>
  );
}

function AnnouncementTicker({ items, slug }) {
  const list = items || [];
  const couponPick = useMemo(
    () => list.find((a) => a.coupon && a.coupon.code) || null,
    [list]);

  if (list.length === 0 && !couponPick) {
    // Reserve the height so layout doesn't shift when announcements
    // appear/disappear during polling.
    return <div data-testid="tv-announcement-ticker-empty"
                style={{ height: "clamp(56px, 5vw, 96px)" }} />;
  }
  // Duplicate the list so the CSS keyframe loops seamlessly.
  const doubled = list.concat(list);
  return (
    <div style={{ display: "grid",
                   gridTemplateColumns: couponPick ? "auto 1fr" : "1fr",
                   gap: "clamp(12px, 1.4vw, 28px)",
                   alignItems: "stretch" }}>
      {couponPick && <CouponSpotlight ann={couponPick} slug={slug} />}
      {list.length > 0 && (
        <div data-testid="tv-announcement-ticker"
              data-count={list.length}
              style={{ height: couponPick ? "clamp(120px, 11vw, 200px)" : "clamp(56px, 5vw, 96px)",
                        borderRadius: "clamp(12px, 1vw, 22px)",
                        background: "rgba(255,255,255,0.07)",
                        border: "1px solid rgba(255,255,255,0.08)",
                        overflow: "hidden", position: "relative",
                        display: "flex", alignItems: "center" }}>
          <div style={{ display: "flex", gap: "clamp(40px, 4vw, 96px)",
                         paddingLeft: "clamp(20px, 2vw, 40px)",
                         animation: list.length > 1
                           ? `bigfm-ticker ${Math.max(20, list.length * 12)}s linear infinite`
                           : "none",
                         whiteSpace: "nowrap",
                         fontSize: "clamp(16px, 1.5vw, 28px)",
                         fontWeight: 600 }}>
            {doubled.map((a, i) => (
              <div key={`${a.id || i}-${i}`}
                   data-testid={`tv-announcement-${a.id || i}`}
                   style={{ display: "inline-flex", alignItems: "center",
                             gap: 10 }}>
                <span style={{ width: 8, height: 8, borderRadius: 999,
                                  background: a.coupon ? "#00d9ff" : "#fff",
                                  boxShadow: a.coupon
                                    ? "0 0 12px #00d9ff" : "none" }} />
                {a.image_url && (
                  <img src={a.image_url} alt=""
                         style={{ height: "clamp(36px, 3vw, 64px)",
                                   width: "clamp(36px, 3vw, 64px)",
                                   borderRadius: 8, objectFit: "cover" }} />
                )}
                <span>{a.message}</span>
                {a.coupon && a.coupon.code && (
                  <span style={{ fontFamily: "monospace",
                                    fontSize: "clamp(13px, 1.1vw, 22px)",
                                    background: "rgba(0,217,255,0.15)",
                                    color: "#00d9ff",
                                    border: "1px solid rgba(0,217,255,0.5)",
                                    padding: "2px 12px", borderRadius: 6,
                                    letterSpacing: "0.06em" }}>
                    🎟 {a.coupon.code}
                  </span>
                )}
              </div>
            ))}
          </div>
          <style>{`
            @keyframes bigfm-ticker {
              0%   { transform: translateX(0); }
              100% { transform: translateX(-50%); }
            }
          `}</style>
        </div>
      )}
    </div>
  );
}

function CouponSpotlight({ ann, slug }) {
  const c = ann.coupon || {};
  const claimUrl = `${window.location.origin}/r/${encodeURIComponent(slug || "")}#coupon-${ann.id}`;
  const discount = c.discount_pct
    ? `${c.discount_pct}% OFF`
    : c.discount_amount_cents
      ? `$${(c.discount_amount_cents/100).toFixed(2)} OFF`
      : "Reward";
  const remaining = (typeof c.remaining === "number") ? c.remaining : null;
  return (
    <div data-testid="tv-coupon-spotlight"
         data-coupon-code={c.code || ""}
         style={{ display: "grid",
                   gridTemplateColumns: "auto 1fr",
                   gap: "clamp(10px, 1vw, 24px)",
                   alignItems: "center",
                   padding: "clamp(10px, 1vw, 18px)",
                   borderRadius: "clamp(12px, 1vw, 22px)",
                   background: "linear-gradient(135deg, rgba(0,217,255,0.18), rgba(255,46,150,0.1))",
                   border: "1px solid rgba(0,217,255,0.4)" }}>
      <div style={{ background: "#fff", padding: 10,
                     borderRadius: 12, lineHeight: 0,
                     boxShadow: "0 8px 24px rgba(0,0,0,0.35)" }}>
        <QRCode value={claimUrl}
                  size={120}
                  bgColor="#ffffff" fgColor="#0b0b0b"
                  data-testid="tv-coupon-qr"
                  style={{ display: "block",
                            width: "clamp(80px, 8vw, 140px)",
                            height: "clamp(80px, 8vw, 140px)" }} />
      </div>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontFamily: "monospace",
                       fontSize: "clamp(10px, 0.9vw, 16px)",
                       letterSpacing: "0.16em",
                       color: "#00d9ff", textTransform: "uppercase",
                       marginBottom: 4 }}>
          Scan to claim
        </div>
        <div style={{ fontSize: "clamp(20px, 2.4vw, 42px)",
                       fontWeight: 800, lineHeight: 1, marginBottom: 6,
                       color: "#fff" }}>
          {discount}
        </div>
        <div style={{ display: "inline-flex", alignItems: "center",
                       gap: 8, flexWrap: "wrap" }}>
          <span data-testid="tv-coupon-code"
                style={{ fontFamily: "monospace",
                          fontSize: "clamp(13px, 1.2vw, 22px)",
                          background: "rgba(0,0,0,0.4)",
                          color: "#00d9ff",
                          border: "1px solid rgba(0,217,255,0.5)",
                          padding: "3px 14px", borderRadius: 8,
                          letterSpacing: "0.08em", fontWeight: 700 }}>
            🎟 {c.code}
          </span>
          {(remaining != null) && (
            <span data-testid="tv-coupon-remaining"
                  style={{ fontSize: "clamp(11px, 0.95vw, 16px)",
                            color: remaining > 0 ? "#cbd5e1" : "#fb7185",
                            fontWeight: 600 }}>
              {remaining > 0 ? `${remaining} left` : "Sold out"}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

function ErrorScreen({ title, message }) {
  return (
    <div data-testid="tv-error-screen"
         style={{ minHeight: "100vh", display: "grid", placeItems: "center",
                   background: "#050505", color: "#fff", padding: 40,
                   textAlign: "center", fontFamily: "Inter, system-ui" }}>
      <div>
        <div style={{ fontSize: 36, fontWeight: 700, marginBottom: 10 }}>
          {title}
        </div>
        <div style={{ color: "#9aa3af" }}>{message}</div>
      </div>
    </div>
  );
}
