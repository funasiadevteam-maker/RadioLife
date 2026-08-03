/** Phase F-1 — Points pill + drawer for the listener.
 *
 *  Renders a small "balance" pill (Lucide Coins icon + number) that
 *  opens a slide-in side drawer showing balance, today's earned, top 5
 *  sources, and a paginated history of ledger entries.
 *
 *  Reads:
 *      GET /api/me/points              — summary {balance, today_earned, ...}
 *      GET /api/me/points/history     — pagination
 *
 *  The pill auto-refreshes on a 30 s tick AND on a custom
 *  `bigfm:points:refresh` event so any grant site (e.g. predict-win
 *  resolver, voucher redemption) can fire it manually without a full
 *  page reload.
 */
import React, { useCallback, useEffect, useState } from "react";
import axios from "axios";
import {
  Coins, X, Sparkles, ChevronDown, Loader2,
  Mic2, Newspaper, Trophy, Gift, Share2, MapPin,
} from "lucide-react";
import { API, useAuth } from "@/AuthContext";

// ─── source → display ──────────────────────────────────────────────
const SOURCE_META = {
  listening_minute:                    { label: "Listening",         icon: Mic2     },
  listening:                                { label: "Listening",          icon: Mic2     },
  predict_win_correct:           { label: "Predict & Win",       icon: Trophy  },
  predict_win_participate:  { label: "Predict participation", icon: Trophy  },
  game_win:                                  { label: "Games",                icon: Trophy  },
  trivia_session_complete: { label: "Trivia",                icon: Trophy  },
  trivia_multiplayer_finish: { label: "Trivia multiplayer", icon: Trophy },
  daily_login:                          { label: "Daily login",       icon: Sparkles },
  social_share:                        { label: "Sharing",                icon: Share2  },
  venue_checkin:                      { label: "Venue check-in", icon: MapPin   },
  referral_signup:                  { label: "Referral",            icon: Gift     },
  voucher_bonus:                      { label: "Voucher bonus",     icon: Gift     },
  admin_grant:                          { label: "Admin grant",        icon: Sparkles },
  admin_adjust:                        { label: "Admin adjust",      icon: Sparkles },
  reversal:                                  { label: "Reversal",            icon: Sparkles },
  onboarding:                            { label: "Onboarding",         icon: Sparkles },
  ad_save:                                  { label: "Ad save",                icon: Gift     },
  streak:                                      { label: "Streak bonus",      icon: Sparkles },
  legacy_backfill_reconciliation: { label: "Legacy reconciliation",
                                                                                          icon: Sparkles },
};
function metaFor(source) {
  return SOURCE_META[source] || { label: source, icon: Coins };
}
function fmtRel(iso) {
  if (!iso) return "";
  const t = Date.parse(iso);
  if (isNaN(t)) return "";
  const m = Math.max(1, Math.floor((Date.now() - t) / 60000));
  if (m < 60) return `${m}m`;
  if (m < 60 * 24) return `${Math.floor(m / 60)}h`;
  return `${Math.floor(m / 1440)}d`;
}

// ─── Hook: pull summary every 30s + custom event ─────────────────
function usePointsSummary() {
  const { user } = useAuth();
  const [summary, setSummary] = useState(null);
  const reload = useCallback(async () => {
    if (!user) return;
    try {
      const r = await axios.get(`${API}/me/points`,
                                                    { withCredentials: true });
      setSummary(r.data);
    } catch (e) { /* anonymous or 401 → silent */ }
  }, [user]);
  useEffect(() => {
    reload();
    const t = setInterval(reload, 30000);
    const onEvt = () => reload();
    window.addEventListener("bigfm:points:refresh", onEvt);
    return () => {
      clearInterval(t);
      window.removeEventListener("bigfm:points:refresh", onEvt);
    };
  }, [reload]);
  return { summary, reload };
}

// ─── PointsPill — compact display ────────────────────────────────
export function PointsPill({ onOpen }) {
  const { user } = useAuth();
  const { summary } = usePointsSummary();
  if (!user) return null;
  const balance = summary?.balance ?? 0;
  return (
    <button
      type="button"
      data-testid="points-pill"
      data-balance={balance}
      onClick={onOpen}
      title="Your points"
      style={{
        display: "inline-flex", alignItems: "center", gap: 6,
        background: "rgba(245, 158, 11, 0.12)",
        border: "1px solid rgba(245, 158, 11, 0.35)",
        color: "#fbbf24", padding: "5px 11px",
        borderRadius: 999, fontSize: 12, fontWeight: 600,
        fontVariantNumeric: "tabular-nums",
        cursor: "pointer", transition: "background-color 0.15s",
      }}
    >
      <Coins size={13} />
      <span data-testid="points-pill-balance">{balance.toLocaleString()}</span>
    </button>
  );
}

