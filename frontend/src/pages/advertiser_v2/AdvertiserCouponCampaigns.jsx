// Phase AD.4 — Advertiser Coupon Campaigns page.
// Route: /advertiser/dashboard/coupon-campaigns
import { useEffect, useState } from "react";
import axios from "axios";
import {
  Ticket, Plus, Loader2, AlertTriangle, PauseCircle, CheckCircle2,
  XCircle, TrendingUp, Send, RefreshCw, X, ChevronRight, Store,
} from "lucide-react";
import { useAdvertiser } from "@/pages/advertiser_v2/AdvertiserShell";
import { useDesignVariant } from "@/hooks/useDesignVariant";
import FlagshipSponsorUpsellBanner from "@/components/FlagshipSponsorUpsellBanner";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

const STATUS_STYLES = {
  draft:                    "bg-slate-500/15 text-slate-400",
  pending_admin:  "bg-blue-500/15 text-blue-400",
  approved:            "bg-emerald-500/15 text-emerald-500",
  live:                      "bg-emerald-500/15 text-emerald-500",
  paused:                "bg-amber-500/15 text-amber-500",
  rejected:            "bg-red-500/15 text-red-400",
  completed:          "bg-slate-500/15 text-slate-400",
};

const fmtCents = (c) => (c == null ? "—" : `$${(c/100).toFixed(2)}`);

