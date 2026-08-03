// AdminAnalytics.js — Phase 12a Admin Analytics Dashboard
// Reads from /api/admin/analytics/{overview,songs,ads,commute,games,revenue,health}
// Honors missing_data_flags — no fake numbers.
import { useCallback, useEffect, useMemo, useState } from "react";
import axios from "axios";
import { Link } from "react-router-dom";
import {
  Loader2, RefreshCw, BarChart3, Download, Music, Megaphone,
  Gamepad2, DollarSign, Activity, AlertCircle,
} from "lucide-react";
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip,
  CartesianGrid, PieChart, Pie, Cell, LineChart, Line, Legend,
} from "recharts";
import { API } from "@/AuthContext";
import "./AdminImaging.css";

axios.defaults.withCredentials = true;

const RANGES = [
  { id: "7d", label: "7 days" },
  { id: "30d", label: "30 days" },
  { id: "90d", label: "90 days" },
];

const TABS = [
  { id: "songs", label: "Songs", icon: Music },
  { id: "ads", label: "Ads & Commute", icon: Megaphone },
  { id: "games", label: "Games", icon: Gamepad2 },
  { id: "revenue", label: "Revenue & Health", icon: DollarSign },
];

const PIE_COLORS = ["#ff2d95", "#7BD3F7", "#fdb756", "#4ade80",
                          "#ff8a3d", "#a78bfa", "#f472b6", "#34d399"];

// ─── Small primitives ───────────────────────────────────────────────────
function fmtNumber(n) {
  if (n === null || n === undefined) return "—";
  if (typeof n !== "number") return String(n);
  if (Math.abs(n) >= 1e6) return `${(n / 1e6).toFixed(2)}M`;
  if (Math.abs(n) >= 1e3) return `${(n / 1e3).toFixed(1)}k`;
  return Number.isInteger(n) ? n.toString() : n.toFixed(2);
}
function fmtPct(n) {
  if (n === null || n === undefined) return "—";
  return `${(n * 100).toFixed(1)}%`;
}
function fmtUSD(cents) {
  if (cents === null || cents === undefined) return "—";
  return `$${(cents / 100).toFixed(2)}`;
}

