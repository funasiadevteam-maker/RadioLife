// Advertiser dashboard — Developer / API keys page (FUUSIC Ads API v1).
// Self-serve management of partner API keys + OAuth2 clients, usage, webhooks
// (events, signing-secret rotation, delivery log + retry), per-key IP allowlist,
// and an interactive API Explorer. Raw secrets are shown exactly once.
import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import {
  KeyRound, Plus, Copy, Trash2, ShieldCheck, ExternalLink, Loader2, Activity,
  Send, RefreshCw, ChevronDown, ChevronUp, Play, Lock,
} from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
const V1_BASE = `${process.env.REACT_APP_BACKEND_URL || ""}/api/v1`;

// Safe read-only endpoints exposed in the API Explorer.
const EXPLORER_PATHS = [
  "/capabilities", "/me", "/products", "/inventory", "/markets", "/rate-card",
  "/stations?limit=5", "/reward-events", "/conversions", "/merchant/businesses",
  "/jobs", "/analytics/summary", "/billing/summary", "/billing/invoices", "/status",
];

function CredCreator({ kind, onCreate }) {
  const [env, setEnv] = useState("sandbox");
  const [label, setLabel] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true);
    try { await onCreate({ environment: env, label }); setLabel(""); }
    finally { setBusy(false); }
  };
  return (
    <div className="flex flex-wrap items-end gap-2 mt-3">
      <div>
        <label className="block text-[11px] font-bold text-slate-400 mb-1">Environment</label>
        <select value={env} onChange={(e) => setEnv(e.target.value)} data-testid={`dev-${kind}-env`}
          className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold">
          <option value="sandbox">Sandbox (test)</option>
          <option value="live">Live</option>
        </select>
      </div>
      <div className="flex-1 min-w-[160px]">
        <label className="block text-[11px] font-bold text-slate-400 mb-1">Label (optional)</label>
        <input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="e.g. Prod server"
          data-testid={`dev-${kind}-label`}
          className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
      </div>
      <button onClick={submit} disabled={busy} data-testid={`dev-${kind}-create`}
        className="inline-flex items-center gap-1.5 bg-slate-900 text-white font-black rounded-lg px-4 py-2 text-sm disabled:opacity-50">
        {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
        Create {kind === "key" ? "API key" : "OAuth client"}
      </button>
    </div>
  );
}

function SecretReveal({ secret, onDone }) {
  return (
    <div className="mt-3 rounded-xl border border-amber-300 bg-amber-50 p-3" data-testid="dev-secret-reveal">
      <div className="flex items-center gap-1.5 font-black text-amber-800 text-sm"><ShieldCheck className="w-4 h-4" />Copy this now — it won&apos;t be shown again</div>
      <div className="mt-2 flex items-center gap-2">
        <code className="flex-1 break-all bg-white border border-amber-200 rounded-lg px-3 py-2 text-xs">{secret}</code>
        <button onClick={() => { navigator.clipboard?.writeText(secret); toast.success("Copied"); }}
          className="p-2 rounded-lg bg-amber-600 text-white" data-testid="dev-secret-copy"><Copy className="w-4 h-4" /></button>
      </div>
      <button onClick={onDone} className="mt-2 text-xs font-bold text-amber-800 underline">I&apos;ve saved it</button>
    </div>
  );
}

function EnvBadge({ env }) {
  const live = env === "LIVE";
  return <span className={`text-[10px] font-black px-2 py-0.5 rounded-full ${live ? "bg-green-100 text-green-700" : "bg-slate-100 text-slate-500"}`}>{live ? "LIVE" : "SANDBOX"}</span>;
}

