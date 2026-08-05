/** Phase 40 — /news listing page with category filter.
 *
 *  Phase 42-D follow-up — Local-first reorder.  Default tab is "Local"
 *  on every visit (does NOT persist across visits — tab state is purely
 *  in-memory).  Market resolution chain:
 *
 *      useGeoStore.market    (user.preferred_market → IP → fallback)
 *      → label via useGeoStore.displayName()
 *      → if `global`, query with no market filter and the backend
 *          flags `fallback_global: true` so we surface a soft banner.
 *
 *  When a local pool exists, the Local tab shows ONLY those articles.
 *  When it's empty, the backend returns the top global stories with
 *  `fallback_global: true` and we render a non-dismissable info banner
 *  so the user knows why they're seeing wide-net headlines.
 */
import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { Newspaper, ChevronRight, MapPin } from "lucide-react";
import { API } from "@/AuthContext";
import { useGeoStore } from "@/store/useGeoStore";
import SafeImage from "@/components/SafeImage";
// Phase 42-E2.2 — Universal share button on each news article card.
import ShareButton from "@/components/ShareButton";
// Phase 42-E2.4 — OG meta for the News feed.
import OGMeta from "@/components/OGMeta";
// BannerAdSlot imported in case the next phase wants to re-enable the
// in-page banner.  Keeping the import line out for now — feature was
// already commented-out in the prior version.

// Phase 42-D — Local goes FIRST.  "All" + the rest follow.
const CATEGORIES = [
  { id: "local",         label: "Local" },
  { id: "",                  label: "All" },
  { id: "top",             label: "Top" },
  { id: "world",         label: "World" },
  { id: "business",    label: "Business" },
  { id: "technology", label: "Technology" },
  { id: "entertainment", label: "Entertainment" },
  { id: "sports",        label: "Sports" },
];

function fmtTime(p) {
  if (!p) return "";
  const t = Date.parse(p.replace(" ", "T") + "Z");
  if (isNaN(t)) return "";
  const m = Math.max(1, Math.floor((Date.now() - t) / 60000));
  if (m < 60)      return `${m}m ago`;
  if (m < 60 * 24) return `${Math.floor(m / 60)}h ago`;
  return `${Math.floor(m / 1440)}d ago`;
}

