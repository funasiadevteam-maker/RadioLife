/** Phase 41 Session 3.A — Station Page (`/r/:slug`).
 *
 * Renamed from `PersonalRadioPage.jsx`. Renders BOTH personal and
 * business radio stations off a single route. When the loaded
 * station's `page_type === "business_radio"`, a `BusinessProfileCard`
 * surfaces at the top of the lower content area: logo / address with
 * Google Maps deep-link / dynamic "Open now"|"Closed" badge / phone /
 * website / verified chip.
 *
 * Phase 41 Session 3.B — Celebration toast for post-reaction
 * milestones. Owner-only. When the notifications poll surfaces an
 * unread `post_reaction_milestone` row whose `station_slug` matches
 * THIS station, we fire a one-shot sonner toast. De-duped via a
 * `seenIdsRef` so the same notification id only ever toasts once
 * within the page lifetime.
 */
import React, { useEffect, useRef, useState, useMemo } from "react";
import { useParams } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import {
  Radio as RadioIcon, Users, Plus, Check, Activity,
  MapPin, Phone, Globe as GlobeIcon, Clock, Shield, Flame,
  Tv, MessageSquare, BarChart3, DollarSign,
} from "lucide-react";
import StationFeed from "@/pages/StationFeed";
import AnnouncementManager from "@/components/AnnouncementManager";
import StationAnalytics from "@/pages/StationAnalytics";
import StationEarnings from "@/pages/StationEarnings";
import MoodVoteWidget from "@/components/MoodVoteWidget";
import TopFansSection from "@/components/TopFansSection";
import StationActiveCoupons from "@/components/StationActiveCoupons";
import TriviaLeaderboard from "@/components/TriviaLeaderboard";
import { API, useAuth } from "@/AuthContext";

const LIVE_COUNT_POLL_MS = 15 * 1000;
// 3.B — re-uses the same 60s cadence as NotificationBell so we
// piggyback on the user's existing polling rhythm.
const MILESTONE_POLL_MS  = 60 * 1000;

const DAYS = [
  { key: "mon", label: "Mon" }, { key: "tue", label: "Tue" },
  { key: "wed", label: "Wed" }, { key: "thu", label: "Thu" },
  { key: "fri", label: "Fri" }, { key: "sat", label: "Sat" },
  { key: "sun", label: "Sun" },
];

function todayKey() {
  // JS Date.getDay(): Sun=0..Sat=6 → map to our mon-first array.
  const d = new Date();
  const idx = (d.getDay() + 6) % 7;  // mon=0..sun=6
  return DAYS[idx].key;
}

function isOpenNowLocal(profile) {
  if (!profile) return null;
  const row = (profile.hours || {})[todayKey()];
  if (!row || row.closed) return false;
  const o = row.open, c = row.close;
  if (!o || !c) return null;
  const [oh, om] = o.split(":").map((n) => parseInt(n, 10));
  const [ch, cm] = c.split(":").map((n) => parseInt(n, 10));
  if ([oh, om, ch, cm].some((n) => Number.isNaN(n))) return null;
  const openMin  = oh * 60 + om;
  const closeMin = ch * 60 + cm;
  const now      = new Date();
  const curMin   = now.getHours() * 60 + now.getMinutes();
  if (closeMin <= openMin) {
    // Overnight (e.g. 22:00 → 02:00)
    return curMin >= openMin || curMin < closeMin;
  }
  return openMin <= curMin && curMin < closeMin;
}

