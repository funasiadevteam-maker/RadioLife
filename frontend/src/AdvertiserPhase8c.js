// Phase 8c — Advertiser dashboard tabs: Leads, Webhooks, Top campaigns
// Mounted at /advertiser/games-insights and from the campaigns dashboard
// as 3 inline tabs.
import { useEffect, useState } from "react";
import axios from "axios";
import { toast, Toaster } from "sonner";
import { Loader2, Webhook, Send, RefreshCw, Trash2, Download,
            Plus, Copy, ChevronRight, BarChart3, Trophy, Users } from "lucide-react";
import { useAuth, API } from "@/AuthContext";
import { Link, useNavigate, useParams } from "react-router-dom";
import "./PlayAndWin.css";


export function LeadsPanel({ campaignId }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [outcome, setOutcome] = useState("");

  useEffect(() => { load(); }, [campaignId, outcome]); // eslint-disable-line

  const load = async () => {
    setLoading(true);
    try {
      const params = {limit: 100};
      if (outcome) params.outcome = outcome;
      const r = await axios.get(
        `${API}/games_v2/advertiser/campaigns/${campaignId}/leads`,
        {params});
      setItems(r.data.items || []);
    } catch (e) {
      toast.error("Failed to load leads");
    } finally {
      setLoading(false);
    }
  };

  const downloadCsv = () => {
    const url = `${API}/games_v2/advertiser/campaigns/${campaignId}/leads.csv`
      + (outcome ? `?outcome=${outcome}` : "");
    window.open(url, "_blank");
  };

  return (
    <div className="leads-panel" data-testid="advertiser-leads-panel"
            data-campaign-id={campaignId}>
      <div className="panel-toolbar">
        <h3><Users size={16} /> Leads</h3>
        <select className="leads-filter mono"
                   value={outcome}
                   onChange={(e) => setOutcome(e.target.value)}
                   data-testid="leads-outcome-filter">
          <option value="">All outcomes</option>
          <option value="game_completed">Game completed</option>
          <option value="game_won">Game won</option>
          <option value="game_lost">Game lost</option>
          <option value="abandoned">Abandoned</option>
        </select>
        <button className="leads-csv-btn" onClick={downloadCsv}
                   data-testid="leads-csv-btn">
          <Download size={12} /> CSV
        </button>
      </div>
      {loading ? <div className="paw-loading"><Loader2 size={20} className="spin" /></div>
        : items.length === 0 ? <div className="leads-empty" data-testid="leads-empty">
            No leads yet for this campaign.
          </div>
        : <table className="leads-table" data-testid="leads-table">
            <thead><tr>
              <th>Submitted</th><th>Email</th><th>Other fields</th>
              <th>Outcome</th><th>Consent</th>
            </tr></thead>
            <tbody>
              {items.map((it) => {
                const fd = it.form_data || {};
                const email = fd.email || "(no email)";
                const other = Object.entries(fd)
                  .filter(([k]) => k !== "email")
                  .map(([k, v]) => `${k}: ${v}`).join(", ");
                return (
                  <tr key={it.submission_id}
                        data-testid={`lead-row-${it.submission_id}`}>
                    <td className="mono dim">
                      {it.submitted_at?.slice(0, 16).replace("T", " ")}
                    </td>
                    <td>{email}</td>
                    <td className="dim small">{other || "—"}</td>
                    <td><span className="status-pill mono">{it.outcome}</span></td>
                    <td className="mono">{it.consent_accepted ? "✓" : "—"}</td>
                  </tr>);
              })}
            </tbody>
          </table>}
    </div>
  );
}


