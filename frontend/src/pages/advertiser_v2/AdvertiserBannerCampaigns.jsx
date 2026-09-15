// Phase AD.11 — Advertiser banner campaigns dashboard + 5-step wizard.
// Route: /advertiser/dashboard/banner-campaigns
import { useEffect, useState, useRef } from "react";
import axios from "axios";
import {
  Plus, X, Loader2, AlertTriangle, CheckCircle2,
  Image as ImageIcon, ChevronRight, ChevronLeft,
} from "lucide-react";
import { useAdvertiser } from "@/pages/advertiser_v2/AdvertiserShell";
import { useDesignVariant } from "@/hooks/useDesignVariant";
import FlagshipSponsorUpsellBanner from "@/components/FlagshipSponsorUpsellBanner";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

const STATUS_STYLES = {
  draft:                        "bg-slate-500/15 text-slate-400 border border-slate-500/30",
  pending_admin:      "bg-amber-500/15 text-amber-400 border border-amber-500/30",
  approved:                "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30",
  live:                          "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30",
  rejected:                "bg-red-500/15 text-red-400 border border-red-500/30",
  requires_changes:  "bg-blue-500/15 text-blue-400 border border-blue-500/30",
  paused:                      "bg-orange-500/15 text-orange-400 border border-orange-500/30",
  completed:              "bg-slate-500/15 text-slate-400 border border-slate-500/30",
};

const ZONE_META = {
  landing_hero:      { label: "Landing hero",        dims: "1200×400" },
  station_detail:  { label: "Station detail",      dims: "970×250"  },
  games:                    { label: "Games grid",              dims: "970×250"  },
  browse_row:          { label: "Browse row inline",  dims: "728×200"  },
  wallet:                  { label: "Wallet top",              dims: "728×90"    },
  now_playing:        { label: "Now Playing",          dims: "320×180"  },
  bottom_bar:          { label: "Bottom bar",            dims: "728×90"    },
};