export default function DeveloperApi() {
  const [state, setState] = useState({ loading: true });
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [reveal, setReveal] = useState(null);
  const [usage, setUsage] = useState(null);
  const [webhooks, setWebhooks] = useState([]);
  const [whUrl, setWhUrl] = useState("");
  const [whEnv, setWhEnv] = useState("sandbox");
  const [whEventOptions, setWhEventOptions] = useState([]);
  const [whSelected, setWhSelected] = useState([]);
  const [deliveries, setDeliveries] = useState({});
  const [expandedWh, setExpandedWh] = useState(null);
  const [ipDraft, setIpDraft] = useState({});
  // API Explorer
  const [exKey, setExKey] = useState("");
  const [exPath, setExPath] = useState("/capabilities");
  const [exResp, setExResp] = useState(null);
  const [exBusy, setExBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/partner/account`);
      setState({ loading: false, ...r.data });
      if (r.data?.exists) {
        const [u, w] = await Promise.all([
          axios.get(`${API}/partner/usage?days=30`).catch(() => ({ data: null })),
          axios.get(`${API}/partner/webhooks`).catch(() => ({ data: { items: [], events: [] } })),
        ]);
        setUsage(u.data);
        setWebhooks(w.data?.items || []);
        setWhEventOptions(w.data?.events || []);
      }
    } catch { setState({ loading: false, exists: false }); }
  }, []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { if (reveal) window.scrollTo({ top: 0, behavior: "smooth" }); }, [reveal]);

  const createAccount = async () => {
    if (!name.trim() || !email.trim()) { toast.error("Name and email required"); return; }
    try {
      await axios.post(`${API}/partner/account`, { name, contact_email: email });
      toast.success("Partner account created");
      load();
    } catch { toast.error("Could not create account"); }
  };

  const createKey = async (body) => {
    try {
      const r = await axios.post(`${API}/partner/keys`, body);
      setReveal({ title: "API key", value: r.data.api_key });
      toast.success("API key created");
      load();
    } catch { toast.error("Could not create key"); }
  };
  const createClient = async (body) => {
    try {
      const r = await axios.post(`${API}/partner/oauth-clients`, body);
      setReveal({ title: "OAuth client secret", value: `client_id: ${r.data.client_id}\nclient_secret: ${r.data.client_secret}` });
      toast.success("OAuth client created");
      load();
    } catch { toast.error("Could not create client"); }
  };
  const revokeKey = async (id) => {
    try { await axios.post(`${API}/partner/keys/${id}/revoke`); toast.success("Key revoked"); load(); }
    catch { toast.error("Could not revoke"); }
  };
  const revokeClient = async (id) => {
    try { await axios.post(`${API}/partner/oauth-clients/${id}/revoke`); toast.success("Client revoked"); load(); }
    catch { toast.error("Could not revoke"); }
  };
  const saveIpAllowlist = async (keyId) => {
    const csv = ipDraft[keyId] ?? "";
    const list = csv.split(",").map((s) => s.trim()).filter(Boolean);
    try {
      await axios.post(`${API}/partner/keys/${keyId}/ip-allowlist`, { ip_allowlist: list });
      toast.success(list.length ? `IP allowlist set (${list.length})` : "IP allowlist cleared");
      load();
    } catch { toast.error("Could not update allowlist"); }
  };
  const toggleEvent = (ev) => {
    setWhSelected((prev) => prev.includes(ev) ? prev.filter((x) => x !== ev) : [...prev, ev]);
  };
  const createWebhook = async () => {
    if (!whUrl.trim()) { toast.error("Endpoint URL required"); return; }
    try {
      const r = await axios.post(`${API}/partner/webhooks`, {
        url: whUrl, environment: whEnv,
        events: whSelected.length ? whSelected : undefined,
      });
      setWhUrl(""); setWhSelected([]);
      if (r.data?.secret) setReveal({ title: "Webhook signing secret", value: r.data.secret });
      toast.success("Webhook added");
      load();
    } catch { toast.error("Could not add webhook"); }
  };
  const pingWebhook = async (id) => {
    try {
      const r = await axios.post(`${API}/partner/webhooks/${id}/ping`);
      toast[r.data?.delivered ? "success" : "error"](r.data?.delivered ? "Ping delivered" : "Ping failed");
      if (expandedWh === id) loadDeliveries(id);
    } catch { toast.error("Ping failed"); }
  };
  const rotateSecret = async (id) => {
    try {
      const r = await axios.post(`${API}/partner/webhooks/${id}/rotate-secret`);
      if (r.data?.secret) setReveal({ title: "New webhook signing secret", value: r.data.secret });
      toast.success("Secret rotated");
    } catch { toast.error("Could not rotate secret"); }
  };
  const deleteWebhook = async (id) => {
    try { await axios.delete(`${API}/partner/webhooks/${id}`); toast.success("Webhook removed"); load(); }
    catch { toast.error("Could not remove"); }
  };
  const loadDeliveries = async (id) => {
    try {
      const r = await axios.get(`${API}/partner/webhooks/${id}/deliveries`);
      setDeliveries((d) => ({ ...d, [id]: r.data?.items || [] }));
    } catch { setDeliveries((d) => ({ ...d, [id]: [] })); }
  };
  const toggleDeliveries = (id) => {
    if (expandedWh === id) { setExpandedWh(null); return; }
    setExpandedWh(id); loadDeliveries(id);
  };
  const retryDelivery = async (whId, delId) => {
    try {
      const r = await axios.post(`${API}/partner/webhooks/${whId}/deliveries/${delId}/retry`);
      toast[r.data?.delivered ? "success" : "error"](r.data?.delivered ? "Redelivered" : "Retry failed");
      loadDeliveries(whId);
    } catch { toast.error("Retry failed"); }
  };
  const runExplorer = async () => {
    if (!exKey.trim()) { toast.error("Paste an API key"); return; }
    setExBusy(true); setExResp(null);
    const t0 = Date.now();
    try {
      const r = await axios.get(`${V1_BASE}${exPath}`, {
        headers: { Authorization: `Bearer ${exKey.trim()}` },
        transformRequest: [(d, h) => { delete h.common?.Authorization; return d; }],
        validateStatus: () => true,
      });
      setExResp({ status: r.status, ms: Date.now() - t0, body: r.data });
    } catch (e) {
      setExResp({ status: "ERR", ms: Date.now() - t0, body: { error: String(e) } });
    } finally { setExBusy(false); }
  };

  if (state.loading) return <div className="p-8 text-center text-slate-400"><Loader2 className="w-6 h-6 animate-spin inline" /></div>;

  return (
    <div className="max-w-3xl" data-testid="developer-api-page">
      <div className="flex items-center gap-2 mb-1">
        <KeyRound className="w-6 h-6 text-slate-900" />
        <h1 className="text-2xl font-black text-slate-900">API &amp; Keys</h1>
      </div>
      <p className="text-sm text-slate-500 mb-5">
        Connect your own systems to FUUSIC to buy audio ads, banners, sponsorships and more, programmatically.
        Base URL <code className="bg-slate-100 px-1.5 py-0.5 rounded text-xs">{V1_BASE}</code>.
        <a href={`${V1_BASE}/docs`} target="_blank" rel="noreferrer" data-testid="dev-docs-link"
          className="inline-flex items-center gap-1 text-orange-600 font-bold ml-1">API reference<ExternalLink className="w-3.5 h-3.5" /></a>
      </p>

      {!state.exists ? (
        <div className="rounded-2xl border border-slate-200 p-5" data-testid="dev-onboard">
          <h2 className="font-black text-slate-900">Create your developer account</h2>
          <p className="text-sm text-slate-500 mt-1 mb-3">One-time setup to start issuing API credentials.</p>
          <div className="grid sm:grid-cols-2 gap-3">
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Company / partner name"
              data-testid="dev-account-name" className="rounded-lg border border-slate-300 px-3 py-2 text-sm" />
            <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Technical contact email"
              data-testid="dev-account-email" className="rounded-lg border border-slate-300 px-3 py-2 text-sm" />
          </div>
          <button onClick={createAccount} data-testid="dev-account-create"
            className="mt-3 bg-orange-600 text-white font-black rounded-lg px-5 py-2.5 text-sm">Create account</button>
        </div>
      ) : (
        <>
          {reveal && (
            <div className="mb-4">
              <div className="text-xs font-bold text-slate-500">{reveal.title}</div>
              <SecretReveal secret={reveal.value} onDone={() => setReveal(null)} />
            </div>
          )}

          {/* API keys */}
          <section className="rounded-2xl border border-slate-200 p-5 mb-4" data-testid="dev-keys-section">
            <h2 className="font-black text-slate-900">API keys</h2>
            <p className="text-xs text-slate-500 mt-0.5">Send as <code className="bg-slate-100 px-1 rounded">Authorization: Bearer &lt;key&gt;</code>. Keep secrets server-side only.</p>
            <div className="mt-3 divide-y divide-slate-100">
              {(state.api_keys || []).length === 0 && <div className="text-sm text-slate-400 py-2">No API keys yet.</div>}
              {(state.api_keys || []).map((k) => (
                <div key={k.key_id} className="py-2.5" data-testid={`dev-key-${k.key_id}`}>
                  <div className="flex items-center justify-between">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <code className="text-xs font-bold text-slate-800">{k.key_id}</code><EnvBadge env={k.environment} />
                        {k.revoked_at && <span className="text-[10px] font-black text-red-600">REVOKED</span>}
                      </div>
                      <div className="text-[11px] text-slate-400 truncate">{k.label || "—"} · scopes: {(k.scopes || []).length} · last used: {k.last_used_at ? new Date(k.last_used_at).toLocaleString() : "never"}</div>
                    </div>
                    {!k.revoked_at && (
                      <button onClick={() => revokeKey(k.key_id)} data-testid={`dev-key-revoke-${k.key_id}`}
                        className="p-2 rounded-lg text-red-600 hover:bg-red-50"><Trash2 className="w-4 h-4" /></button>
                    )}
                  </div>
                  {!k.revoked_at && (
                    <div className="mt-2 flex flex-wrap items-center gap-2" data-testid={`dev-key-ip-row-${k.key_id}`}>
                      <Lock className="w-3.5 h-3.5 text-slate-400" />
                      <span className="text-[11px] font-bold text-slate-400">IP allowlist</span>
                      <input
                        defaultValue={(k.ip_allowlist || []).join(", ")}
                        onChange={(e) => setIpDraft((d) => ({ ...d, [k.key_id]: e.target.value }))}
                        placeholder="e.g. 203.0.113.5, 10.0.0.0/24 (blank = any)"
                        data-testid={`dev-key-ip-input-${k.key_id}`}
                        className="flex-1 min-w-[180px] rounded-lg border border-slate-300 px-2.5 py-1.5 text-xs" />
                      <button onClick={() => saveIpAllowlist(k.key_id)} data-testid={`dev-key-ip-save-${k.key_id}`}
                        className="text-xs font-black text-slate-700 bg-slate-100 rounded-lg px-3 py-1.5">Save</button>
                    </div>
                  )}
                </div>
              ))}
            </div>
            <CredCreator kind="key" onCreate={createKey} />
          </section>

          {/* OAuth clients */}
          <section className="rounded-2xl border border-slate-200 p-5" data-testid="dev-oauth-section">
            <h2 className="font-black text-slate-900">OAuth2 clients</h2>
            <p className="text-xs text-slate-500 mt-0.5">Exchange <code className="bg-slate-100 px-1 rounded">client_id/secret</code> at <code className="bg-slate-100 px-1 rounded">/api/v1/oauth/token</code> for a short-lived access token.</p>
            <div className="mt-3 divide-y divide-slate-100">
              {(state.oauth_clients || []).length === 0 && <div className="text-sm text-slate-400 py-2">No OAuth clients yet.</div>}
              {(state.oauth_clients || []).map((c) => (
                <div key={c.client_id} className="flex items-center justify-between py-2.5" data-testid={`dev-client-${c.client_id}`}>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <code className="text-xs font-bold text-slate-800">{c.client_id}</code><EnvBadge env={c.environment} />
                      {c.revoked_at && <span className="text-[10px] font-black text-red-600">REVOKED</span>}
                    </div>
                    <div className="text-[11px] text-slate-400 truncate">{c.label || "—"} · scopes: {(c.scopes || []).length}</div>
                  </div>
                  {!c.revoked_at && (
                    <button onClick={() => revokeClient(c.client_id)} data-testid={`dev-client-revoke-${c.client_id}`}
                      className="p-2 rounded-lg text-red-600 hover:bg-red-50"><Trash2 className="w-4 h-4" /></button>
                  )}
                </div>
              ))}
            </div>
            <CredCreator kind="client" onCreate={createClient} />
          </section>

          {/* Usage */}
          <section className="rounded-2xl border border-slate-200 p-5 mt-4" data-testid="dev-usage-section">
            <div className="flex items-center gap-1.5"><Activity className="w-4 h-4 text-slate-700" /><h2 className="font-black text-slate-900">Usage (last 30 days)</h2></div>
            {usage ? (
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-3">
                {[["API calls", usage.total_calls], ["Campaigns", usage.campaigns], ["Active", usage.active_campaigns], ["Spend", `$${((usage.spend_cents || 0) / 100).toFixed(2)}`], ["Impressions", usage.impressions], ["Clicks", usage.clicks], ["CTR", `${((usage.ctr || 0) * 100).toFixed(2)}%`]].map(([l, v]) => (
                  <div key={l} className="rounded-xl bg-slate-50 border border-slate-100 p-3">
                    <div className="text-[11px] font-bold text-slate-400">{l}</div>
                    <div className="text-lg font-black text-slate-900">{v ?? 0}</div>
                  </div>
                ))}
              </div>
            ) : <div className="text-sm text-slate-400 mt-2">No usage yet.</div>}
          </section>

          {/* Webhooks */}
          <section className="rounded-2xl border border-slate-200 p-5 mt-4" data-testid="dev-webhooks-section">
            <h2 className="font-black text-slate-900">Webhooks</h2>
            <p className="text-xs text-slate-500 mt-0.5">We POST signed events. Verify with <code className="bg-slate-100 px-1 rounded">X-FUUSIC-Signature</code>. Rotate the secret or replay a delivery anytime.</p>
            <div className="mt-3 divide-y divide-slate-100">
              {webhooks.length === 0 && <div className="text-sm text-slate-400 py-2">No webhooks yet.</div>}
              {webhooks.map((w) => (
                <div key={w.webhook_id} className="py-2.5" data-testid={`dev-webhook-${w.webhook_id}`}>
                  <div className="flex items-center justify-between">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2"><code className="text-xs font-bold text-slate-800 truncate">{w.url}</code><EnvBadge env={w.environment} /></div>
                      <div className="text-[11px] text-slate-400 truncate">{(w.events || []).length} events · last: {w.last_delivery_at ? new Date(w.last_delivery_at).toLocaleString() : "never"}</div>
                    </div>
                    <div className="flex items-center gap-1">
                      <button onClick={() => pingWebhook(w.webhook_id)} title="Send test ping" data-testid={`dev-webhook-ping-${w.webhook_id}`} className="p-2 rounded-lg text-slate-600 hover:bg-slate-100"><Send className="w-4 h-4" /></button>
                      <button onClick={() => rotateSecret(w.webhook_id)} title="Rotate signing secret" data-testid={`dev-webhook-rotate-${w.webhook_id}`} className="p-2 rounded-lg text-slate-600 hover:bg-slate-100"><RefreshCw className="w-4 h-4" /></button>
                      <button onClick={() => toggleDeliveries(w.webhook_id)} title="Delivery log" data-testid={`dev-webhook-deliveries-${w.webhook_id}`} className="p-2 rounded-lg text-slate-600 hover:bg-slate-100">{expandedWh === w.webhook_id ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}</button>
                      <button onClick={() => deleteWebhook(w.webhook_id)} data-testid={`dev-webhook-delete-${w.webhook_id}`} className="p-2 rounded-lg text-red-600 hover:bg-red-50"><Trash2 className="w-4 h-4" /></button>
                    </div>
                  </div>
                  {expandedWh === w.webhook_id && (
                    <div className="mt-2 rounded-xl bg-slate-50 border border-slate-100 p-2.5" data-testid={`dev-webhook-delivery-log-${w.webhook_id}`}>
                      {(deliveries[w.webhook_id] || []).length === 0 ? (
                        <div className="text-[11px] text-slate-400 py-1">No deliveries yet.</div>
                      ) : (deliveries[w.webhook_id] || []).map((d) => (
                        <div key={d.delivery_id} className="flex items-center justify-between py-1 text-[11px]" data-testid={`dev-delivery-${d.delivery_id}`}>
                          <div className="min-w-0 truncate">
                            <span className={`font-black ${d.ok ? "text-green-600" : "text-red-600"}`}>{d.ok ? "OK" : (d.status_code || "FAIL")}</span>
                            <span className="text-slate-500"> · {d.event_type} · {d.ts ? new Date(d.ts).toLocaleTimeString() : ""}</span>
                          </div>
                          <button onClick={() => retryDelivery(w.webhook_id, d.delivery_id)} data-testid={`dev-delivery-retry-${d.delivery_id}`}
                            className="ml-2 shrink-0 text-[11px] font-black text-orange-600 hover:underline">Retry</button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
            <div className="mt-3">
              <label className="block text-[11px] font-bold text-slate-400 mb-1">Events (none = all)</label>
              <div className="flex flex-wrap gap-1.5" data-testid="dev-webhook-events">
                {whEventOptions.filter((e) => e !== "ping").map((ev) => {
                  const on = whSelected.includes(ev);
                  return (
                    <button key={ev} onClick={() => toggleEvent(ev)} data-testid={`dev-webhook-event-${ev}`}
                      className={`text-[11px] font-bold rounded-full px-2.5 py-1 border ${on ? "bg-slate-900 text-white border-slate-900" : "bg-white text-slate-600 border-slate-300"}`}>{ev}</button>
                  );
                })}
              </div>
            </div>
            <div className="flex flex-wrap items-end gap-2 mt-3">
              <div className="flex-1 min-w-[200px]">
                <label className="block text-[11px] font-bold text-slate-400 mb-1">Endpoint URL</label>
                <input value={whUrl} onChange={(e) => setWhUrl(e.target.value)} placeholder="https://your-app.com/webhooks/radiolife" data-testid="dev-webhook-url" className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
              </div>
              <div>
                <label className="block text-[11px] font-bold text-slate-400 mb-1">Environment</label>
                <select value={whEnv} onChange={(e) => setWhEnv(e.target.value)} data-testid="dev-webhook-env" className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold">
                  <option value="sandbox">Sandbox</option><option value="live">Live</option>
                </select>
              </div>
              <button onClick={createWebhook} data-testid="dev-webhook-create" className="inline-flex items-center gap-1.5 bg-slate-900 text-white font-black rounded-lg px-4 py-2 text-sm"><Plus className="w-4 h-4" />Add webhook</button>
            </div>
          </section>

          {/* API Explorer */}
          <section className="rounded-2xl border border-slate-200 p-5 mt-4" data-testid="dev-explorer-section">
            <div className="flex items-center gap-1.5"><Play className="w-4 h-4 text-slate-700" /><h2 className="font-black text-slate-900">API Explorer</h2></div>
            <p className="text-xs text-slate-500 mt-0.5">Try a read-only <code className="bg-slate-100 px-1 rounded">GET</code> against the live API with one of your keys. Nothing is stored.</p>
            <div className="mt-3 flex flex-wrap items-end gap-2">
              <div className="flex-1 min-w-[220px]">
                <label className="block text-[11px] font-bold text-slate-400 mb-1">API key</label>
                <input value={exKey} onChange={(e) => setExKey(e.target.value)} placeholder="rlk_test_… paste a key"
                  data-testid="dev-explorer-key" className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
              </div>
              <div>
                <label className="block text-[11px] font-bold text-slate-400 mb-1">Endpoint</label>
                <select value={exPath} onChange={(e) => setExPath(e.target.value)} data-testid="dev-explorer-path"
                  className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold">
                  {EXPLORER_PATHS.map((p) => <option key={p} value={p}>GET {p}</option>)}
                </select>
              </div>
              <button onClick={runExplorer} disabled={exBusy} data-testid="dev-explorer-send"
                className="inline-flex items-center gap-1.5 bg-orange-600 text-white font-black rounded-lg px-4 py-2 text-sm disabled:opacity-50">
                {exBusy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}Send
              </button>
            </div>
            {exResp && (
              <div className="mt-3" data-testid="dev-explorer-response">
                <div className={`text-xs font-black mb-1 ${String(exResp.status).startsWith("2") ? "text-green-600" : "text-red-600"}`}>HTTP {exResp.status} · {exResp.ms}ms</div>
                <pre className="max-h-72 overflow-auto rounded-xl bg-slate-900 text-slate-100 text-[11px] p-3">{JSON.stringify(exResp.body, null, 2)}</pre>
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}