function KpiCard({ label, value, sub, accent = "#ff2d95",
                       missing = false, testid }) {
  return (
    <div className="img-station-card" style={{ padding: 18, gap: 6 }}
            data-testid={testid}>
      <div className="meta-label" style={{ fontSize: 10 }}>{label}</div>
      {missing ? (
        <div data-testid={`${testid}-missing`}
                style={{ display: "flex", alignItems: "center", gap: 6,
                            color: "#888892", fontSize: 12,
                            fontStyle: "italic", lineHeight: 1.3 }}>
          <AlertCircle size={14} />
          Data unavailable — integration not live
        </div>
      ) : (
        <>
          <div style={{ fontSize: 28, fontWeight: 800, color: accent,
                            lineHeight: 1.0 }}>
            {value}
          </div>
          {sub && (
            <div className="asset-slug"
                    style={{ fontSize: 11, color: "#888892" }}>
              {sub}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function MissingPanel({ label, testid }) {
  return (
    <div className="img-station-card" data-testid={testid}
            style={{ padding: 24, alignItems: "center",
                        textAlign: "center", color: "#888892" }}>
      <AlertCircle size={20} />
      <div style={{ fontSize: 12, fontWeight: 600, marginTop: 8,
                       textTransform: "uppercase", letterSpacing: 0.6 }}>
        {label}
      </div>
      <div style={{ fontSize: 12, marginTop: 4 }}>
        Data unavailable — integration not live
      </div>
    </div>
  );
}

// ─── CSV export ─────────────────────────────────────────────────────────
function downloadCsv(rows, filename) {
  if (!rows || rows.length === 0) return;
  const keys = Array.from(
    rows.reduce((acc, r) => { Object.keys(r).forEach((k) => acc.add(k));
                                       return acc; }, new Set()));
  const esc = (v) => {
    if (v === null || v === undefined) return "";
    const s = typeof v === "object" ? JSON.stringify(v) : String(v);
    if (s.includes(",") || s.includes("\n") || s.includes("\""))
      return `"${s.replace(/"/g, "\"\"")}"`;
    return s;
  };
  const csv = [keys.join(","),
                  ...rows.map((r) => keys.map((k) => esc(r[k])).join(","))]
                  .join("\n");
  const blob = new Blob([csv], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename;
  document.body.appendChild(a); a.click(); a.remove();
  URL.revokeObjectURL(url);
}

// ─── Tab content ────────────────────────────────────────────────────────
function SongsTab({ data, flags }) {
  if (!data) return null;
  const top = data.top_played || [];
  const skipped = data.most_skipped || [];
  const liked = data.top_liked || [];
  return (
    <div style={{ display: "grid",
                       gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))",
                       gap: 18 }} data-testid="tab-songs">
      <div className="img-station-card" data-testid="songs-top-played">
        <div className="meta-label" style={{ display: "flex",
                                                                 justifyContent: "space-between" }}>
          <span>TOP PLAYED</span>
          <button type="button" className="asset-type-chip"
                       onClick={() => downloadCsv(top, "top_played.csv")}
                       data-testid="csv-top-played">
            <Download size={11} /> CSV
          </button>
        </div>
        {top.length === 0 ? (
          <div style={{ color: "#888892", fontSize: 12 }}>No data</div>
        ) : top.slice(0, 15).map((t) => (
          <div key={t.track_id} className="asset-meta-row"
                  style={{ justifyContent: "space-between", padding: "6px 0",
                             borderBottom: "1px solid #25252f", fontSize: 13 }}>
            <span style={{ overflow: "hidden",
                                textOverflow: "ellipsis", whiteSpace: "nowrap",
                                maxWidth: 240 }}>
              {t.title || t.track_id}{" "}
              <span style={{ color: "#888892" }}>· {t.artist || "—"}</span>
            </span>
            <span style={{ color: "#4ade80", fontWeight: 700 }}>
              {fmtNumber(t.plays)}
            </span>
          </div>
        ))}
      </div>

      <div className="img-station-card" data-testid="songs-most-skipped">
        <div className="meta-label" style={{ display: "flex",
                                                                 justifyContent: "space-between" }}>
          <span>MOST SKIPPED (≥3 plays)</span>
          <button type="button" className="asset-type-chip"
                       onClick={() => downloadCsv(skipped, "most_skipped.csv")}
                       data-testid="csv-most-skipped">
            <Download size={11} /> CSV
          </button>
        </div>
        {skipped.length === 0 ? (
          <div style={{ color: "#888892", fontSize: 12 }}>No data</div>
        ) : skipped.slice(0, 15).map((t) => (
          <div key={t.track_id} className="asset-meta-row"
                  style={{ justifyContent: "space-between", padding: "6px 0",
                             borderBottom: "1px solid #25252f", fontSize: 13 }}>
            <span style={{ overflow: "hidden",
                                textOverflow: "ellipsis", whiteSpace: "nowrap",
                                maxWidth: 240 }}>
              {t.title || t.track_id}
            </span>
            <span style={{ color: "#ff8a3d", fontWeight: 700 }}>
              {fmtPct(t.skip_rate)}
            </span>
          </div>
        ))}
      </div>

      <div className="img-station-card" data-testid="songs-top-liked">
        <div className="meta-label" style={{ display: "flex",
                                                                 justifyContent: "space-between" }}>
          <span>TOP LIKED</span>
          {flags.includes("top_liked") || liked.length === 0 ? null : (
            <button type="button" className="asset-type-chip"
                         onClick={() => downloadCsv(liked, "top_liked.csv")}
                         data-testid="csv-top-liked">
              <Download size={11} /> CSV
            </button>
          )}
        </div>
        {flags.includes("top_liked") ? (
          <div data-testid="top-liked-missing"
                  style={{ color: "#888892", fontSize: 12, fontStyle: "italic" }}>
            <AlertCircle size={13} style={{ verticalAlign: -2,
                                                          marginRight: 4 }} />
            Data unavailable — integration not live
          </div>
        ) : liked.length === 0 ? (
          <div style={{ color: "#888892", fontSize: 12 }}>No data</div>
        ) : liked.slice(0, 15).map((t) => (
          <div key={t.track_id} className="asset-meta-row"
                  style={{ justifyContent: "space-between", padding: "6px 0",
                             borderBottom: "1px solid #25252f", fontSize: 13 }}>
            <span>{t.title || t.track_id}</span>
            <span style={{ color: "#fdb756", fontWeight: 700 }}>
              {fmtNumber(t.likes)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function AdsTab({ ads, commute, flags, commuteFlags }) {
  if (!ads) return null;
  const byCampaign = (ads.by_campaign || []).map((c) => ({
    name: (c.campaign_name || c.campaign_id || "").slice(0, 18),
    impressions: c.impressions,
    revenue_usd: (c.revenue_cents || 0) / 100,
  }));
  const byAdvertiser = ads.by_advertiser || [];
  const byTrigger = (commute?.by_trigger || []);
  return (
    <div style={{ display: "grid", gap: 18 }} data-testid="tab-ads">
      <div style={{ display: "grid",
                         gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))",
                         gap: 18 }}>
        <div className="img-station-card" data-testid="ads-by-campaign">
          <div className="meta-label" style={{ display: "flex",
                                                                   justifyContent: "space-between" }}>
            <span>IMPRESSIONS BY CAMPAIGN (TOP 10)</span>
            <button type="button" className="asset-type-chip"
                          onClick={() => downloadCsv(ads.by_campaign || [],
                                                                "by_campaign.csv")}
                          data-testid="csv-by-campaign">
              <Download size={11} /> CSV
            </button>
          </div>
          {byCampaign.length === 0 ? (
            <div style={{ color: "#888892", fontSize: 12 }}>No data</div>
          ) : (
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={byCampaign}>
                <CartesianGrid stroke="#25252f" strokeDasharray="3 3" />
                <XAxis dataKey="name" stroke="#888892" fontSize={10} />
                <YAxis stroke="#888892" fontSize={10} />
                <Tooltip contentStyle={{ background: "#1a1a25",
                                                       border: "1px solid #2a2a36",
                                                       fontSize: 12 }} />
                <Bar dataKey="impressions" fill="#ff2d95" />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        <div className="img-station-card" data-testid="ads-by-advertiser">
          <div className="meta-label" style={{ display: "flex",
                                                                  justifyContent: "space-between" }}>
            <span>REVENUE BY ADVERTISER (TOP 10)</span>
            <button type="button" className="asset-type-chip"
                         onClick={() => downloadCsv(byAdvertiser,
                                                                "by_advertiser.csv")}
                         data-testid="csv-by-advertiser">
              <Download size={11} /> CSV
            </button>
          </div>
          {byAdvertiser.length === 0 ? (
            <div style={{ color: "#888892", fontSize: 12 }}>No data</div>
          ) : byAdvertiser.map((a) => (
            <div key={a.advertiser_id} className="asset-meta-row"
                    style={{ justifyContent: "space-between",
                                padding: "6px 0",
                                borderBottom: "1px solid #25252f",
                                fontSize: 13 }}>
              <span>{a.advertiser_id}</span>
              <span style={{ color: "#4ade80", fontWeight: 700 }}>
                {fmtUSD(a.revenue_cents)}
              </span>
            </div>
          ))}
        </div>

        <div className="img-station-card" data-testid="commute-by-trigger">
          <div className="meta-label">COMMUTE TRIGGERS</div>
          {byTrigger.length === 0 ? (
            commuteFlags.includes("by_trigger") ? (
              <div data-testid="commute-triggers-missing"
                       style={{ color: "#888892", fontSize: 12,
                                  fontStyle: "italic" }}>
                <AlertCircle size={13} style={{ verticalAlign: -2,
                                                              marginRight: 4 }} />
                Data unavailable — integration not live
              </div>
            ) : (
              <div style={{ color: "#888892", fontSize: 12 }}>No data</div>
            )
          ) : (
            <ResponsiveContainer width="100%" height={240}>
              <PieChart>
                <Pie data={byTrigger} dataKey="count" nameKey="trigger"
                          outerRadius={70} innerRadius={36}>
                  {byTrigger.map((_, i) => (
                    <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip contentStyle={{ background: "#1a1a25",
                                                          border: "1px solid #2a2a36",
                                                          fontSize: 12 }} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      <div style={{ display: "grid",
                         gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
                         gap: 18 }}>
        <KpiCard label="ECPM" testid="kpi-ecpm"
                      value={fmtUSD(ads.eCPM)} sub="GAM not live"
                      missing={flags.includes("eCPM")} accent="#fdb756" />
        <KpiCard label="FILL RATE" testid="kpi-fill-rate"
                      value={fmtPct(ads.fill_rate)} sub="GAM not live"
                      missing={flags.includes("fill_rate")} accent="#fdb756" />
        <KpiCard label="ROUTE AD IMPRESSIONS"
                      testid="kpi-route-ad-impressions"
                      value={fmtNumber(commute?.route_ad_impressions)}
                      missing={commute?.route_ad_impressions === null} />
        <KpiCard label="ROUTE CONV RATE"
                      testid="kpi-route-conv-rate"
                      value={fmtPct(commute?.route_ad_conversion_rate)}
                      missing={commute?.route_ad_conversion_rate === null}
                      accent="#7BD3F7" />
      </div>
    </div>
  );
}

function GamesTab({ data, flags }) {
  if (!data) return null;
  const byType = (data.by_game_type || []).map((g) => ({
    name: g.game_type, plays: g.plays, wins: g.wins,
  }));
  return (
    <div style={{ display: "grid", gap: 18 }} data-testid="tab-games">
      <div style={{ display: "grid",
                         gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
                         gap: 18 }}>
        <KpiCard label="TOTAL PLAYS" testid="kpi-games-plays"
                      value={fmtNumber(data.plays_total)} accent="#7BD3F7" />
        <KpiCard label="REWARDS ISSUED (BC)"
                      testid="kpi-rewards-issued"
                      value={fmtNumber(data.rewards_issued_bigcoin)}
                      missing={data.rewards_issued_bigcoin === null}
                      accent="#fdb756" />
        <KpiCard label="CLAIM RATE" testid="kpi-claim-rate"
                      value={fmtPct(data.claim_rate)}
                      missing={data.claim_rate === null
                                  || flags.includes("claim_rate")}
                      sub={`${data.claimed || 0}/${data.wins || 0} wins`}
                      accent="#4ade80" />
        <KpiCard label="LEAD FORM COMPLETION"
                      testid="kpi-lead-form-rate"
                      value={fmtPct(data.lead_form_completion_rate)}
                      missing={flags.includes("lead_form_completion_rate")
                                  || data.lead_form_completion_rate === null}
                      accent="#ff2d95" />
      </div>

      <div className="img-station-card" data-testid="games-by-type">
        <div className="meta-label" style={{ display: "flex",
                                                                 justifyContent: "space-between" }}>
          <span>PLAYS BY GAME TYPE</span>
          <button type="button" className="asset-type-chip"
                       onClick={() => downloadCsv(data.by_game_type || [],
                                                              "by_game_type.csv")}
                       data-testid="csv-games-by-type">
            <Download size={11} /> CSV
          </button>
        </div>
        {byType.length === 0 ? (
          <div style={{ color: "#888892", fontSize: 12 }}>No data</div>
        ) : (
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={byType}>
              <CartesianGrid stroke="#25252f" strokeDasharray="3 3" />
              <XAxis dataKey="name" stroke="#888892" fontSize={10} />
              <YAxis stroke="#888892" fontSize={10} />
              <Tooltip contentStyle={{ background: "#1a1a25",
                                                      border: "1px solid #2a2a36",
                                                      fontSize: 12 }} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="plays" fill="#7BD3F7" />
              <Bar dataKey="wins" fill="#4ade80" />
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}

function RevenueHealthTab({ revenue, health, flags, healthFlags }) {
  if (!revenue || !health) return null;
  const mrrRows = (revenue.mrr_breakdown || []).map((b) => ({
    tier: b.tier, subscribers: b.subscribers,
    monthly_usd: (b.monthly_price_cents || 0) / 100,
  }));
  return (
    <div style={{ display: "grid", gap: 18 }} data-testid="tab-revenue">
      <div style={{ display: "grid",
                         gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
                         gap: 18 }}>
        <KpiCard label="SUBSCRIPTION MRR" testid="kpi-mrr"
                      value={fmtUSD(revenue.subscription_mrr_cents)}
                      sub={`${revenue.active_subscriptions} active`}
                      accent="#4ade80" />
        <KpiCard label="ADVERTISER REVENUE"
                      testid="kpi-advertiser-revenue"
                      value={fmtUSD(revenue.advertiser_revenue_cents)}
                      sub={`${revenue.ad_impressions ?? "—"} impressions`}
                      missing={flags.includes("advertiser_revenue_cents")} />
        <KpiCard label="CHURN RATE" testid="kpi-churn"
                      value={fmtPct(revenue.subscription_churn?.churn_rate)}
                      missing={flags.includes("subscription_churn")
                                  || !revenue.subscription_churn}
                      sub={revenue.subscription_churn
                              ? `${revenue.subscription_churn.churned_in_window} churned`
                              : null}
                      accent="#ff8a3d" />
        <KpiCard label="ECPM" testid="kpi-revenue-ecpm"
                      value={fmtUSD(revenue.eCPM)}
                      sub="GAM not live"
                      missing={flags.includes("eCPM")} accent="#fdb756" />
        <KpiCard label="PROGRAMMATIC FILL"
                      testid="kpi-fill"
                      value={fmtPct(revenue.programmatic_fill_rate)}
                      sub="GAM not live"
                      missing={flags.includes("programmatic_fill_rate")}
                      accent="#fdb756" />
      </div>

      <div className="img-station-card" data-testid="revenue-mrr-breakdown">
        <div className="meta-label" style={{ display: "flex",
                                                                 justifyContent: "space-between" }}>
          <span>MRR BREAKDOWN BY TIER</span>
          <button type="button" className="asset-type-chip"
                       onClick={() => downloadCsv(mrrRows, "mrr_breakdown.csv")}
                       data-testid="csv-mrr-breakdown">
            <Download size={11} /> CSV
          </button>
        </div>
        {mrrRows.length === 0 ? (
          <div style={{ color: "#888892", fontSize: 12 }}>
            No active subscribers
          </div>
        ) : mrrRows.map((r) => (
          <div key={r.tier} className="asset-meta-row"
                  style={{ justifyContent: "space-between", padding: "6px 0",
                             borderBottom: "1px solid #25252f", fontSize: 13 }}>
            <span>{r.tier}</span>
            <span>{r.subscribers} × ${r.monthly_usd.toFixed(2)}/mo</span>
          </div>
        ))}
      </div>

      <div style={{ display: "grid",
                         gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
                         gap: 18 }} data-testid="health-tiles">
        <KpiCard label="COLD START p50"
                      testid="kpi-cold-p50"
                      value={`${fmtNumber(health.cold_start_segment_latency_p50_ms)} ms`}
                      missing={healthFlags.includes("cold_start_segment_latency")
                                  || health.cold_start_segment_latency_p50_ms === null}
                      sub={`n=${health.cold_start_sample_size || 0}`} />
        <KpiCard label="COLD START p95"
                      testid="kpi-cold-p95"
                      value={`${fmtNumber(health.cold_start_segment_latency_p95_ms)} ms`}
                      missing={healthFlags.includes("cold_start_segment_latency")
                                  || health.cold_start_segment_latency_p95_ms === null}
                      accent="#ff8a3d" />
        <KpiCard label="AI RJ FAIL RATE"
                      testid="kpi-ai-rj-fail"
                      value={fmtPct(health.ai_rj_generation_failure_rate)}
                      missing={healthFlags.includes("ai_rj_generation_failure_rate")}
                      sub={`${health.ai_rj_attempts_since_boot} attempts`} />
        <KpiCard label="FFMPEG FAIL RATE"
                      testid="kpi-ffmpeg-fail"
                      value={fmtPct(health.ffmpeg_concat_failure_rate)}
                      missing={healthFlags.includes("ffmpeg_concat_failure_rate")}
                      sub={`${health.ffmpeg_concat_attempts_since_boot} attempts`} />
        <KpiCard label="ACTIVE LOBBIES"
                      testid="kpi-active-lobbies"
                      value={fmtNumber(health.active_lobbies)}
                      accent="#7BD3F7" />
        <KpiCard label="WS DISCONNECT RATE"
                      testid="kpi-ws-disconnect"
                      value={fmtPct(health.ws_disconnect_rate)}
                      missing={healthFlags.includes("ws_disconnect_rate")} />
      </div>
    </div>
  );
}

// ─── Main page ──────────────────────────────────────────────────────────
export default function AdminAnalytics() {
  const [range, setRange] = useState("7d");
  const [tab, setTab] = useState("songs");
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [error, setError] = useState(null);
  const [bundle, setBundle] = useState({
    overview: null, songs: null, ads: null, commute: null,
    games: null, revenue: null, health: null,
  });

  const fetchAll = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const endpoints = ["overview", "songs", "ads", "commute",
                                 "games", "revenue", "health"];
      const results = await Promise.all(endpoints.map((ep) =>
        axios.get(`${API}/admin/analytics/${ep}${ep === "health"
                       ? "" : `?range=${range}`}`)
              .then((r) => [ep, r.data])
              .catch((e) => [ep, { __error: e.message }])));
      const next = {};
      results.forEach(([ep, payload]) => { next[ep] = payload; });
      setBundle(next);
      setLastUpdated(new Date());
    } catch (e) {
      setError(e.message || "Failed to load analytics");
    } finally { setLoading(false); }
  }, [range]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const overview = bundle.overview?.data;
  const overviewFlags = bundle.overview?.missing_data_flags || [];
  const songs = bundle.songs?.data;
  const songsFlags = bundle.songs?.missing_data_flags || [];
  const ads = bundle.ads?.data;
  const adsFlags = bundle.ads?.missing_data_flags || [];
  const commute = bundle.commute?.data;
  const commuteFlags = bundle.commute?.missing_data_flags || [];
  const games = bundle.games?.data;
  const gamesFlags = bundle.games?.missing_data_flags || [];
  const revenue = bundle.revenue?.data;
  const revenueFlags = bundle.revenue?.missing_data_flags || [];
  const health = bundle.health?.data;
  const healthFlags = bundle.health?.missing_data_flags || [];

  const topChannelsChart = useMemo(() => (
    (overview?.top_channels || []).slice(0, 10).map((c) => ({
      name: c.channel_slug, plays: c.plays,
    }))), [overview]);

  return (
    <div className="admin-img-wrap" data-testid="admin-analytics-page">
      <header className="admin-img-header">
        <div>
          <h1>
            <BarChart3 size={24} style={{ verticalAlign: "-4px",
                                                       marginRight: 8 }} />
            Analytics
          </h1>
          <p>
            Real-time KPIs across listening, ads, commute targeting, games,
            and revenue.  Surfaces NULL with a flag whenever the source
            integration is not live — no fabricated numbers.
          </p>
          <p style={{ marginTop: 6, fontSize: 11, color: "#666670" }}>
            <Link to="/admin" className="admin-pill"
                     data-testid="link-admin-home">← Admin</Link>
            {" · "}
            <Link to="/admin/revenue/live" className="admin-pill"
                     data-testid="link-revenue-live">Live revenue</Link>
          </p>
        </div>
        <div style={{ display: "flex", flexDirection: "column",
                          gap: 10, alignItems: "flex-end" }}>
          <div className="admin-img-pills" data-testid="range-selector">
            {RANGES.map((r) => (
              <button key={r.id} type="button"
                      className={`asset-type-chip ${range === r.id ? "on" : ""}`}
                      onClick={() => setRange(r.id)}
                      data-testid={`range-${r.id}`}>
                {r.label}
              </button>
            ))}
          </div>
          <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
            <button type="button" className="asset-type-chip"
                          onClick={fetchAll} disabled={loading}
                          data-testid="btn-refresh">
              <RefreshCw size={11}
                                   className={loading ? "spin" : ""} /> Refresh
            </button>
            {lastUpdated && (
              <span style={{ fontSize: 11, color: "#666670" }}
                       data-testid="last-updated">
                Updated {lastUpdated.toLocaleTimeString()}
              </span>
            )}
          </div>
        </div>
      </header>

      {error && (
        <div className="img-station-card" style={{ borderColor: "#ff4d4d",
                                                                       marginBottom: 18 }}
                data-testid="error-banner">
          <AlertCircle size={16} color="#ff4d4d" /> {error}
        </div>
      )}

      {/* KPI grid (overview) */}
      <section className="img-stations-grid" data-testid="kpi-grid"
                  style={{ marginBottom: 24 }}>
        <KpiCard testid="kpi-dau" label="DAU"
                      value={fmtNumber(overview?.dau)} accent="#ff2d95"
                      missing={overview?.dau === null
                                  || overviewFlags.includes("dau_wau_mau")} />
        <KpiCard testid="kpi-wau" label="WAU"
                      value={fmtNumber(overview?.wau)} accent="#7BD3F7"
                      missing={overview?.wau === null
                                  || overviewFlags.includes("dau_wau_mau")} />
        <KpiCard testid="kpi-mau" label="MAU"
                      value={fmtNumber(overview?.mau)} accent="#fdb756"
                      missing={overview?.mau === null
                                  || overviewFlags.includes("dau_wau_mau")} />
        <KpiCard testid="kpi-listening-hours" label="LISTENING HOURS"
                      value={fmtNumber(overview?.listening_hours_total)}
                      missing={overviewFlags.includes("listening_hours_total")}
                      accent="#4ade80" sub={`${range} window`} />
        <KpiCard testid="kpi-skip-rate" label="SKIP RATE"
                      value={fmtPct(overview?.skip_rate)}
                      missing={overview?.skip_rate === null}
                      sub={`${overview?.plays_total || 0} plays`}
                      accent="#ff8a3d" />
        <KpiCard testid="kpi-premium-conv" label="PREMIUM CONV"
                      value={fmtPct(overview?.premium_conversion_rate)}
                      sub={`${overview?.premium_users || 0}/${overview?.total_users || 0}`}
                      accent="#a78bfa" />
        <KpiCard testid="kpi-rewards-liability"
                      label="REWARDS LIABILITY (BC)"
                      value={fmtNumber(overview?.rewards_liability_bigcoin)}
                      accent="#fdb756" />
        <KpiCard testid="kpi-revenue-total" label="REVENUE TOTAL"
                      value={fmtUSD(overview?.revenue_total_cents)}
                      missing={overviewFlags.includes("revenue_total_cents")}
                      accent="#4ade80" />
      </section>

      <section style={{ display: "grid",
                              gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))",
                              gap: 18, marginBottom: 24 }}>
        <div className="img-station-card" data-testid="overview-top-channels">
          <div className="meta-label" style={{ display: "flex",
                                                                   justifyContent: "space-between" }}>
            <span>TOP CHANNELS</span>
            <button type="button" className="asset-type-chip"
                         onClick={() => downloadCsv(overview?.top_channels || [],
                                                                "top_channels.csv")}
                         data-testid="csv-top-channels">
              <Download size={11} /> CSV
            </button>
          </div>
          {topChannelsChart.length === 0 ? (
            <div style={{ color: "#888892", fontSize: 12 }}>No data</div>
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={topChannelsChart} layout="vertical">
                <CartesianGrid stroke="#25252f" strokeDasharray="3 3" />
                <XAxis type="number" stroke="#888892" fontSize={10} />
                <YAxis type="category" dataKey="name" stroke="#888892"
                           fontSize={10} width={120} />
                <Tooltip contentStyle={{ background: "#1a1a25",
                                                         border: "1px solid #2a2a36",
                                                         fontSize: 12 }} />
                <Bar dataKey="plays" fill="#ff2d95" />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        <div className="img-station-card"
                data-testid="overview-revenue-by-channel">
          <div className="meta-label" style={{ display: "flex",
                                                                  justifyContent: "space-between" }}>
            <span>REVENUE BY CHANNEL</span>
            <button type="button" className="asset-type-chip"
                          onClick={() => downloadCsv(
                            overview?.revenue_by_channel || [],
                            "revenue_by_channel.csv")}
                          data-testid="csv-revenue-by-channel">
              <Download size={11} /> CSV
            </button>
          </div>
          {(overview?.revenue_by_channel || []).length === 0 ? (
            overviewFlags.includes("revenue_by_channel") ? (
              <MissingPanel testid="revenue-by-channel-missing"
                                       label="REVENUE BY CHANNEL" />
            ) : (
              <div style={{ color: "#888892", fontSize: 12 }}>No data</div>
            )
          ) : (overview.revenue_by_channel.map((c) => (
            <div key={c.channel_slug} className="asset-meta-row"
                    style={{ justifyContent: "space-between",
                                padding: "6px 0",
                                borderBottom: "1px solid #25252f", fontSize: 13 }}>
              <span>{c.channel_slug}</span>
              <span style={{ color: "#4ade80", fontWeight: 700 }}>
                {fmtUSD(c.revenue_cents)}
                <span style={{ color: "#888892", marginLeft: 6 }}>
                  · {c.impressions}
                </span>
              </span>
            </div>
          )))}
        </div>
      </section>

      {/* Tab bar */}
      <nav className="admin-img-pills" data-testid="tab-bar"
              style={{ marginBottom: 18 }}>
        {TABS.map(({ id, label, icon: Icon }) => (
          <button key={id} type="button"
                  className={`asset-type-chip ${tab === id ? "on" : ""}`}
                  onClick={() => setTab(id)} data-testid={`tab-${id}`}>
            <Icon size={11} /> {label}
          </button>
        ))}
      </nav>

      {loading && !overview ? (
        <div data-testid="loading-spinner"
                style={{ display: "flex", justifyContent: "center", padding: 40 }}>
          <Loader2 size={28} className="spin" />
        </div>
      ) : (
        <>
          {tab === "songs" && (
            <SongsTab data={songs} flags={songsFlags} />)}
          {tab === "ads" && (
            <AdsTab ads={ads} commute={commute} flags={adsFlags}
                          commuteFlags={commuteFlags} />)}
          {tab === "games" && (
            <GamesTab data={games} flags={gamesFlags} />)}
          {tab === "revenue" && (
            <RevenueHealthTab revenue={revenue} health={health}
                                          flags={revenueFlags}
                                          healthFlags={healthFlags} />)}
        </>
      )}
    </div>
  );
}