function mapsDeepLink(p) {
  const parts = [p.address, p.city, p.country].filter(Boolean).join(", ");
  if (!parts) return null;
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(parts)}`;
}

export default function StationPage() {
  const { slug } = useParams();
  const { user } = useAuth();
  const [s, setS]       = useState(null);
  const [err, setErr]   = useState(null);
  const [following, setFollowing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [liveCount, setLiveCount] = useState(null);
  const [activeTab, setActiveTab] = useState("feed");
  const milestoneSeenRef = useRef(new Set());

  useEffect(() => {
    let cancel = false;
    (async () => {
      try {
        const r = await axios.get(
          `${API}/stations/by-slug/${encodeURIComponent(slug)}`,
          { withCredentials: true });
        if (cancel) return;
        setS(r.data);
        const fs = await axios.get(
          `${API}/stations/${r.data.station_id}/follow/status`,
          { withCredentials: true });
        if (!cancel) setFollowing(!!fs.data?.following);
      } catch (e) {
        if (!cancel) setErr(e.response?.data?.detail?.code || "error");
      }
    })();
    return () => { cancel = true; };
  }, [slug]);

  // Live listener count poll
  useEffect(() => {
    if (!slug) return undefined;
    let cancelled = false;
    let timer = null;
    const tick = async () => {
      if (document.visibilityState !== "visible") return;
      try {
        const r = await axios.get(
          `${API}/stations/${encodeURIComponent(slug)}/listeners`,
          { withCredentials: true });
        if (!cancelled) setLiveCount(r.data?.count ?? 0);
      } catch { /* ignore */ }
    };
    tick();
    timer = setInterval(tick, LIVE_COUNT_POLL_MS);
    return () => { cancelled = true; if (timer) clearInterval(timer); };
  }, [slug]);

  // Phase 41 S3.B — milestone celebration toast (owner-only).
  const isOwner = !!(s && user && s.owner_user_id === user.user_id);
  useEffect(() => {
    if (!isOwner || !slug) return undefined;
    let cancelled = false;
    let timer = null;
    const tick = async () => {
      if (document.visibilityState !== "visible") return;
      try {
        const r = await axios.get(
          `${API}/me/notifications?unread_only=true&limit=20`,
          { withCredentials: true });
        if (cancelled) return;
        const items = r.data?.items || [];
        for (const n of items) {
          if (n.type !== "post_reaction_milestone") continue;
          if (n.station_slug !== slug) continue;
          if (milestoneSeenRef.current.has(n.id)) continue;
          milestoneSeenRef.current.add(n.id);
          const m = n.payload?.milestone;
          const total = n.payload?.total_reactions || m;
          toast.success(
            `Your post just hit ${m} reactions 🔥`,
            { description: `${total} total reactions — keep it up!`,
              duration: 6000,
              id: `milestone-${n.id}` });
        }
      } catch { /* ignore */ }
    };
    // First tick is delayed slightly so we don't burst-fire on initial
    // mount before the user has even seen the page.
    const initial = setTimeout(tick, 1500);
    timer = setInterval(tick, MILESTONE_POLL_MS);
    return () => {
      cancelled = true;
      clearTimeout(initial);
      if (timer) clearInterval(timer);
    };
  }, [isOwner, slug]);

  const toggleFollow = async () => {
    if (!s || busy) return;
    setBusy(true);
    try {
      const path = following ? "unfollow" : "follow";
      await axios.post(`${API}/stations/${s.station_id}/${path}`, {},
        { withCredentials: true });
      setFollowing((f) => !f);
    } catch { /* silent */ }
    setBusy(false);
  };

  if (err) {
    return (
      <div data-testid="station-page-error"
           style={{ maxWidth: 720, margin: "60px auto", padding: 24,
                    color: "#9aa3af", textAlign: "center" }}>
        Station not found.
      </div>
    );
  }
  if (!s) return <div style={{ color: "#9aa3af", padding: 40 }}>Loading…</div>;

  const isBusiness = s.page_type === "business_radio";

  return (
    <div data-testid="station-page"
         data-page-type={s.page_type}
         style={{ maxWidth: 880, margin: "0 auto", padding: 24, color: "#fff" }}>
      <div style={{ height: 180, borderRadius: 14, marginBottom: 22,
                     background: `linear-gradient(135deg, ${s.cover_color || "#00d9ff"}, #0b0b0b)`,
                     display: "flex", alignItems: "flex-end", padding: 22 }}>
        <div>
          <div style={{ fontSize: 10, letterSpacing: 2, fontFamily: "monospace",
                          opacity: 0.85, marginBottom: 6 }}>
            {s.page_type?.toUpperCase().replace(/_/g, " ")}
          </div>
          <h1 style={{ fontSize: 32, fontWeight: 800, margin: 0,
                        lineHeight: 1.1, display: "inline-flex",
                        alignItems: "center", gap: 10 }}>
            {s.name}
            {isBusiness && s.business_profile?.verified && (
              <VerifiedChip />
            )}
          </h1>
          {s.tagline && (
            <div style={{ color: "rgba(255,255,255,0.85)", fontSize: 14,
                            marginTop: 6 }}>
              {s.tagline}
            </div>
          )}
        </div>
      </div>

      <div style={{ display: "flex", gap: 14, alignItems: "center",
                     marginBottom: 22, flexWrap: "wrap" }}>
        <button data-testid="station-play"
                onClick={() => { window.location.href = `/radio?channel=${encodeURIComponent(s.slug)}`; }}
                style={{ background: "#00d9ff", color: "#0b0b0b",
                         border: "none", padding: "10px 18px",
                         borderRadius: 8, fontWeight: 600, fontSize: 14,
                         cursor: "pointer", display: "inline-flex",
                         alignItems: "center", gap: 6 }}>
          <RadioIcon size={16} /> Listen
        </button>
        <button data-testid="station-follow"
                onClick={toggleFollow} disabled={busy}
                style={{ background: following ? "rgba(255,255,255,0.06)"
                                                : "rgba(0,217,255,0.15)",
                         color: following ? "#cbd5e1" : "#00d9ff",
                         border: `1px solid ${following ? "rgba(255,255,255,0.1)" : "#00d9ff"}`,
                         padding: "9px 16px", borderRadius: 8,
                         fontWeight: 600, fontSize: 13, cursor: "pointer",
                         display: "inline-flex", alignItems: "center", gap: 6 }}>
          {following ? <Check size={14} /> : <Plus size={14} />}
          {following ? "Following" : "Follow"}
        </button>
        <a data-testid="station-tv-cta"
           href={`/tv/${encodeURIComponent(s.slug)}`}
           target="_blank" rel="noopener noreferrer"
           title="Open the in-store TV display in a new tab"
           style={{ background: "rgba(255,255,255,0.04)",
                     color: "#cbd5e1",
                     border: "1px solid rgba(255,255,255,0.1)",
                     padding: "9px 14px", borderRadius: 8,
                     fontWeight: 600, fontSize: 13, cursor: "pointer",
                     textDecoration: "none",
                     display: "inline-flex", alignItems: "center", gap: 6 }}>
          <Tv size={14} /> Open TV display
        </a>
        <span data-testid="station-follower-count"
              style={{ display: "inline-flex", alignItems: "center", gap: 4,
                        color: "#9aa3af", fontSize: 13 }}>
          <Users size={13} /> {s.follower_count || 0}
        </span>
        {liveCount !== null && (
          <span data-testid="station-live-listener-count"
                title="Listeners right now"
                style={{ display: "inline-flex", alignItems: "center", gap: 4,
                          color: liveCount > 0 ? "#10b981" : "#6b7280",
                          fontSize: 13, fontWeight: 500 }}>
            <Activity size={13} />
            <span data-testid="station-live-listener-count-value">
              {liveCount}
            </span>
            <span style={{ color: "#9aa3af", fontWeight: 400 }}>live</span>
          </span>
        )}
      </div>

      {isBusiness && (
        <BusinessProfileCard s={s} isOwner={isOwner} />
      )}

      {s.bio && (
        <div style={{ padding: 14, background: "rgba(255,255,255,0.04)",
                       borderRadius: 10, marginBottom: 22, color: "#cbd5e1",
                       fontSize: 14, lineHeight: 1.6 }}>
          {s.bio}
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr",
                     gap: 16 }}>
        <Tile label="Genres"   v={(s.allowed_genres || []).join(", ") || "—"} />
        <Tile label="Moods"    v={(s.allowed_moods  || []).join(", ") || "—"} />
        <Tile label="Host"     v={(s.hosts && s.hosts[0]?.voice_key) || "—"} />
        <Tile label="Language" v={(s.language_mix && s.language_mix[0]?.language) || "—"} />
      </div>

      {/* Phase 41M.A — Mood vote widget (auth-only inside) */}
      <MoodVoteWidget slug={s.slug} />

      {/* Phase 41 S4.5.A — Active offers (listener-facing claim flow) */}
      <StationActiveCoupons slug={s.slug} />

      <div style={{ marginTop: 26 }}>
        {isBusiness && isOwner && (
          <AnnouncementManager slug={s.slug} />
        )}
        {isOwner ? (
          <>
            <div data-testid="station-tabs"
                 role="tablist"
                 style={{ display: "flex", gap: 4,
                           borderBottom: "1px solid rgba(255,255,255,0.06)",
                           marginTop: 28, marginBottom: 18 }}>
              <TabButton testId="station-tab-feed"
                         active={activeTab === "feed"}
                         onClick={() => setActiveTab("feed")}
                         icon={<MessageSquare size={13} />}
                         label="Feed" />
              <TabButton testId="station-tab-analytics"
                         active={activeTab === "analytics"}
                         onClick={() => setActiveTab("analytics")}
                         icon={<BarChart3 size={13} />}
                         label="Analytics" />
              <TabButton testId="station-tab-earnings"
                         active={activeTab === "earnings"}
                         onClick={() => setActiveTab("earnings")}
                         icon={<DollarSign size={13} />}
                         label="Earnings" />
            </div>
            {activeTab === "feed" && (
              <StationFeed slug={s.slug} station={s} />
            )}
            {activeTab === "analytics" && (
              <StationAnalytics slug={s.slug} isBusiness={isBusiness} />
            )}
            {activeTab === "earnings" && (
              <StationEarnings slug={s.slug} />
            )}
          </>
        ) : (
          <StationFeed slug={s.slug} station={s} />
        )}
        {/* Phase 41M.B — Public Top Fans surface (auto-hides if empty) */}
        <TopFansSection slug={s.slug} limit={10} />
        {/* Phase 41 S4.5.B — Trivia "Top Brains" leaderboard */}
        <TriviaLeaderboard slug={s.slug}
                              currentUserId={user?.user_id} />
      </div>
    </div>
  );
}

