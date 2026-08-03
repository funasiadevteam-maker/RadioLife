// AdminSafety.js — Phase 12c Trust & Safety hub
// Tabs: moderation queue, fraud events, abuse events, user actions, settings.
import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { Link } from "react-router-dom";
import {
  Loader2, ShieldAlert, AlertTriangle, Ban, UserSearch,
  Settings, Activity, RefreshCw, Check, X,
} from "lucide-react";
import { Toaster, toast } from "sonner";
import { API } from "@/AuthContext";
import "./AdminImaging.css";

axios.defaults.withCredentials = true;

const TABS = [
  { id: "moderation", label: "Moderation Queue", icon: ShieldAlert },
  { id: "fraud", label: "Fraud Events", icon: AlertTriangle },
  { id: "abuse", label: "Abuse Events", icon: Ban },
  { id: "users", label: "User Actions", icon: UserSearch },
  { id: "settings", label: "Settings", icon: Settings },
];

function fmtDate(iso) {
  if (!iso) return "—";
  try { return new Date(iso).toLocaleString(); } catch { return iso; }
}

function VerdictPill({ verdict }) {
  const color = verdict === "block" ? "#ff4d4d"
                  : verdict === "warn" ? "#fdb756" : "#4ade80";
  return <span style={{ color, fontWeight: 700,
                                  textTransform: "uppercase", fontSize: 11 }}>
    {verdict}
  </span>;
}

function StatusPill({ status }) {
  const colors = { open: "#ff4d4d", reviewed: "#7BD3F7",
                          dismissed: "#888892" };
  return <span style={{ color: colors[status] || "#888892",
                                  fontWeight: 700, textTransform: "uppercase",
                                  fontSize: 11 }}>{status || "—"}</span>;
}