// ─── PointsDrawer — slide-in side panel ────────────────────────────
export function PointsDrawer({ open, onClose }) {
  const { user } = useAuth();
  const { summary } = usePointsSummary();
  const [history, setHistory] = useState([]);
  const [cursor, setCursor] = useState(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [initialLoaded, setInitialLoaded] = useState(false);

  const loadInitial = useCallback(async () => {
    if (!user || !open) return;
    setInitialLoaded(false);
    try {
      const r = await axios.get(`${API}/me/points/history?limit=20`,
                                                    { withCredentials: true });
      setHistory(r.data?.items || []);
      setCursor(r.data?.next_cursor || null);
    } catch (e) { setHistory([]); }
    setInitialLoaded(true);
  }, [user, open]);

  useEffect(() => { if (open) loadInitial(); }, [open, loadInitial]);

  const loadMore = async () => {
    if (!cursor || loadingMore) return;
    setLoadingMore(true);
    try {
      const r = await axios.get(`${API}/me/points/history`, {
        params: { limit: 20, cursor },
        withCredentials: true,
      });
      setHistory((h) => [...h, ...(r.data?.items || [])]);
      setCursor(r.data?.next_cursor || null);
    } catch (e) { /* silent */ }
    setLoadingMore(false);
  };

  if (!open) return null;

  const balance       = summary?.balance ?? 0;
  const todayEarned = summary?.today_earned ?? 0;
  const weekEarned  = summary?.this_week_earned ?? 0;
  const topSources = summary?.top_sources || [];
  const topMax        = Math.max(1, ...topSources.map((s) => s.total));

  return (
    <>
      {/* Backdrop */}
      <div
        data-testid="points-drawer-backdrop"
        onClick={onClose}
        style={{
          position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)",
          zIndex: 60,
        }}
      />
      {/* Panel */}
      <aside
        data-testid="points-drawer"
        style={{
          position: "fixed", top: 0, right: 0, height: "100vh",
          width: "min(420px, 90vw)", background: "#0b0b12",
          borderLeft: "1px solid #1f1f28", zIndex: 61,
          display: "flex", flexDirection: "column",
          boxShadow: "-30px 0 80px rgba(0,0,0,0.5)",
        }}
      >
        <header style={{
          padding: "16px 18px", borderBottom: "1px solid #1f1f28",
          display: "flex", justifyContent: "space-between", alignItems: "center",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <Coins size={20} color="#fbbf24" />
            <div style={{ color: "#fff", fontSize: 16, fontWeight: 600 }}>
              Your Points
            </div>
          </div>
          <button data-testid="points-drawer-close" onClick={onClose}
                          style={{ background: "transparent", border: 0,
                                      color: "#9aa3af", cursor: "pointer", padding: 4 }}>
            <X size={18} />
          </button>
        </header>

        <div style={{ padding: 18, overflowY: "auto", flex: 1 }}>
          {/* Balance hero */}
          <div data-testid="points-drawer-hero"
                style={{ marginBottom: 18 }}>
            <div style={{ fontSize: 11, color: "#9aa3af",
                                      textTransform: "uppercase", letterSpacing: 1.3 }}>
              Balance
            </div>
            <div style={{ fontSize: 42, color: "#fbbf24",
                                      fontWeight: 700, fontVariantNumeric: "tabular-nums",
                                      lineHeight: 1.1 }}
                      data-testid="points-drawer-balance">
              {balance.toLocaleString()}
            </div>
            <div style={{ marginTop: 6, fontSize: 12, color: "#cbd5e1" }}>
              <span data-testid="points-drawer-today">
                Today: <strong style={{ color: "#4ade80" }}>+{todayEarned}</strong>
              </span>
              <span style={{ marginLeft: 14 }}>
                This week: <strong style={{ color: "#4ade80" }}>+{weekEarned}</strong>
              </span>
            </div>
          </div>

          {/* Top sources */}
          {topSources.length > 0 && (
            <section data-testid="points-drawer-top-sources"
                              style={{ marginBottom: 22 }}>
              <h3 style={{ fontSize: 11, color: "#9aa3af",
                                          textTransform: "uppercase", letterSpacing: 1.3,
                                          marginBottom: 8 }}>
                Top sources lifetime
              </h3>
              {topSources.map((s) => {
                const m = metaFor(s.source);
                const Ic = m.icon;
                const pct = Math.round((s.total / topMax) * 100);
                return (
                  <div key={s.source} style={{ marginBottom: 8 }}>
                    <div style={{ display: "flex",
                                              justifyContent: "space-between",
                                              fontSize: 12, color: "#cbd5e1",
                                              marginBottom: 3 }}>
                      <span style={{ display: "inline-flex",
                                                gap: 5, alignItems: "center" }}>
                        <Ic size={11} />{m.label}
                      </span>
                      <span style={{ fontVariantNumeric: "tabular-nums",
                                                fontWeight: 600 }}>
                        +{s.total.toLocaleString()}
                      </span>
                    </div>
                    <div style={{ height: 4, background: "#1f1f28",
                                              borderRadius: 2 }}>
                      <div style={{ width: `${pct}%`, height: "100%",
                                                background: "#fbbf24",
                                                borderRadius: 2 }} />
                    </div>
                  </div>
                );
              })}
            </section>
          )}

          {/* History list */}
          <section data-testid="points-drawer-history">
            <h3 style={{ fontSize: 11, color: "#9aa3af",
                                      textTransform: "uppercase", letterSpacing: 1.3,
                                      marginBottom: 8 }}>
              Recent activity
            </h3>
            {!initialLoaded && (
              <div style={{ color: "#9aa3af", padding: 20,
                                          textAlign: "center", fontSize: 12 }}
                      data-testid="points-drawer-loading">
                Loading…
              </div>
            )}
            {initialLoaded && history.length === 0 && (
              <div data-testid="points-drawer-empty"
                        style={{ color: "#9aa3af", padding: 20,
                                      textAlign: "center", fontSize: 12,
                                      border: "1px dashed #25252f",
                                      borderRadius: 8 }}>
                Earn points by predicting, playing, listening, sharing.
              </div>
            )}
            {history.map((h) => {
              const m = metaFor(h.source);
              const Ic = m.icon;
              const positive = (h.delta || 0) > 0;
              return (
                <div
                  key={h.entry_id || h._id}
                  data-testid={`points-history-row-${h.entry_id || h._id}`}
                  data-source={h.source}
                  style={{
                    display: "flex", justifyContent: "space-between",
                    alignItems: "center", padding: "8px 10px",
                    borderBottom: "1px solid #16161f",
                  }}>
                  <div style={{ display: "flex", gap: 10,
                                            alignItems: "center", minWidth: 0 }}>
                    <Ic size={14} color={positive ? "#4ade80" : "#f87171"} />
                    <div style={{ minWidth: 0 }}>
                      <div style={{ color: "#fff", fontSize: 13,
                                                  fontWeight: 500 }}>
                        {m.label}
                      </div>
                      {h.metadata?.note && (
                        <div style={{ color: "#9aa3af", fontSize: 11,
                                                    overflow: "hidden",
                                                    textOverflow: "ellipsis",
                                                    whiteSpace: "nowrap" }}>
                          {h.metadata.note}
                        </div>
                      )}
                    </div>
                  </div>
                  <div style={{ textAlign: "right", flexShrink: 0,
                                            marginLeft: 8 }}>
                    <div style={{ color: positive ? "#4ade80" : "#f87171",
                                              fontWeight: 600, fontSize: 13,
                                              fontVariantNumeric: "tabular-nums" }}>
                      {positive ? "+" : ""}{(h.delta || 0).toLocaleString()}
                    </div>
                    <div style={{ color: "#666", fontSize: 10,
                                              fontFamily: "monospace" }}>
                      {fmtRel(h.created_at)}
                    </div>
                  </div>
                </div>
              );
            })}
            {cursor && (
              <button
                onClick={loadMore}
                data-testid="points-drawer-load-more"
                disabled={loadingMore}
                style={{
                  width: "100%", marginTop: 10, padding: "8px 12px",
                  background: "#1f1f28", border: "1px solid #25252f",
                  color: "#cbd5e1", borderRadius: 6, cursor: "pointer",
                  fontSize: 12, display: "inline-flex", justifyContent: "center",
                  alignItems: "center", gap: 6,
                }}
              >
                {loadingMore
                  ? <Loader2 size={12} className="spin" />
                  : <ChevronDown size={12} />}
                Load more
              </button>
            )}
          </section>
        </div>
      </aside>
    </>
  );
}

// ─── PointsHeaderWidget — pill + drawer combined ───────────────────
export default function PointsHeaderWidget() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <PointsPill onOpen={() => setOpen(true)} />
      <PointsDrawer open={open} onClose={() => setOpen(false)} />
    </>
  );
}
