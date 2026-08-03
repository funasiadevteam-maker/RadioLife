/** Phase 41 Session 1 — Community Radio discovery surface.
 *
 *  Shows featured + trending + recent buckets with filter (genre /
 *  language / city) and search by name/handle.  Public+published-only
 *  per /api/stations/discover privacy rules.
 */
import React, { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { Search, Users, Radio as RadioIcon, ArrowLeft, Plus, Sparkles,
          TrendingUp, Clock, Shield, Briefcase } from "lucide-react";
import { API } from "@/AuthContext";
import BannerAdSlot from "@/components/BannerAdSlot";
// Phase 41 S2.C.2 — Live Heat Ribbon at the top of /community.
import LiveHeatRibbon from "@/components/LiveHeatRibbon";

const GENRES   = ["", "pop", "indie", "bollywood", "electronic", "hip_hop",
                    "rock", "classical", "jazz", "punjabi"];
const LANGS    = ["", "english", "hindi", "arabic", "tamil", "punjabi"];
const CITIES   = ["", "dubai", "dfw", "london", "mumbai", "delhi"];

export default function Community() {
  const [filters, setFilters] = useState({ genre: "", language: "",
                                              city: "", q: "",
                                              type: "" });
  const [data, setData]   = useState({ featured: [], trending: [], recent: [], total: 0 });
  const [loading, setLoading] = useState(true);
  const [err, setErr]     = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setErr(null);
    try {
      const params = new URLSearchParams();
      if (filters.genre)    params.set("genre",    filters.genre);
      if (filters.language) params.set("language", filters.language);
      if (filters.city)     params.set("city",     filters.city);
      if (filters.q)        params.set("q",         filters.q);
      if (filters.type)     params.set("filter",   filters.type);
      const r = await axios.get(
        `${API}/stations/discover${params.toString() ? `?${params}` : ""}`,
        { withCredentials: true });
      setData(r.data);
    } catch (e) {
      setErr(e.response?.data?.detail?.code || "load_failed");
    } finally { setLoading(false); }
  }, [filters]);

  useEffect(() => {
    let cancelled = false;
    Promise.resolve().then(() => { if (!cancelled) load(); });
    return () => { cancelled = true; };
  }, [load]);

  return (
    <div data-testid="community-page"
         style={{ maxWidth: 1080, margin: "0 auto",
                  padding: "24px 20px", color: "#fff" }}>
      <Link to="/" data-testid="community-back"
            style={{ display: "inline-flex", alignItems: "center", gap: 6,
                     color: "#9aa3af", textDecoration: "none",
                     fontSize: 13, marginBottom: 18 }}>
        <ArrowLeft size={14} /> Back to home
      </Link>

      <div style={{ display: "flex", alignItems: "flex-start",
                     justifyContent: "space-between", marginBottom: 18,
                     gap: 16, flexWrap: "wrap" }}>
        <div>
          <h1 style={{ display: "flex", alignItems: "center", gap: 10,
                       fontSize: 28, fontWeight: 700, margin: "0 0 6px" }}>
            <Users size={24} color="#00d9ff" /> Community Radio
          </h1>
          <p style={{ color: "#9aa3af", fontSize: 14, margin: 0,
                       maxWidth: 640, lineHeight: 1.6 }}>
            Discover listener-built stations. {data.total > 0
              ? `${data.total} public station${data.total === 1 ? "" : "s"} live now.`
              : "Be the first — your station goes here."}
          </p>
        </div>
        <Link to="/radio/create" data-testid="community-create-cta"
              style={{ background: "#00d9ff", color: "#0b0b0b",
                        padding: "9px 16px", borderRadius: 8, fontWeight: 600,
                        fontSize: 13, textDecoration: "none",
                        display: "inline-flex", alignItems: "center", gap: 6 }}>
          <Plus size={14} /> Create my radio
        </Link>
      </div>

      <FilterBar filters={filters} setFilters={setFilters} />

      {err && (
        <div data-testid="community-error"
             style={{ background: "rgba(239,68,68,0.1)",
                       border: "1px solid #ef4444", color: "#fca5a5",
                       padding: "8px 12px", borderRadius: 6,
                       fontSize: 13, marginBottom: 16 }}>
          Could not load stations. Try again.
        </div>
      )}

      {loading ? (
        <div data-testid="community-loading"
             style={{ color: "#9aa3af", padding: 30, textAlign: "center" }}>
          Loading stations…
        </div>
      ) : (
        <>
          {/* Phase 41 S2.C.2 — Live Heat Ribbon (top-3 stations by
              current live listener count). Self-hides when empty. */}
          <LiveHeatRibbon />
          <Bucket testId="bucket-featured" icon={Sparkles}
                   label="Featured" stations={data.featured}
                   emptyMsg="No featured stations yet." />
          {/* Phase 42 S1 UX correction — TOI-style inline horizontal
                banner between Featured and Trending. Replaces the
                stacked left/right rail clutter from the previous pass. */}
          <div style={{ margin: "8px 0 18px", display: "flex",
                          justifyContent: "center" }}>
            <BannerAdSlot slotKey="featured_horizontal" pageRoute="/community" />
          </div>
          <Bucket testId="bucket-trending" icon={TrendingUp}
                   label="Trending" stations={data.trending}
                   emptyMsg="No trending stations match your filters." />
          {/* Phase 42 S1 UX — center_mid between Trending and Recent. */}
          <div style={{ margin: "8px 0 18px", display: "flex",
                          justifyContent: "center" }}>
            <BannerAdSlot slotKey="center_mid" pageRoute="/community" />
          </div>
          <Bucket testId="bucket-recent" icon={Clock}
                   label="Just launched" stations={data.recent}
                   emptyMsg="No new stations match your filters." />

          {data.total === 0 && (
            <div data-testid="community-empty"
                 style={{ marginTop: 24, padding: 30, textAlign: "center",
                           background: "rgba(255,255,255,0.03)",
                           border: "1px dashed rgba(255,255,255,0.1)",
                           borderRadius: 12, color: "#9aa3af",
                           fontSize: 14 }}>
              Nothing matches these filters yet.
            </div>
          )}
        </>
      )}
    </div>
  );
}