// ─── Moderation tab ─────────────────────────────────────────────────────
function ModerationTab() {
  const [items, setItems] = useState([]);
  const [filter, setFilter] = useState("warn");
  const [loading, setLoading] = useState(true);

  const fetchIt = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(
        `${API}/admin/safety/moderation_queue?status=${filter}`);
      setItems(r.data.items || []);
    } finally { setLoading(false); }
  }, [filter]);
  useEffect(() => { fetchIt(); }, [fetchIt]);

  return (
    <div data-testid="tab-moderation" style={{ display: "grid", gap: 12 }}>
      <div style={{ display: "flex", gap: 8 }}>
        {["warn", "block", "all"].map((f) => (
          <button key={f} type="button"
                  className={`asset-type-chip ${filter === f ? "on" : ""}`}
                  onClick={() => setFilter(f)}
                  data-testid={`mod-filter-${f}`}>
            {f}
          </button>
        ))}
        <button type="button" className="asset-type-chip"
                     onClick={fetchIt} data-testid="mod-refresh">
          <RefreshCw size={11} /> Refresh
        </button>
      </div>
      {loading ? <Loader2 className="spin" size={20} /> : items.length === 0 ? (
        <div style={{ color: "#888892", fontSize: 12 }}>No items</div>
      ) : items.map((m) => (
        <div key={m.moderation_id} className="img-station-card"
                data-testid={`mod-row-${m.moderation_id}`}
                style={{ padding: 12, fontSize: 13, gap: 8 }}>
          <div style={{ display: "flex", justifyContent: "space-between",
                              alignItems: "center" }}>
            <VerdictPill verdict={m.verdict} />
            <span style={{ color: "#666670", fontSize: 11 }}>
              {fmtDate(m.created_at)}
            </span>
          </div>
          <div style={{ color: "#aaaab0" }}>
            <strong>{m.ref_type}</strong> · {m.ref_id || "—"} · user{" "}
            <code style={{ color: "#7BD3F7" }}>{m.user_id}</code>
          </div>
          <div style={{ color: "#888892", fontSize: 12 }}>
            Categories: {(m.categories || []).join(", ") || "none"} ·
            score {m.score} · model {m.model}
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── Generic events tab (fraud + abuse share UI shape) ──────────────────
function EventsTab({ kind, testid }) {
  const [items, setItems] = useState([]);
  const [status, setStatus] = useState("open");
  const [loading, setLoading] = useState(true);

  const fetchIt = useCallback(async () => {
    setLoading(true);
    try {
      const qs = status === "all" ? "" : `?status=${status}`;
      const r = await axios.get(
        `${API}/admin/safety/${kind}_events${qs}`);
      setItems(r.data.items || []);
    } finally { setLoading(false); }
  }, [kind, status]);
  useEffect(() => { fetchIt(); }, [fetchIt]);

  const triage = async (ev, newStatus) => {
    try {
      const endpoint = kind === "fraud"
        ? `${API}/admin/safety/fraud_events/${ev.fraud_id}`
        : `${API}/admin/safety/abuse_events/${ev.abuse_id}/triage`;
      const method = kind === "fraud" ? "patch" : "patch";
      await axios[method](endpoint, { status: newStatus });
      toast.success(`${kind} event ${newStatus}`);
      fetchIt();
    } catch (e) {
      toast.error(`Triage failed: ${e.response?.data?.detail || e.message}`);
    }
  };

  return (
    <div data-testid={testid} style={{ display: "grid", gap: 12 }}>
      <div style={{ display: "flex", gap: 8 }}>
        {["open", "reviewed", "dismissed", "all"].map((s) => (
          <button key={s} type="button"
                  className={`asset-type-chip ${status === s ? "on" : ""}`}
                  onClick={() => setStatus(s)}
                  data-testid={`${kind}-filter-${s}`}>
            {s}
          </button>
        ))}
        <button type="button" className="asset-type-chip" onClick={fetchIt}
                     data-testid={`${kind}-refresh`}>
          <RefreshCw size={11} /> Refresh
        </button>
      </div>
      {loading ? <Loader2 className="spin" size={20} /> : items.length === 0 ? (
        <div style={{ color: "#888892", fontSize: 12 }}>No events</div>
      ) : items.map((ev) => {
        const id = ev.fraud_id || ev.abuse_id;
        return (
          <div key={id} className="img-station-card"
                  data-testid={`${kind}-row-${id}`}
                  style={{ padding: 12, fontSize: 13, gap: 6 }}>
            <div style={{ display: "flex",
                                justifyContent: "space-between" }}>
              <strong style={{ color: "#ff8a3d" }}>{ev.rule}</strong>
              <StatusPill status={ev.status} />
            </div>
            <div style={{ color: "#aaaab0", fontSize: 12 }}>
              user <code style={{ color: "#7BD3F7" }}>{ev.user_id}</code> ·
              severity <strong>{ev.severity}</strong> · {fmtDate(ev.created_at)}
            </div>
            <pre style={{ background: "#0d0d14", color: "#888892",
                                fontSize: 11, padding: 8, borderRadius: 4,
                                margin: 0, overflowX: "auto" }}>
              {JSON.stringify(ev.detail || {}, null, 2)}
            </pre>
            {ev.status === "open" && (
              <div style={{ display: "flex", gap: 8 }}>
                <button type="button" className="asset-type-chip"
                              onClick={() => triage(ev, "reviewed")}
                              data-testid={`${kind}-triage-reviewed-${id}`}>
                  <Check size={11} /> Mark Reviewed
                </button>
                <button type="button" className="asset-type-chip"
                              onClick={() => triage(ev, "dismissed")}
                              data-testid={`${kind}-triage-dismissed-${id}`}>
                  <X size={11} /> Dismiss
                </button>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ─── User actions tab ──────────────────────────────────────────────────
function UsersTab() {
  const [uid, setUid] = useState("");
  const [card, setCard] = useState(null);
  const [busy, setBusy] = useState(false);

  const lookup = async () => {
    if (!uid) return;
    setBusy(true);
    try {
      const r = await axios.get(`${API}/admin/safety/users/${uid}`);
      setCard(r.data);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Lookup failed");
      setCard(null);
    } finally { setBusy(false); }
  };

  const suspend = async (days) => {
    try {
      await axios.post(
        `${API}/admin/safety/users/${uid}/suspend`,
        { duration_days: days, reason: "admin_action" });
      toast.success(`Suspended ${days}d`);
      lookup();
    } catch (e) { toast.error("Suspend failed"); }
  };
  const unsuspend = async () => {
    try {
      await axios.post(
        `${API}/admin/safety/users/${uid}/unsuspend`, {});
      toast.success("Unsuspended");
      lookup();
    } catch (e) { toast.error("Unsuspend failed"); }
  };

  return (
    <div data-testid="tab-users" style={{ display: "grid", gap: 14 }}>
      <div style={{ display: "flex", gap: 8 }}>
        <input type="text" value={uid}
                   onChange={(e) => setUid(e.target.value)}
                   placeholder="user_xxxxxxxxxxxxxxxx"
                   data-testid="users-uid-input"
                   style={{ flex: 1, padding: 8, background: "#15151c",
                               color: "#fff", border: "1px solid #2a2a36",
                               borderRadius: 6 }} />
        <button type="button" className="asset-type-chip on"
                     onClick={lookup} disabled={busy}
                     data-testid="users-lookup">
          {busy ? <Loader2 size={11} className="spin" /> : <UserSearch size={11} />} Lookup
        </button>
      </div>

      {card && card.user && (
        <div className="img-station-card" data-testid="users-card"
                style={{ padding: 14, gap: 12 }}>
          <div style={{ fontSize: 14, fontWeight: 700 }}>
            {card.user.name || card.user.email || card.user.user_id}
          </div>
          <div style={{ color: "#aaaab0", fontSize: 12 }}>
            {card.user.email} · {card.user.is_premium ? "Premium" : "Free"}
          </div>
          {card.user.suspended_until && (
            <div style={{ color: "#ff4d4d", fontSize: 12 }}>
              SUSPENDED until {fmtDate(card.user.suspended_until)} —
              {" "}{card.user.suspended_reason}
            </div>
          )}
          {card.user.strikes_summary && (
            <div style={{ color: "#888892", fontSize: 12 }}>
              Strikes: low {card.user.strikes_summary.low || 0} ·
              medium {card.user.strikes_summary.medium || 0} ·
              high {card.user.strikes_summary.high || 0}
            </div>
          )}
          <div style={{ display: "flex", gap: 8 }}>
            <button type="button" className="asset-type-chip"
                          onClick={() => suspend(7)}
                          data-testid="users-suspend-7d">Suspend 7d</button>
            <button type="button" className="asset-type-chip"
                          onClick={() => suspend(30)}
                          data-testid="users-suspend-30d">Suspend 30d</button>
            <button type="button" className="asset-type-chip"
                          onClick={unsuspend}
                          data-testid="users-unsuspend">Unsuspend</button>
          </div>

          <div className="meta-label" style={{ marginTop: 12 }}>
            STRIKES (RECENT)
          </div>
          {(card.strikes_recent || []).slice(0, 10).map((s) => (
            <div key={s.strike_id} className="asset-meta-row"
                    style={{ justifyContent: "space-between",
                                borderBottom: "1px solid #25252f",
                                fontSize: 12, padding: "4px 0" }}>
              <span>{s.severity} · {s.reason}</span>
              <span style={{ color: "#666670" }}>{fmtDate(s.created_at)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Settings tab ──────────────────────────────────────────────────────
function SettingsTab() {
  const [settings, setSettings] = useState(null);
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/admin/safety/settings`);
      setSettings(r.data.settings);
      setDraft(JSON.stringify(r.data.settings || {}, null, 2));
    } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const save = async () => {
    try {
      const payload = JSON.parse(draft);
      await axios.patch(`${API}/admin/safety/settings`, payload);
      toast.success("Settings saved");
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || e.message);
    }
  };

  if (loading) return <Loader2 className="spin" size={20} />;

  return (
    <div data-testid="tab-settings" style={{ display: "grid", gap: 12 }}>
      <div className="meta-label">SAFETY SETTINGS (JSON)</div>
      <textarea value={draft}
                      onChange={(e) => setDraft(e.target.value)}
                      data-testid="settings-textarea"
                      rows={20}
                      style={{ background: "#0d0d14", color: "#e4e4ec",
                                 fontFamily: "monospace", fontSize: 12,
                                 padding: 12, border: "1px solid #25252f",
                                 borderRadius: 6 }} />
      <div style={{ display: "flex", gap: 8 }}>
        <button type="button" className="asset-type-chip on"
                     onClick={save} data-testid="settings-save">
          Save
        </button>
        <button type="button" className="asset-type-chip" onClick={load}
                     data-testid="settings-reload">
          <RefreshCw size={11} /> Reload
        </button>
      </div>
      <div style={{ color: "#666670", fontSize: 11 }}>
        Editable keys: <code>profanity_extra</code> (object: lang → [word]),
        <code> leak_allowlist_partner_ids</code> (array),
        <code> strike_thresholds</code> (object).
      </div>
    </div>
  );
}

// ─── Main page ──────────────────────────────────────────────────────────
export default function AdminSafety() {
  const [tab, setTab] = useState("moderation");

  return (
    <div className="admin-img-wrap" data-testid="admin-safety-page">
      <Toaster position="top-right" theme="dark" richColors />
      <header className="admin-img-header">
        <div>
          <h1>
            <ShieldAlert size={24} style={{ verticalAlign: "-4px",
                                                            marginRight: 8 }} />
            Trust & Safety
          </h1>
          <p>
            Content moderation · coupon fraud detection · abuse heuristics ·
            user suspensions.  Rule-based pre-filter + OpenAI moderation
            (HIGHLIGHTED MOCK when OPENAI_API_KEY is unset — every check
            still runs the rule pipeline and persists an audit row).
          </p>
          <p style={{ marginTop: 6, fontSize: 11, color: "#666670" }}>
            <Link to="/admin" className="admin-pill"
                     data-testid="link-admin-home">← Admin</Link>
            {" · "}
            <Link to="/admin/retention" className="admin-pill"
                     data-testid="link-retention">Retention</Link>
          </p>
        </div>
      </header>

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

      {tab === "moderation" && <ModerationTab />}
      {tab === "fraud" && <EventsTab kind="fraud" testid="tab-fraud" />}
      {tab === "abuse" && <EventsTab kind="abuse" testid="tab-abuse" />}
      {tab === "users" && <UsersTab />}
      {tab === "settings" && <SettingsTab />}
    </div>
  );
}
