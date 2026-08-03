/** Phase 41 P1-interrupt — Community Radio strip on the `/radio` tab.
 *
 * Sits BELOW the admin/system channel grid + ON AIR button. Renders
 * up to 10 community stations sourced from `GET /api/community/top_listened`
 * with a 3-tier fallback (live → followers → recent) so the section
 * is never empty.
 *
 * Tapping a card routes to `/r/{slug}` (the full StationPage), NOT
 * to a stream channel — community stations are full social pages,
 * not just admin-style audio channels.
 */
import React, { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { Radio as RadioIcon, Activity, Shield, Briefcase, ChevronRight } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function CommunityRadioStrip({ limit = 10 }) {
  const [items, setItems] = useState(null); // null = loading, [] = empty
  const [tier, setTier]   = useState(null);

  const load = useCallback(async () => {
    try {
      const r = await axios.get(
        `${API}/community/top_listened`,
        { params: { limit } });
      setItems(r.data?.stations || []);
      setTier(r.data?.tier_used || null);
    } catch {
      setItems([]);
    }
  }, [limit]);

  useEffect(() => {
    let cancelled = false;
    Promise.resolve().then(() => { if (!cancelled) load(); });
    return () => { cancelled = true; };
  }, [load]);

  // Hide when no stations exist at all (after fallback) — section
  // height stays reserved during loading via the skeleton.
  if (items !== null && items.length === 0) return null;

  const subtitle = tier === "recent"
    ? "Recently launched stations"
    : tier === "followers"
      ? "Most-followed community stations"
      : "Top 10 most-listened community stations";

  return (
    <section data-testid="radio-community-strip"
             data-tier={tier || ""}
             style={{ width: "100%", maxWidth: 980, margin: "32px auto 16px",
                       padding: "0 16px" }}>
      <div style={{ display: "flex", alignItems: "baseline",
                     justifyContent: "space-between", gap: 10,
                     marginBottom: 14 }}>
        <div>
          <h2 data-testid="radio-community-strip-heading"
              style={{ display: "inline-flex", alignItems: "center", gap: 8,
                        fontSize: 18, fontWeight: 800, color: "#fff",
                        margin: 0 }}>
            <RadioIcon size={16} color="#00d9ff" />
            Community Radio
            <span style={{ fontSize: 10, padding: "2px 8px", borderRadius: 999,
                            background: "rgba(0,217,255,0.12)", color: "#00d9ff",
                            border: "1px solid rgba(0,217,255,0.35)",
                            letterSpacing: "0.05em", fontWeight: 700,
                            textTransform: "uppercase" }}>
              Top {Math.min(limit, items?.length ?? limit) || limit}
            </span>
          </h2>
          <div style={{ marginTop: 4, fontSize: 12, color: "#9aa3af" }}>
            {subtitle}
          </div>
        </div>
        <Link to="/community"
              data-testid="radio-community-view-all"
              style={{ display: "inline-flex", alignItems: "center", gap: 4,
                        color: "#00d9ff", fontSize: 12, fontWeight: 600,
                        textDecoration: "none" }}>
          View all community stations
          <ChevronRight size={13} />
        </Link>
      </div>

      <div data-testid="radio-community-strip-grid"
           style={{ display: "grid",
                     gridTemplateColumns:
                       "repeat(auto-fill, minmax(200px, 1fr))",
                     gap: 12 }}>
        {(items === null) && (
          // Skeleton row — reserves height so the page doesn't jump.
          [0,1,2,3,4].map((i) => <CardSkeleton key={i} />)
        )}
        {(items || []).map((s) => (
          <CommunityCard key={s.slug} s={s} />
        ))}
      </div>
    </section>
  );
}

function CommunityCard({ s }) {
  const isBusiness = s.page_type === "business_radio";
  const isVerified = isBusiness && s.business_profile_summary?.verified;
  // Phase C — Use a real <img> when artwork URL is set so the browser can
  // lazy-load + cache it.  Falls back to the deterministic gradient
  // (current behaviour) on either: (a) no artwork URL, or (b) the image
  // 404s / errors at render time.  The gradient stays in the parent
  // container's background so the fallback is instant — no white flash.
  const [imgFailed, setImgFailed] = React.useState(false);
  const gradient = `linear-gradient(135deg, ${s.cover_color || "#00d9ff"}, ${s.cover_color || "#00d9ff"}55 60%, #050505)`;
  const BACKEND = process.env.REACT_APP_BACKEND_URL || "";
  const fullUrl = (u) => (!u ? "" : (u.startsWith("http") ? u : `${BACKEND}${u}`));
  const hasArt = !imgFailed && !!s.cover_image_url;
  const generating = s.artwork_status === "running"
                            || s.artwork_status === "queued";
  return (
    <Link to={`/r/${s.slug}`}
          data-testid={`radio-community-card-${s.slug}`}
          data-page-type={s.page_type}
          data-has-artwork={hasArt ? "true" : "false"}
          style={{ display: "block", textDecoration: "none",
                    color: "inherit",
                    borderRadius: 12, overflow: "hidden",
                    background: "rgba(255,255,255,0.04)",
                    border: "1px solid rgba(255,255,255,0.06)",
                    transition: "transform 120ms, border-color 120ms",
                  }}
          onMouseEnter={(e) => {
            e.currentTarget.style.transform = "translateY(-2px)";
            e.currentTarget.style.borderColor = "rgba(0,217,255,0.4)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.transform = "translateY(0)";
            e.currentTarget.style.borderColor = "rgba(255,255,255,0.06)";
          }}>
      <div style={{ aspectRatio: "16/10", background: gradient,
                          position: "relative", overflow: "hidden" }}>
        {hasArt && (
          <img
            src={fullUrl(s.cover_image_url)}
            alt={`${s.name} cover art`}
            loading="lazy"
            data-testid={`radio-community-card-artwork-${s.slug}`}
            onError={() => setImgFailed(true)}
            style={{ width: "100%", height: "100%",
                        objectFit: "cover", display: "block" }}
          />
        )}
        {generating && (
          <span data-testid={`radio-community-card-generating-${s.slug}`}
                  style={{ position: "absolute", top: 8, right: 8,
                            background: "rgba(0,0,0,0.55)", color: "#00d9ff",
                            padding: "3px 7px", borderRadius: 999,
                            fontSize: 9, fontWeight: 700,
                            letterSpacing: "0.04em", textTransform: "uppercase",
                            border: "1px solid rgba(0,217,255,0.4)" }}>
            Generating cover…
          </span>
        )}
      </div>
      <div style={{ padding: 10 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6,
                       marginBottom: 4 }}>
          <div data-testid={`radio-community-card-name-${s.slug}`}
               style={{ flex: 1, minWidth: 0, fontSize: 13, fontWeight: 700,
                         color: "#fff", whiteSpace: "nowrap",
                         overflow: "hidden", textOverflow: "ellipsis" }}>
            {s.name}
          </div>
          {isVerified && (
            <span data-testid={`radio-community-verified-${s.slug}`}
                  title="Verified business"
                  style={{ display: "inline-flex", alignItems: "center", gap: 2,
                            padding: "1px 6px", borderRadius: 999,
                            background: "rgba(0,217,255,0.15)",
                            color: "#00d9ff",
                            border: "1px solid rgba(0,217,255,0.4)",
                            fontSize: 9, fontWeight: 700,
                            textTransform: "uppercase",
                            letterSpacing: "0.04em" }}>
              <Shield size={9} /> Verified
            </span>
          )}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10,
                       fontSize: 11, color: "#9aa3af" }}>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
            {isBusiness
              ? <Briefcase size={11} color="#fb923c" />
              : <RadioIcon size={11} color="#00d9ff" />}
            {isBusiness ? "Business" : "Personal"}
          </span>
          {s.tier === "live" ? (
            <span data-testid={`radio-community-listener-${s.slug}`}
                  style={{ display: "inline-flex", alignItems: "center", gap: 3,
                            color: "#10b981", fontWeight: 600 }}>
              <Activity size={11} />
              {s.listener_count} live
            </span>
          ) : (
            <span style={{ display: "inline-flex", alignItems: "center", gap: 3 }}>
              {s.follower_count} {s.follower_count === 1 ? "follower" : "followers"}
            </span>
          )}
        </div>
      </div>
    </Link>
  );
}

function CardSkeleton() {
  return (
    <div aria-hidden
         data-testid="radio-community-card-skeleton"
         style={{ borderRadius: 12, overflow: "hidden",
                   background: "rgba(255,255,255,0.04)",
                   border: "1px solid rgba(255,255,255,0.06)" }}>
      <div style={{
        aspectRatio: "16/10",
        background: "linear-gradient(90deg, rgba(255,255,255,0.04) 0%, rgba(255,255,255,0.08) 50%, rgba(255,255,255,0.04) 100%)",
        backgroundSize: "200% 100%",
        animation: "skel 1.4s linear infinite",
      }} />
      <div style={{ padding: 10, display: "grid", gap: 6 }}>
        <div style={{ height: 12, borderRadius: 4, width: "70%",
                       background: "rgba(255,255,255,0.06)" }} />
        <div style={{ height: 10, borderRadius: 4, width: "45%",
                       background: "rgba(255,255,255,0.04)" }} />
      </div>
      <style>{`@keyframes skel { 0%{background-position:200% 0} 100%{background-position:-200% 0} }`}</style>
    </div>
  );
}
