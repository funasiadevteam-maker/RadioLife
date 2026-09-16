// Soft-launch — Admin Launch Controls (/admin/launch).
// Toggle Business Setup Mode + consumer waitlist, set the merchant free-months
// offer, mint / revoke shareable preview access links, and view the waitlist.
import React, { useCallback, useEffect, useState } from "react";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
const cfg = { withCredentials: true };

function isoToLocalInput(iso) {
  try {
    const d = new Date(iso);
    const local = new Date(d.getTime() - d.getTimezoneOffset() * 60000);
    return local.toISOString().slice(0, 16);
  } catch (_e) { return ""; }
}

function Card({ title, children, testid }) {
  return (
    <div data-testid={testid}
      className="rounded-2xl bg-slate-900/60 border border-slate-800 p-5">
      {title && <div className="text-sm font-black text-white mb-4">{title}</div>}
      {children}
    </div>
  );
}

function Toggle({ on, onChange, label, hint, testid }) {
  return (
    <div className="flex items-center justify-between gap-4 py-2">
      <div>
        <div className="text-sm font-semibold text-white">{label}</div>
        {hint && <div className="text-xs text-slate-400 mt-0.5">{hint}</div>}
      </div>
      <button type="button" onClick={() => onChange(!on)} data-testid={testid}
        className={`relative w-12 h-7 rounded-full transition-colors shrink-0 ${on ? "bg-emerald-500" : "bg-slate-700"}`}>
        <span className={`absolute top-0.5 w-6 h-6 rounded-full bg-white transition-all ${on ? "left-[22px]" : "left-0.5"}`} />
      </button>
    </div>
  );
}

