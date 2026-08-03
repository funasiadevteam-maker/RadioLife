// Phase 8c — Admin analytics + inventory pages.
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { ChevronLeft, BarChart3, Loader2, Trophy, Download,
            AlertTriangle, Wrench, RefreshCw, CheckCircle2 } from "lucide-react";
import { toast, Toaster } from "sonner";
import { useAuth, API } from "@/AuthContext";
import "./PlayAndWin.css";


export function AdminGamesAnalytics() {
  const [metric, setMetric] = useState("plays");
  const [window, setWindow] = useState("7d");
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    axios.get(`${API}/games_v2/admin/leaderboard`,
                  {params: {metric, window, limit: 50}})
      .then((r) => setItems(r.data.items || []))
      .catch(() => toast.error("Failed to load leaderboard"))
      .finally(() => setLoading(false));
  }, [metric, window]);

  return (
    <div className="advgames-wrap" data-testid="admin-games-analytics-page">
      <Toaster theme="dark" position="bottom-right" richColors />
      <header className="paw-header">
        <div>
          <Link to="/admin/games-approval" className="paw-back">
            <ChevronLeft size={14} /> back
          </Link>
          <h1><BarChart3 size={18} /> Games analytics</h1>
          <p className="sub">Platform-wide leaderboard across all campaigns.</p>
        </div>
        <div className="analytics-controls">
          <select className="leads-filter mono"
                     value={metric}
                     onChange={(e) => setMetric(e.target.value)}
                     data-testid="admin-analytics-metric">
            <option value="plays">Plays</option>
            <option value="wins">Wins</option>
            <option value="saves">Saves</option>
            <option value="redemptions">Redemptions</option>
            <option value="completion_rate">Completion rate</option>
          </select>
          <select className="leads-filter mono"
                     value={window}
                     onChange={(e) => setWindow(e.target.value)}
                     data-testid="admin-analytics-window">
            <option value="24h">Last 24h</option>
            <option value="7d">Last 7 days</option>
            <option value="30d">Last 30 days</option>
          </select>
        </div>
      </header>
      {loading ? <div className="paw-loading"><Loader2 size={28} className="spin" /></div>
        : items.length === 0 ? <div className="paw-empty">No data in window.</div>
        : <table className="advgames-table" data-testid="admin-analytics-table">
            <thead><tr>
              <th>#</th><th>Campaign</th><th>Status</th><th>{metric}</th>
              {metric === "completion_rate" && <><th>Starts</th><th>Wins</th></>}
            </tr></thead>
            <tbody>
              {items.map((it) => (
                <tr key={it.campaign_id}
                      data-testid={`admin-leaderboard-row-${it.campaign_id}`}>
                  <td className="mono">#{it.rank}</td>
                  <td>{it.title}</td>
                  <td><span className="status-pill mono">{it.status}</span></td>
                  <td className="mono">
                    {metric === "completion_rate"
                      ? `${(it.value * 100).toFixed(1)}%`
                      : it.value.toLocaleString()}
                  </td>
                  {metric === "completion_rate" && (
                    <>
                      <td className="mono dim">{it.starts}</td>
                      <td className="mono dim">{it.wins}</td>
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </table>}
    </div>
  );
}


export function AdminGamesInventory() {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);

  useEffect(() => { load(); }, []);

  const load = async () => {
    setLoading(true);
    try {
      const r = await axios.get(
        `${API}/games_v2/admin/inventory_reconcile_alerts`);
      setAlerts(r.data.items || []);
    } catch (_e) { toast.error("Failed to load alerts"); }
    finally { setLoading(false); }
  };

  const runScan = async () => {
    setScanning(true);
    try {
      const r = await axios.post(
        `${API}/games_v2/admin/inventory_reconcile/run_daily_scan`);
      toast.success(`Scan ran: ${r.data.alerts_generated} alerts`);
      load();
    } catch (_e) { toast.error("Scan failed"); }
    finally { setScanning(false); }
  };

  const force = async (cid) => {
    if (!window.confirm("Force-correct inventory for this campaign?")) return;
    try {
      const r = await axios.post(
        `${API}/games_v2/admin/inventory_reconcile/${cid}/force_correct`);
      toast.success(`Corrected ${r.data.corrected} prizes`);
      load();
    } catch (_e) { toast.error("Force correct failed"); }
  };

  return (
    <div className="advgames-wrap" data-testid="admin-games-inventory-page">
      <Toaster theme="dark" position="bottom-right" richColors />
      <header className="paw-header">
        <div>
          <Link to="/admin/games-approval" className="paw-back">
            <ChevronLeft size={14} /> back
          </Link>
          <h1><Wrench size={18} /> Inventory reconciler</h1>
          <p className="sub">Detects ledger drift across active campaigns.
              Run the scan manually or wait for the daily sweep.</p>
        </div>
        <button className="lobbies-host-btn"
                   onClick={runScan} disabled={scanning}
                   data-testid="admin-inventory-scan-btn">
          {scanning
            ? <><Loader2 size={14} className="spin" /> scanning…</>
            : <><RefreshCw size={14} /> run scan now</>}
        </button>
      </header>
      {loading ? <div className="paw-loading"><Loader2 size={28} className="spin" /></div>
        : alerts.length === 0 ? <div className="paw-empty" data-testid="inventory-empty">
            <CheckCircle2 size={32} /> All campaigns reconciled.
          </div>
        : <div className="inventory-alerts" data-testid="inventory-alerts">
            {alerts.map((a) => (
              <div key={a.campaign_id} className="inventory-alert-card"
                       data-testid={`inventory-alert-${a.campaign_id}`}>
                <div className="ia-head">
                  <AlertTriangle size={16} />
                  <span className="ia-cid mono">{a.campaign_id}</span>
                  <span className="dim mono small">
                    {a.ts?.slice(0, 16).replace("T", " ")}
                  </span>
                  <button className="ghost-btn"
                            onClick={() => force(a.campaign_id)}
                            data-testid={`inventory-fix-btn-${a.campaign_id}`}>
                    <Wrench size={12} /> force correct
                  </button>
                </div>
                <table className="ia-table">
                  <thead><tr><th>Prize</th><th>Stored</th><th>Expected</th><th>Δ</th></tr></thead>
                  <tbody>
                    {(a.discrepancies || []).map((d) => (
                      <tr key={d.prize_id}>
                        <td>{d.title}</td>
                        <td className="mono">{d.inventory_remaining_stored}</td>
                        <td className="mono">{d.inventory_remaining_expected}</td>
                        <td className={`mono ${d.delta > 0 ? "delta-pos" : "delta-neg"}`}>
                          {d.delta > 0 ? "+" : ""}{d.delta}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
          </div>}
    </div>
  );
}
