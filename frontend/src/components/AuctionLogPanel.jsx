// Phase 18d.1 — Programmatic Auction Log panel.
//
// Read-only audit view of the last N ad picks merged across the
// `ad_impressions` and `openrtb_auctions` streams. Auto-refreshes every
// 10s; toggle pauses the refresh. Columns:
//   Time · Source · Channel · Advertiser · Creative · Bid · Clear · Reason
//
// No write actions; no auction-tampering surface; admin-only.

import React, {useEffect, useState, useRef} from "react";
import axios from "axios";
import {Loader2, Pause, Play, RefreshCw} from "lucide-react";
import "../AdminImaging.css";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
axios.defaults.withCredentials = true;
const POLL_MS = 10000;

export const SOURCE_BADGE = {
  direct:                       {label: "Direct",                     color: "#22c55e",
                                            bg: "rgba(34,197,94,0.15)",   bd: "rgba(34,197,94,0.4)"},
  sponsored:                {label: "Sponsored",            color: "#14b8a6",
                                            bg: "rgba(20,184,166,0.15)", bd: "rgba(20,184,166,0.4)"},
  private_marketplace: {label: "PMP",                          color: "#3b82f6",
                                            bg: "rgba(59,130,246,0.15)", bd: "rgba(59,130,246,0.4)"},
  gam:                              {label: "GAM",                          color: "#a855f7",
                                            bg: "rgba(168,85,247,0.15)", bd: "rgba(168,85,247,0.4)"},
  openrtb:                      {label: "OpenRTB",               color: "#f97316",
                                            bg: "rgba(249,115,22,0.15)", bd: "rgba(249,115,22,0.4)"},
  house:                          {label: "House",                      color: "#9ca3af",
                                            bg: "rgba(156,163,175,0.15)", bd: "rgba(156,163,175,0.4)"},
};

// Format integer cents as a currency string. Below 1¢ shows 4 decimals
// (eCPM-style); 1¢ and above shows 2 decimals.
export function formatCents(n) {
  if (n == null || Number.isNaN(n)) return "—";
  const dollars = n / 100;
  if (Math.abs(dollars) < 0.01) return `$${dollars.toFixed(4)}`;
  return `$${dollars.toFixed(2)}`;
}

function relativeTime(iso) {
  if (!iso) return "—";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return iso;
  const dt = (Date.now() - t) / 1000;
  if (dt < 60)        return `${Math.floor(dt)}s ago`;
  if (dt < 3600)    return `${Math.floor(dt / 60)}m ago`;
  if (dt < 86400) return `${Math.floor(dt / 3600)}h ago`;
  return `${Math.floor(dt / 86400)}d ago`;
}

function SourceBadge({source}) {
  const b = SOURCE_BADGE[source] || SOURCE_BADGE.house;
  return (
    <span data-testid={`source-badge-${source}`}
              data-source={source}
              style={{display: "inline-block", padding: "2px 8px",
                          borderRadius: 999, background: b.bg,
                          color: b.color, border: `1px solid ${b.bd}`,
                          fontSize: 11, fontWeight: 700,
                          textTransform: "uppercase", letterSpacing: 0.3}}>
      {b.label}
    </span>
  );
}

function Reason({text}) {
  if (!text) return <span style={{color: "#6b7280"}}>—</span>;
  const trimmed = text.length > 60 ? text.slice(0, 57) + "…" : text;
  return <span title={text} data-testid="auction-reason">{trimmed}</span>;
}