export default function AdvertiserCouponCampaigns() {
  const variant = useDesignVariant();
  const light = variant === "radiolife";
  const { active: advertiser, permissions } = useAdvertiser() || {};
  const [tab, setTab] = useState("campaigns"); // campaigns | spend
  const [campaigns, setCampaigns] = useState(null);
  const [transactions, setTransactions] = useState(null);
  const [reviewBadges, setReviewBadges] = useState({});   // ADMOD.1
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [wizardOpen, setWizardOpen] = useState(false);
  const [toast, setToast] = useState(null);

  const canManage = permissions?.has?.("can_manage_campaigns");
  const isBlocked = advertiser?.status === "blocked";  // ADMOD.1

  const showToast = (kind, message) => {
    setToast({ kind, message });
    setTimeout(() => setToast(null), 4500);
  };

  async function load() {
    if (!advertiser) return;
    setLoading(true);
    try {
      const [c, t, b] = await Promise.all([
        axios.get(`${API}/advertiser/${advertiser.advertiser_id}/coupon-campaigns`),
        axios.get(`${API}/advertiser/${advertiser.advertiser_id}/coupon-transactions`),
        axios.get(`${API}/advertiser/${advertiser.advertiser_id}/review-badges?ad_type=coupon_campaign`)
          .catch(() => ({ data: { badges: {} } })),
      ]);
      setCampaigns(c.data.items || []);
      setTransactions(t.data);
      setReviewBadges(b.data.badges || {});
      setError(null);
    } catch (err) {
      setError(err?.response?.data?.detail?.code || err.message);
    } finally { setLoading(false); }
  }
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [advertiser]);

  async function publishCampaign(id) {
    try {
      await axios.post(`${API}/advertiser/coupon-campaigns/${id}/publish`);
      showToast("success", "Submitted for admin review");
      load();
    } catch (err) {
      const code = err?.response?.data?.detail?.code || "publish_failed";
      const detail = err?.response?.data?.detail?.detail || "";
      showToast("error", `${code}: ${detail}`);
    }
  }

  if (!advertiser) return null;
  const cardCls = light ? "bg-white border border-slate-200"
                                              : "bg-slate-900/60 border border-slate-800";
  const muted = light ? "text-slate-500" : "text-slate-400";

  return (
    <div className={`space-y-6 ${light ? "text-slate-900" : "text-white"}`}
              data-testid="advertiser-coupon-page">
      <FlagshipSponsorUpsellBanner business_id={advertiser?.advertiser_id}
                                    source_page="advertiser_coupons" />
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <div className="text-[10px] uppercase tracking-widest font-mono text-amber-500">
            Phase AD.4 · Pay per save
          </div>
          <h1 className="mt-1 text-3xl md:text-4xl xl:text-5xl font-black inline-flex items-center gap-2">
            <Ticket className="w-6 h-6 xl:w-8 xl:h-8 text-amber-500" /> Coupon Campaigns
          </h1>
          <p className={`text-sm mt-1 ${muted}`}>
            Brand-owned coupons.  Pay only when a customer saves.  70% goes to your sponsoring merchant.
          </p>
        </div>
        {canManage && (
          <button onClick={() => setWizardOpen(true)}
                          disabled={isBlocked}
                          data-testid="advertiser-coupon-new-button"
                          title={isBlocked ? "Advertiser blocked — cannot create new campaigns." : ""}
                          className={`inline-flex items-center gap-2 font-black text-sm px-4 py-2.5 rounded-full shadow-lg transition ${
                                                    isBlocked
                                                        ? "bg-slate-500/40 text-slate-400 cursor-not-allowed shadow-none"
                                                        : "bg-amber-500 text-slate-900 hover:bg-amber-400 shadow-amber-500/30"}`}>
            <Plus className="w-4 h-4" /> New campaign
          </button>
        )}
      </div>

      {/* ADMOD.1 — advertiser-blocked banner */}
      {isBlocked && (
        <div className="rounded-2xl px-4 py-3 bg-red-500/10 border border-red-500/40 text-red-300 text-sm inline-flex items-center gap-3"
                    data-testid="advertiser-blocked-banner">
          <AlertTriangle className="w-5 h-5 shrink-0" />
          <div>
            <div className="font-black">Advertiser account blocked</div>
            <div className="text-xs opacity-90">
              Reason: {advertiser?.blocked_reason || "—"} · Contact support to appeal.
            </div>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-2">
        {["campaigns", "spend"].map((t) => (
          <button key={t} onClick={() => setTab(t)}
                          data-testid={`advertiser-coupon-tab-${t}`}
                          className={`px-4 py-2 rounded-full text-sm font-black transition ${
                                              tab === t
                                                  ? "bg-amber-500 text-slate-900 shadow-lg shadow-amber-500/20"
                                                  : (light ? "bg-slate-100 text-slate-600 hover:bg-slate-200"
                                                                        : "bg-slate-800 text-slate-400 hover:bg-slate-700")}`}>
            {t === "campaigns" ? "Campaigns" : "Spend history"}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="flex items-center gap-2 py-8"><Loader2 className="animate-spin w-4 h-4" /> Loading…</div>
      ) : error ? (
        <div className="rounded-xl px-4 py-3 bg-red-500/10 border border-red-500/40 text-red-400 text-sm inline-flex items-center gap-2"
                    data-testid="advertiser-coupon-error">
          <AlertTriangle className="w-4 h-4" /> {String(error)}
        </div>
      ) : tab === "campaigns" ? (
        <div className={`${cardCls} rounded-2xl overflow-hidden`}
                    data-testid="advertiser-coupon-table">
          {(campaigns || []).length === 0 ? (
            <div className={`py-12 text-center text-sm ${muted}`}
                        data-testid="advertiser-coupon-empty">
              No campaigns yet.  Click <b>New campaign</b> to launch your first coupon.
            </div>
          ) : (
            <>
              <div className={`hidden md:grid grid-cols-[2fr,110px,120px,110px,110px,120px] gap-3 px-5 py-3 text-[10px] uppercase tracking-widest font-mono ${
                                        light ? "text-slate-500 bg-slate-50 border-b border-slate-200"
                                                      : "text-slate-500 bg-slate-950 border-b border-slate-800"}`}>
                <div>Title</div><div>Status</div><div>Inventory</div><div>CPS</div><div>Value</div><div>Actions</div>
              </div>
              {(campaigns || []).map((c) => (
                <div key={c.campaign_id}
                              className={`grid md:grid-cols-[2fr,110px,120px,110px,110px,120px] gap-3 px-5 py-4 items-center ${
                                          light ? "border-b border-slate-100 last:border-0"
                                                        : "border-b border-slate-800 last:border-0"}`}
                              data-testid={`advertiser-coupon-row-${c.campaign_id}`}>
                  <div className="min-w-0">
                    <div className="font-semibold truncate">{c.title || "(untitled)"}</div>
                    <div className={`text-[11px] ${muted} truncate`}>
                      {(c.category_tags || []).join(" · ") || "no tags"} · {c.sponsoring_merchant_id ? "sponsor set" : "no sponsor"}
                    </div>
                    {/* ADMOD.1 — surface reviewer notes when reviewer requires changes. */}
                    {reviewBadges[c.campaign_id]?.review_status === "requires_changes" && (
                      <div data-testid={`advertiser-coupon-changes-${c.campaign_id}`}
                                  className="mt-1.5 text-[11px] px-2 py-1 rounded-md bg-blue-500/15 text-blue-300 border border-blue-500/30">
                        <b>Reviewer requested changes:</b> {reviewBadges[c.campaign_id].review_notes || "—"}
                      </div>
                    )}
                    {reviewBadges[c.campaign_id]?.review_status === "rejected" && (
                      <div data-testid={`advertiser-coupon-rejected-${c.campaign_id}`}
                                  className="mt-1.5 text-[11px] px-2 py-1 rounded-md bg-red-500/15 text-red-300 border border-red-500/30">
                        <b>Rejected:</b> {reviewBadges[c.campaign_id].reject_reason || "—"}
                      </div>
                    )}
                  </div>
                  <div className="flex flex-col gap-1">
                    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] uppercase font-semibold tracking-wider ${
                                                        STATUS_STYLES[c.status] || "bg-slate-500/15 text-slate-400"}`}
                                  data-testid={`advertiser-coupon-status-${c.campaign_id}`}>
                      {c.status}
                      {c.auto_paused_reason && ` · ${c.auto_paused_reason.split("_")[0]}`}
                    </span>
                    {/* ADMOD.1 review badge */}
                    {reviewBadges[c.campaign_id] && (
                      <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[9px] uppercase font-semibold tracking-wider ${
                                                          reviewBadges[c.campaign_id].review_status === "approved"
                                                              ? "bg-emerald-500/15 text-emerald-400"
                                                              : reviewBadges[c.campaign_id].review_status === "rejected"
                                                                  ? "bg-red-500/15 text-red-400"
                                                                  : reviewBadges[c.campaign_id].review_status === "requires_changes"
                                                                      ? "bg-blue-500/15 text-blue-400"
                                                                      : "bg-amber-500/15 text-amber-400"}`}
                                    data-testid={`advertiser-coupon-review-${c.campaign_id}`}>
                        review: {reviewBadges[c.campaign_id].review_status}
                      </span>
                    )}
                  </div>
                  <div className="text-sm font-mono">
                    {c.saves_count}/{c.total_inventory}
                    <div className={`text-[10px] ${muted}`}>{c.inventory_remaining} left</div>
                  </div>
                  <div className="text-sm font-mono">
                    {c.pricing_model === "cpa" ? "CPA" : c.pricing_model === "hybrid" ? "HYB" : "CPS"}
                    <div className={`text-[10px] ${muted}`}>
                      {c.pricing_model === "cpa"
                        ? `${fmtCents(c.cost_per_action_cents)}/act`
                        : c.pricing_model === "hybrid"
                            ? `${fmtCents(c.cost_per_save_cents)}+${fmtCents(c.cost_per_action_cents)}`
                            : `${fmtCents(c.cost_per_save_cents)}/save`}
                    </div>
                  </div>
                  <div className="text-sm font-mono">{fmtCents(c.retail_value_cents)}<span className={`text-[10px] ${muted}`}> {c.value_currency}</span></div>
                  <div className="text-right">
                    {c.status === "draft" && (
                      <button onClick={() => publishCampaign(c.campaign_id)}
                                      data-testid={`advertiser-coupon-publish-${c.campaign_id}`}
                                      className="inline-flex items-center gap-1 text-xs font-bold px-3 py-1.5 rounded-full bg-emerald-500 text-slate-900 hover:bg-emerald-400">
                        <Send className="w-3 h-3" /> Publish
                      </button>
                    )}
                    {c.status === "pending_admin" && (
                      <span className={`text-[11px] ${muted}`}>awaiting admin</span>
                    )}
                    {(c.status === "live" || c.status === "paused") && (
                      <a href={`/offers?campaign=${c.campaign_id}`}
                            className={`inline-flex items-center gap-1 text-xs font-bold ${
                                              light ? "text-purple-600 hover:text-purple-700"
                                                            : "text-amber-500 hover:text-amber-400"}`}>
                        Preview <ChevronRight className="w-3 h-3" />
                      </a>
                    )}
                  </div>
                </div>
              ))}
            </>
          )}
        </div>
      ) : (
        <TransactionsTab data={transactions} light={light} muted={muted} cardCls={cardCls} />
      )}

      {toast && (
        <div className="fixed bottom-6 right-6 z-50 max-w-sm"
                    data-testid="advertiser-coupon-toast">
          <div className={`${toast.kind === "error"
                                            ? "bg-red-500/15 border border-red-500/40 text-red-300"
                                            : "bg-emerald-500/15 border border-emerald-500/40 text-emerald-300"}
                                    rounded-lg px-4 py-3 shadow-xl text-sm font-medium`}>{toast.message}</div>
        </div>
      )}

      {wizardOpen && (
        <CampaignWizard advertiserId={advertiser.advertiser_id}
                                            light={light}
                                            onClose={() => setWizardOpen(false)}
                                            onSuccess={(m) => { load(); showToast("success", m); }}
                                            onError={(m) => showToast("error", m)} />
      )}
    </div>
  );
}