export function WebhooksPanel() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [url, setUrl] = useState("");
  const [events, setEvents] = useState(["lead_submitted", "game_completed"]);
  const [reveal, setReveal] = useState(null);
  const [deliveries, setDeliveries] = useState({});

  const EVENT_OPTIONS = [
    "lead_submitted", "game_started", "game_completed",
    "prize_won", "prize_claimed", "prize_redeemed", "test_ping",
  ];

  useEffect(() => { load(); }, []);

  const load = async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/games_v2/advertiser/webhooks`);
      setItems(r.data.items || []);
    } catch (_e) { toast.error("Failed to load webhooks"); }
    finally { setLoading(false); }
  };

  const register = async () => {
    if (!url) return;
    setCreating(true);
    try {
      const r = await axios.post(`${API}/games_v2/advertiser/webhooks`,
                                          {url, events_subscribed: events});
      setReveal(r.data);
      setUrl("");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Registration failed");
    } finally { setCreating(false); }
  };

  const sendTest = async (eid) => {
    try {
      const r = await axios.post(
        `${API}/games_v2/advertiser/webhooks/${eid}/test`);
      const ok = r.data?.delivery_result?.success;
      if (ok) toast.success(`test_ping delivered (${r.data.delivery_result.status_code})`);
      else toast.error("test_ping failed; see deliveries");
      loadDeliveries(eid);
    } catch (_e) { toast.error("Test ping failed"); }
  };

  const rotate = async (eid) => {
    try {
      const r = await axios.post(
        `${API}/games_v2/advertiser/webhooks/${eid}/rotate_secret`);
      setReveal(r.data);
    } catch (_e) { toast.error("Rotate failed"); }
  };

  const del = async (eid) => {
    if (!window.confirm("Delete this webhook endpoint?")) return;
    try {
      await axios.delete(`${API}/games_v2/advertiser/webhooks/${eid}`);
      load();
    } catch (_e) { toast.error("Delete failed"); }
  };

  const loadDeliveries = async (eid) => {
    try {
      const r = await axios.get(
        `${API}/games_v2/advertiser/webhooks/${eid}/deliveries?limit=10`);
      setDeliveries((d) => ({...d, [eid]: r.data.items}));
    } catch (_e) { /* */ }
  };

  return (
    <div className="webhooks-panel" data-testid="webhooks-panel">
      <Toaster theme="dark" position="bottom-right" richColors />
      <div className="panel-toolbar">
        <h3><Webhook size={16} /> Webhook endpoints</h3>
      </div>
      <div className="webhook-create" data-testid="webhook-create-form">
        <input className="lead-input" type="url"
                  placeholder="https://your-server.com/webhook"
                  value={url} onChange={(e) => setUrl(e.target.value)}
                  data-testid="webhook-url-input" />
        <div className="webhook-events-grid">
          {EVENT_OPTIONS.map((ev) => (
            <label key={ev} className="webhook-event-chip mono"
                      data-active={events.includes(ev)}>
              <input type="checkbox" checked={events.includes(ev)}
                        onChange={() => setEvents((e) =>
                          e.includes(ev) ? e.filter((x) => x !== ev) : [...e, ev])} />
              {ev}
            </label>
          ))}
        </div>
        <button className="lead-submit" onClick={register}
                  disabled={creating || !url || events.length === 0}
                  data-testid="webhook-register-btn">
          {creating ? <><Loader2 size={14} className="spin" /> Registering…</>
            : <><Plus size={14} /> Register endpoint</>}
        </button>
      </div>

      {reveal && (
        <div className="secret-reveal" data-testid="webhook-secret-reveal">
          <div className="mono dim">SIGNING SECRET (shown ONCE)</div>
          <div className="secret-value mono">{reveal.raw_secret}</div>
          <div className="secret-help">
            Sign each receiver-side with HMAC-SHA256 of
            <code>{`<timestamp>.<body>`}</code>. Headers:
            <code>X-FUUSIC-Signature</code>, <code>X-FUUSIC-Timestamp</code>.
          </div>
          <button className="lead-submit" onClick={() => {
            navigator.clipboard.writeText(reveal.raw_secret);
            toast.success("Copied to clipboard");
          }}><Copy size={12} /> Copy & close</button>
          <button className="webhook-dismiss" onClick={() => setReveal(null)}>
            Close
          </button>
        </div>
      )}

      {loading ? <div className="paw-loading"><Loader2 size={20} className="spin" /></div>
        : items.length === 0 ? <div className="leads-empty">
            No endpoints registered yet.
          </div>
        : <div className="webhook-list" data-testid="webhook-list">
            {items.map((ep) => (
              <div key={ep.endpoint_id} className="webhook-row"
                       data-testid={`webhook-row-${ep.endpoint_id}`}>
                <div className="webhook-row-head">
                  <div>
                    <div className="webhook-url">{ep.url}</div>
                    <div className="mono dim small">
                      {ep.endpoint_id} ·  
                      subscribes: {ep.events_subscribed.join(", ")}
                    </div>
                  </div>
                  <div className="webhook-row-actions">
                    <button className="ghost-btn"
                              onClick={() => sendTest(ep.endpoint_id)}
                              data-testid={`webhook-test-btn-${ep.endpoint_id}`}>
                      <Send size={12} /> test_ping
                    </button>
                    <button className="ghost-btn"
                              onClick={() => rotate(ep.endpoint_id)}>
                      <RefreshCw size={12} /> rotate
                    </button>
                    <button className="ghost-btn"
                              onClick={() => loadDeliveries(ep.endpoint_id)}>
                      deliveries
                    </button>
                    <button className="ghost-btn danger"
                              onClick={() => del(ep.endpoint_id)}>
                      <Trash2 size={12} />
                    </button>
                  </div>
                </div>
                {deliveries[ep.endpoint_id] && (
                  <div className="webhook-deliveries"
                          data-testid={`webhook-deliveries-${ep.endpoint_id}`}>
                    {deliveries[ep.endpoint_id].length === 0
                      ? <div className="dim mono">No deliveries yet</div>
                      : deliveries[ep.endpoint_id].map((d) => (
                          <div key={d.webhook_event_id}
                                  className="webhook-delivery-row mono"
                                  data-status={d.status}>
                            <span>{d.event_type}</span>
                            <span className="status-pill mono">{d.status}</span>
                            <span className="dim">{d.last_response_code || "—"}</span>
                            <span className="dim small">{d.attempts} attempts</span>
                          </div>))}
                  </div>)}
              </div>
            ))}
          </div>}
    </div>
  );
}


export function LeaderboardWidget() {
  const [metric, setMetric] = useState("saves");
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    axios.get(`${API}/games_v2/advertiser/leaderboard`,
                  {params: {metric, window: "7d", limit: 5}})
      .then((r) => setItems(r.data.items || []))
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, [metric]);

  return (
    <div className="leaderboard-widget" data-testid="leaderboard-widget">
      <div className="panel-toolbar">
        <h3><Trophy size={16} /> Top campaigns · 7d</h3>
        <select className="leads-filter mono"
                   value={metric}
                   onChange={(e) => setMetric(e.target.value)}
                   data-testid="leaderboard-metric-select">
          <option value="plays">By plays</option>
          <option value="wins">By wins</option>
          <option value="saves">By saves</option>
          <option value="redemptions">By redemptions</option>
          <option value="completion_rate">Completion rate</option>
        </select>
      </div>
      {loading ? <div className="paw-loading"><Loader2 size={20} className="spin" /></div>
        : items.length === 0 ? <div className="leads-empty">
            No data in window yet.
          </div>
        : <div className="leaderboard-list">
            {items.map((it) => (
              <Link key={it.campaign_id}
                       to={`/advertiser/games/${it.campaign_id}/edit`}
                       className="leaderboard-row"
                       data-testid={`leaderboard-row-${it.campaign_id}`}
                       style={{"--brand": it.brand_color || "#ff2d95"}}>
                <span className="lb-rank mono">#{it.rank}</span>
                <span className="lb-title">{it.title}</span>
                <span className="lb-metric mono">
                  {metric === "completion_rate"
                    ? `${(it.value * 100).toFixed(0)}%`
                    : it.value.toLocaleString()}
                </span>
                <ChevronRight size={12} />
              </Link>
            ))}
          </div>}
    </div>
  );
}
