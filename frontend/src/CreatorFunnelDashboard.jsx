// Phase 36e Turn 2 — Creator-side Conversion Funnel Dashboard.
//
// Surfaces a 5-stage subscription funnel (visit → play → cta → trial → paid),
// a sortable per-channel breakdown, and a daily time-series (7/14/30 days).
// All numbers come from /api/podcasts/creators/:creator_id/funnel/*. Reuses
// the existing dark aesthetic from CreatorChannelSettings.
import React, {useEffect, useMemo, useState} from "react";
import axios from "axios";
import {useParams, useNavigate} from "react-router-dom";
import {LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid,
                Legend, ResponsiveContainer} from "recharts";

const API = `${process.env.REACT_APP_BACKEND_URL}/api/podcasts`;
const HDRS = () => {
  const t = localStorage.getItem("session_token");
  return t ? {Authorization: `Bearer ${t}`} : {};
};
const STAGES = [
  {key: "visits",         label: "Channel Visits", next: "plays"},
  {key: "plays",          label: "Episode Plays",   next: "cta_clicks"},
  {key: "cta_clicks", label: "CTA Clicks",          next: "trials"},
  {key: "trials",         label: "Trials Started",  next: "conversions"},
  {key: "conversions", label: "Paid Subs",         next: null},
];
const PALETTE = {visits: "#5dd6c2", plays: "#7aa5ff", cta_clicks: "#f0b95a",
                                  trials: "#d27ad8", conversions: "#ff8a6b"};

const card = {background: "#15171c", border: "1px solid rgba(255,255,255,0.06)",
                            borderRadius: 12, padding: 18};
const cardLabel = {fontSize: 10, color: "#8a93a3", textTransform: "uppercase",
                                      letterSpacing: 0.8, marginBottom: 6};

function dropoff(curr, next) {
  if (!curr || !next) return null;
  return Math.round(((curr - next) / curr) * 100);
}

function StageCard({stage, value, nextValue}) {
  const drop = stage.next ? dropoff(value, nextValue) : null;
  return (
    <div data-testid={`funnel-stage-${stage.key}`} style={{
      ...card, flex: 1, minWidth: 160,
      borderLeft: `4px solid ${PALETTE[stage.key]}`,
    }}>
      <div style={cardLabel}>{stage.label}</div>
      <div data-testid={`funnel-stage-${stage.key}-count`}
              style={{fontSize: 32, fontWeight: 800, color: "#f6f7fa"}}>
        {value.toLocaleString()}
      </div>
      {drop !== null && (
        <div data-testid={`funnel-stage-${stage.key}-dropoff`}
                style={{fontSize: 12, color: drop > 50 ? "#ff8a6b" : "#8a93a3",
                            marginTop: 4}}>
          ↓ {drop}% dropoff to next
        </div>
      )}
    </div>
  );
}

