/**
 * Phase PDX.1 — Admin panel for the Predexon auto-curator.
 *
 * Shows:
 *   - Curator status row (enabled + counts by category + next run)
 *   - Table of currently active auto-imported campaigns
 *   - Actions: Run curator now, Pause / Resume, edit points inline,
 *     open the Polymarket source URL
 *
 * Rendered inside `Admin/PredictWinCampaigns.jsx` above the status
 * filter chips.
 */
import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import {
  Sparkles, Play, Pause, RefreshCw, ExternalLink, Loader2,
  Zap, PenSquare, Check, X,
} from "lucide-react";

const API_BASE = process.env.REACT_APP_BACKEND_URL;
const CURATOR_API = `${API_BASE}/api/admin/pdx-curator`;
const CAMPAIGN_POINTS_API = `${API_BASE}/api/admin/predict-win/campaigns`;

const CAT_LABELS = {
  sports_top:         "Sports",
  stocks_top:         "Stocks",
  us_politics:        "US Politics",
  national_games: "Games",
};
const CAT_COLORS = {
  sports_top:         "#22d3ee",
  stocks_top:         "#22c55e",
  us_politics:        "#a855f7",
  national_games: "#f59e0b",
};

async function _api(method, url, body) {
  return axios({ method, url, data: body, withCredentials: true })
    .then((r) => r.data)
    .catch((e) => {
      const d = e?.response?.data?.detail;
      const msg = typeof d === "string" ? d : d?.message || d?.code || e.message;
      throw new Error(msg || "Request failed");
    });
}

function fmtWhen(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString(undefined,
      { dateStyle: "short", timeStyle: "short" });
  } catch { return String(iso); }
}