function Tile({ label, v }) {
  return (
    <div style={{ padding: 12, borderRadius: 10,
                   background: "rgba(255,255,255,0.04)" }}>
      <div style={{ fontSize: 10, color: "#9aa3af", letterSpacing: 1.5,
                     fontFamily: "monospace", marginBottom: 4 }}>
        {label.toUpperCase()}
      </div>
      <div style={{ fontSize: 13, color: "#fff" }}>{v}</div>
    </div>
  );
}

function TabButton({ testId, active, onClick, icon, label }) {
  return (
    <button data-testid={testId}
            data-active={active ? "true" : "false"}
            role="tab"
            aria-selected={active}
            onClick={onClick}
            style={{ display: "inline-flex", alignItems: "center", gap: 6,
                      padding: "10px 16px",
                      background: "transparent",
                      color: active ? "#00d9ff" : "#9aa3af",
                      border: "none",
                      borderBottom: `2px solid ${active ? "#00d9ff" : "transparent"}`,
                      fontSize: 13, fontWeight: 600, cursor: "pointer",
                      marginBottom: "-1px" }}>
      {icon}{label}
    </button>
  );
}

function VerifiedChip() {
  return (
    <span data-testid="station-verified-chip"
          title="Verified by RadioLife"
          style={{ display: "inline-flex", alignItems: "center", gap: 4,
                    background: "rgba(0,217,255,0.15)",
                    color: "#00d9ff",
                    border: "1px solid rgba(0,217,255,0.4)",
                    borderRadius: 999, padding: "3px 10px",
                    fontSize: 11, fontWeight: 600, letterSpacing: "0.04em",
                    textTransform: "uppercase" }}>
      <Shield size={11} /> Verified
    </span>
  );
}