export default function News() {
  // Local-first default — purposely NOT persisted (just `useState` so
  // a refresh always lands back on Local).
  const [cat,             setCat]             = useState("local");
  const [items,           setItems]           = useState([]);
  const [loading,         setLoading]         = useState(true);
  const [live,             setLive]             = useState(false);
  const [fallback,    setFallback]    = useState(false);
  // Phase 42-F.7 — blended Local + National breakdown returned by the
  // /headlines endpoint on the Local tab.  `null` outside the Local
  // tab.  When non-null we add the "12 local · 8 national" chip next
  // to the Local pill and tag each card with a blue/purple type chip.
  const [blendCounts, setBlendCounts] = useState(null);
  // Resolved market (e.g. "dubai", "dfw", "global") + display label.
  const market           = useGeoStore((s) => s.market);
  const displayFor   = useGeoStore((s) => s.displayName);
  const geoReady    = useGeoStore((s) => s.ready);
  const cityLabel    = useMemo(() => {
    if (!market || market === "global") return null;
    return displayFor(market);
  }, [market, displayFor]);

  useEffect(() => {
    let cancel = false;
    setLoading(true);
    setFallback(false);
    (async () => {
      try {
        const params = { limit: 20 };
        if (cat === "local") {
          // Local tab — pass `market` so backend filters + flags fallback.
          if (market && market !== "global") {
            params.market = market;
          }
        } else if (cat) {
          params.category = cat;
        }
        const r = await axios.get(`${API}/news/headlines`,
                                                  { params, withCredentials: true });
        if (!cancel) {
          setItems(r.data?.items || []);
          setLive(!!r.data?.live);
          setFallback(!!r.data?.fallback_global);
        }
      } catch (e) {
        if (!cancel) setItems([]);
      }
      if (!cancel) setLoading(false);
    })();
    return () => { cancel = true; };
    // Re-fire when the geo store flips from `loading → ready` so the
    // initial Local request uses the right market instead of the cached
    // "global" default.  Same trick for explicit city overrides.
  }, [cat, market, geoReady]);

  return (
    <div data-testid="news-page"
                style={{ maxWidth: 1080, margin: "0 auto", padding: "24px 20px" }}>
      {/* Phase 42-E2.4 — OG meta for News-feed share. */}
      <OGMeta entityType="news_article" entityId="feed"
                          title="RadioLife News — your headlines, your voice"
                          description="Local + national news, refreshed continuously and read aloud on RadioLife News Radio." />
      <div style={{ display: "flex", alignItems: "center",
                              justifyContent: "space-between", marginBottom: 18 }}>
        <h1 style={{ display: "flex", alignItems: "center", gap: 10,
                                color: "#fff", fontSize: 26, fontWeight: 700, margin: 0 }}>
          <Newspaper size={22} color="#00d9ff" /> RadioLife News
        </h1>
        <Link to="/radio/news" data-testid="news-tune-radio"
                    style={{ display: "inline-flex", alignItems: "center", gap: 6,
                                background: "#00d9ff", color: "#0b0b0b",
                                padding: "8px 14px", borderRadius: 8,
                                textDecoration: "none", fontWeight: 600, fontSize: 13 }}>
          🎙️ Tune to News Radio
        </Link>
      </div>

      {!live && (
        <div data-testid="news-mock-banner"
                  style={{ background: "rgba(245,158,11,0.1)",
                              border: "1px dashed #f59e0b", color: "#f59e0b",
                              padding: "6px 12px", borderRadius: 6, fontSize: 11,
                              marginBottom: 14, letterSpacing: 0.5 }}>
          MOCK MODE — NewsData.io key not configured. Showing sample headlines.
        </div>
      )}

      {/* Local-fallback soft banner — only on the Local tab + when the
                  backend reports it gave us global stories instead. */}
      {cat === "local" && fallback && !loading && items.length > 0 && (
        <div data-testid="news-local-fallback-banner"
                  style={{ background: "rgba(0,217,255,0.08)",
                              border: "1px solid rgba(0,217,255,0.3)",
                              color: "#67e8f9", padding: "8px 12px",
                              borderRadius: 6, fontSize: 12,
                              marginBottom: 14, display: "flex",
                              alignItems: "center", gap: 8 }}>
          <MapPin size={12} />
          No local news for {cityLabel || "your area"} yet — showing top stories.
        </div>
      )}

      <div data-testid="news-category-chips"
                  style={{ display: "flex", gap: 8, flexWrap: "wrap",
                              marginBottom: 18 }}>
        {CATEGORIES.map(c => {
          const isActive = cat === c.id;
          const isLocal  = c.id === "local";
          // Phase 42-F.7 — on the Local pill, append a compact
          // breakdown ("12L · 8N") when we have blended data.
          const breakdown = (isLocal && isActive && blendCounts)
            ? ` · ${blendCounts.local}L · ${blendCounts.national}N`
            : "";
          const label    = isLocal && cityLabel
                                          ? `Local · ${cityLabel}${breakdown}`
                                          : c.label;
          return (
            <button key={c.id || "all"}
                            data-testid={`news-cat-${c.id || "all"}`}
                            data-active={isActive ? "true" : "false"}
                            onClick={() => setCat(c.id)}
                            style={{
                              background: isActive ? "#00d9ff" : "rgba(255,255,255,0.05)",
                              color:      isActive ? "#0b0b0b" : "#cbd5e1",
                              border: isLocal && !isActive
                                ? "1px solid rgba(0,217,255,0.4)"
                                : "1px solid rgba(255,255,255,0.06)",
                              padding: "6px 12px", borderRadius: 16,
                              fontSize: 12, cursor: "pointer",
                              fontWeight: isActive ? 600 : 400,
                              display: "inline-flex", alignItems: "center", gap: 6,
                            }}>
              {isLocal && <MapPin size={11} />}
              {label}
            </button>
          );
        })}
      </div>

      {loading ? (
        <div data-testid="news-loading"
                  style={{ color: "#9aa3af", padding: 40, textAlign: "center" }}>
          Loading headlines…
        </div>
      ) : items.length === 0 ? (
        <div data-testid="news-empty"
                  style={{ color: "#9aa3af", padding: 40, textAlign: "center" }}>
          {cat === "local"
            ? <>No news yet for {cityLabel || "your area"} — check back soon.</>
            : <>No headlines available right now.</>}
        </div>
      ) : (
        <div data-testid="news-grid"
                  style={{ display: "grid",
                              gridTemplateColumns: "repeat(auto-fill,minmax(280px,1fr))",
                              gap: 14 }}>
          {items.map(n => (
            <div key={n.news_id} style={{ position: "relative" }}>
              <Link to={`/news/${encodeURIComponent(n.news_id)}`}
                          data-testid={`news-card-${n.news_id}`}
                          style={{
                            background: "#1f2937", borderRadius: 12,
                            overflow: "hidden", textDecoration: "none",
                            border: "1px solid rgba(255,255,255,0.05)",
                            transition: "border-color 0.15s",
                            display: "block",
                          }}>
              {n.image_url && (
                <SafeImage src={n.image_url} alt=""
                                          fallbackKind="generic"
                                          fallbackText={n.title || ""}
                                          style={{ width: "100%", height: 140,
                                                              objectFit: "cover", display: "block" }} />
              )}
              <div style={{ padding: 14 }}>
                {/* Phase 42-F.7 — Local / National type chip.  Only
                            rendered when the article has been tagged by the
                            blended-feed pipeline. */}
                {n.news_type === "local" && (
                  <span data-testid={`news-type-chip-${n.news_id}`}
                                data-news-type="local"
                                style={{ display: "inline-block",
                                                  background: "rgba(59,130,246,0.12)",
                                                  color: "#60a5fa",
                                                  border: "1px solid rgba(59,130,246,0.35)",
                                                  borderRadius: 12,
                                                  fontSize: 10, lineHeight: 1,
                                                  padding: "3px 8px",
                                                  letterSpacing: 0.4,
                                                  marginBottom: 8 }}>
                    LOCAL
                  </span>
                )}
                {n.news_type === "national" && (
                  <span data-testid={`news-type-chip-${n.news_id}`}
                                data-news-type="national"
                                style={{ display: "inline-block",
                                                  background: "rgba(168,85,247,0.12)",
                                                  color: "#c084fc",
                                                  border: "1px solid rgba(168,85,247,0.35)",
                                                  borderRadius: 12,
                                                  fontSize: 10, lineHeight: 1,
                                                  padding: "3px 8px",
                                                  letterSpacing: 0.4,
                                                  marginBottom: 8 }}>
                    NATIONAL
                  </span>
                )}
                <div style={{ color: "#fff", fontWeight: 600, fontSize: 14,
                                        lineHeight: 1.4, marginBottom: 8,
                                        display: "-webkit-box", WebkitLineClamp: 3,
                                        WebkitBoxOrient: "vertical", overflow: "hidden" }}>
                  {n.title}
                </div>
                {n.description && (
                  <div style={{ color: "#9aa3af", fontSize: 12, lineHeight: 1.5,
                                          marginBottom: 10,
                                          display: "-webkit-box", WebkitLineClamp: 2,
                                          WebkitBoxOrient: "vertical", overflow: "hidden" }}>
                    {n.description}
                  </div>
                )}
                <div style={{ display: "flex", justifyContent: "space-between",
                                        alignItems: "center", fontSize: 11,
                                        color: "#cbd5e1", fontFamily: "monospace" }}>
                  <span>{n.source_name || n.source_id}</span>
                  <span style={{ display: "inline-flex", alignItems: "center",
                                              gap: 3 }}>
                    {fmtTime(n.pubDate)} <ChevronRight size={11} />
                  </span>
                </div>
              </div>
            </Link>
            {/* Phase 42-E2.2 — share this article. */}
            <div style={{ position: "absolute", top: 8, right: 8 }}>
              <ShareButton
                compact
                featureType="news_article"
                contentId={n.news_id}
                title={n.title}
                text={`${n.title} — read on RadioLife`}
                url={typeof window !== "undefined"
                  ? `${window.location.origin}/news/${n.news_id}`
                  : `/news/${n.news_id}`} />
            </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