function FilterBar({ filters, setFilters }) {
  const upd = (k, v) => setFilters(f => ({ ...f, [k]: v }));
  return (
    <div data-testid="community-filter-bar"
         style={{ display: "flex", gap: 10, alignItems: "center",
                  flexWrap: "wrap", marginBottom: 22 }}>
      <div style={{ position: "relative", flex: "1 1 220px", maxWidth: 320 }}>
        <Search size={14} color="#9aa3af"
                style={{ position: "absolute", left: 12, top: 11 }} />
        <input data-testid="community-search"
               value={filters.q} placeholder="Search station name or handle…"
               onChange={e => upd("q", e.target.value)}
               style={{ width: "100%", padding: "8px 12px 8px 34px",
                         borderRadius: 8,
                         background: "rgba(255,255,255,0.05)", color: "#fff",
                         border: "1px solid rgba(255,255,255,0.08)",
                         fontSize: 13 }} />
      </div>
      <div data-testid="community-type-chips"
           style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
        <TypeChip testId="community-type-all"
                  active={!filters.type}
                  onClick={() => upd("type", "")}>All</TypeChip>
        <TypeChip testId="community-type-personal"
                  active={filters.type === "personal"}
                  onClick={() => upd("type", "personal")}
                  icon={<Users size={11} />}>Personal</TypeChip>
        <TypeChip testId="community-type-business"
                  active={filters.type === "business"}
                  onClick={() => upd("type", "business")}
                  icon={<Briefcase size={11} />}>Business</TypeChip>
      </div>
      <Select testId="community-filter-genre" label="Genre"
              value={filters.genre} onChange={v => upd("genre", v)}
              options={GENRES} />
      <Select testId="community-filter-language" label="Language"
              value={filters.language} onChange={v => upd("language", v)}
              options={LANGS} />
      <Select testId="community-filter-city" label="City"
              value={filters.city} onChange={v => upd("city", v)}
              options={CITIES} />
    </div>
  );
}

function TypeChip({ testId, active, onClick, icon, children }) {
  return (
    <button type="button" data-testid={testId}
            data-active={active ? "true" : "false"}
            onClick={onClick}
            style={{ display: "inline-flex", alignItems: "center", gap: 4,
                      background: active ? "#00d9ff" : "rgba(255,255,255,0.05)",
                      color: active ? "#0b0b0b" : "#cbd5e1",
                      border: active ? "1px solid #00d9ff"
                                     : "1px solid rgba(255,255,255,0.08)",
                      padding: "6px 12px", borderRadius: 16,
                      fontSize: 12, fontWeight: active ? 600 : 500,
                      cursor: "pointer", letterSpacing: "0.02em" }}>
      {icon}{children}
    </button>
  );
}

function Select({ testId, label, value, onChange, options }) {
  return (
    <label style={{ display: "inline-flex", alignItems: "center",
                     gap: 6, fontSize: 12, color: "#9aa3af" }}>
      {label}:
      <select data-testid={testId} value={value}
              onChange={e => onChange(e.target.value)}
              style={{ background: "rgba(255,255,255,0.05)", color: "#fff",
                       border: "1px solid rgba(255,255,255,0.08)",
                       padding: "6px 10px", borderRadius: 6,
                       fontSize: 12 }}>
        {options.map(o => (
          <option key={o || "any"} value={o}
                   style={{ background: "#0b0b0b" }}>
            {o || "Any"}
          </option>
        ))}
      </select>
    </label>
  );
}

