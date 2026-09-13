/** Phase 41 Session 5.A — Creator Analytics Dashboard tab.
 *
 * Rendered inside `StationPage.jsx` for the owner only. Single round-
 * trip to `/api/stations/{slug}/analytics?window=…` powers everything.
 * Hard NO polling — analytics refresh only on window change or
 * manual refresh button.
 *
 * Layout-shift hygiene: all sections render skeletons matching the
 * final size while loading.
 */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import axios from "axios";
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis,
  Tooltip, CartesianGrid, ReferenceLine,
} from "recharts";
import {
  BarChart3, RefreshCw, Download, Clock, Users, Activity,
  Heart, MessageCircle, ArrowUpRight, ArrowDownRight,
  TrendingUp, Megaphone, Tv, MapPin,
} from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const WINDOWS = [
  { key: "7d",  label: "7 days"  },
  { key: "30d", label: "30 days" },
  { key: "90d", label: "90 days" },
  { key: "all", label: "All-time" },
];

function fmtNumber(n) {
  if (n === undefined || n === null) return "0";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 10_000)    return `${(n / 1000).toFixed(1)}K`;
  if (n >= 1_000)     return n.toLocaleString();
  return n.toString();
}

function fmtMinutes(m) {
  if (!m) return "0m";
  if (m < 60)        return `${m}m`;
  const h = Math.floor(m / 60);
  const rest = m % 60;
  if (h < 100)       return rest > 0 ? `${h}h ${rest}m` : `${h}h`;
  return `${h}h`;
}

function pct(curr, prev) {
  if (!prev) return curr > 0 ? +100 : 0;
  return Math.round(((curr - prev) / prev) * 100);
}

