// AdminIntegrations.js — Phase 4.5: GAM service-account upload + SSP partner mgmt.
import { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import {
  Loader2, ChevronLeft, ShieldCheck, AlertTriangle, CheckCircle2, KeyRound,
  Network, Power, Save, History, Activity, Zap, Wallet, Mail, MapPin,
} from "lucide-react";
import "./AdminImaging.css";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
axios.defaults.withCredentials = true;

export default function AdminIntegrations() {
  const [tab, setTab] = useState("health");
  return (
    <div className="admin-img-wrap" data-testid="admin-integrations">
      <RegionBanner />
      <header className="admin-img-header">
        <div>
          <Link to="/admin" style={{ color: "#888892", fontSize: 12, textDecoration: "none" }} data-testid="back-to-admin">
            <ChevronLeft size={11} style={{ verticalAlign: "-1px" }} /> back to admin
          </Link>
          <h1><Network size={24} style={{ verticalAlign: "-4px", marginRight: 8 }} />Integrations</h1>
          <p>Configure programmatic ad demand: Google Ad Manager backfill + OpenRTB SSP partners.</p>
        </div>
        <div className="admin-img-pills">
          <button className={`asset-type-chip ${tab === "health" ? "on" : ""}`}
            onClick={() => setTab("health")} data-testid="tab-health">
            <Activity size={11} style={{ verticalAlign: "-1px" }} /> Health (12d)
          </button>
          <button className={`asset-type-chip ${tab === "gam" ? "on" : ""}`}
            onClick={() => setTab("gam")} data-testid="tab-gam">Google Ad Manager</button>
          <button className={`asset-type-chip ${tab === "ssp" ? "on" : ""}`}
            onClick={() => setTab("ssp")} data-testid="tab-ssp">OpenRTB SSP partners</button>
          <button className={`asset-type-chip ${tab === "auctions" ? "on" : ""}`}
            onClick={() => setTab("auctions")} data-testid="tab-auctions">Recent auctions</button>
          <button className={`asset-type-chip ${tab === "phase18d" ? "on" : ""}`}
            onClick={() => setTab("phase18d")} data-testid="tab-phase18d">Phase 18d stack</button>
        </div>
      </header>
      {tab === "health" && <HealthPanel />}
      {tab === "gam" && <GAMPanel />}
      {tab === "ssp" && <SSPPanel />}
      {tab === "auctions" && <AuctionsPanel />}
      {tab === "phase18d" && <Phase18dPanel />}
    </div>
  );
}

// ─── Phase 18d — Programmatic status + ads.txt editor ───────────────────
function StatusPill({ live, label, testid }) {
  const isLive = !!live;
  const style = {
    display: "inline-flex", alignItems: "center", gap: 6,
    padding: "4px 10px", borderRadius: 999,
    fontSize: 11, fontWeight: 600, letterSpacing: 0.5,
    background: isLive ? "rgba(34,197,94,0.12)" : "rgba(245,158,11,0.14)",
    color:           isLive ? "#22c55e"               : "#f59e0b",
    border:        `1px solid ${isLive ? "rgba(34,197,94,0.4)" : "rgba(245,158,11,0.4)"}`,
  };
  return (
    <span style={style} data-testid={testid}>
      {isLive ? "● LIVE" : "● MOCKED"} {label}
    </span>
  );
}

function Phase18dPanel() {
  const [gam, setGam] = useState(null);
  const [ortb, setOrtb] = useState(null);
  const [adsTxt, setAdsTxt] = useState(null);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState(null);

  const refresh = useCallback(() => {
    axios.get(`${API}/admin/integrations/gam/status`)
            .then((r) => setGam(r.data)).catch(() => setGam({error: true}));
    axios.get(`${API}/admin/integrations/openrtb/status`)
            .then((r) => setOrtb(r.data)).catch(() => setOrtb({error: true}));
    axios.get(`${API}/admin/integrations/ads-txt`)
            .then((r) => { setAdsTxt(r.data); setDraft(r.data.content || ""); })
            .catch(() => setAdsTxt({error: true}));
  }, []);
  useEffect(() => { refresh(); }, [refresh]);

  const save = async () => {
    setSaving(true); setErr(null);
    try {
      const r = await axios.post(`${API}/admin/integrations/ads-txt`,
                                                {content: draft});
      toast.success(`ads.txt saved — ${r.data.bytes} bytes`);
      refresh();
    } catch (e) {
      const d = e?.response?.data?.detail;
      setErr(d?.detail || d || "save failed");
      toast.error("ads.txt save failed");
    } finally { setSaving(false); }
  };

  return (
    <div className="admin-img-body" data-testid="phase18d-panel">
      <div className="rounded-2xl border border-white/[0.08] p-4 mb-4">
        <div className="text-sm font-bold mb-2">Programmatic demand</div>
        <div style={{display: "flex", gap: 10, flexWrap: "wrap"}}>
          <StatusPill live={gam?.is_live} label="GAM"
                              testid="phase18d-gam-pill" />
          <StatusPill live={ortb?.is_live} label="OpenRTB"
                              testid="phase18d-openrtb-pill" />
        </div>
        <div className="text-[10px] text-text-secondary mt-2">
          {gam ? `GAM: network_code=${gam.network_code_present ? "✓" : "—"} svc_acct=${gam.service_account_present ? "✓" : "—"}` : "loading..."}
          {" · "}
          {ortb ? `OpenRTB: ${(ortb.ssp_endpoints_configured || []).length} SSP(s) configured` : "loading..."}
        </div>
      </div>
      <div className="rounded-2xl border border-white/[0.08] p-4">
        <div className="flex items-center justify-between mb-2">
          <div className="text-sm font-bold">ads.txt / app-ads.txt</div>
          <button onClick={save} disabled={saving}
                          className="bigfm-cta" data-testid="ads-txt-save">
            {saving ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
            <span> Save</span>
          </button>
        </div>
        <p className="text-[10px] text-text-secondary mb-2">
          Plain text. Each non-comment line:
          <code> domain, publisher_id, RELATIONSHIP[, tag_id]</code> where
          RELATIONSHIP is DIRECT or RESELLER. Comments start with <code>#</code>.
        </p>
        <textarea data-testid="ads-txt-editor"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          spellCheck={false}
          style={{width: "100%", minHeight: 200, fontFamily: "ui-monospace, monospace",
                       fontSize: 12, padding: 10,
                       background: "rgba(255,255,255,0.03)",
                       color: "#e7e7ea",
                       border: "1px solid rgba(255,255,255,0.08)",
                       borderRadius: 8}} />
        {err && (
          <div className="text-xs mt-2" style={{color: "#ef4444"}}
                  data-testid="ads-txt-err">
            {typeof err === "string" ? err : JSON.stringify(err)}
          </div>
        )}
        <div className="text-[10px] text-text-secondary mt-2">
          {adsTxt ? `${adsTxt.valid_line_count || 0} valid seller line(s) · file: ${adsTxt.path || "ads.txt"}` : ""}
        </div>
      </div>
    </div>
  );
}

// ─── Phase 13d — Region banner (top of /admin/integrations) ─────────────
function RegionBanner() {
  const [status, setStatus] = useState(null);
  useEffect(() => {
    let alive = true;
    axios.get(`${API}/admin/region/status`)
            .then((r) => { if (alive) setStatus(r.data); })
            .catch(() => {});
    return () => { alive = false; };
  }, []);
  if (!status) return null;
  const down = status.primary_down === true;
  const bg = down ? "#3a2a0a" : "#0b2a18";
  const border = down ? "#facc15" : "#16a34a";
  const dot = down ? "#facc15" : "#22c55e";
  return (
    <div data-testid="region-banner"
            style={{ background: bg, border: `1px solid ${border}`,
                        padding: "10px 14px", borderRadius: 8,
                        display: "flex", alignItems: "center", gap: 12,
                        marginBottom: 12, fontSize: 12 }}>
      <span style={{ width: 8, height: 8, borderRadius: 4,
                            background: dot, display: "inline-block" }} />
      <strong style={{ color: "#fff" }}>
        region: {status.region}
      </strong>
      <span style={{ color: "#9ca3af" }}>
        role={status.role} · active_cluster={status.active_cluster} ·
        failovers/24h={status.failover_count_24h ?? 0}
        {down ? " — PRIMARY DOWN, reads → replica" : " — all systems normal"}
      </span>
    </div>
  );
}


// ─── Phase 12d — unified Health tab ────────────────────────────────────
const INTEGRATION_ICONS = {
  maps: MapPin, wallet: Wallet, gam: Network, sendgrid: Mail,
};
const MODE_COLOR = {
  live: "#4ade80",       // green
  mock: "#fdb756",       // amber
  degraded: "#fb7185",   // pink/red
};

function ModeBadge({ mode }) {
  const c = MODE_COLOR[mode] || "#888";
  return (
    <span
      className="asset-type-chip"
      data-testid={`mode-badge-${mode}`}
      style={{
        background: "transparent", borderColor: c, color: c,
        fontSize: 11, padding: "4px 10px",
      }}>
      {mode === "live" ? <CheckCircle2 size={11} /> :
        mode === "degraded" ? <AlertTriangle size={11} /> :
        <Zap size={11} />}{" "}
      {mode.toUpperCase()}
    </span>
  );
}

function IntegrationCard({ name, info, onProbe, probing }) {
  const Icon = INTEGRATION_ICONS[name] || Activity;
  const fail = info.failure_count_1h || 0;
  const ok = info.success_count_1h || 0;
  const total = ok + fail;
  const successPct = total ? Math.round((ok / total) * 100) : null;
  const canProbe = name === "maps" || name === "gam";
  return (
    <div className="img-station-card" data-testid={`integration-card-${name}`}
        style={{ borderColor: MODE_COLOR[info.mode] || "#25252f", padding: 18 }}>
      <div style={{ display: "flex", justifyContent: "space-between",
                          alignItems: "center", gap: 12 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <Icon size={22} style={{ color: MODE_COLOR[info.mode] || "#aaa" }} />
          <h3 style={{ margin: 0, color: "#fff", fontSize: 18,
                              textTransform: "capitalize" }}>{name}</h3>
        </div>
        <ModeBadge mode={info.mode} />
      </div>
      <div style={{ color: "#888892", fontSize: 12, marginTop: 12,
                          display: "flex", gap: 18, flexWrap: "wrap" }}>
        <span>creds<b style={{ marginLeft: 4,
              color: info.creds_present ? "#4ade80" : "#fdb756" }}>
          {info.creds_present ? "yes" : "no"}</b></span>
        <span>1h ok<b style={{ marginLeft: 4, color: "#4ade80" }}>{ok}</b></span>
        <span>1h fail<b style={{ marginLeft: 4, color: "#fb7185" }}>{fail}</b></span>
        {successPct !== null && (
          <span>rate<b style={{ marginLeft: 4 }}>{successPct}%</b></span>
        )}
      </div>
      {info.last_error && (
        <div style={{ marginTop: 10, color: "#fb7185", fontSize: 11,
                            fontFamily: "monospace", overflow: "hidden",
                            textOverflow: "ellipsis", whiteSpace: "nowrap" }}
              title={info.last_error}
              data-testid={`integration-error-${name}`}>
          {info.last_error}
        </div>
      )}
      {canProbe && (
        <div style={{ marginTop: 14 }}>
          <button className="img-regenerate-btn" onClick={() => onProbe(name)}
                       disabled={probing === name}
                       data-testid={`probe-btn-${name}`}>
            {probing === name
              ? <Loader2 className="spin" size={14} />
              : <ShieldCheck size={14} />}
            {probing === name ? " Probing..." : " Run probe"}
          </button>
        </div>
      )}
      <details style={{ marginTop: 14 }}>
        <summary style={{ color: "#aaa", fontSize: 12, cursor: "pointer" }}
                       data-testid={`human-steps-toggle-${name}`}>
          Human steps to promote ({(info.human_steps || []).length})
        </summary>
        <ol style={{ color: "#aaa", fontSize: 12, paddingLeft: 18,
                          marginTop: 8, lineHeight: 1.55 }}
              data-testid={`human-steps-${name}`}>
          {(info.human_steps || []).map((s, i) => (<li key={i}>{s}</li>))}
        </ol>
      </details>
    </div>
  );
}

function HealthPanel() {
  const [items, setItems] = useState(null);
  const [probing, setProbing] = useState(null);
  const [quota, setQuota] = useState(null);

  const load = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/admin/integrations/status`);
      setItems(r.data.items || {});
    } catch (e) { toast.error("Failed to load integrations status"); }
    try {
      const q = await axios.get(`${API}/admin/integrations/sendgrid/quota`);
      setQuota(q.data);
    } catch { /* sendgrid quota may be empty when never sent */ }
  }, []);

  useEffect(() => { load(); }, [load]);

  const probe = async (name) => {
    setProbing(name);
    try {
      if (name === "maps") {
        await axios.get(`${API}/admin/integrations/maps/probe`);
        toast.success("Maps probe complete");
      } else if (name === "gam") {
        await axios.post(`${API}/admin/integrations/gam/probe`);
        toast.success("GAM probe complete");
      }
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Probe failed");
    } finally { setProbing(null); }
  };

  if (!items) return <Loader2 className="spin" size={28} />;
  const names = Object.keys(items);

  return (
    <section style={{ marginTop: 8 }} data-testid="integrations-health">
      <p style={{ color: "#888892", fontSize: 12, marginBottom: 14 }}>
        Phase 12d — each integration auto-detects creds and tracks its 1h
        success/failure window. Mode flips to <b style={{ color: "#4ade80" }}>live</b>
        {" "}when ≥3 calls land with &gt;80% success, demotes to
        {" "}<b style={{ color: "#fb7185" }}>degraded</b> below 50%. No creds →
        permanent <b style={{ color: "#fdb756" }}>mock</b> with a
        HIGHLIGHTED MOCK log on every call.
      </p>
      <div className="assets-grid" style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(360px, 1fr))",
            gap: 16 }}>
        {names.map((n) =>
          items[n] ? (
            <IntegrationCard key={n} name={n} info={items[n]}
                                      onProbe={probe} probing={probing} />
          ) : null
        )}
      </div>
      {quota && (
        <div className="img-station-card" style={{ marginTop: 18 }}
              data-testid="sendgrid-quota-card">
          <div className="meta-label"><Mail size={11} /> SENDGRID QUOTA · plan {quota.plan_tier}</div>
          <div className="asset-meta-row" style={{ marginTop: 6 }}>
            <span>HOUR<b style={{ color: quota.soft_limit_hit ? "#fb7185" : "#fff" }}>
              {quota.hourly_sent} / {quota.caps?.hourly_soft}</b></span>
            <span>DAY<b style={{ color: quota.hard_limit_hit ? "#fb7185" : "#fff" }}>
              {quota.daily_sent} / {quota.caps?.daily_hard}</b></span>
            <span>THROTTLED<b>{quota.throttled_count || 0}</b></span>
            <span>BLOCKED<b style={{ color: "#fb7185" }}>{quota.quota_blocked_count || 0}</b></span>
            <span>RESETS IN<b>{Math.round((quota.seconds_to_daily_reset || 0) / 60)}m</b></span>
          </div>
        </div>
      )}
    </section>
  );
}

function GAMPanel() {
  const [cfg, setCfg] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saJson, setSaJson] = useState("");
  const [adUnit, setAdUnit] = useState("");
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testResult, setTestResult] = useState(null);

  const load = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/admin/ads/integrations/gam`);
      setCfg(r.data);
      if (r.data.ad_unit_id) setAdUnit(r.data.ad_unit_id);
    } catch (e) {
      toast.error("Failed to load GAM config");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const save = async () => {
    if (!saJson.trim()) return toast.error("Paste the service-account JSON first");
    setSaving(true);
    try {
      JSON.parse(saJson); // local validation
      await axios.post(`${API}/admin/ads/integrations/gam`,
        { service_account_json: saJson, ad_unit_id: adUnit || null });
      toast.success("GAM config saved (encrypted)"); setSaJson(""); load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message || "Save failed");
    } finally { setSaving(false); }
  };

  const test = async () => {
    setTesting(true); setTestResult(null);
    try {
      const r = await axios.post(`${API}/admin/ads/integrations/gam/test`);
      setTestResult(r.data);
      r.data.ok ? toast.success("GAM connection OK") : toast.error(r.data.reason);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Test failed");
    } finally { setTesting(false); }
  };

  if (loading) return <Loader2 className="spin" size={28} />;

  return (
    <section style={{ marginTop: 8 }} data-testid="gam-panel">
      <div className="img-station-card" style={{ borderColor: cfg.service_account_configured ? "#4ade80" : "#fdb756" }}>
        <div className="meta-label" style={{ color: cfg.service_account_configured ? "#4ade80" : "#fdb756" }}>
          {cfg.service_account_configured ? <CheckCircle2 size={11} /> : <AlertTriangle size={11} />}{" "}
          {cfg.service_account_configured ? "GAM CONFIGURED" : "GAM NOT CONFIGURED"}
        </div>
        {cfg.service_account_configured && (
          <div style={{ color: "#aaa", fontSize: 12, marginTop: 6 }}>
            Network: <code style={{ color: "#fff" }}>{cfg.network_code}</code> · Ad unit:{" "}
            <code style={{ color: "#fff" }}>{cfg.ad_unit_id || "—"}</code>
          </div>
        )}
      </div>

      <div className="img-station-card" style={{ marginTop: 12 }}>
        <div className="meta-label"><KeyRound size={11} /> SERVICE ACCOUNT JSON (encrypted with Fernet)</div>
        <textarea
          value={saJson} onChange={(e) => setSaJson(e.target.value)}
          placeholder='Paste the entire { "type": "service_account", ... } JSON here'
          rows={10} data-testid="gam-sa-input"
          style={{ width: "100%", background: "#0f0f15", color: "#fff", padding: 12,
                    fontFamily: "monospace", fontSize: 11, borderRadius: 6,
                    border: "1px solid #25252f", marginTop: 8 }} />
        <label className="meta-label" style={{ marginTop: 12 }}>AD UNIT ID (optional)</label>
        <input className="asset-btn" style={{ background: "#15151e", padding: 11, fontSize: 14, width: "100%", maxWidth: 480 }}
          value={adUnit} onChange={(e) => setAdUnit(e.target.value)}
          placeholder="e.g. 1234567890" data-testid="gam-adunit" />
        <div style={{ display: "flex", gap: 10, marginTop: 14 }}>
          <button className="img-regenerate-btn" onClick={save} disabled={saving || !saJson} data-testid="gam-save-btn">
            {saving ? <Loader2 className="spin" size={14} /> : <Save size={14} />}
            {saving ? " Saving..." : " Save (encrypted)"}
          </button>
          <button className="asset-type-chip" onClick={test} disabled={testing || !cfg.service_account_configured} data-testid="gam-test-btn">
            {testing ? <Loader2 className="spin" size={14} /> : <ShieldCheck size={14} />}
            {testing ? " Testing..." : " Test connection"}
          </button>
        </div>
        {testResult && (
          <pre style={{ marginTop: 14, padding: 12, background: "#0f0f15", color: testResult.ok ? "#4ade80" : "#fb7185",
                          borderRadius: 6, fontSize: 11, whiteSpace: "pre-wrap" }} data-testid="gam-test-result">
            {JSON.stringify(testResult, null, 2)}
          </pre>
        )}
      </div>
    </section>
  );
}

function SSPPanel() {
  const [items, setItems] = useState(null);
  const [busy, setBusy] = useState(null);

  const load = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/admin/ssp/partners`);
      setItems(r.data.items || []);
    } catch (e) { toast.error("Failed to load SSP partners"); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const toggle = async (p) => {
    setBusy(p.id);
    try {
      await axios.post(`${API}/admin/ssp/partners/${p.id}/${p.enabled ? "disable" : "enable"}`);
      toast.success(`${p.name} ${p.enabled ? "disabled" : "enabled"}`); load();
    } catch (e) { toast.error("Toggle failed"); } finally { setBusy(null); }
  };

  const updateField = async (p, field, value) => {
    setBusy(p.id);
    try {
      await axios.post(`${API}/admin/ssp/partners/${p.id}`, { [field]: value });
      load();
    } catch (e) { toast.error("Update failed"); } finally { setBusy(null); }
  };

  if (!items) return <Loader2 className="spin" size={28} />;

  return (
    <section style={{ marginTop: 8 }} data-testid="ssp-panel">
      <p style={{ color: "#888892", fontSize: 12, marginBottom: 12 }}>
        Adapters fan out a 200ms OpenRTB 2.5 BidRequest. Only enabled partners are queried.
        <code> mock_ssp</code> always returns a $1.00 bid for testing the auction loop.
      </p>
      <div className="assets-grid">
        {items.map((p) => (
          <div key={p.id} className="asset-row" data-testid={`ssp-partner-${p.id}`}>
            <div className="asset-row-head">
              <div style={{ fontSize: 14, fontWeight: 700, color: "#fff" }}>{p.name}</div>
              <button className={`asset-type-chip ${p.enabled ? "on" : ""}`}
                onClick={() => toggle(p)} disabled={busy === p.id} data-testid={`ssp-toggle-${p.id}`}>
                {busy === p.id ? <Loader2 className="spin" size={12} /> : <Power size={12} />}
                {p.enabled ? " ENABLED" : " DISABLED"}
              </button>
            </div>
            <div className="asset-meta-row" style={{ marginTop: 6 }}>
              <span>ADAPTER<b>{p.adapter_module}</b></span>
              <span>WINS 30d<b style={{ color: "#4ade80" }}>{p.win_count_30d || 0}</b></span>
              <span>BIDS 30d<b>{p.bid_count_30d || 0}</b></span>
              <span>AVG ¢<b>{p.avg_bid_cents || 0}</b></span>
            </div>
            <label className="meta-label" style={{ marginTop: 10 }}>ENDPOINT URL</label>
            <input className="asset-btn" style={{ background: "#15151e", padding: 9, fontSize: 12, width: "100%" }}
              defaultValue={p.endpoint_url || ""}
              onBlur={(e) => e.target.value !== (p.endpoint_url || "") &&
                updateField(p, "endpoint_url", e.target.value)}
              placeholder="https://partner.com/openrtb/bid"
              data-testid={`ssp-endpoint-${p.id}`} />
            <label className="meta-label" style={{ marginTop: 8 }}>BIDDER ID</label>
            <input className="asset-btn" style={{ background: "#15151e", padding: 9, fontSize: 12, width: "100%" }}
              defaultValue={p.bidder_id || ""}
              onBlur={(e) => e.target.value !== (p.bidder_id || "") &&
                updateField(p, "bidder_id", e.target.value)}
              data-testid={`ssp-bidderid-${p.id}`} />
            <label className="meta-label" style={{ marginTop: 8 }}>TIMEOUT (ms)</label>
            <input className="asset-btn" type="number" style={{ background: "#15151e", padding: 9, fontSize: 12, width: 120 }}
              defaultValue={p.timeout_ms || 200}
              onBlur={(e) => Number(e.target.value) !== (p.timeout_ms || 200) &&
                updateField(p, "timeout_ms", Number(e.target.value))}
              data-testid={`ssp-timeout-${p.id}`} />
          </div>
        ))}
      </div>
    </section>
  );
}

function AuctionsPanel() {
  const [items, setItems] = useState(null);
  useEffect(() => {
    (async () => {
      try {
        const r = await axios.get(`${API}/admin/ssp/auctions/recent?limit=30`);
        setItems(r.data.items || []);
      } catch (e) { setItems([]); }
    })();
  }, []);
  if (!items) return <Loader2 className="spin" size={28} />;
  return (
    <section style={{ marginTop: 8 }} data-testid="auctions-panel">
      <div className="meta-label"><History size={11} /> LAST 30 AUCTIONS</div>
      {items.length === 0 ? (
        <p style={{ color: "#888", fontSize: 12, marginTop: 12 }}>No auctions run yet. They fire on free-listener segments when SSPs are enabled.</p>
      ) : (
        <div className="assets-grid" style={{ marginTop: 8 }}>
          {items.map((a, i) => (
            <div key={i} className="asset-row" data-testid={`auction-row-${i}`}>
              <div className="asset-row-head">
                <div style={{ fontSize: 12, color: "#fff" }}>
                  {a.winner_partner ? <b style={{ color: "#4ade80" }}>{a.winner_partner}</b> : <b style={{ color: "#888" }}>no_bid</b>}
                  {" "}<span style={{ color: "#888892" }}>· {a.duration_ms}ms · {a.adapter_count} adapters</span>
                </div>
                <span style={{ color: "#aaa", fontSize: 11 }}>
                  {a.winner_price_cents ? `${(a.winner_price_cents / 100).toFixed(2)} USD` : "—"}
                </span>
              </div>
              <div style={{ color: "#888", fontSize: 10, marginTop: 4 }}>{a.ran_at}</div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