export default function PdxAutoCuratedPanel() {
  const [status, setStatus] = useState(null);
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [toggling, setToggling] = useState(false);
  const [catFilter, setCatFilter] = useState("");
  const [editing, setEditing] = useState(null);    // campaign_id being edited
  const [pointsInput, setPointsInput] = useState("");

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const s = await _api("GET", `${CURATOR_API}/status`);
      setStatus(s);
      const url = catFilter
        ? `${CURATOR_API}/active-events?category_slug=${catFilter}`
        : `${CURATOR_API}/active-events`;
      const e = await _api("GET", url);
      setEvents(e.items || []);
    } catch (err) {
      toast.error(err.message || "Failed to load curator status");
    } finally { setLoading(false); }
  }, [catFilter]);

  useEffect(() => { refresh(); }, [refresh]);

  const runNow = async () => {
    setRunning(true);
    try {
      const r = await _api("POST", `${CURATOR_API}/run-now`);
      const created = Object.values(r?.per_category || {})
        .reduce((a, v) => a + (v?.created || 0), 0);
      toast.success(`Curator tick complete · imported ${created} new`);
      await refresh();
    } catch (err) {
      toast.error(err.message || "Curator run failed");
    } finally { setRunning(false); }
  };

  const togglePause = async () => {
    if (!status) return;
    setToggling(true);
    try {
      const next = !status.enabled;
      const r = await _api("PATCH", `${CURATOR_API}/settings`,
        { enabled: next });
      toast.success(r.settings?.enabled
        ? "Auto-import RESUMED" : "Auto-import PAUSED");
      await refresh();
    } catch (err) {
      toast.error(err.message || "Failed to toggle curator");
    } finally { setToggling(false); }
  };

  const beginEdit = (row) => {
    setEditing(row.campaign_id);
    setPointsInput(String(row.points_reward));
  };

  const cancelEdit = () => { setEditing(null); setPointsInput(""); };

  const saveEdit = async (row) => {
    const n = parseInt(pointsInput, 10);
    if (!Number.isFinite(n) || n < 10 || n > 100) {
      toast.error("Points must be an integer between 10 and 100");
      return;
    }
    try {
      await _api("PATCH", `${CAMPAIGN_POINTS_API}/${row.campaign_id}/points`,
        { points_reward: n });
      toast.success("Points updated");
      cancelEdit();
      await refresh();
    } catch (err) {
      toast.error(err.message || "Failed to update points");
    }
  };

  return (
    <section data-testid="admin-pdx-curator-panel"
                    style={{
                      marginBottom: 22, padding: 16, borderRadius: 10,
                      background: "linear-gradient(180deg,#0d1220 0%,#0a0b12 100%)",
                      border: "1px solid rgba(168,85,247,0.20)",
                    }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center",
                                justifyContent: "space-between", gap: 12,
                                marginBottom: 12, flexWrap: "wrap" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{ width: 34, height: 34, borderRadius: 8,
                                    background: "linear-gradient(135deg,#a855f7,#ec4899)",
                                    display: "flex", alignItems: "center",
                                    justifyContent: "center" }}>
            <Sparkles size={16} color="#0a0a0c" />
          </div>
          <div>
            <div style={{ fontSize: 10, letterSpacing: 0.8,
                                        color: "#c4b5fd" }}>
              PHASE PDX.1 · AUTOMATED CURATOR
            </div>
            <h2 data-testid="admin-pdx-title"
                    style={{ margin: "3px 0 0", fontSize: 16,
                                    color: "#e7e7ea" }}>
              Auto-Curated Events
            </h2>
          </div>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button data-testid="admin-pdx-toggle-pause"
                          onClick={togglePause}
                          disabled={toggling || !status}
                          style={{
                            display: "inline-flex", alignItems: "center", gap: 6,
                            padding: "7px 12px", fontSize: 12, borderRadius: 8,
                            border: "1px solid rgba(255,255,255,0.14)",
                            background: status?.enabled
                              ? "rgba(239,68,68,0.10)" : "rgba(34,197,94,0.10)",
                            color: status?.enabled ? "#fca5a5" : "#86efac",
                            cursor: toggling ? "wait" : "pointer",
                          }}>
            {toggling ? <Loader2 size={13} className="spin" />
                                : status?.enabled ? <Pause size={13} /> : <Play size={13} />}
            {status?.enabled ? "Pause auto-import" : "Resume auto-import"}
          </button>
          <button data-testid="admin-pdx-run-now"
                          onClick={runNow}
                          disabled={running || !status?.enabled}
                          style={{
                            display: "inline-flex", alignItems: "center", gap: 6,
                            padding: "7px 12px", fontSize: 12, borderRadius: 8,
                            border: "1px solid rgba(168,85,247,0.40)",
                            background: "rgba(168,85,247,0.18)",
                            color: "#c4b5fd",
                            cursor: running ? "wait" : "pointer",
                            opacity: !status?.enabled ? 0.5 : 1,
                          }}>
            {running ? <Loader2 size={13} className="spin" /> : <Zap size={13} />}
            {running ? "Running…" : "Run curator now"}
          </button>
        </div>
      </div>

      {/* Status counts */}
      <div data-testid="admin-pdx-counts"
                style={{ display: "grid",
                            gridTemplateColumns: "repeat(auto-fit, minmax(120px,1fr))",
                            gap: 8, marginBottom: 14 }}>
        {["sports_top","stocks_top","us_politics","national_games"].map((k) => (
          <button key={k}
                          data-testid={`admin-pdx-cat-${k}`}
                          onClick={() => setCatFilter(catFilter === k ? "" : k)}
                          style={{
                            textAlign: "left", padding: "8px 10px",
                            borderRadius: 8, cursor: "pointer",
                            border: `1px solid ${catFilter === k ? CAT_COLORS[k] : "rgba(255,255,255,0.08)"}`,
                            background: catFilter === k
                              ? `${CAT_COLORS[k]}22`
                              : "rgba(255,255,255,0.03)",
                          }}>
            <div style={{ fontSize: 10, color: "#9aa3af",
                                        textTransform: "uppercase", letterSpacing: 0.6 }}>
              {CAT_LABELS[k]}
            </div>
            <div style={{ fontSize: 20, color: CAT_COLORS[k],
                                        fontWeight: 700, lineHeight: 1.1 }}>
              {status?.active_by_category?.[k] ?? "—"}
            </div>
          </button>
        ))}
        <div style={{ padding: "8px 10px", borderRadius: 8,
                                background: "rgba(255,255,255,0.03)",
                                border: "1px solid rgba(255,255,255,0.08)" }}>
          <div style={{ fontSize: 10, color: "#9aa3af",
                                    textTransform: "uppercase", letterSpacing: 0.6 }}>
            Total active
          </div>
          <div data-testid="admin-pdx-total-active"
                    style={{ fontSize: 20, color: "#e7e7ea",
                                    fontWeight: 700, lineHeight: 1.1 }}>
            {status?.active_total ?? "—"}
          </div>
        </div>
        <div style={{ padding: "8px 10px", borderRadius: 8,
                                background: "rgba(255,255,255,0.03)",
                                border: "1px solid rgba(255,255,255,0.08)" }}>
          <div style={{ fontSize: 10, color: "#9aa3af",
                                    textTransform: "uppercase", letterSpacing: 0.6 }}>
            Cadence
          </div>
          <div style={{ fontSize: 12, color: "#e7e7ea",
                                    lineHeight: 1.4, marginTop: 3 }}>
            every {status?.interval_min ?? "—"}m<br/>
            <span style={{ fontSize: 10, color: "#9aa3af" }}>
              next {fmtWhen(status?.next_run_at)}
            </span>
          </div>
        </div>
      </div>

      {/* Filter reset chip */}
      {catFilter && (
        <div style={{ display: "flex", alignItems: "center", gap: 6,
                                    marginBottom: 8, fontSize: 11, color: "#9aa3af" }}>
          <span>Filtering by:</span>
          <span style={{ padding: "2px 8px", borderRadius: 12,
                                        background: `${CAT_COLORS[catFilter]}22`,
                                        color: CAT_COLORS[catFilter], fontWeight: 600 }}>
            {CAT_LABELS[catFilter]}
          </span>
          <button data-testid="admin-pdx-clear-filter"
                          onClick={() => setCatFilter("")}
                          style={{ background: "transparent", border: 0,
                                            color: "#71717a", cursor: "pointer",
                                            display: "inline-flex", alignItems: "center", gap: 2 }}>
            <X size={11} /> clear
          </button>
        </div>
      )}

      {/* Events table */}
      <div data-testid="admin-pdx-events-table"
                style={{ border: "1px solid rgba(255,255,255,0.06)",
                            borderRadius: 8, overflow: "hidden" }}>
        <div style={{ display: "grid",
                                gridTemplateColumns: "1.6fr 0.7fr 0.6fr 0.9fr 0.5fr",
                                padding: "8px 12px",
                                background: "rgba(255,255,255,0.04)",
                                fontSize: 10, textTransform: "uppercase",
                                letterSpacing: 0.6, color: "#9aa3af" }}>
          <div>Title</div>
          <div>Category</div>
          <div>Points</div>
          <div>Lock time</div>
          <div style={{ textAlign: "right" }}>Actions</div>
        </div>
        {loading ? (
          <div style={{ padding: 16, textAlign: "center", color: "#71717a" }}>
            <Loader2 size={16} className="spin" />
          </div>
        ) : events.length === 0 ? (
          <div data-testid="admin-pdx-empty"
                    style={{ padding: 20, textAlign: "center",
                                    color: "#71717a", fontSize: 12 }}>
            No active auto-imported events yet.
            Try&nbsp;
            <button onClick={runNow}
                        style={{ background: "transparent", border: 0,
                                        color: "#c4b5fd", cursor: "pointer",
                                        textDecoration: "underline" }}>
              running the curator
            </button>.
          </div>
        ) : events.map((row) => {
          const catCol = CAT_COLORS[row.category_slug] || "#71717a";
          const isEditing = editing === row.campaign_id;
          return (
            <div key={row.campaign_id}
                      data-testid={`admin-pdx-row-${row.campaign_id}`}
                      style={{ display: "grid",
                                          gridTemplateColumns: "1.6fr 0.7fr 0.6fr 0.9fr 0.5fr",
                                          padding: "10px 12px", alignItems: "center",
                                          fontSize: 12, color: "#e7e7ea",
                                          borderTop: "1px solid rgba(255,255,255,0.04)" }}>
              <div style={{ overflow: "hidden", textOverflow: "ellipsis",
                                          whiteSpace: "nowrap", paddingRight: 8 }}
                        title={row.title}>
                {row.title}
              </div>
              <div>
                <span style={{ fontSize: 10, fontWeight: 700,
                                            padding: "2px 8px", borderRadius: 999,
                                            background: `${catCol}22`, color: catCol,
                                            letterSpacing: 0.6 }}>
                  {CAT_LABELS[row.category_slug] || row.category_slug}
                </span>
              </div>
              <div>
                {isEditing ? (
                  <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
                    <input data-testid={`admin-pdx-points-input-${row.campaign_id}`}
                                    type="number" min={10} max={100}
                                    value={pointsInput}
                                    onChange={(e) => setPointsInput(e.target.value)}
                                    style={{ width: 56, padding: "3px 6px",
                                                    fontSize: 12, borderRadius: 4,
                                                    background: "#111",
                                                    border: "1px solid rgba(255,255,255,0.15)",
                                                    color: "#e7e7ea" }} />
                    <button data-testid={`admin-pdx-points-save-${row.campaign_id}`}
                                    onClick={() => saveEdit(row)}
                                    style={{ background: "transparent", border: 0,
                                                    cursor: "pointer", color: "#22c55e" }}>
                      <Check size={13} />
                    </button>
                    <button onClick={cancelEdit}
                                    style={{ background: "transparent", border: 0,
                                                    cursor: "pointer", color: "#71717a" }}>
                      <X size={12} />
                    </button>
                  </div>
                ) : (
                  <button data-testid={`admin-pdx-points-edit-${row.campaign_id}`}
                                    onClick={() => beginEdit(row)}
                                    style={{ display: "inline-flex", alignItems: "center", gap: 4,
                                                    background: "transparent", border: 0, cursor: "pointer",
                                                    color: "#c4b5fd", fontSize: 12, fontWeight: 600 }}>
                    +{row.points_reward} pts <PenSquare size={11} color="#71717a" />
                  </button>
                )}
              </div>
              <div style={{ color: "#9aa3af", fontSize: 11 }}>
                {fmtWhen(row.lock_time)}
              </div>
              <div style={{ textAlign: "right" }}>
                {row.external_market_url && (
                  <a href={row.external_market_url}
                        target="_blank" rel="noopener noreferrer"
                        data-testid={`admin-pdx-source-${row.campaign_id}`}
                        title="Open on Polymarket"
                        style={{ color: "#71717a", display: "inline-flex",
                                        alignItems: "center" }}>
                    <ExternalLink size={12} />
                  </a>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Refresh footer */}
      <div style={{ display: "flex", justifyContent: "space-between",
                                alignItems: "center", marginTop: 10 }}>
        <div style={{ fontSize: 10, color: "#71717a" }}>
          Data source: Predexon (Polymarket proxy).
          Last tick: {fmtWhen(status?.last_run_at)}.
        </div>
        <button data-testid="admin-pdx-refresh"
                        onClick={refresh}
                        style={{ background: "transparent", border: 0, cursor: "pointer",
                                        color: "#9aa3af", display: "inline-flex",
                                        alignItems: "center", gap: 4, fontSize: 11 }}>
          <RefreshCw size={11} /> Refresh
        </button>
      </div>
    </section>
  );
}
