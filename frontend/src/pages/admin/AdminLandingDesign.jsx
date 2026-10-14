// Admin → Appearance → Public Social Landing (§21). Enable the landing, set the
// default public theme, hero copy/CTAs, station-count copy, and house/external
// promo controls. Writes the shared `landing_config` doc consumed by fuusic.com.
import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { Loader2, Save, ExternalLink, Plus, Trash2, Check } from "lucide-react";
import AdminPageHeader from "@/components/AdminPageHeader";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

const HOUSE_PROMOS = [
  { id: "premium", name: "FUUSIC Premium" },
  { id: "business", name: "FUUSIC for Business" },
  { id: "bigpoints", name: "BigPoints" },
  { id: "dining", name: "Dining Club" },
  { id: "invite", name: "Invite Friends" },
];

function Toggle({ on, onChange, testid }) {
  return (
    <button type="button" data-testid={testid} onClick={() => onChange(!on)}
      className={`relative w-11 h-6 rounded-full transition ${on ? "bg-violet-500" : "bg-white/15"}`}>
      <span className={`absolute top-0.5 w-5 h-5 rounded-full bg-white transition ${on ? "left-[22px]" : "left-0.5"}`} />
    </button>
  );
}

function Field({ label, children }) {
  return (
    <label className="block mb-4">
      <span className="block text-xs font-bold uppercase tracking-wide text-white/50 mb-1.5">{label}</span>
      {children}
    </label>
  );
}
const input = "w-full px-3 py-2.5 rounded-xl bg-white/5 border border-white/10 text-white text-sm outline-none focus:border-violet-400";