export default function AuctionLogPanel() {
  const [items, setItems]               = useState([]);
  const [meta, setMeta]                 = useState({total_in_window: 0, window_seconds: 86400});
  const [loading, setLoading]      = useState(true);
  const [paused, setPaused]        = useState(false);
  const [err, setErr]                       = useState("");
  const [lastFetched, setLastFetched] = useState(null);
  const timerRef = useRef(null);

  const fetchData = async () => {
    try {
      // Use a 7-day window so the panel is useful in dev; cap to 100.
      const r = await axios.get(
        `${API}/admin/ads/auction-log/recent?limit=20&window_seconds=86400`);
      setItems(r.data?.items || []);
      setMeta({total_in_window: r.data?.total_in_window || 0,
                          window_seconds: r.data?.window_seconds || 86400});
      setErr("");
    } catch (e) {
      setErr(e?.response?.data?.detail || e.message || "Fetch failed");
    } finally {
      setLoading(false);
      setLastFetched(new Date());
    }
  };

  useEffect(() => {
    fetchData();
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, []);
  useEffect(() => {
    if (timerRef.current) clearInterval(timerRef.current);
    if (!paused) timerRef.current = setInterval(fetchData, POLL_MS);
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [paused]);

  return (
    <div className="admin-img-wrap" data-testid="auction-log-panel">
      <div style={{display: "flex", justifyContent: "space-between",
                          alignItems: "center", marginBottom: 16}}>
        <div>
          <h1 style={{fontSize: 24, fontWeight: 800, margin: 0}}>
            Programmatic Auction Log
          </h1>
          <div style={{fontSize: 13, color: "#9aa3af", marginTop: 2}}>
            Last 20 ad picks · {meta.total_in_window} in the past{" "}
            {Math.round(meta.window_seconds / 3600)}h
          </div>
        </div>
        <div style={{display: "flex", gap: 8, alignItems: "center"}}>
          {lastFetched && (
            <span data-testid="auction-log-fetched-at"
                      style={{fontSize: 11, color: "#6b7280"}}>
              Updated {relativeTime(lastFetched.toISOString())}
            </span>
          )}
          <button data-testid="auction-log-refresh-now"
                          onClick={fetchData} title="Refresh now"
                          style={btnStyle()}>
            <RefreshCw size={14} />
          </button>
          <button data-testid="auction-log-pause-toggle"
                          onClick={() => setPaused((p) => !p)}
                          title={paused ? "Resume auto-refresh" : "Pause auto-refresh"}
                          style={btnStyle(paused)}>
            {paused ? <Play size={14} /> : <Pause size={14} />}
            <span style={{marginLeft: 6}}>{paused ? "Paused" : "Auto 10s"}</span>
          </button>
        </div>
      </div>

      {err && (
        <div data-testid="auction-log-err"
                style={{padding: 10, borderRadius: 6,
                            background: "rgba(239,68,68,0.1)",
                            border: "1px solid rgba(239,68,68,0.3)",
                            color: "#f87171", fontSize: 13, marginBottom: 12}}>
          {String(err)}
        </div>
      )}

      {loading && items.length === 0 && (
        <div data-testid="auction-log-loading"
                style={{padding: 40, textAlign: "center"}}>
          <Loader2 className="spin" size={28} />
        </div>
      )}

      {!loading && items.length === 0 && (
        <div data-testid="auction-log-empty"
                style={{padding: 40, textAlign: "center", color: "#9aa3af"}}>
          No auctions in the last 24 hours.
        </div>
      )}

      {items.length > 0 && (
        <div data-testid="auction-log-table"
                style={{overflowX: "auto", border: "1px solid rgba(255,255,255,0.06)",
                            borderRadius: 8}}>
          <table style={{width: "100%", borderCollapse: "collapse",
                                  fontSize: 13}}>
            <thead>
              <tr style={{background: "rgba(255,255,255,0.03)"}}>
                <Th>Time</Th><Th>Source</Th><Th>Channel</Th>
                <Th>Advertiser</Th><Th>Creative</Th>
                <Th align="right">Bid</Th><Th align="right">Clear</Th>
                <Th>Reason</Th>
              </tr>
            </thead>
            <tbody>
              {items.map((it, idx) => (
                <tr key={it.auction_id || idx}
                       data-testid={`auction-row-${idx}`}
                       style={{borderTop: "1px solid rgba(255,255,255,0.04)"}}>
                  <Td><span title={it.timestamp}>{relativeTime(it.timestamp)}</span></Td>
                  <Td><SourceBadge source={it.source || "house"} /></Td>
                  <Td>{it.channel_id || "—"}</Td>
                  <Td>{it.advertiser_name || it.advertiser_id || "—"}</Td>
                  <Td>{it.creative_title || it.creative_id || "—"}</Td>
                  <Td align="right" testid="auction-bid">{formatCents(it.bid_price_cents)}</Td>
                  <Td align="right" testid="auction-clear">{formatCents(it.clear_price_cents)}</Td>
                  <Td><Reason text={it.reason} /></Td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

const Th = ({children, align}) => (
  <th style={{padding: "8px 10px", textAlign: align || "left",
                      fontSize: 10, textTransform: "uppercase",
                      letterSpacing: 0.5, color: "#9aa3af", fontWeight: 700}}>
    {children}
  </th>
);
const Td = ({children, align, testid}) => (
  <td data-testid={testid}
          style={{padding: "8px 10px", textAlign: align || "left",
                      color: "#e7e7ea", verticalAlign: "middle"}}>
    {children}
  </td>
);
const btnStyle = (active) => ({
  display: "inline-flex", alignItems: "center",
  padding: "5px 10px", borderRadius: 6, fontSize: 11, fontWeight: 700,
  cursor: "pointer", border: "1px solid rgba(255,255,255,0.08)",
  background: active ? "rgba(245,158,11,0.15)" : "rgba(255,255,255,0.04)",
  color: active ? "#fbbf24" : "#e7e7ea",
});
