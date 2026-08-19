// Advertiser dashboard — Developer / API keys page.
// Self-serve management of RadioLife Ads API credentials (partner API keys +
// OAuth2 clients). Raw secrets are shown exactly once, on creation.
import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { KeyRound, Plus, Copy, Trash2, ShieldCheck, ExternalLink, Loader2 } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
const V1_BASE = `${process.env.REACT_APP_BACKEND_URL || ""}/api/v1`;

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

  const load = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/partner/account`);
      setState({ loading: false, ...r.data });
    } catch { setState({ loading: false, exists: false }); }
  }, []);
  useEffect(() => { load(); }, [load]);

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

  if (state.loading) return <div className="p-8 text-center text-slate-400"><Loader2 className="w-6 h-6 animate-spin inline" /></div>;

  return (
    <div className="max-w-3xl" data-testid="developer-api-page">
      <div className="flex items-center gap-2 mb-1">
        <KeyRound className="w-6 h-6 text-slate-900" />
        <h1 className="text-2xl font-black text-slate-900">API &amp; Keys</h1>
      </div>
      <p className="text-sm text-slate-500 mb-5">
        Connect your own systems to RadioLife to buy audio ads, banners, sponsorships and more, programmatically.
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
                <div key={k.key_id} className="flex items-center justify-between py-2.5" data-testid={`dev-key-${k.key_id}`}>
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
        </>
      )}
    </div>
  );
}