function Bucket({ testId, icon: Icon, label, stations, emptyMsg }) {
  if (!stations || stations.length === 0) {
    return (
      <section data-testid={testId} style={{ marginBottom: 28 }}>
        <BucketHeader Icon={Icon} label={label} />
        <div style={{ color: "#6b7280", fontSize: 12,
                       padding: "10px 0" }}>{emptyMsg}</div>
      </section>
    );
  }
  return (
    <section data-testid={testId} style={{ marginBottom: 28 }}>
      <BucketHeader Icon={Icon} label={label} count={stations.length} />
      <div style={{ display: "grid",
                     gridTemplateColumns: "repeat(auto-fill,minmax(220px,1fr))",
                     gap: 14 }}>
        {stations.map(s => <StationCard key={s.station_id} s={s} />)}
      </div>
    </section>
  );
}

function BucketHeader({ Icon, label, count }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8,
                   marginBottom: 12 }}>
      <Icon size={16} color="#00d9ff" />
      <h2 style={{ fontSize: 15, fontWeight: 600, margin: 0 }}>{label}</h2>
      {count != null && (
        <span style={{ color: "#6b7280", fontSize: 11,
                        fontFamily: "monospace" }}>· {count}</span>
      )}
    </div>
  );
}

function StationCard({ s }) {
  return (
    <Link to={`/r/${encodeURIComponent(s.slug)}`}
          data-testid={`station-card-${s.slug}`}
          style={{ display: "block", textDecoration: "none",
                    background: "rgba(255,255,255,0.04)", borderRadius: 12,
                    overflow: "hidden", border: "1px solid rgba(255,255,255,0.05)",
                    transition: "transform 0.15s, border-color 0.15s" }}
          onMouseEnter={e => {
            e.currentTarget.style.transform = "translateY(-2px)";
            e.currentTarget.style.borderColor = "#00d9ff";
          }}
          onMouseLeave={e => {
            e.currentTarget.style.transform = "";
            e.currentTarget.style.borderColor = "rgba(255,255,255,0.05)";
          }}>
      <div style={{ height: 90,
                     background: `linear-gradient(135deg, ${s.cover_color || "#00d9ff"}, #0b0b0b)`,
                     display: "flex", alignItems: "flex-end", padding: 10 }}>
        <RadioIcon size={18} color="#fff"
                    style={{ opacity: 0.85 }} />
      </div>
      <div style={{ padding: 12 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6,
                       marginBottom: 4 }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: "#fff",
                         flex: 1, minWidth: 0, overflow: "hidden",
                         textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {s.name}
          </div>
          {s.is_business && s.business_profile?.verified && (
            <span data-testid={`station-card-verified-${s.slug}`}
                  title="Verified business"
                  style={{ display: "inline-flex", alignItems: "center",
                            gap: 3, padding: "1px 6px", borderRadius: 999,
                            background: "rgba(0,217,255,0.15)",
                            color: "#00d9ff",
                            border: "1px solid rgba(0,217,255,0.4)",
                            fontSize: 9, fontWeight: 600,
                            textTransform: "uppercase",
                            letterSpacing: "0.04em" }}>
              <Shield size={9} /> Verified
            </span>
          )}
          {s.is_business && !s.business_profile?.verified && (
            <span data-testid={`station-card-business-${s.slug}`}
                  title="Business"
                  style={{ display: "inline-flex", alignItems: "center",
                            gap: 3, padding: "1px 6px", borderRadius: 999,
                            background: "rgba(251,146,60,0.15)",
                            color: "#fb923c",
                            border: "1px solid rgba(251,146,60,0.35)",
                            fontSize: 9, fontWeight: 600,
                            textTransform: "uppercase",
                            letterSpacing: "0.04em" }}>
              <Briefcase size={9} /> Business
            </span>
          )}
        </div>
        <div style={{ fontSize: 11, color: "#9aa3af",
                       fontFamily: "monospace", marginBottom: 8 }}>
          /r/{s.slug}
        </div>
        {s.tagline && (
          <div style={{ fontSize: 12, color: "#cbd5e1",
                         lineHeight: 1.4, marginBottom: 8,
                         display: "-webkit-box", WebkitBoxOrient: "vertical",
                         WebkitLineClamp: 2, overflow: "hidden" }}>
            {s.tagline}
          </div>
        )}
        <div style={{ display: "flex", alignItems: "center",
                       gap: 10, fontSize: 11, color: "#9aa3af" }}>
          <span style={{ display: "inline-flex", alignItems: "center",
                          gap: 3 }}>
            <Users size={11} /> {s.follower_count || 0}
          </span>
          {(s.allowed_genres || []).slice(0, 2).map(g => (
            <span key={g} style={{ padding: "1px 6px", borderRadius: 4,
                                     background: "rgba(0,217,255,0.1)",
                                     color: "#00d9ff", fontSize: 10 }}>
              {g}
            </span>
          ))}
        </div>
      </div>
    </Link>
  );
}