function TransactionsTab({ data, light, muted, cardCls }) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3"
                  data-testid="advertiser-coupon-totals">
        <Stat label="Total saves" value={data?.totals?.saves || 0} light={light} testid="cs-total-saves" />
        <Stat label="Gross spend" value={fmtCents(data?.totals?.gross_cents)} light={light} accent testid="cs-total-gross" />
        <Stat label="Merchant share" value={fmtCents(data?.totals?.merchant_cents)} light={light} testid="cs-total-merchant" />
        <Stat label="Platform fee" value={fmtCents(data?.totals?.platform_cents)} light={light} testid="cs-total-platform" />
      </div>
      <div className={`${cardCls} rounded-2xl overflow-hidden`}>
        <div className={`hidden md:grid grid-cols-[2fr,1fr,90px,110px,110px] gap-3 px-5 py-3 text-[10px] uppercase tracking-widest font-mono ${
                                    light ? "text-slate-500 bg-slate-50 border-b border-slate-200"
                                                  : "text-slate-500 bg-slate-950 border-b border-slate-800"}`}>
          <div>Campaign</div><div>Sponsor</div><div>Saves</div><div>Gross</div><div>Merchant</div>
        </div>
        {(data?.per_campaign || []).length === 0 ? (
          <div className={`py-8 text-center text-sm ${muted}`}>No save events yet.</div>
        ) : (data.per_campaign.map((r) => (
          <div key={r.campaign_id}
                        className={`grid md:grid-cols-[2fr,1fr,90px,110px,110px] gap-3 px-5 py-4 items-center ${
                                  light ? "border-b border-slate-100 last:border-0"
                                                : "border-b border-slate-800 last:border-0"}`}
                        data-testid={`cs-row-${r.campaign_id}`}>
            <div className="min-w-0">
              <div className="font-semibold truncate">{r.title || "(untitled)"}</div>
              <div className={`text-[11px] ${muted}`}>
                {r.auto_paused_reason && <span className="text-amber-500 font-mono">{r.auto_paused_reason}</span>}
              </div>
            </div>
            <div className={`text-xs ${muted} truncate flex items-center gap-1`}>
              <Store className="w-3 h-3" /> {r.sponsoring_merchant_name || "—"}
            </div>
            <div className="text-sm font-mono">{r.saves}</div>
            <div className="text-sm font-mono">{fmtCents(r.gross_cents)}</div>
            <div className={`text-sm font-mono ${light ? "text-emerald-600" : "text-emerald-400"}`}>{fmtCents(r.merchant_cents)}</div>
          </div>
        )))}
      </div>
    </div>
  );
}