function ChannelTable({rows, onSelect}) {
  const [sortKey, setSortKey] = useState("visits");
  const [asc, setAsc] = useState(false);
  const sorted = useMemo(() => {
    const s = [...rows];
    s.sort((a, b) => (asc ? 1 : -1) *
        ((a[sortKey] || 0) - (b[sortKey] || 0)));
    return s;
  }, [rows, sortKey, asc]);
  const toggle = (k) => {
    if (sortKey === k) setAsc(!asc); else { setSortKey(k); setAsc(false); }
  };
  const head = (k, label) => (
    <th data-testid={`channel-th-${k}`}
          onClick={() => toggle(k)}
          style={{padding: "10px 12px", cursor: "pointer", textAlign: "left",
                      fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6,
                      color: sortKey === k ? "#f6f7fa" : "#8a93a3"}}>
      {label} {sortKey === k ? (asc ? "↑" : "↓") : ""}
    </th>);
  return (
    <div data-testid="channel-table" style={{...card, padding: 0,
                                                                              overflow: "hidden"}}>
      <table style={{width: "100%", borderCollapse: "collapse",
                                color: "#cfd6e4", fontSize: 13}}>
        <thead style={{background: "#1c1f26"}}>
          <tr>{head("channel_name", "Channel")}{head("visits", "Visits")}
                  {head("plays", "Plays")}{head("cta_clicks", "CTA")}
                  {head("trials", "Trials")}{head("conversions", "Paid")}
                  {head("trial_to_paid", "Convert %")}</tr>
        </thead>
        <tbody>
          {sorted.map((r) => (
            <tr key={r.channel_id} data-testid={`channel-row-${r.channel_id}`}
                  onClick={() => onSelect && onSelect(r.channel_id)}
                  style={{cursor: onSelect ? "pointer" : "default",
                              borderTop: "1px solid rgba(255,255,255,0.04)"}}>
              <td style={{padding: "10px 12px"}}>{r.channel_name}</td>
              <td style={{padding: "10px 12px"}}>{r.visits}</td>
              <td style={{padding: "10px 12px"}}>{r.plays}</td>
              <td style={{padding: "10px 12px"}}>{r.cta_clicks}</td>
              <td style={{padding: "10px 12px"}}>{r.trials}</td>
              <td style={{padding: "10px 12px"}}>{r.conversions}</td>
              <td style={{padding: "10px 12px", color: "#7aa5ff"}}>
                {(r.trial_to_paid * 100).toFixed(1)}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>);
}

function DailyChart({series}) {
  return (
    <div data-testid="funnel-daily-chart" style={card}>
      <div style={cardLabel}>Daily activity</div>
      <ResponsiveContainer width="100%" height={260}>
        <LineChart data={series} margin={{top: 8, right: 16, left: 0, bottom: 0}}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
          <XAxis dataKey="date" stroke="#8a93a3" fontSize={11} />
          <YAxis stroke="#8a93a3" fontSize={11} allowDecimals={false} />
          <Tooltip contentStyle={{background: "#15171c",
                                                            border: "1px solid #2a2d35"}} />
          <Legend wrapperStyle={{fontSize: 11, color: "#cfd6e4"}} />
          {STAGES.map(s => (
            <Line key={s.key} type="monotone" dataKey={s.key}
                      stroke={PALETTE[s.key]} strokeWidth={2} dot={false}
                      name={s.label} />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>);
}

export default function CreatorFunnelDashboard() {
  const params = useParams();
  const nav = useNavigate();
  const [creatorId, setCreatorId] = useState(params.creator_id || null);
  const [summary, setSummary] = useState(null);
  const [series, setSeries] = useState(null);
  const [days, setDays] = useState(7);
  const [err, setErr] = useState(null);

  // Resolve own creator_id if not in route params.
  useEffect(() => {
    if (creatorId) return;
    (async () => {
      try {
        const r = await axios.get(`${API}/creators/me`, {headers: HDRS()});
        if (r.data?.id) setCreatorId(r.data.id);
        else setErr("no_creator_profile");
      } catch (e) {
        setErr(e?.response?.data?.detail || "load_creator_failed");
      }
    })();
  }, [creatorId]);

  useEffect(() => {
    if (!creatorId) return;
    (async () => {
      try {
        const [s, d] = await Promise.all([
          axios.get(`${API}/creators/${creatorId}/funnel/summary?window_days=${days}`,
                              {headers: HDRS()}),
          axios.get(`${API}/creators/${creatorId}/funnel/daily?days=${days}`,
                              {headers: HDRS()}),
        ]);
        setSummary(s.data); setSeries(d.data.series); setErr(null);
      } catch (e) {
        setErr(e?.response?.data?.detail || "load_funnel_failed");
      }
    })();
  }, [creatorId, days]);

  if (err) return <div data-testid="funnel-error" style={{padding: 24,
                                              color: "#ff8a6b"}}>Error: {err}</div>;
  if (!summary) return <div data-testid="funnel-loading"
                                                          style={{padding: 24, color: "#8a93a3"}}>Loading…</div>;

  const totals = summary.overall;
  const isEmpty = STAGES.every(s => (totals[s.key] || 0) === 0);

  return (
    <div data-testid="creator-funnel-dashboard" style={{
      maxWidth: 1200, margin: "0 auto", padding: 24, color: "#cfd6e4",
      fontFamily: "Inter, -apple-system, sans-serif"}}>
      <div style={{display: "flex", justifyContent: "space-between",
                              alignItems: "center", marginBottom: 16}}>
        <div>
          <div style={{fontSize: 11, color: "#8a93a3",
                                      textTransform: "uppercase", letterSpacing: 0.8}}>
            Phase 36e · Conversion Funnel
          </div>
          <h1 style={{fontSize: 22, fontWeight: 700, color: "#f6f7fa",
                                    margin: "4px 0 0"}}>
            Subscription funnel — last {days} days
          </h1>
        </div>
        <div data-testid="funnel-range-toggle"
                style={{display: "flex", gap: 6}}>
          {[7, 14, 30].map(n => (
            <button key={n} data-testid={`funnel-range-${n}`}
                          onClick={() => setDays(n)}
                          style={{padding: "6px 14px", borderRadius: 999,
                                      background: days === n ? "#2f8fff" : "#1c1f26",
                                      color: "#f6f7fa", border: "none",
                                      cursor: "pointer", fontSize: 12}}>
              {n}d
            </button>))}
        </div>
      </div>

      {isEmpty ? (
        <div data-testid="funnel-empty-state" style={{...card,
                                              padding: 40, textAlign: "center"}}>
          <div style={{fontSize: 36, marginBottom: 8}}>📈</div>
          <div style={{fontSize: 16, fontWeight: 600, color: "#f6f7fa"}}>
            Your first {days} days will appear here
          </div>
          <div style={{fontSize: 13, color: "#8a93a3", marginTop: 6}}>
            As listeners visit your channel, play episodes, and consider
            subscribing, every step will show up in this funnel.
          </div>
        </div>
      ) : (
        <>
          <div data-testid="funnel-stage-strip"
                  style={{display: "flex", gap: 10, marginBottom: 18}}>
            {STAGES.map((s, i) => (
              <StageCard key={s.key} stage={s}
                                value={totals[s.key] || 0}
                                nextValue={s.next ? (totals[s.next] || 0) : null} />
            ))}
          </div>

          {series && <div style={{marginBottom: 18}}>
            <DailyChart series={series} />
          </div>}

          <ChannelTable rows={summary.per_channel || []}
                                    onSelect={(cid) => nav(`/creator/channels/${cid}/settings`)} />
        </>
      )}
    </div>);
}