export default function AdminLaunchControls() {
  const [settings, setSettings] = useState(null);
  const [tokens, setTokens] = useState([]);
  const [waitlist, setWaitlist] = useState({ total: 0, items: [] });
  const [months, setMonths] = useState(6);
  const [launchAt, setLaunchAt] = useState("");
  const [tokenLabel, setTokenLabel] = useState("");
  const [tokenMaxUses, setTokenMaxUses] = useState(0);
  const [tokenExpiry, setTokenExpiry] = useState(0);
  const [copied, setCopied] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [s, t, w] = await Promise.all([
        axios.get(`${API}/admin/launch-settings`, cfg),
        axios.get(`${API}/admin/preview-tokens`, cfg),
        axios.get(`${API}/admin/waitlist`, cfg),
      ]);
      setSettings(s.data);
      setMonths(s.data?.offer_months || 6);
      setLaunchAt(s.data?.launch_at ? isoToLocalInput(s.data.launch_at) : "");
      setTokens(t.data?.items || []);
      setWaitlist(w.data || { total: 0, items: [] });
    } catch (_e) { /* ignore */ }
  }, []);

  useEffect(() => { load(); }, [load]);

  const patch = useCallback(async (updates) => {
    setBusy(true);
    try {
      const r = await axios.patch(`${API}/admin/launch-settings`, updates, cfg);
      setSettings(r.data);
      setMonths(r.data?.offer_months || 6);
    } catch (_e) { /* ignore */ } finally { setBusy(false); }
  }, []);

  const createToken = useCallback(async () => {
    setBusy(true);
    try {
      await axios.post(`${API}/admin/preview-tokens`, {
        label: tokenLabel || undefined,
        max_uses: Number(tokenMaxUses) || 0,
        expires_days: Number(tokenExpiry) || 0,
      }, cfg);
      setTokenLabel(""); setTokenMaxUses(0); setTokenExpiry(0);
      await load();
    } catch (_e) { /* ignore */ } finally { setBusy(false); }
  }, [tokenLabel, tokenMaxUses, tokenExpiry, load]);

  const revokeToken = useCallback(async (tok) => {
    try { await axios.post(`${API}/admin/preview-tokens/${tok}/revoke`, {}, cfg); await load(); }
    catch (_e) { /* ignore */ }
  }, [load]);

  const linkFor = (tok) => `${window.location.origin}/preview?token=${tok}`;
  const copy = (tok) => {
    try { navigator.clipboard.writeText(linkFor(tok)); setCopied(tok); setTimeout(() => setCopied(""), 1500); }
    catch (_e) { /* ignore */ }
  };

  const mode = !!settings?.business_setup_mode_enabled;

  return (
    <div data-testid="admin-launch-controls" className="min-h-screen bg-slate-950 text-white px-4 sm:px-8 py-8">
      <div className="max-w-4xl mx-auto space-y-6">
        <div>
          <h1 className="text-2xl font-black">🚀 Launch Controls</h1>
          <p className="text-sm text-slate-400 mt-1">Business Setup Mode gates the listener app behind a Coming-Soon page while businesses set up.</p>
        </div>

        <Card title="Mode" testid="launch-mode-card">
          <div className={`mb-4 rounded-xl px-4 py-3 text-sm font-semibold ${mode ? "bg-amber-500/15 text-amber-300 border border-amber-500/30" : "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30"}`}
            data-testid="launch-mode-status">
            {mode ? "Business Setup Mode is ON — listeners see the Coming-Soon page." : "Business Setup Mode is OFF — the app is fully open to everyone."}
          </div>
          <Toggle on={mode} testid="launch-mode-toggle"
            onChange={(v) => patch({ business_setup_mode_enabled: v })}
            label="Business Setup Mode"
            hint="Locks Listen / Shop / Play / Social for the public. Admins, approved businesses and preview-token holders keep full access." />
          <Toggle on={!!settings?.waitlist_enabled} testid="launch-waitlist-toggle"
            onChange={(v) => patch({ waitlist_enabled: v })}
            label="Consumer waitlist"
            hint="Capture listener emails on the Coming-Soon page." />
          <div className="flex items-center justify-between gap-4 py-2">
            <div>
              <div className="text-sm font-semibold">Merchant free months</div>
              <div className="text-xs text-slate-400 mt-0.5">Waived monthly fee for the soft-launch period.</div>
            </div>
            <div className="flex items-center gap-2">
              <input type="number" min={1} max={24} value={months} data-testid="launch-months-input"
                onChange={(e) => setMonths(e.target.value)}
                className="w-20 h-9 rounded-lg bg-slate-800 border border-slate-700 px-3 text-sm" />
              <button type="button" disabled={busy} data-testid="launch-months-save"
                onClick={() => patch({ offer_months: Number(months) || 6 })}
                className="h-9 px-3 rounded-lg bg-purple-600 hover:bg-purple-500 text-sm font-semibold disabled:opacity-60">Save</button>
            </div>
          </div>
          <div className="flex items-center justify-between gap-4 py-2">
            <div>
              <div className="text-sm font-semibold">Launch date &amp; countdown</div>
              <div className="text-xs text-slate-400 mt-0.5">Shown as a live countdown on the Coming-Soon page (enter your local time). Flipping Business Setup Mode OFF emails the whole waitlist.</div>
            </div>
            <div className="flex items-center gap-2">
              <input type="datetime-local" value={launchAt} data-testid="launch-date-input"
                onChange={(e) => setLaunchAt(e.target.value)}
                className="h-9 rounded-lg bg-slate-800 border border-slate-700 px-3 text-sm" />
              <button type="button" disabled={busy} data-testid="launch-date-save"
                onClick={() => patch({ launch_at: launchAt ? new Date(launchAt).toISOString() : null })}
                className="h-9 px-3 rounded-lg bg-purple-600 hover:bg-purple-500 text-sm font-semibold disabled:opacity-60">Save</button>
            </div>
          </div>
        </Card>

        <Card title="Preview access links" testid="launch-tokens-card">
          <div className="grid grid-cols-1 sm:grid-cols-4 gap-2 mb-4">
            <input placeholder="Label (e.g. Acme QA)" value={tokenLabel} data-testid="token-label-input"
              onChange={(e) => setTokenLabel(e.target.value)}
              className="sm:col-span-2 h-10 rounded-lg bg-slate-800 border border-slate-700 px-3 text-sm" />
            <input type="number" min={0} placeholder="Max uses (0=∞)" value={tokenMaxUses || ""} data-testid="token-maxuses-input"
              onChange={(e) => setTokenMaxUses(e.target.value)}
              className="h-10 rounded-lg bg-slate-800 border border-slate-700 px-3 text-sm" />
            <input type="number" min={0} placeholder="Expires (days)" value={tokenExpiry || ""} data-testid="token-expiry-input"
              onChange={(e) => setTokenExpiry(e.target.value)}
              className="h-10 rounded-lg bg-slate-800 border border-slate-700 px-3 text-sm" />
          </div>
          <button type="button" disabled={busy} onClick={createToken} data-testid="token-create-btn"
            className="h-10 px-4 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-sm font-bold disabled:opacity-60">
            Generate link
          </button>

          <div className="mt-4 space-y-2" data-testid="token-list">
            {tokens.length === 0 && <div className="text-sm text-slate-500">No preview links yet.</div>}
            {tokens.map((t) => (
              <div key={t.token} data-testid={`token-row-${t.token}`}
                className={`rounded-xl border p-3 flex flex-wrap items-center gap-2 ${t.revoked ? "border-slate-800 opacity-50" : "border-slate-700"}`}>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-semibold truncate">{t.label || "Preview access"}</div>
                  <div className="text-[11px] text-slate-400 truncate font-mono">{linkFor(t.token)}</div>
                  <div className="text-[11px] text-slate-500 mt-0.5">
                    uses {t.uses || 0}{t.max_uses ? `/${t.max_uses}` : ""}{t.expires_at ? ` · expires ${new Date(t.expires_at).toLocaleDateString()}` : ""}{t.revoked ? " · REVOKED" : ""}
                  </div>
                </div>
                {!t.revoked && (
                  <>
                    <button type="button" onClick={() => copy(t.token)} data-testid={`token-copy-${t.token}`}
                      className="h-8 px-3 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-semibold">
                      {copied === t.token ? "Copied!" : "Copy link"}
                    </button>
                    <button type="button" onClick={() => revokeToken(t.token)} data-testid={`token-revoke-${t.token}`}
                      className="h-8 px-3 rounded-lg bg-rose-600/80 hover:bg-rose-500 text-xs font-semibold">Revoke</button>
                  </>
                )}
              </div>
            ))}
          </div>
        </Card>

        <Card title={`Consumer waitlist · ${waitlist.total}`} testid="launch-waitlist-card">
          <div className="space-y-1 max-h-72 overflow-auto">
            {(!waitlist.items || waitlist.items.length === 0) && <div className="text-sm text-slate-500">No signups yet.</div>}
            {(waitlist.items || []).map((w, i) => (
              <div key={w.email || i} className="flex items-center justify-between text-sm border-b border-slate-800/60 py-1.5">
                <span className="font-mono text-slate-200">{w.email}</span>
                <span className="text-[11px] text-slate-500">{w.city || ""} {w.created_at ? new Date(w.created_at).toLocaleDateString() : ""}</span>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