export default function AdvertiserBannerCampaigns() {
  const variant = useDesignVariant();
  const light = variant === "radiolife";
  const { active: advertiser, permissions } = useAdvertiser() || {};
  const [items, setItems] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [wizardOpen, setWizardOpen] = useState(false);
  const [toast, setToast] = useState(null);
  const [hints, setHints] = useState(null);

  const canManage = permissions?.has?.("can_manage_campaigns");
  const isBlocked = advertiser?.status === "blocked";
  const bg = light ? "bg-white text-slate-900" : "bg-slate-950 text-white";
  const muted = light ? "text-slate-500" : "text-slate-400";

  const showToast = (kind, msg) => {
    setToast({ kind, msg });
    setTimeout(() => setToast(null), 3500);
  };

  async function load() {
    if (!advertiser) return;
    setLoading(true);
    try {
      const [r, h] = await Promise.all([
        axios.get(`${API}/advertiser/${advertiser.advertiser_id}/banner-campaigns`),
        hints ? Promise.resolve({ data: hints })
                    : axios.get(`${API}/ad-pricing-hints`),
      ]);
      setItems(r.data.items || []);
      if (!hints) setHints(h.data);
      setError(null);
    } catch (err) {
      setError(err?.response?.data?.detail?.code || err.message);
    } finally { setLoading(false); }
  }
  useEffect(() => { load();
                                        }, [advertiser?.advertiser_id]);

  if (!advertiser) {
    return (
      <div className={`${bg} min-h-screen p-8`}>
        <div className={muted}>Loading advertiser context…</div>
      </div>
    );
  }

  return (
    <div className={`${bg} min-h-screen`} data-testid="advertiser-banner-page">
      <div className="max-w-none mx-auto px-4 py-8">
        <FlagshipSponsorUpsellBanner business_id={advertiser?.advertiser_id}
                                      source_page="advertiser_banners" />
        <div className="flex items-center justify-between flex-wrap gap-3 mb-6">
          <div>
            <div className="text-[10px] uppercase tracking-widest font-mono text-amber-500">
              Phase AD.11 · Banner Ads
            </div>
            <h1 className="text-3xl md:text-4xl xl:text-5xl font-black inline-flex items-center gap-2 mt-1">
              <ImageIcon className="w-7 h-7 xl:w-9 xl:h-9 text-amber-500" />
              Banner campaigns
            </h1>
            <p className={`text-sm mt-1 ${muted}`}>
              Buy banner placements across 7 zones (landing, browse, station,
              now-playing, wallet, games, bottom bar).  Auction is
              priority-based (CPM + VIP boost).
            </p>
          </div>
          {canManage && (
            <button onClick={() => setWizardOpen(true)}
                            disabled={isBlocked}
                            data-testid="advertiser-banner-new-button"
                            className={`inline-flex items-center gap-2 font-black text-sm px-4 py-2.5 rounded-full shadow-lg transition ${
                                                        isBlocked
                                                            ? "bg-slate-500/40 text-slate-400 cursor-not-allowed shadow-none"
                                                            : "bg-amber-500 text-slate-900 hover:bg-amber-400 shadow-amber-500/30"}`}>
              <Plus className="w-4 h-4" /> New campaign
            </button>
          )}
        </div>

        <RightRailSlotsPanel light={light} />

        {isBlocked && (
          <div className="rounded-2xl px-4 py-3 mb-4 bg-red-500/10 border border-red-500/40 text-red-300 text-sm inline-flex items-center gap-3"
                      data-testid="advertiser-banner-blocked-banner">
            <AlertTriangle className="w-5 h-5 shrink-0" />
            <div>
              <div className="font-black">Advertiser account blocked</div>
              <div className="text-xs opacity-90">
                Reason: {advertiser?.blocked_reason || "—"} · Contact support.
              </div>
            </div>
          </div>
        )}

        {loading ? (
          <div className={`inline-flex items-center gap-2 ${muted}`}><Loader2 className="w-4 h-4 animate-spin" /> Loading…</div>
        ) : error ? (
          <div className="rounded-xl px-4 py-3 bg-red-500/10 border border-red-500/40 text-red-400 text-sm"
                      data-testid="advertiser-banner-error">{String(error)}</div>
        ) : (items || []).length === 0 ? (
          <div className={`rounded-2xl px-6 py-14 text-center ${light ? "bg-slate-50 border border-slate-200" : "bg-slate-900/60 border border-slate-800"}`}
                      data-testid="advertiser-banner-empty">
            <ImageIcon className={`w-10 h-10 mx-auto mb-3 ${muted}`} />
            <div className="font-semibold">No banner campaigns yet.</div>
            <p className={`text-sm mt-1 ${muted}`}>
              Create your first campaign to reach RadioLife listeners across 7 placement zones.
            </p>
          </div>
        ) : (
          <div className={`rounded-2xl overflow-hidden ${light ? "bg-white border border-slate-200" : "bg-slate-900/60 border border-slate-800"}`}
                      data-testid="advertiser-banner-table">
            <div className={`hidden md:grid grid-cols-[2fr,110px,140px,120px,110px] gap-3 px-5 py-3 text-[10px] uppercase tracking-widest font-mono ${
                                        light ? "text-slate-500 bg-slate-50 border-b border-slate-200"
                                                      : "text-slate-500 bg-slate-950 border-b border-slate-800"}`}>
              <div>Campaign</div><div>Status</div><div>Zones</div>
              <div>Spend</div><div>Impressions</div>
            </div>
            {items.map((c) => (
              <div key={c.banner_id}
                            className={`grid md:grid-cols-[2fr,110px,140px,120px,110px] gap-3 px-5 py-4 items-center ${
                                        light ? "border-b border-slate-100 last:border-0"
                                                      : "border-b border-slate-800 last:border-0"}`}
                            data-testid={`advertiser-banner-row-${c.banner_id}`}>
                <div className="min-w-0">
                  <div className="font-semibold truncate">{c.title}</div>
                  <div className={`text-[11px] ${muted} truncate`}>
                    → {c.target_url}
                  </div>
                </div>
                <div>
                  <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] uppercase font-semibold tracking-wider ${
                                              STATUS_STYLES[c.status] || "bg-slate-500/15 text-slate-400"}`}
                              data-testid={`advertiser-banner-status-${c.banner_id}`}>
                    {c.status}
                  </span>
                </div>
                <div className={`text-[11px] font-mono ${muted}`}>
                  {(c.placement_zones || []).length} · {(c.placement_zones || []).slice(0,2).join(", ")}
                </div>
                <div className="text-sm font-mono">${((c.spent_cents || 0)/100).toFixed(2)} / ${((c.total_budget_cents || 0)/100).toFixed(2)}</div>
                <div className="text-sm font-mono">{c.impressions_count || 0}</div>
              </div>
            ))}
          </div>
        )}
      </div>

      {wizardOpen && (
        <BannerWizard
          advertiser={advertiser}
          hints={hints}
          light={light}
          onClose={() => setWizardOpen(false)}
          onDone={(msg) => {
            showToast("success", msg);
            setWizardOpen(false);
            load();
          }}
        />
      )}

      {toast && (
        <div className="fixed bottom-6 right-6 z-50 max-w-sm"
                    data-testid="advertiser-banner-toast">
          <div className={`${toast.kind === "error"
                                            ? "bg-red-500/15 border border-red-500/40 text-red-300"
                                            : "bg-emerald-500/15 border border-emerald-500/40 text-emerald-300"}
                                    rounded-lg px-4 py-3 shadow-xl text-sm font-medium`}>{toast.msg}</div>
        </div>
      )}
    </div>
  );
}


// ─── Sell the Rail — New Look V2 right-rail sponsored slots ──────────
// These are `banner_ads_v2` slot campaigns (the same engine that serves the
// V2 home right rail), so a purchased + approved campaign actually renders
// in the rail. Distinct from the zone-based banner campaigns above.
const RAIL_SLOTS = [
  { key: "right_rail_mpu_1", label: "Rail · Top",    dims: "300×250" },
  { key: "right_rail_mpu_2", label: "Rail · Middle", dims: "300×250" },
  { key: "right_rail_mpu_3", label: "Rail · Bottom", dims: "300×250" },
];
const RAIL_KEYS = new Set(RAIL_SLOTS.map((s) => s.key));

function RightRailSlotsPanel({ light }) {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);
  const [form, setForm] = useState({
    slot_keys: RAIL_SLOTS.map((s) => s.key),
    creative_image_url: "",
    click_url: "https://",
    total_budget: 500,
    end_date: new Date(Date.now() + 30 * 864e5).toISOString().slice(0, 10),
  });

  const cardBg = light ? "bg-white border-slate-200" : "bg-slate-900/60 border-slate-800";
  const muted = light ? "text-slate-500" : "text-slate-400";
  const inputCls = light
    ? "w-full px-3 py-2 rounded-lg text-sm bg-white border border-slate-300"
    : "w-full px-3 py-2 rounded-lg text-sm bg-slate-900 border border-slate-700";
  const labelCls = `block text-[10px] uppercase tracking-widest mb-1 font-mono ${muted}`;

  async function load() {
    try {
      const { data } = await axios.get(`${API}/ads/advertiser/banner-campaigns`, { withCredentials: true });
      setItems((data.items || []).filter((c) => (c.slot_keys || []).some((k) => RAIL_KEYS.has(k))));
    } catch (_e) { setItems([]); }
  }
  useEffect(() => { load(); }, []);

  const toggleSlot = (k) => setForm((f) => ({
    ...f,
    slot_keys: f.slot_keys.includes(k) ? f.slot_keys.filter((x) => x !== k) : [...f.slot_keys, k],
  }));

  async function buy() {
    if (!form.slot_keys.length) { setMsg({ kind: "error", text: "Pick at least one rail slot." }); return; }
    if (!/^https?:\/\/.+/.test(form.click_url)) { setMsg({ kind: "error", text: "Enter a valid click URL." }); return; }
    if (!/^https?:\/\/.+/.test(form.creative_image_url)) { setMsg({ kind: "error", text: "Enter a 300×250 creative image URL." }); return; }
    setBusy(true); setMsg(null);
    try {
      const create = await axios.post(`${API}/ads/advertiser/banner-campaigns`, {
        slot_keys: form.slot_keys,
        creative_image_url: form.creative_image_url,
        click_url: form.click_url,
        start_date: new Date().toISOString(),
        end_date: `${form.end_date}T23:59:59Z`,
        total_budget: Number(form.total_budget) || 0,
      }, { withCredentials: true });
      const cid = create.data.campaign_id;
      const co = await axios.post(`${API}/ads/advertiser/banner-campaigns/${cid}/checkout`, {}, { withCredentials: true });
      const url = co.data?.checkout_url;
      if (url && /^https?:\/\//.test(url)) { window.location.href = url; return; }
      setMsg({ kind: "success", text: "Rail slot purchased — submitted for review. It goes live once approved." });
      setOpen(false);
      setForm((f) => ({ ...f, creative_image_url: "", click_url: "https://" }));
      load();
    } catch (err) {
      setMsg({ kind: "error", text: err?.response?.data?.detail?.code || err.message || "Purchase failed." });
    } finally { setBusy(false); }
  }

  return (
    <div className={`rounded-2xl border ${cardBg} p-5 mb-6`} data-testid="advertiser-rail-panel">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-widest font-mono text-fuchsia-500">New Look V2 · Right Rail</div>
          <h2 className="text-xl font-black mt-0.5">Right-rail sponsored slots</h2>
          <p className={`text-sm ${muted}`}>Premium 300×250 units in the New Look V2 home right rail (desktop). House-filled until sold.</p>
        </div>
        <button onClick={() => setOpen((v) => !v)} data-testid="advertiser-rail-buy-toggle"
          className="inline-flex items-center gap-2 font-black text-sm px-4 py-2.5 rounded-full bg-fuchsia-500 text-white hover:bg-fuchsia-400 shadow-lg shadow-fuchsia-500/30">
          <Plus className="w-4 h-4" /> Buy rail slot
        </button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-4">
        {RAIL_SLOTS.map((s) => (
          <div key={s.key} data-testid={`advertiser-rail-slot-${s.key}`}
            className={`rounded-xl p-3 border ${light ? "border-slate-200 bg-slate-50" : "border-slate-800 bg-slate-950"}`}>
            <div className="aspect-[300/250] rounded-lg mb-2 grid place-items-center text-[10px] font-mono"
              style={{ background: "linear-gradient(135deg, rgba(168,85,247,0.18), rgba(236,72,153,0.14))", color: light ? "#7c3aed" : "#d8b4fe" }}>
              {s.dims}
            </div>
            <div className="text-sm font-black">{s.label}</div>
            <div className={`text-[10px] font-mono ${muted}`}>{s.key}</div>
          </div>
        ))}
      </div>

      {msg && (
        <div data-testid="advertiser-rail-msg"
          className={`mt-4 rounded-lg px-4 py-2 text-sm ${msg.kind === "error"
            ? "bg-red-500/10 border border-red-500/40 text-red-400"
            : "bg-emerald-500/10 border border-emerald-500/40 text-emerald-400"}`}>{msg.text}</div>
      )}

      {open && (
        <div className={`mt-4 rounded-xl border ${light ? "border-slate-200 bg-slate-50" : "border-slate-800 bg-slate-950"} p-4 space-y-3`}
          data-testid="advertiser-rail-form">
          <div>
            <label className={labelCls}>Slots</label>
            <div className="flex flex-wrap gap-2">
              {RAIL_SLOTS.map((s) => {
                const on = form.slot_keys.includes(s.key);
                return (
                  <button key={s.key} type="button" onClick={() => toggleSlot(s.key)}
                    data-testid={`advertiser-rail-pick-${s.key}`}
                    className={`px-3 py-1.5 rounded-full text-xs font-bold border-2 transition ${on
                      ? "border-fuchsia-500 bg-fuchsia-500/10 text-fuchsia-400"
                      : (light ? "border-slate-200 text-slate-500" : "border-slate-700 text-slate-400")}`}>
                    {s.label}
                  </button>
                );
              })}
            </div>
          </div>
          <div>
            <label className={labelCls}>Creative image URL (300×250) *</label>
            <input value={form.creative_image_url} onChange={(e) => setForm((f) => ({ ...f, creative_image_url: e.target.value }))}
              data-testid="advertiser-rail-creative" className={inputCls} placeholder="https://…/banner-300x250.jpg" />
          </div>
          <div>
            <label className={labelCls}>Click-through URL *</label>
            <input value={form.click_url} onChange={(e) => setForm((f) => ({ ...f, click_url: e.target.value }))}
              data-testid="advertiser-rail-clickurl" className={inputCls} placeholder="https://your-site.com/offer" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={labelCls}>Total budget (USD)</label>
              <input type="number" min="5" value={form.total_budget}
                onChange={(e) => setForm((f) => ({ ...f, total_budget: e.target.value }))}
                data-testid="advertiser-rail-budget" className={inputCls} />
            </div>
            <div>
              <label className={labelCls}>Run until</label>
              <input type="date" value={form.end_date}
                onChange={(e) => setForm((f) => ({ ...f, end_date: e.target.value }))}
                data-testid="advertiser-rail-enddate" className={inputCls} />
            </div>
          </div>
          <button onClick={buy} disabled={busy} data-testid="advertiser-rail-submit"
            className="inline-flex items-center gap-2 font-black text-sm px-4 py-2 rounded-full bg-emerald-500 text-slate-900 hover:bg-emerald-400 disabled:opacity-40">
            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : null} Buy & submit for review
          </button>
        </div>
      )}

      {items && items.length > 0 && (
        <div className="mt-5" data-testid="advertiser-rail-list">
          <div className={`text-[10px] uppercase tracking-widest font-mono ${muted} mb-2`}>Your rail campaigns</div>
          <div className="space-y-2">
            {items.map((c) => (
              <div key={c.campaign_id}
                className={`flex items-center gap-3 px-3 py-2 rounded-lg ${light ? "bg-slate-50 border border-slate-200" : "bg-slate-950 border border-slate-800"}`}
                data-testid={`advertiser-rail-row-${c.campaign_id}`}>
                {c.creative_image_url
                  ? <img src={c.creative_image_url} alt="" className="w-12 h-9 rounded object-cover" />
                  : <div className="w-12 h-9 rounded bg-slate-700" />}
                <div className="min-w-0 flex-1">
                  <div className="text-xs font-mono truncate">{(c.slot_keys || []).join(", ")}</div>
                  <div className={`text-[11px] ${muted} truncate`}>→ {c.click_url}</div>
                </div>
                <span className={`text-[10px] uppercase font-semibold px-2 py-0.5 rounded-full ${STATUS_STYLES[c.status] || "bg-slate-500/15 text-slate-400"}`}>
                  {c.status}
                </span>
                <div className={`text-[11px] font-mono ${muted}`}>{c.impressions || 0} impr</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── 5-step wizard ───────────────────────────────────────────────────
function BannerWizard({ advertiser, hints, light, onClose, onDone }) {
  const [step, setStep] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [bannerId, setBannerId] = useState(null);
  const [form, setForm] = useState({
    title: "",
    description: "",
    target_url: "https://",
    cta_text: "Learn more",
    sponsoring_merchant_id: "",
    placement_zones: ["landing_hero", "browse_row"],
    per_zone_cpm_cents: hints?.banner_zone_cpm_cents || {},
    total_budget_cents: 100000,   // $1000 default
    country_codes: ["AE", "US"],
    language: "",
    category_tags: ["food"],
  });
  const [creatives, setCreatives] = useState({});   // {zone: url}
  const fileInputs = useRef({});

  const inputCls = light
    ? "w-full px-3 py-2 rounded-lg text-sm bg-white border border-slate-300"
    : "w-full px-3 py-2 rounded-lg text-sm bg-slate-900 border border-slate-700";
  const labelCls = `block text-[10px] uppercase tracking-widest mb-1 font-mono ${light ? "text-slate-500" : "text-slate-400"}`;

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const toggleZone = (z) => setForm((f) => {
    const zones = f.placement_zones.includes(z)
      ? f.placement_zones.filter((x) => x !== z)
      : [...f.placement_zones, z];
    // Merge default CPM for newly-added zones.
    const cpm = { ...f.per_zone_cpm_cents };
    for (const zn of zones) {
      if (cpm[zn] == null) {
        cpm[zn] = hints?.banner_zone_cpm_cents?.[zn] || 300;
      }
    }
    return { ...f, placement_zones: zones, per_zone_cpm_cents: cpm };
  });

  async function saveDraft() {
    // First-time save creates the banner; subsequent PATCH.
    setBusy(true); setError(null);
    try {
      const payload = {
        ...form,
        per_zone_cpm_cents: Object.fromEntries(
          form.placement_zones.map((z) => [z, Number(form.per_zone_cpm_cents[z] || 300)])),
      };
      if (!bannerId) {
        const { data } = await axios.post(
          `${API}/advertiser/${advertiser.advertiser_id}/banner-campaigns`,
          payload, { withCredentials: true });
        setBannerId(data.banner_id);
        return data.banner_id;
      } else {
        await axios.patch(
          `${API}/advertiser/banner-campaigns/${bannerId}`,
          payload, { withCredentials: true });
        return bannerId;
      }
    } catch (err) {
      setError(err?.response?.data?.detail?.code || err.message);
      return null;
    } finally { setBusy(false); }
  }

  async function uploadCreative(zone, file) {
    let id = bannerId;
    if (!id) id = await saveDraft();
    if (!id) return;
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await axios.post(
        `${API}/advertiser/banner-campaigns/${id}/creative-upload?zone=${zone}`,
        fd, { withCredentials: true,
                    headers: { "Content-Type": "multipart/form-data" }});
      setCreatives((c) => ({ ...c, [zone]: data.creative_url }));
    } catch (err) {
      setError(err?.response?.data?.detail?.code || err.message);
    } finally { setBusy(false); }
  }

  async function publish() {
    setBusy(true); setError(null);
    try {
      const id = bannerId || await saveDraft();
      if (!id) return;
      await axios.post(
        `${API}/advertiser/banner-campaigns/${id}/publish`,
        {}, { withCredentials: true });
      onDone("Banner submitted for review.");
    } catch (err) {
      setError(err?.response?.data?.detail?.code || err.message);
    } finally { setBusy(false); }
  }

  const cardBg = light ? "bg-white" : "bg-slate-900";
  const border = light ? "border-slate-200" : "border-slate-800";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm overflow-y-auto"
              data-testid="advertiser-banner-wizard"
              onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className={`${cardBg} border ${border} rounded-2xl shadow-2xl max-w-2xl w-full my-8 ${light ? "text-slate-900" : "text-white"}`}>
        <div className={`px-6 py-4 border-b ${border} flex items-center justify-between`}>
          <div>
            <div className="text-[10px] uppercase tracking-widest font-mono text-amber-500">
              Step {step} / 5
            </div>
            <h2 className="text-lg font-black">
              {step === 1 && "Identity"}
              {step === 2 && "Zones + Creative"}
              {step === 3 && "Targeting"}
              {step === 4 && "Budget + CPM"}
              {step === 5 && "Review + Submit"}
            </h2>
          </div>
          <button onClick={onClose} data-testid="advertiser-banner-wizard-close"
                          className={`p-1.5 rounded-md ${light ? "hover:bg-slate-100" : "hover:bg-slate-800"}`}>
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6 space-y-4 max-h-[70vh] overflow-y-auto">
          {error && (
            <div className="rounded-lg px-4 py-2 bg-red-500/10 border border-red-500/40 text-red-400 text-sm inline-flex items-center gap-2">
              <AlertTriangle className="w-4 h-4" /> {String(error)}
            </div>
          )}

          {step === 1 && (
            <div data-testid="advertiser-banner-wizard-step-1" className="space-y-3">
              <div>
                <label className={labelCls}>Title *</label>
                <input value={form.title} onChange={(e) => set("title", e.target.value)}
                              data-testid="advertiser-banner-wizard-title"
                              className={inputCls} placeholder="Weekend Karak Special" />
              </div>
              <div>
                <label className={labelCls}>Description</label>
                <textarea value={form.description}
                                        onChange={(e) => set("description", e.target.value)}
                                        rows={3} className={inputCls}
                                        placeholder="A short internal description shown to reviewers." />
              </div>
              <div>
                <label className={labelCls}>Target URL *</label>
                <input value={form.target_url}
                              onChange={(e) => set("target_url", e.target.value)}
                              data-testid="advertiser-banner-wizard-url"
                              className={inputCls} placeholder="https://..." />
              </div>
              <div>
                <label className={labelCls}>CTA text</label>
                <input value={form.cta_text}
                              onChange={(e) => set("cta_text", e.target.value)}
                              data-testid="advertiser-banner-wizard-cta"
                              className={inputCls} placeholder="Learn more" />
              </div>
              <div>
                <label className={labelCls}>Sponsoring merchant (optional)</label>
                <input value={form.sponsoring_merchant_id}
                              onChange={(e) => set("sponsoring_merchant_id", e.target.value)}
                              className={inputCls} placeholder="biz_*" />
              </div>
            </div>
          )}

          {step === 2 && (
            <div data-testid="advertiser-banner-wizard-step-2" className="space-y-3">
              <label className={labelCls}>Placement zones *</label>
              <div className="grid grid-cols-2 gap-2">
                {Object.entries(ZONE_META).map(([z, m]) => {
                  const on = form.placement_zones.includes(z);
                  return (
                    <button key={z} onClick={() => toggleZone(z)}
                                    data-testid={`advertiser-banner-wizard-zone-${z}`}
                                    className={`p-3 rounded-lg text-left border-2 transition ${
                                                            on
                                                                ? "border-amber-500 bg-amber-500/10"
                                                                : (light ? "border-slate-200 hover:border-slate-300"
                                                                                        : "border-slate-800 hover:border-slate-700")}`}>
                      <div className="text-sm font-black">{m.label}</div>
                      <div className={`text-[10px] font-mono ${light ? "text-slate-500" : "text-slate-400"}`}>
                        {m.dims} · ${(hints?.banner_zone_cpm_cents?.[z] || 300)/100} CPM
                      </div>
                    </button>
                  );
                })}
              </div>
              <div className="mt-4">
                <label className={labelCls}>Upload creative per zone</label>
                <div className="space-y-2">
                  {form.placement_zones.map((z) => (
                    <div key={z}
                                  className={`flex items-center gap-2 p-2 rounded-lg ${light ? "bg-slate-50" : "bg-slate-950"}`}
                                  data-testid={`advertiser-banner-wizard-creative-row-${z}`}>
                      <div className="flex-1 min-w-0">
                        <div className="text-xs font-black">{ZONE_META[z].label}</div>
                        <div className={`text-[10px] font-mono ${light ? "text-slate-500" : "text-slate-400"}`}>
                          {ZONE_META[z].dims}
                        </div>
                      </div>
                      {creatives[z] ? (
                        <span data-testid={`advertiser-banner-wizard-creative-done-${z}`}
                                    className="text-[10px] font-black text-emerald-400 inline-flex items-center gap-1">
                          <CheckCircle2 className="w-3 h-3" /> uploaded
                        </span>
                      ) : (
                        <input type="file" accept="image/png,image/jpeg,image/webp"
                                      ref={(el) => (fileInputs.current[z] = el)}
                                      onChange={(e) => e.target.files?.[0] && uploadCreative(z, e.target.files[0])}
                                      data-testid={`advertiser-banner-wizard-upload-${z}`}
                                      className="text-xs" />
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {step === 3 && (
            <div data-testid="advertiser-banner-wizard-step-3" className="space-y-3">
              <div>
                <label className={labelCls}>Country codes (ISO-2, comma-separated)</label>
                <input value={(form.country_codes || []).join(", ")}
                              onChange={(e) => set("country_codes",
                                                                                  e.target.value.split(",").map((s) => s.trim()).filter(Boolean))}
                              data-testid="advertiser-banner-wizard-countries"
                              className={inputCls} placeholder="AE, US, IN" />
              </div>
              <div>
                <label className={labelCls}>Language (optional)</label>
                <input value={form.language || ""}
                              onChange={(e) => set("language", e.target.value)}
                              className={inputCls} placeholder="en" />
              </div>
              <div>
                <label className={labelCls}>Category tags (comma-separated)</label>
                <input value={(form.category_tags || []).join(", ")}
                              onChange={(e) => set("category_tags",
                                                                                  e.target.value.split(",").map((s) => s.trim()).filter(Boolean))}
                              data-testid="advertiser-banner-wizard-tags"
                              className={inputCls} placeholder="food, coffee, weekend" />
              </div>
            </div>
          )}

          {step === 4 && (
            <div data-testid="advertiser-banner-wizard-step-4" className="space-y-3">
              <div>
                <label className={labelCls}>Total budget (cents) *</label>
                <input type="number" value={form.total_budget_cents}
                              onChange={(e) => set("total_budget_cents", Number(e.target.value))}
                              min="100"
                              data-testid="advertiser-banner-wizard-budget"
                              className={inputCls} />
                <p className={`text-[11px] mt-1 ${light ? "text-slate-500" : "text-slate-400"}`}>
                  ${((form.total_budget_cents || 0)/100).toFixed(2)} total
                </p>
              </div>
              <label className={labelCls}>Per-zone CPM (cents per 1000 impressions)</label>
              <div className="space-y-2">
                {form.placement_zones.map((z) => (
                  <div key={z} className="flex items-center gap-2">
                    <div className="flex-1 text-xs font-black">{ZONE_META[z].label}</div>
                    <input type="number" min="10" max="100000"
                                  value={form.per_zone_cpm_cents[z] || ""}
                                  onChange={(e) => setForm((f) => ({
                                    ...f,
                                    per_zone_cpm_cents: { ...f.per_zone_cpm_cents,
                                                                                  [z]: Number(e.target.value) },
                                  }))}
                                  data-testid={`advertiser-banner-wizard-cpm-${z}`}
                                  className={`w-24 ${inputCls}`} />
                    <span className={`text-[10px] font-mono ${light ? "text-slate-500" : "text-slate-400"}`}>
                      = ${((form.per_zone_cpm_cents[z] || 0)/100).toFixed(2)} CPM
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {step === 5 && (
            <div data-testid="advertiser-banner-wizard-step-5" className="space-y-3">
              <div className={`rounded-xl p-4 ${light ? "bg-slate-50" : "bg-slate-950"}`}>
                <div className="text-xs font-black">{form.title}</div>
                <div className={`text-[11px] font-mono ${light ? "text-slate-500" : "text-slate-400"} truncate`}>
                  {form.target_url}
                </div>
                <div className="text-[11px] mt-1">
                  Zones: {form.placement_zones.join(", ")}
                </div>
                <div className="text-[11px]">
                  Budget: ${((form.total_budget_cents || 0)/100).toFixed(2)} · Countries: {form.country_codes.join(", ")}
                </div>
              </div>
              <div className={`text-xs ${light ? "text-slate-600" : "text-slate-400"}`}>
                Submitting will send this campaign to the Ad Review Queue.  It goes live after admin/ad-manager approval.
              </div>
            </div>
          )}
        </div>

        <div className={`px-6 py-4 border-t ${border} flex items-center justify-between gap-2`}>
          <button onClick={() => setStep((s) => Math.max(1, s - 1))}
                          disabled={step === 1 || busy}
                          data-testid="advertiser-banner-wizard-back"
                          className={`inline-flex items-center gap-1 text-sm px-3 py-2 rounded-full ${light ? "hover:bg-slate-100" : "hover:bg-slate-800"} disabled:opacity-40`}>
            <ChevronLeft className="w-4 h-4" /> Back
          </button>
          <div className="text-[10px] font-mono opacity-60">Step {step}/5</div>
          {step < 5 ? (
            <button onClick={async () => {
                if (step === 1 || step === 2) await saveDraft();
                setStep((s) => Math.min(5, s + 1));
              }}
              disabled={busy || (step === 1 && (!form.title || !form.target_url))
                                || (step === 2 && (form.placement_zones.length === 0
                                                                                      || form.placement_zones.some((z) => !creatives[z])))}
              data-testid="advertiser-banner-wizard-next"
              className="inline-flex items-center gap-1 text-sm font-black px-4 py-2 rounded-full bg-amber-500 text-slate-900 hover:bg-amber-400 disabled:opacity-40">
              {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
              Next <ChevronRight className="w-4 h-4" />
            </button>
          ) : (
            <button onClick={publish} disabled={busy}
                            data-testid="advertiser-banner-wizard-submit"
                            className="inline-flex items-center gap-1 text-sm font-black px-4 py-2 rounded-full bg-emerald-500 text-slate-900 hover:bg-emerald-400 disabled:opacity-40">
              {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
              Submit for review
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