function Stat({ label, value, light, accent, testid }) {
  return (
    <div className={`rounded-xl p-4 ${light ? "bg-white border border-slate-200" : "bg-slate-900/60 border border-slate-800"}`}
              data-testid={testid}>
      <div className={`text-[10px] uppercase tracking-widest font-mono ${light ? "text-slate-500" : "text-slate-500"}`}>{label}</div>
      <div className={`mt-2 text-2xl font-black ${
                                  accent ? (light ? "text-amber-600" : "text-amber-400")
                                                    : (light ? "text-slate-900" : "text-white")}`}>{value}</div>
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════
// Wizard — 5 steps: identity → prize → CPS+inventory → targeting → review
// ═══════════════════════════════════════════════════════════════════
function CampaignWizard({ advertiserId, light, onClose, onSuccess, onError }) {
  const [step, setStep] = useState(1);
  const [merchants, setMerchants] = useState([]);
  const [busy, setBusy] = useState(false);
  const [pricingHints, setPricingHints] = useState(null);   // ADMOD.1
  const [form, setForm] = useState({
    title: "",
    description: "",
    terms: "",
    sponsoring_merchant_id: "",
    retail_value_dollars: "5",
    value_currency: "USD",
    // Phase N (M7) — pricing model.
    pricing_model: "cps",           // cps | cpa | hybrid
    cost_per_save_cents: 15,
    cost_per_action_cents: 200,
    total_inventory: 100,
    category_tags_csv: "food, coffee",
    country_codes_csv: "AE, US",
  });
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  useEffect(() => {
    // Lightweight merchant picker: pull from merchant_v2 shell endpoint.
    axios.get(`${API}/merchant/mine`).then(({ data }) =>
      setMerchants(data.items || [])).catch(() => {});
    // ADMOD.1 — recommended CPS by category (advisory tooltip).
    axios.get(`${API}/ad-pricing-hints`).then(({ data }) =>
      setPricingHints(data)).catch(() => {});
  }, []);

  // ADMOD.1 — compute the recommended CPS for the advertiser's chosen tags.
  const recommendedCps = (() => {
    if (!pricingHints) return null;
    const tags = form.category_tags_csv
      .split(",").map((s) => s.trim().toLowerCase()).filter(Boolean);
    for (const t of tags) {
      if (pricingHints.categories?.[t]) return pricingHints.categories[t];
    }
    return pricingHints.default_cents;
  })();

  const next = () => setStep((s) => Math.min(5, s + 1));
  const prev = () => setStep((s) => Math.max(1, s - 1));
  const canNext = () => {
    if (step === 1) return !!form.title.trim() && !!form.sponsoring_merchant_id;
    if (step === 2) return true;
    if (step === 3) {
      const pm = form.pricing_model;
      const cpsOk = (pm === "cpa") || Number(form.cost_per_save_cents) > 0;
      const cpaOk = (pm === "cps") || Number(form.cost_per_action_cents) > 0;
      return cpsOk && cpaOk && Number(form.total_inventory) > 0;
    }
    return true;
  };

  async function submit(publish = false) {
    setBusy(true);
    try {
      const payload = {
        title: form.title.trim(),
        description: form.description.trim() || null,
        terms: form.terms.trim() || null,
        sponsoring_merchant_id: form.sponsoring_merchant_id,
        retail_value_cents: Math.round(Number(form.retail_value_dollars) * 100),
        value_currency: form.value_currency,
        pricing_model: form.pricing_model,
        cost_per_save_cents:
          form.pricing_model === "cpa" ? 0
              : Number(form.cost_per_save_cents),
        cost_per_action_cents:
          form.pricing_model === "cps" ? 0
              : Number(form.cost_per_action_cents),
        total_inventory: Number(form.total_inventory),
        category_tags: form.category_tags_csv
                                            .split(",").map(s => s.trim().toLowerCase()).filter(Boolean),
        targeting: {
          country_codes: form.country_codes_csv.split(",")
                                          .map(s => s.trim().toUpperCase()).filter(Boolean),
        },
      };
      const resp = await axios.post(
        `${API}/advertiser/${advertiserId}/coupon-campaigns`, payload);
      const cid = resp.data.campaign_id;
      if (publish) {
        await axios.post(`${API}/advertiser/coupon-campaigns/${cid}/publish`);
        onSuccess(`Campaign submitted to admin for review.`);
      } else {
        onSuccess(`Draft saved — publish when ready.`);
      }
      onClose();
    } catch (err) {
      const code = err?.response?.data?.detail?.code || "create_failed";
      onError(`${code}`);
    } finally { setBusy(false); }
  }

  const inputCls = `w-full px-3 py-2 rounded-lg border text-sm ${
                          light ? "bg-white border-slate-300 text-slate-900"
                                        : "bg-slate-950 border-slate-800 text-white"} focus:outline-none focus:ring-2 focus:ring-amber-500`;
  const labelCls = `block text-xs uppercase tracking-wider font-mono mb-1 ${
                          light ? "text-slate-500" : "text-slate-400"}`;
  const bg = light ? "bg-white" : "bg-slate-900";
  const border = light ? "border-slate-200" : "border-slate-800";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm overflow-y-auto"
              data-testid="advertiser-coupon-wizard"
              onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className={`${bg} border ${border} rounded-2xl shadow-2xl max-w-lg w-full my-8`}>
        <div className={`px-6 py-4 border-b ${border} flex items-center justify-between`}>
          <div>
            <div className="text-[10px] uppercase tracking-widest font-mono text-amber-500">Step {step}/5</div>
            <h2 className="text-lg font-black">{[
              "Identity", "Prize", "Cost & inventory",
              "Targeting", "Review",
            ][step - 1]}</h2>
          </div>
          <button onClick={onClose}
                          data-testid="advertiser-coupon-wizard-close"
                          className={`p-1.5 rounded-md ${light ? "hover:bg-slate-100" : "hover:bg-slate-800"}`}>
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6 space-y-4 min-h-[280px]">
          {step === 1 && (
            <>
              <div>
                <label className={labelCls}>Title *</label>
                <input value={form.title} onChange={(e) => set("title", e.target.value)}
                              className={inputCls} placeholder="Free Karak upgrade"
                              data-testid="advertiser-coupon-wizard-title" />
              </div>
              <div>
                <label className={labelCls}>Sponsoring merchant *</label>
                <select value={form.sponsoring_merchant_id}
                                onChange={(e) => set("sponsoring_merchant_id", e.target.value)}
                                className={inputCls}
                                data-testid="advertiser-coupon-wizard-merchant">
                  <option value="">— pick a merchant —</option>
                  {merchants.map((m) => (
                    <option key={m.merchant_id || m.business_id}
                                    value={m.merchant_id || m.business_id}>
                      {m.name}
                    </option>
                  ))}
                </select>
                <p className={`text-[11px] mt-1 ${light ? "text-slate-500" : "text-slate-400"}`}>
                  This is the merchant your customers redeem at.  They receive 70% of every save fee.
                </p>
              </div>
              <div>
                <label className={labelCls}>Description</label>
                <textarea value={form.description} onChange={(e) => set("description", e.target.value)}
                                    rows={2} className={inputCls}
                                    placeholder="One free Karak upgrade this weekend only." />
              </div>
            </>
          )}

          {step === 2 && (
            <>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className={labelCls}>Retail value</label>
                  <input type="number" value={form.retail_value_dollars}
                                onChange={(e) => set("retail_value_dollars", e.target.value)}
                                className={inputCls} step="0.5"
                                data-testid="advertiser-coupon-wizard-retail-value" />
                </div>
                <div>
                  <label className={labelCls}>Currency</label>
                  <select value={form.value_currency}
                                  onChange={(e) => set("value_currency", e.target.value)}
                                  className={inputCls}>
                    {["USD","AED","EUR","GBP","INR"].map(c => <option key={c} value={c}>{c}</option>)}
                  </select>
                </div>
              </div>
              <div>
                <label className={labelCls}>Terms & conditions</label>
                <textarea value={form.terms} onChange={(e) => set("terms", e.target.value)}
                                    rows={3} className={inputCls}
                                    placeholder="One per customer. Valid at Dubai locations only." />
              </div>
            </>
          )}

          {step === 3 && (
            <>
              {/* Phase N (M7) — pricing model selector */}
              <div>
                <label className={labelCls}>Pricing model</label>
                <div className="grid grid-cols-3 gap-2"
                     data-testid="advertiser-coupon-wizard-pricing-model">
                  {[
                    {v: "cps",    label: "Pay per save",     hint: "Charged when a user saves"},
                    {v: "cpa",    label: "Pay per action",   hint: "Charged only when redeemed"},
                    {v: "hybrid", label: "Hybrid",            hint: "Small save fee + redemption fee"},
                  ].map((opt) => (
                    <button key={opt.v} type="button"
                            onClick={() => set("pricing_model", opt.v)}
                            data-testid={`advertiser-coupon-wizard-pm-${opt.v}`}
                            className={`px-3 py-2.5 rounded-lg text-left border ${
                              form.pricing_model === opt.v
                                ? (light
                                    ? "bg-amber-500 border-amber-500 text-white"
                                    : "bg-amber-500 border-amber-500 text-white")
                                : (light
                                    ? "bg-white border-slate-300 text-slate-900"
                                    : "bg-slate-950 border-slate-800 text-slate-200")}`}>
                      <div className="text-xs font-bold">{opt.label}</div>
                      <div className="text-[10px] opacity-80 mt-0.5">{opt.hint}</div>
                    </button>
                  ))}
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                {form.pricing_model !== "cpa" && (
                <div>
                  <label className={labelCls}>Cost per save (¢) *</label>
                  <input type="number" value={form.cost_per_save_cents}
                                onChange={(e) => set("cost_per_save_cents", e.target.value)}
                                min="1" max="100000" className={inputCls}
                                data-testid="advertiser-coupon-wizard-cps" />
                  <p className={`text-[11px] mt-1 ${light ? "text-slate-500" : "text-slate-400"}`}>
                    ${(Number(form.cost_per_save_cents)/100).toFixed(2)} per save
                  </p>
                  {recommendedCps !== null && (
                    <div data-testid="advertiser-coupon-wizard-cps-hint"
                                className={`mt-2 rounded-lg px-3 py-2 text-[11px] flex items-start gap-2 ${light ? "bg-amber-50 border border-amber-200 text-amber-800" : "bg-amber-500/10 border border-amber-500/30 text-amber-300"}`}>
                      <span className="mt-0.5">💡</span>
                      <div>
                        <b>Recommended for your category: {recommendedCps}¢</b>
                        <details className="mt-1">
                          <summary className="cursor-pointer opacity-80 hover:opacity-100">Learn more</summary>
                          <ul className="mt-1 space-y-0.5 pl-3 opacity-90">
                            {(pricingHints?.groups || []).map((g) => (
                              <li key={g.label}>{g.label}: <b>{g.cents}¢</b></li>
                            ))}
                          </ul>
                        </details>
                      </div>
                    </div>
                  )}
                </div>
                )}
                {form.pricing_model !== "cps" && (
                <div>
                  <label className={labelCls}>Cost per action (¢) *</label>
                  <input type="number" value={form.cost_per_action_cents}
                                onChange={(e) => set("cost_per_action_cents", e.target.value)}
                                min="1" max="100000" className={inputCls}
                                data-testid="advertiser-coupon-wizard-cpa" />
                  <p className={`text-[11px] mt-1 ${light ? "text-slate-500" : "text-slate-400"}`}>
                    ${(Number(form.cost_per_action_cents)/100).toFixed(2)} per redemption
                  </p>
                </div>
                )}
                <div>
                  <label className={labelCls}>Save cap (inventory) *</label>
                  <input type="number" value={form.total_inventory}
                                onChange={(e) => set("total_inventory", e.target.value)}
                                min="1" className={inputCls}
                                data-testid="advertiser-coupon-wizard-inventory" />
                  <p className={`text-[11px] mt-1 ${light ? "text-slate-500" : "text-slate-400"}`}>
                    {form.pricing_model === "cps" && (
                      <>Max total spend: ${((Number(form.cost_per_save_cents) * Number(form.total_inventory))/100).toFixed(2)}</>
                    )}
                    {form.pricing_model === "cpa" && (
                      <>Max total spend (if all redeem): ${((Number(form.cost_per_action_cents) * Number(form.total_inventory))/100).toFixed(2)}</>
                    )}
                    {form.pricing_model === "hybrid" && (
                      <>Max total spend (if all redeem): ${(((Number(form.cost_per_save_cents) + Number(form.cost_per_action_cents)) * Number(form.total_inventory))/100).toFixed(2)}</>
                    )}
                  </p>
                </div>
              </div>
              <div className={`rounded-lg p-3 text-xs ${light ? "bg-amber-50 border border-amber-200 text-amber-800" : "bg-amber-500/10 border border-amber-500/30 text-amber-300"}`}>
                Auto-pause hits when the cap is reached OR when your advertiser wallet drops below the CPS.
              </div>
            </>
          )}

          {step === 4 && (
            <>
              <div>
                <label className={labelCls}>Category tags (comma-separated)</label>
                <input value={form.category_tags_csv}
                              onChange={(e) => set("category_tags_csv", e.target.value)}
                              data-testid="advertiser-coupon-wizard-categories"
                              className={inputCls} placeholder="food, coffee, weekend" />
              </div>
              <div>
                <label className={labelCls}>Country codes (ISO-2, comma-separated)</label>
                <input value={form.country_codes_csv}
                              onChange={(e) => set("country_codes_csv", e.target.value)}
                              data-testid="advertiser-coupon-wizard-countries"
                              className={inputCls} placeholder="AE, US" />
                <p className={`text-[11px] mt-1 ${light ? "text-slate-500" : "text-slate-400"}`}>
                  Leave blank to show worldwide.
                </p>
              </div>
            </>
          )}

          {step === 5 && (
            <div className={`rounded-lg p-4 space-y-2 text-sm ${light ? "bg-slate-50 border border-slate-200" : "bg-slate-950 border border-slate-800"}`}
                        data-testid="advertiser-coupon-wizard-review">
              <div className="flex justify-between"><span className="opacity-60">Title</span><b>{form.title}</b></div>
              <div className="flex justify-between"><span className="opacity-60">Sponsor</span><b>{(merchants.find(m => (m.merchant_id||m.business_id) === form.sponsoring_merchant_id) || {}).name || "—"}</b></div>
              <div className="flex justify-between"><span className="opacity-60">Prize value</span><b>{form.retail_value_dollars} {form.value_currency}</b></div>
              <div className="flex justify-between"><span className="opacity-60">Pricing model</span><b data-testid="advertiser-coupon-wizard-review-pm">{form.pricing_model.toUpperCase()}</b></div>
              {form.pricing_model !== "cpa" && (
                <div className="flex justify-between"><span className="opacity-60">Cost per save</span><b>${(Number(form.cost_per_save_cents)/100).toFixed(2)}</b></div>
              )}
              {form.pricing_model !== "cps" && (
                <div className="flex justify-between"><span className="opacity-60">Cost per action</span><b data-testid="advertiser-coupon-wizard-review-cpa">${(Number(form.cost_per_action_cents)/100).toFixed(2)}</b></div>
              )}
              <div className="flex justify-between"><span className="opacity-60">Save cap</span><b>{form.total_inventory}</b></div>
              <div className="flex justify-between"><span className="opacity-60">Max spend</span>
                <b className="text-amber-500">
                  ${(((
                      (form.pricing_model !== "cpa" ? Number(form.cost_per_save_cents) : 0)
                      + (form.pricing_model !== "cps" ? Number(form.cost_per_action_cents) : 0)
                    ) * Number(form.total_inventory))/100).toFixed(2)}
                </b></div>
              <div className="flex justify-between"><span className="opacity-60">Categories</span><b>{form.category_tags_csv}</b></div>
              <div className="flex justify-between"><span className="opacity-60">Countries</span><b>{form.country_codes_csv || "worldwide"}</b></div>
            </div>
          )}
        </div>

        <div className={`px-6 py-4 border-t ${border} flex items-center justify-between gap-2`}>
          <button onClick={step === 1 ? onClose : prev} disabled={busy}
                          data-testid="advertiser-coupon-wizard-back"
                          className={`px-4 py-2 rounded-full text-sm font-semibold ${
                                              light ? "text-slate-700 hover:bg-slate-100"
                                                            : "text-slate-300 hover:bg-slate-800"}`}>
            {step === 1 ? "Cancel" : "Back"}
          </button>
          {step < 5 ? (
            <button onClick={next} disabled={!canNext() || busy}
                            data-testid="advertiser-coupon-wizard-next"
                            className="inline-flex items-center gap-2 bg-amber-500 text-slate-900 hover:bg-amber-400 rounded-full font-black px-6 py-2 disabled:opacity-50">
              Next <ChevronRight className="w-4 h-4" />
            </button>
          ) : (
            <div className="flex gap-2">
              <button onClick={() => submit(false)} disabled={busy}
                              data-testid="advertiser-coupon-wizard-save-draft"
                              className={`px-4 py-2 rounded-full text-sm font-semibold ${
                                              light ? "border border-slate-300 hover:bg-slate-100"
                                                            : "border border-slate-700 hover:bg-slate-800"}`}>
                Save draft
              </button>
              <button onClick={() => submit(true)} disabled={busy}
                              data-testid="advertiser-coupon-wizard-publish"
                              className="inline-flex items-center gap-2 bg-emerald-500 text-slate-900 hover:bg-emerald-400 rounded-full font-black px-6 py-2 disabled:opacity-50">
                {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                Publish
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