export default function AdminLandingDesign() {
  const [cfg, setCfg] = useState(null);
  const [opts, setOpts] = useState({ themes: ["light", "dark", "system"], station_copy: {} });
  const [busy, setBusy] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [err, setErr] = useState(null);
  const [ext, setExt] = useState({ name: "", text: "", cta_label: "Learn More", cta_to: "/shop", image_url: "" });

  const load = useCallback(async () => {
    setBusy(true); setErr(null);
    try {
      const { data } = await axios.get(`${API}/admin/landing-config`, { withCredentials: true });
      setCfg(data.config); setOpts(data.options || opts);
    } catch (e) { setErr(e?.response?.data?.detail || e.message); }
    finally { setBusy(false); }
  }, []); // eslint-disable-line

  useEffect(() => { load(); }, [load]);

  const setHero = (k, v) => setCfg((c) => ({ ...c, hero: { ...(c.hero || {}), [k]: v } }));
  const disabledSet = new Set(cfg?.promos?.disabled || []);
  const togglePromo = (id) => {
    const next = new Set(disabledSet);
    next.has(id) ? next.delete(id) : next.add(id);
    setCfg((c) => ({ ...c, promos: { ...(c.promos || {}), disabled: [...next] } }));
  };
  const addExternal = () => {
    if (!ext.name.trim()) return;
    const id = `ext_${Date.now()}`;
    const list = [...(cfg.promos?.external || []), { id, sponsored: true, house: false, ...ext }];
    setCfg((c) => ({ ...c, promos: { ...(c.promos || {}), external: list } }));
    setExt({ name: "", text: "", cta_label: "Learn More", cta_to: "/shop", image_url: "" });
  };
  const removeExternal = (id) =>
    setCfg((c) => ({ ...c, promos: { ...(c.promos || {}), external: (c.promos?.external || []).filter((e) => e.id !== id) } }));

  const save = async () => {
    setSaving(true); setErr(null); setSaved(false);
    try {
      const { data } = await axios.put(`${API}/admin/landing-config`, cfg, { withCredentials: true });
      setCfg(data.config); setSaved(true); setTimeout(() => setSaved(false), 2200);
    } catch (e) { setErr(e?.response?.data?.detail || e.message); }
    finally { setSaving(false); }
  };

  return (
    <div className="min-h-screen bg-[#0a0e1a] text-white">
      <AdminPageHeader title="Public Social Landing"
        subtitle="Configure the fuusic.com social-first homepage (Light/Dark, hero, promos)"
        breadcrumbs={[{ label: "Admin", to: "/admin" }, { label: "Appearance" }]} />

      <div className="max-w-[1100px] mx-auto px-4 sm:px-6 py-6">
        {busy ? (
          <div className="grid place-items-center py-24 text-white/50"><Loader2 className="animate-spin" /></div>
        ) : !cfg ? (
          <div className="text-red-400">{String(err || "Failed to load")}</div>
        ) : (
          <div className="grid lg:grid-cols-2 gap-6">
            {/* General */}
            <section className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
              <h2 className="text-lg font-black mb-4">General</h2>
              <div className="flex items-center justify-between mb-4">
                <span className="text-sm font-semibold">Enable New Social Landing</span>
                <Toggle testid="ald-enabled" on={cfg.new_landing_enabled !== false}
                  onChange={(v) => setCfg((c) => ({ ...c, new_landing_enabled: v }))} />
              </div>
              <div className="flex items-center justify-between mb-4">
                <span className="text-sm font-semibold">Allow Public Theme Switching</span>
                <Toggle testid="ald-allow-switch" on={cfg.allow_theme_switch !== false}
                  onChange={(v) => setCfg((c) => ({ ...c, allow_theme_switch: v }))} />
              </div>
              <Field label="Default Public Theme">
                <select data-testid="ald-theme" className={input} value={cfg.default_theme || "light"}
                  onChange={(e) => setCfg((c) => ({ ...c, default_theme: e.target.value }))}>
                  {opts.themes.map((th) => <option key={th} value={th}>{th}</option>)}
                </select>
              </Field>
              <Field label="Radio Station Copy">
                <select data-testid="ald-station-copy" className={input} value={cfg.station_copy || "thousands"}
                  onChange={(e) => setCfg((c) => ({ ...c, station_copy: e.target.value }))}>
                  {Object.entries(opts.station_copy || {}).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </Field>
              <div className="flex gap-2 mt-2">
                <a href="/" target="_blank" rel="noreferrer"
                  className="inline-flex items-center gap-1.5 text-xs font-bold px-3 py-2 rounded-lg bg-white/5 border border-white/10 hover:bg-white/10">
                  <ExternalLink size={13} /> Open Landing
                </a>
                <a href="/?landing=classic" target="_blank" rel="noreferrer"
                  className="inline-flex items-center gap-1.5 text-xs font-bold px-3 py-2 rounded-lg bg-white/5 border border-white/10 hover:bg-white/10">
                  <ExternalLink size={13} /> Open Classic
                </a>
              </div>
            </section>

            {/* Hero */}
            <section className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
              <h2 className="text-lg font-black mb-4">Hero</h2>
              <Field label="Headline"><input data-testid="ald-headline" className={input}
                value={cfg.hero?.headline || ""} onChange={(e) => setHero("headline", e.target.value)} /></Field>
              <Field label="Subheadline"><input className={input}
                value={cfg.hero?.subheadline || ""} onChange={(e) => setHero("subheadline", e.target.value)} /></Field>
              <Field label="Supporting copy"><textarea className={input} rows={3}
                value={cfg.hero?.supporting || ""} onChange={(e) => setHero("supporting", e.target.value)} /></Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Primary CTA"><input className={input}
                  value={cfg.hero?.primary_cta_label || ""} onChange={(e) => setHero("primary_cta_label", e.target.value)} /></Field>
                <Field label="Secondary CTA"><input className={input}
                  value={cfg.hero?.secondary_cta_label || ""} onChange={(e) => setHero("secondary_cta_label", e.target.value)} /></Field>
              </div>
            </section>

            {/* Promos */}
            <section className="rounded-2xl border border-white/10 bg-white/[0.03] p-5 lg:col-span-2">
              <h2 className="text-lg font-black mb-4">Sponsored &amp; Discover promos</h2>
              <div className="grid sm:grid-cols-2 gap-6">
                <div>
                  <div className="text-xs font-bold uppercase tracking-wide text-white/50 mb-2">House promos</div>
                  {HOUSE_PROMOS.map((p) => (
                    <div key={p.id} className="flex items-center justify-between py-2 border-b border-white/5">
                      <span className="text-sm">{p.name}</span>
                      <Toggle testid={`ald-house-${p.id}`} on={!disabledSet.has(p.id)} onChange={() => togglePromo(p.id)} />
                    </div>
                  ))}
                </div>
                <div>
                  <div className="text-xs font-bold uppercase tracking-wide text-white/50 mb-2">External promos</div>
                  {(cfg.promos?.external || []).map((e) => (
                    <div key={e.id} className="flex items-center justify-between py-2 border-b border-white/5">
                      <span className="text-sm truncate">{e.name} <span className="text-white/40">· {e.cta_label}</span></span>
                      <button onClick={() => removeExternal(e.id)} className="text-red-400 p-1"><Trash2 size={15} /></button>
                    </div>
                  ))}
                  <div className="mt-3 space-y-2">
                    <input className={input} placeholder="Business name" value={ext.name}
                      onChange={(e) => setExt({ ...ext, name: e.target.value })} />
                    <input className={input} placeholder="Short text" value={ext.text}
                      onChange={(e) => setExt({ ...ext, text: e.target.value })} />
                    <div className="grid grid-cols-2 gap-2">
                      <input className={input} placeholder="CTA label" value={ext.cta_label}
                        onChange={(e) => setExt({ ...ext, cta_label: e.target.value })} />
                      <input className={input} placeholder="CTA link (/shop)" value={ext.cta_to}
                        onChange={(e) => setExt({ ...ext, cta_to: e.target.value })} />
                    </div>
                    <input className={input} placeholder="Image URL (optional)" value={ext.image_url}
                      onChange={(e) => setExt({ ...ext, image_url: e.target.value })} />
                    <button onClick={addExternal} data-testid="ald-add-external"
                      className="inline-flex items-center gap-1.5 text-xs font-bold px-3 py-2 rounded-lg bg-violet-500/20 text-violet-300 border border-violet-400/30">
                      <Plus size={14} /> Add external promo
                    </button>
                  </div>
                </div>
              </div>
            </section>
          </div>
        )}

        {cfg && (
          <div className="sticky bottom-4 mt-6 flex items-center gap-3">
            <button data-testid="ald-save" onClick={save} disabled={saving}
              className="inline-flex items-center gap-2 px-6 py-3 rounded-xl font-bold text-white bg-gradient-to-r from-violet-500 to-pink-500 disabled:opacity-60">
              {saving ? <Loader2 className="animate-spin" size={17} /> : <Save size={17} />} Save landing
            </button>
            {saved && <span className="inline-flex items-center gap-1.5 text-emerald-400 text-sm font-bold"><Check size={16} /> Saved</span>}
            {err && <span className="text-red-400 text-sm">{String(err)}</span>}
          </div>
        )}
      </div>
    </div>
  );
}