export default function StationAnalytics({ slug, isBusiness }) {
  const [data, setData]       = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr]         = useState(null);
  const [window_, setWindow]  = useState("7d");
  // Phase J.2 — per-station mood distribution.
  const [moodDist, setMoodDist] = useState(null);

  const load = useCallback(async (selected) => {
    setLoading(true); setErr(null);
    try {
      const r = await axios.get(
        `${API}/stations/${encodeURIComponent(slug)}/analytics`,
        { params: { window: selected },
          withCredentials: true });
      setData(r.data);
    } catch (e) {
      setErr(e.response?.data?.detail?.code || "error");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [slug]);

  // Phase J.2 — fetch the mood distribution alongside the main payload.
  // Map window_ (7d/30d/90d/all) → server window (week/month/all).
  const loadMoodDistribution = useCallback(async (selected) => {
    const srvWindow = selected === "7d" ? "week"
                                    : selected === "30d" ? "month"
                                    : selected === "90d" ? "month"
                                    : "all";
    try {
      const r = await axios.get(
        `${API}/stations/${encodeURIComponent(slug)}/mood-distribution`,
        { params: { window: srvWindow }, withCredentials: true });
      setMoodDist(r.data);
    } catch (_e) { setMoodDist(null); }
  }, [slug]);

  useEffect(() => {
    let cancelled = false;
    Promise.resolve().then(() => {
      if (cancelled) return;
      load(window_);
      loadMoodDistribution(window_);
    });
    return () => { cancelled = true; };
  }, [load, loadMoodDistribution, window_]);

  const exportCsv = () => {
    const href = `${API}/stations/${encodeURIComponent(slug)}/analytics.csv?window=${window_}`;
    // Use a tiny anchor so we can pass the cookie via same-origin nav.
    const a = document.createElement("a");
    a.href = href; a.target = "_blank"; a.rel = "noopener";
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
  };

  const headline = data?.headline_metrics || {};
  const prev     = data?.prev_window_metrics || {};
  const series   = data?.daily_series || [];
  const posts    = data?.top_posts || [];
  const cities   = data?.top_listeners_by_city || [];
  const moods    = data?.mood_top_tracks || [];
  const biz      = isBusiness ? (data?.business_only || {}) : null;

  return (
    <div data-testid="station-analytics"
         data-window={window_}
         style={{ marginTop: 28 }}>
      <div style={{ display: "flex", alignItems: "center",
                     justifyContent: "space-between", flexWrap: "wrap",
                     gap: 12, marginBottom: 18 }}>
        <div style={{ display: "inline-flex", alignItems: "center", gap: 10 }}>
          <BarChart3 size={20} color="#00d9ff" />
          <h2 style={{ fontSize: 18, fontWeight: 700, color: "#fff",
                         margin: 0 }}>
            Station analytics
          </h2>
        </div>
        <div style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
          <WindowChips active={window_} onChange={setWindow} />
          <button data-testid="analytics-refresh"
                  onClick={() => load(window_)}
                  disabled={loading}
                  title="Refresh"
                  style={{ background: "rgba(255,255,255,0.04)",
                            color: "#cbd5e1",
                            border: "1px solid rgba(255,255,255,0.08)",
                            padding: 8, borderRadius: 6, cursor: "pointer",
                            opacity: loading ? 0.5 : 1 }}>
            <RefreshCw size={13} className={loading ? "spin" : ""} />
          </button>
          <button data-testid="analytics-export-csv"
                  onClick={exportCsv}
                  title="Export CSV"
                  style={{ display: "inline-flex", alignItems: "center", gap: 4,
                            background: "rgba(0,217,255,0.12)",
                            color: "#00d9ff",
                            border: "1px solid rgba(0,217,255,0.4)",
                            padding: "7px 12px", borderRadius: 6,
                            fontSize: 12, fontWeight: 600, cursor: "pointer" }}>
            <Download size={12} /> CSV
          </button>
        </div>
      </div>

      {err && (
        <div data-testid="analytics-error"
             style={{ padding: 14, borderRadius: 10,
                       background: "rgba(239,68,68,0.08)",
                       border: "1px solid rgba(239,68,68,0.3)",
                       color: "#fca5a5", fontSize: 13 }}>
          Failed to load analytics ({err}). Try the refresh button.
        </div>
      )}

      <div data-testid="analytics-kpi-row"
           style={{ display: "grid", gap: 12, marginBottom: 16,
                     gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))" }}>
        <KPI testId="kpi-listen-minutes"
             icon={<Clock size={14} color="#00d9ff" />}
             label="Listen minutes"
             value={fmtMinutes(headline.total_listen_minutes)}
             rawValue={headline.total_listen_minutes}
             prevValue={prev.total_listen_minutes}
             loading={loading} />
        <KPI testId="kpi-unique-listeners"
             icon={<Users size={14} color="#00d9ff" />}
             label="Unique listeners"
             value={fmtNumber(headline.unique_listeners)}
             rawValue={headline.unique_listeners}
             prevValue={prev.unique_listeners}
             loading={loading} />
        <KPI testId="kpi-peak-concurrent"
             icon={<Activity size={14} color="#00d9ff" />}
             label="Peak concurrent"
             value={fmtNumber(headline.peak_concurrent_listeners)}
             rawValue={headline.peak_concurrent_listeners}
             prevValue={null}
             loading={loading} />
        <KPI testId="kpi-followers"
             icon={<TrendingUp size={14} color="#00d9ff" />}
             label="Followers"
             value={fmtNumber(headline.followers_total)}
             rawValue={headline.followers_total}
             prevValue={headline.followers_total - headline.followers_delta}
             deltaOverride={headline.followers_delta}
             loading={loading} />
      </div>

      {biz && (
        <div data-testid="analytics-kpi-row-business"
             style={{ display: "grid", gap: 12, marginBottom: 16,
                       gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))" }}>
          <KPI testId="kpi-announcements"
               icon={<Megaphone size={14} color="#fb923c" />}
               label="Announcements created"
               value={fmtNumber(biz.announcement_count)}
               rawValue={biz.announcement_count}
               prevValue={null} loading={loading} />
          <KPI testId="kpi-tv-polls"
               icon={<Tv size={14} color="#fb923c" />}
               label="TV display polls"
               value={fmtNumber(biz.tv_display_polls)}
               rawValue={biz.tv_display_polls}
               prevValue={null} loading={loading} />
        </div>
      )}

      <div style={{ display: "grid", gap: 16,
                     gridTemplateColumns: "minmax(0, 2fr) minmax(260px, 1fr)" }}>
        <DailyTrendChart series={series} loading={loading} window_={window_} />
        <TopPostsCard posts={posts} loading={loading} slug={slug} />
      </div>

      <div style={{ marginTop: 16 }}>
        <TopCitiesCard cities={cities} loading={loading} />
      </div>

      {/* Phase 41M.B — Track moods mini-section (owner-only via the
          existing analytics route auth gate). */}
      <div style={{ marginTop: 16 }}>
        <TrackMoodsCard moods={moods} loading={loading} />
      </div>

      {/* Phase J.2 — Mood Profile mini-section (per-station mood
          distribution).  Stacked horizontal bar + top-3 chips. */}
      <div style={{ marginTop: 16 }} data-testid="mood-profile-section">
        <MoodProfileCard data={moodDist} loading={loading} />
      </div>

      <style>{`
        @keyframes spin { from {transform:rotate(0)} to {transform:rotate(360deg)} }
        .spin { animation: spin 1s linear infinite; }
        @keyframes skel { 0% {background-position: 200% 0} 100% {background-position: -200% 0} }
      `}</style>
    </div>
  );
}

function WindowChips({ active, onChange }) {
  return (
    <div data-testid="analytics-window-chips"
         style={{ display: "inline-flex",
                   background: "rgba(255,255,255,0.04)", borderRadius: 8,
                   padding: 3, gap: 2 }}>
      {WINDOWS.map((w) => (
        <button key={w.key}
                data-testid={`window-${w.key}`}
                data-active={active === w.key ? "true" : "false"}
                onClick={() => onChange(w.key)}
                style={{ padding: "5px 10px", borderRadius: 6,
                          background: active === w.key
                            ? "rgba(0,217,255,0.18)"
                            : "transparent",
                          color: active === w.key ? "#00d9ff" : "#9aa3af",
                          border: active === w.key
                            ? "1px solid rgba(0,217,255,0.4)"
                            : "1px solid transparent",
                          fontSize: 11, fontWeight: 600, cursor: "pointer" }}>
          {w.label}
        </button>
      ))}
    </div>
  );
}

function KPI({ testId, icon, label, value, rawValue, prevValue,
                deltaOverride, loading }) {
  const delta = (deltaOverride !== undefined && deltaOverride !== null)
    ? deltaOverride
    : (rawValue ?? 0) - (prevValue ?? 0);
  const showDelta = (prevValue !== null && prevValue !== undefined)
                     || deltaOverride !== undefined;
  const pctChange = showDelta && (prevValue || prevValue === 0)
    ? pct(rawValue ?? 0, prevValue || 0) : null;
  const positive = delta > 0;
  const negative = delta < 0;
  const muted    = delta === 0;
  return (
    <div data-testid={testId}
         data-loading={loading ? "true" : "false"}
         style={{ padding: 14, borderRadius: 12,
                   background: "rgba(255,255,255,0.04)",
                   border: "1px solid rgba(255,255,255,0.06)",
                   minHeight: 86 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6,
                     marginBottom: 6 }}>
        {icon}
        <span style={{ fontSize: 11, color: "#9aa3af",
                          textTransform: "uppercase",
                          letterSpacing: "0.06em", fontWeight: 600 }}>
          {label}
        </span>
      </div>
      {loading ? (
        <Skel w={88} h={28} />
      ) : (
        <div data-testid={`${testId}-value`}
             style={{ fontSize: 24, fontWeight: 800, color: "#fff",
                       lineHeight: 1.1 }}>
          {value}
        </div>
      )}
      {!loading && showDelta && pctChange !== null && (
        <div data-testid={`${testId}-delta`}
             data-direction={positive ? "up" : (negative ? "down" : "flat")}
             style={{ marginTop: 6, display: "inline-flex",
                       alignItems: "center", gap: 3, fontSize: 11,
                       fontWeight: 600,
                       color: positive ? "#10b981"
                                       : (negative ? "#ef4444" : "#9aa3af") }}>
          {positive && <ArrowUpRight size={11} />}
          {negative && <ArrowDownRight size={11} />}
          {muted && "—"}
          {!muted && (
            <span>
              {positive ? "+" : ""}{pctChange}% vs prev
            </span>
          )}
        </div>
      )}
    </div>
  );
}

function DailyTrendChart({ series, loading, window_ }) {
  const chartData = useMemo(() => {
    if (!series || series.length === 0) return [];
    return series.map((d) => ({
      date: d.date,
      label: d.date.slice(5),     // MM-DD
      minutes: d.listen_minutes,
      uniques: d.unique_listeners,
    }));
  }, [series]);

  return (
    <div data-testid="analytics-chart-card"
         style={{ padding: 16, borderRadius: 12,
                   background: "rgba(255,255,255,0.04)",
                   border: "1px solid rgba(255,255,255,0.06)",
                   minHeight: 280 }}>
      <div style={{ display: "flex", justifyContent: "space-between",
                     alignItems: "center", marginBottom: 12 }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: "#fff" }}>
          Listening trend ({window_})
        </div>
        <div style={{ fontSize: 11, color: "#9aa3af" }}>
          listen minutes / day
        </div>
      </div>
      {loading ? (
        <Skel w={"100%"} h={220} />
      ) : chartData.length === 0 ? (
        <div data-testid="analytics-chart-empty"
             style={{ height: 220, display: "grid", placeItems: "center",
                       color: "#9aa3af", fontSize: 12 }}>
          No listening data in this window yet.
        </div>
      ) : (
        <div style={{ height: 220, width: "100%" }}>
          <ResponsiveContainer>
            <LineChart data={chartData}
                       margin={{ top: 8, right: 16, bottom: 0, left: -8 }}>
              <CartesianGrid stroke="rgba(255,255,255,0.05)"
                             strokeDasharray="3 4" vertical={false} />
              <XAxis dataKey="label"
                     stroke="#6b7280"
                     fontSize={10}
                     tickLine={false}
                     axisLine={{ stroke: "rgba(255,255,255,0.05)" }} />
              <YAxis stroke="#6b7280" fontSize={10}
                     tickLine={false}
                     axisLine={{ stroke: "rgba(255,255,255,0.05)" }}
                     width={32} />
              <Tooltip
                contentStyle={{ background: "#111", border: "1px solid #2a2a2a",
                                  borderRadius: 6, fontSize: 12, color: "#fff" }}
                labelStyle={{ color: "#9aa3af" }}
                formatter={(v, n) => [`${v} min`, "Listen minutes"]} />
              <ReferenceLine y={0} stroke="rgba(255,255,255,0.05)" />
              <Line type="monotone" dataKey="minutes"
                     stroke="#00d9ff" strokeWidth={2}
                     dot={{ fill: "#00d9ff", r: 2 }}
                     activeDot={{ r: 5, stroke: "#0b0b0b", strokeWidth: 2 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

function TopPostsCard({ posts, loading, slug }) {
  return (
    <div data-testid="analytics-top-posts-card"
         style={{ padding: 16, borderRadius: 12,
                   background: "rgba(255,255,255,0.04)",
                   border: "1px solid rgba(255,255,255,0.06)",
                   minHeight: 280 }}>
      <div style={{ fontSize: 13, fontWeight: 700, color: "#fff",
                     marginBottom: 12 }}>
        Top posts
      </div>
      {loading ? (
        <div style={{ display: "grid", gap: 8 }}>
          {[1,2,3].map((i) => <Skel key={i} w={"100%"} h={42} />)}
        </div>
      ) : (posts || []).length === 0 ? (
        <div data-testid="analytics-top-posts-empty"
             style={{ color: "#9aa3af", fontSize: 12, padding: 8,
                       textAlign: "center" }}>
          No posts in this window. Try sharing what you&apos;re listening to —
          posts drive 3× more follow conversion than just music.
        </div>
      ) : (
        <ol data-testid="analytics-top-posts-list"
            style={{ display: "grid", gap: 8,
                      margin: 0, padding: 0, listStyle: "none" }}>
          {posts.map((p) => (
            <li key={p.post_id}
                data-testid={`analytics-top-post-${p.post_id}`}
                style={{ padding: 10, borderRadius: 8,
                          background: "rgba(255,255,255,0.03)" }}>
              <a href={`/r/${slug}#post-${p.post_id}`}
                 style={{ color: "#cbd5e1", textDecoration: "none",
                          fontSize: 12, lineHeight: 1.4,
                          display: "block", marginBottom: 6 }}>
                {p.body_excerpt}
              </a>
              <div style={{ display: "flex", gap: 12, fontSize: 11,
                              color: "#9aa3af" }}>
                <span style={{ display: "inline-flex", alignItems: "center", gap: 3 }}>
                  <Heart size={11} /> {p.reaction_total}
                </span>
                <span style={{ display: "inline-flex", alignItems: "center", gap: 3 }}>
                  <MessageCircle size={11} /> {p.comment_count}
                </span>
                <span style={{ color: "#00d9ff", fontWeight: 600 }}>
                  {p.engagement_score} pts
                </span>
              </div>

            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

// Phase 41M.B — Mood mini-section. Reads `mood_top_tracks` from the
// station analytics response (owner-only via the route's auth gate).
const MOOD_META = {
  chill: { emoji: "😌", label: "Chill", tint: "#67e8f9" },
  hype:  { emoji: "🔥", label: "Hype",  tint: "#f59e0b" },
  sad:   { emoji: "😢", label: "Sad",   tint: "#818cf8" },
  party: { emoji: "🎉", label: "Party", tint: "#ec4899" },
  focus: { emoji: "🎯", label: "Focus", tint: "#22d3ee" },
};
const MOOD_KEYS = ["chill", "hype", "sad", "party", "focus"];

function TrackMoodsCard({ moods, loading }) {
  return (
    <div data-testid="analytics-track-moods-card"
         style={{ padding: 16, borderRadius: 12,
                   background: "rgba(255,255,255,0.04)",
                   border: "1px solid rgba(255,255,255,0.06)",
                   minHeight: 140 }}>
      <div style={{ fontSize: 13, fontWeight: 700, color: "#fff",
                     marginBottom: 12 }}>
        Track moods
      </div>
      {loading ? (
        <div style={{ display: "grid", gap: 8 }}>
          {[1,2,3].map((i) => <Skel key={i} w={"100%"} h={42} />)}
        </div>
      ) : (moods || []).length === 0 ? (
        <div data-testid="analytics-track-moods-empty"
             style={{ color: "#9aa3af", fontSize: 12, padding: 8,
                       textAlign: "center" }}>
          Listeners haven&apos;t voted moods yet — share the station to get
          votes flowing.
        </div>
      ) : (
        <ol data-testid="analytics-track-moods-list"
            style={{ display: "grid", gap: 10, margin: 0,
                      padding: 0, listStyle: "none" }}>
          {moods.map((m) => {
            const total = m.sample_count || 0;
            const dom   = MOOD_META[m.dominant_mood] || {};
            return (
              <li key={m.track_id}
                  data-testid={`analytics-track-mood-${m.track_id}`}
                  style={{ padding: 10, borderRadius: 8,
                            background: "rgba(255,255,255,0.03)" }}>
                <div style={{ display: "flex", alignItems: "center",
                               gap: 10, marginBottom: 6 }}>
                  <span style={{ fontSize: 18 }}>{dom.emoji || "🎵"}</span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 12, color: "#fff",
                                   fontWeight: 600,
                                   overflow: "hidden",
                                   textOverflow: "ellipsis",
                                   whiteSpace: "nowrap" }}>
                      {m.title || m.track_id}
                    </div>
                    <div style={{ fontSize: 10, color: "#9aa3af",
                                   marginTop: 2 }}>
                      {m.artist || "—"} · {dom.label || "—"} · {total} vote{total === 1 ? "" : "s"}
                    </div>
                  </div>
                </div>
                <div style={{ display: "flex", height: 5,
                               borderRadius: 3, overflow: "hidden",
                               background: "rgba(255,255,255,0.04)" }}>
                  {MOOD_KEYS.map((k) => {
                    const c = m.distribution?.[k] || 0;
                    const w = total > 0 ? (c / total) * 100 : 0;
                    if (w <= 0) return null;
                    const meta = MOOD_META[k];
                    return (
                      <div key={k}
                           data-testid={`analytics-mood-bar-${m.track_id}-${k}`}
                           title={`${meta.label}: ${c}`}
                           style={{ width: `${w}%`,
                                     background: meta.tint }} />
                    );
                  })}
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}


function TopCitiesCard({ cities, loading }) {
  return (
    <div data-testid="analytics-top-cities-card"
         style={{ padding: 16, borderRadius: 12,
                   background: "rgba(255,255,255,0.04)",
                   border: "1px solid rgba(255,255,255,0.06)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6,
                     marginBottom: 12 }}>
        <MapPin size={14} color="#00d9ff" />
        <div style={{ fontSize: 13, fontWeight: 700, color: "#fff" }}>
          Top listener cities
        </div>
      </div>
      {loading ? (
        <Skel w={"100%"} h={40} />
      ) : (cities || []).length === 0 ? (
        <div data-testid="analytics-top-cities-empty"
             style={{ color: "#9aa3af", fontSize: 12, padding: 8 }}>
          No location data yet.
        </div>
      ) : (
        <div data-testid="analytics-top-cities-list"
             style={{ display: "grid", gap: 6 }}>
          {cities.map((c, i) => {
            const max = Math.max(...cities.map((x) => x.count));
            const pctW = max > 0 ? (c.count / max) * 100 : 0;
            return (
              <div key={`${c.city}-${i}`}
                   data-testid={`analytics-city-row-${i}`}
                   style={{ display: "grid",
                             gridTemplateColumns: "1fr auto",
                             alignItems: "center", gap: 12 }}>
                <div style={{ position: "relative", minWidth: 0 }}>
                  <div style={{ position: "absolute", top: 0, left: 0,
                                  height: "100%", width: `${pctW}%`,
                                  background: "rgba(0,217,255,0.12)",
                                  borderRadius: 4 }} />
                  <div style={{ position: "relative", padding: "4px 8px",
                                  fontSize: 12, color: "#fff" }}>
                    {c.city}
                    <span style={{ color: "#9aa3af", marginLeft: 6 }}>
                      · {c.country}
                    </span>
                  </div>
                </div>
                <div style={{ fontSize: 12, fontWeight: 700, color: "#00d9ff",
                                minWidth: 40, textAlign: "right" }}>
                  {fmtNumber(c.count)}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function Skel({ w, h }) {
  return (
    <div aria-hidden style={{
      width: typeof w === "number" ? `${w}px` : w,
      height: typeof h === "number" ? `${h}px` : h,
      borderRadius: 6,
      background: "linear-gradient(90deg, rgba(255,255,255,0.04) 0%, rgba(255,255,255,0.08) 50%, rgba(255,255,255,0.04) 100%)",
      backgroundSize: "200% 100%",
      animation: "skel 1.4s linear infinite",
    }} />
  );
}


// ─── Phase J.2 — Mood Profile card (horizontal stacked bar) ──────────
const MOOD_PALETTE = ["#00d9ff", "#a855f7", "#f59e0b", "#10b981",
                                          "#ec4899", "#6b7280"];

function MoodProfileCard({ data, loading }) {
  const total = Number(data?.total_plays || 0);
  const counts = data?.mood_counts || {};
  const sorted = Object.entries(counts)
    .sort((a, b) => b[1] - a[1]);
  const top5   = sorted.slice(0, 5);
  const other  = sorted.slice(5).reduce((acc, [, n]) => acc + n, 0);
  const segments = [];
  top5.forEach(([m, n], i) => {
    if (n > 0) segments.push({ mood: m, count: n, color: MOOD_PALETTE[i],
                                                          pct: total ? (n / total * 100) : 0 });
  });
  if (other > 0) {
    segments.push({ mood: "other", count: other,
                                  color: MOOD_PALETTE[5],
                                  pct: total ? (other / total * 100) : 0 });
  }
  const top3 = (data?.top_3 || []).slice(0, 3);

  return (
    <div data-testid="analytics-mood-profile-card"
              style={{ padding: 16, borderRadius: 12,
                              background: "rgba(255,255,255,0.04)",
                              border: "1px solid rgba(255,255,255,0.06)" }}>
      <div style={{ display: "flex", alignItems: "center",
                              justifyContent: "space-between", marginBottom: 10 }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: "#fff",
                                display: "inline-flex", alignItems: "center", gap: 6 }}>
          <Heart size={13} color="#ec4899" /> Mood profile
        </div>
        <div style={{ fontSize: 11, color: "#9aa3af" }}>
          {total ? `${total.toLocaleString()} weighted plays` : "—"}
        </div>
      </div>

      {loading && <Skel w={"100%"} h={24} />}

      {!loading && total === 0 && (
        <div data-testid="mood-profile-empty"
                  style={{ height: 60, display: "grid", placeItems: "center",
                                  color: "#9aa3af", fontSize: 12 }}>
          No mood-tagged plays in this window yet.
        </div>
      )}

      {!loading && total > 0 && (
        <>
          {/* Stacked bar */}
          <div data-testid="mood-profile-bar"
                    style={{ display: "flex", height: 22, borderRadius: 6,
                                    overflow: "hidden",
                                    border: "1px solid rgba(255,255,255,0.06)" }}>
            {segments.map((s) => (
              <div key={s.mood}
                          title={`${s.mood} · ${s.count.toLocaleString()} (${s.pct.toFixed(1)}%)`}
                          data-testid={`mood-profile-seg-${s.mood}`}
                          style={{ width: `${s.pct}%`, background: s.color }} />
            ))}
          </div>

          {/* Top-3 chips */}
          <div style={{ marginTop: 10, display: "flex", flexWrap: "wrap",
                                  gap: 6 }} data-testid="mood-profile-top3">
            {top3.map((t, i) => (
              <span key={t.mood}
                          data-testid={`mood-profile-top-${i}`}
                          style={{
                            padding: "3px 9px", borderRadius: 999,
                            background: `${MOOD_PALETTE[i]}22`,
                            color: MOOD_PALETTE[i],
                            border: `1px solid ${MOOD_PALETTE[i]}44`,
                            fontSize: 11, fontWeight: 600,
                          }}>
                {t.mood} · {t.pct}%
              </span>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