function BusinessProfileCard({ s, isOwner }) {
  const openNow = useMemo(
    () => isOpenNowLocal(s.business_profile || {}),
    [s.business_profile]
  );
  const bp = s.business_profile || {};
  const mapsHref = mapsDeepLink(bp);
  const todays  = (bp.hours || {})[todayKey()] || {};

  return (
    <div data-testid="business-info-card"
         data-verified={bp.verified ? "true" : "false"}
         style={{ display: "grid",
                   gridTemplateColumns: bp.logo_url ? "72px 1fr" : "1fr",
                   gap: 16, padding: 16, borderRadius: 14, marginBottom: 22,
                   background: "rgba(255,255,255,0.04)",
                   border: "1px solid rgba(255,255,255,0.06)" }}>
      {bp.logo_url && (
        <img data-testid="business-logo"
             src={bp.logo_url} alt={`${bp.display_name || bp.legal_name} logo`}
             style={{ width: 72, height: 72, borderRadius: 12,
                       objectFit: "cover",
                       background: "rgba(255,255,255,0.04)" }} />
      )}
      <div style={{ minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8,
                       flexWrap: "wrap", marginBottom: 6 }}>
          <div data-testid="business-display-name"
               style={{ fontSize: 16, fontWeight: 700, color: "#fff" }}>
            {bp.display_name || bp.legal_name}
          </div>
          {bp.verified
            ? <VerifiedChip />
            : (
              <span data-testid="business-pending-chip"
                    style={{ fontSize: 10, padding: "2px 8px",
                              borderRadius: 999,
                              background: "rgba(251,146,60,0.15)",
                              color: "#fb923c",
                              border: "1px solid rgba(251,146,60,0.35)",
                              fontWeight: 600, letterSpacing: "0.04em",
                              textTransform: "uppercase" }}>
                Pending Verification
              </span>
            )}
          {bp.category && (
            <span style={{ fontSize: 11, color: "#9aa3af",
                            padding: "2px 8px", borderRadius: 6,
                            background: "rgba(255,255,255,0.04)" }}>
              {bp.category}
            </span>
          )}
          <OpenNowBadge openNow={openNow} todays={todays} />
        </div>

        <div style={{ display: "grid", gap: 6,
                       fontSize: 12, color: "#cbd5e1" }}>
          {(bp.address || bp.city) && (
            <a data-testid="business-address-link"
               href={mapsHref || "#"}
               target={mapsHref ? "_blank" : undefined}
               rel="noopener noreferrer"
               onClick={(e) => { if (!mapsHref) e.preventDefault(); }}
               style={{ color: "#cbd5e1", textDecoration: "none",
                         display: "inline-flex", alignItems: "center",
                         gap: 6 }}>
              <MapPin size={12} color="#9aa3af" />
              <span>
                {[bp.address, bp.city, bp.country]
                  .filter(Boolean).join(", ")}
              </span>
            </a>
          )}
          {bp.phone && (
            <a data-testid="business-phone-link"
               href={`tel:${bp.phone}`}
               style={{ color: "#cbd5e1", textDecoration: "none",
                         display: "inline-flex", alignItems: "center",
                         gap: 6 }}>
              <Phone size={12} color="#9aa3af" /> {bp.phone}
            </a>
          )}
          {!bp.phone && isOwner && !bp.verified && (
            <span data-testid="business-phone-redacted"
                  style={{ fontSize: 11, color: "#9aa3af",
                            fontStyle: "italic" }}>
              Phone hidden from listeners until verified.
            </span>
          )}
          {bp.website && (
            <a data-testid="business-website-link"
               href={bp.website}
               target="_blank" rel="noopener noreferrer"
               style={{ color: "#00d9ff", textDecoration: "none",
                         display: "inline-flex", alignItems: "center",
                         gap: 6 }}>
              <GlobeIcon size={12} /> {bp.website.replace(/^https?:\/\//, "")}
            </a>
          )}
        </div>

        <details data-testid="business-hours-details"
                  style={{ marginTop: 10 }}>
          <summary style={{ fontSize: 11, color: "#9aa3af",
                              cursor: "pointer", listStyle: "none",
                              display: "inline-flex", alignItems: "center",
                              gap: 6 }}>
            <Clock size={11} /> Full week hours
          </summary>
          <div style={{ marginTop: 8, display: "grid",
                          gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))",
                          gap: 6, fontSize: 11, color: "#cbd5e1" }}>
            {DAYS.map(({ key, label }) => {
              const row = (bp.hours || {})[key] || {};
              return (
                <div key={key}
                     data-testid={`business-hours-${key}`}
                     style={{ display: "flex", justifyContent: "space-between",
                               padding: "3px 6px", borderRadius: 4,
                               background: key === todayKey()
                                 ? "rgba(0,217,255,0.06)"
                                 : "transparent" }}>
                  <span style={{ color: "#9aa3af", fontWeight: 600 }}>
                    {label}
                  </span>
                  <span>
                    {row.closed
                      ? <span style={{ color: "#6b7280",
                                         fontStyle: "italic" }}>Closed</span>
                      : (row.open && row.close)
                        ? `${row.open}–${row.close}`
                        : <span style={{ color: "#6b7280" }}>—</span>}
                  </span>
                </div>
              );
            })}
          </div>
        </details>
      </div>
    </div>
  );
}

function OpenNowBadge({ openNow, todays }) {
  if (openNow === null || openNow === undefined) return null;
  const isOpen = openNow === true;
  const label = isOpen
    ? (todays.close ? `Open · until ${todays.close}` : "Open now")
    : "Closed";
  return (
    <span data-testid="business-open-now-badge"
          data-open={isOpen ? "true" : "false"}
          style={{ fontSize: 11, padding: "2px 9px", borderRadius: 999,
                    background: isOpen ? "rgba(16,185,129,0.15)"
                                       : "rgba(255,255,255,0.06)",
                    color: isOpen ? "#10b981" : "#9aa3af",
                    border: `1px solid ${isOpen ? "rgba(16,185,129,0.35)"
                                                : "rgba(255,255,255,0.08)"}`,
                    fontWeight: 600, letterSpacing: "0.03em",
                    display: "inline-flex", alignItems: "center", gap: 4 }}>
      {isOpen ? <Flame size={10} /> : null}
      {label}
    </span>
  );
}
