// Phase AD.12a — Advertiser notification-ad campaigns dashboard + 5-step wizard.
// Route: /advertiser/dashboard/notification-campaigns
import { useEffect, useState, useRef } from "react";
import axios from "axios";
import {
  Plus, X, Loader2, AlertTriangle, CheckCircle2,
  BellRing, ChevronRight, ChevronLeft, Info,
} from "lucide-react";
import { useAdvertiser } from "@/pages/advertiser_v2/AdvertiserShell";
import { useDesignVariant } from "@/hooks/useDesignVariant";

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
  scheduled:              "bg-blue-500/15 text-blue-400 border border-blue-500/30",
};


export default function AdvertiserNotificationCampaigns() {
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
        axios.get(`${API}/advertiser/${advertiser.advertiser_id}/notification-campaigns`),
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
    <div className="space-y-6" data-testid="advertiser-notification-page">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-widest font-mono text-amber-500">
            Phase AD.12 · Notification Ads
          </div>
          <h1 className="text-3xl md:text-4xl xl:text-5xl font-black inline-flex items-center gap-2 mt-1">
            <BellRing className="w-7 h-7 text-amber-500" />
            Notification campaigns
          </h1>
          <p className={`text-sm mt-1 ${muted}`}>
            Reach RadioLife users right in their in-app inbox.  Billed per delivery.
            Push channel is on the roadmap — in-app only for now.
          </p>
        </div>
        {canManage && (
          <button onClick={() => setWizardOpen(true)}
                          disabled={isBlocked}
                          data-testid="advertiser-notification-new-button"
                          className={`inline-flex items-center gap-2 font-black text-sm px-4 py-2.5 rounded-full shadow-lg transition ${
                                                      isBlocked
                                                          ? "bg-slate-500/40 text-slate-400 cursor-not-allowed shadow-none"
                                                          : "bg-amber-500 text-slate-900 hover:bg-amber-400 shadow-amber-500/30"}`}>
            <Plus className="w-4 h-4" /> New notification
          </button>
        )}
      </div>

      {isBlocked && (
        <div className="rounded-2xl px-4 py-3 mb-4 bg-red-500/10 border border-red-500/40 text-red-300 text-sm inline-flex items-center gap-3"
                    data-testid="advertiser-notification-blocked-banner">
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
                    data-testid="advertiser-notification-error">{String(error)}</div>
      ) : (items || []).length === 0 ? (
        <div className={`rounded-2xl px-6 py-14 text-center ${light ? "bg-slate-50 border border-slate-200" : "bg-slate-900/60 border border-slate-800"}`}
                    data-testid="advertiser-notification-empty">
          <BellRing className={`w-10 h-10 mx-auto mb-3 ${muted}`} />
          <div className="font-semibold">No notification campaigns yet.</div>
          <p className={`text-sm mt-1 ${muted}`}>
            Nudge listeners with a relevant, timely message right in their inbox.
          </p>
        </div>
      ) : (
        <div className={`rounded-2xl overflow-hidden ${light ? "bg-white border border-slate-200" : "bg-slate-900/60 border border-slate-800"}`}
                    data-testid="advertiser-notification-table">
          <div className={`hidden md:grid grid-cols-[2fr,110px,120px,140px,110px] gap-3 px-5 py-3 text-[10px] uppercase tracking-widest font-mono ${
                                      light ? "text-slate-500 bg-slate-50 border-b border-slate-200"
                                                    : "text-slate-500 bg-slate-950 border-b border-slate-800"}`}>
            <div>Campaign</div><div>Status</div><div>Channel</div>
            <div>Spend</div><div>Delivered</div>
          </div>
          {items.map((c) => (
            <div key={c.notification_campaign_id}
                          className={`grid md:grid-cols-[2fr,110px,120px,140px,110px] gap-3 px-5 py-4 items-center ${
                                      light ? "border-b border-slate-100 last:border-0"
                                                    : "border-b border-slate-800 last:border-0"}`}
                          data-testid={`advertiser-notification-row-${c.notification_campaign_id}`}>
              <div className="min-w-0">
                <div className="font-semibold truncate">{c.title}</div>
                <div className={`text-[11px] ${muted} truncate`}>
                  {(c.body || "").slice(0, 80)}
                </div>
              </div>
              <div>
                <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] uppercase font-semibold tracking-wider ${
                                            STATUS_STYLES[c.status] || "bg-slate-500/15 text-slate-400"}`}
                            data-testid={`advertiser-notification-status-${c.notification_campaign_id}`}>
                  {c.status}
                </span>
              </div>
              <div className={`text-[11px] font-mono ${muted}`}>
                {c.channel === "push" || c.channel === "both"
                  ? <span className="text-amber-500">push (deferred)</span>
                  : "in-app"}
              </div>
              <div className="text-sm font-mono">${((c.spent_cents || 0)/100).toFixed(2)} / ${((c.budget_cents || 0)/100).toFixed(2)}</div>
              <div className="text-sm font-mono">{c.delivered_count || 0}</div>
            </div>
          ))}
        </div>
      )}

      {wizardOpen && (
        <NotificationWizard
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
                    data-testid="advertiser-notification-toast">
          <div className={`${toast.kind === "error"
                                            ? "bg-red-500/15 border border-red-500/40 text-red-300"
                                            : "bg-emerald-500/15 border border-emerald-500/40 text-emerald-300"}
                                    rounded-lg px-4 py-3 shadow-xl text-sm font-medium`}>{toast.msg}</div>
        </div>
      )}
    </div>
  );
}


// ─── 5-step wizard ───────────────────────────────────────────────────
function NotificationWizard({ advertiser, hints, light, onClose, onDone }) {
  const [step, setStep] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [campId, setCampId] = useState(null);
  const [form, setForm] = useState({
    title: "",
    body: "",
    cta_text: "Learn more",
    target_url: "https://",
    sponsoring_merchant_id: "",
    channel: "in_app",   // push is disabled
    delivery_schedule: "immediate",
    scheduled_at: "",
    trigger_type: "",
    targeting: {
      country_codes: ["AE"],
      language: "",
      category_tags: ["food"],
      min_user_tier: "",
    },
    budget_cents: 50000,      // $500 default
    cost_per_delivery_cents: 10,
    max_deliveries: 1000,
  });
  const [iconUploaded, setIconUploaded] = useState(false);
  const [showCpdTooltip, setShowCpdTooltip] = useState(false);
  const iconInputRef = useRef(null);

  const inputCls = light
    ? "w-full px-3 py-2 rounded-lg text-sm bg-white border border-slate-300"
    : "w-full px-3 py-2 rounded-lg text-sm bg-slate-900 border border-slate-700";
  const labelCls = `block text-[10px] uppercase tracking-widest mb-1 font-mono ${light ? "text-slate-500" : "text-slate-400"}`;

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const setTargeting = (k, v) => setForm((f) => ({
    ...f, targeting: { ...f.targeting, [k]: v }}));

  async function saveDraft() {
    setBusy(true); setError(null);
    try {
      const payload = { ...form };
      if (!campId) {
        const { data } = await axios.post(
          `${API}/advertiser/${advertiser.advertiser_id}/notification-campaigns`,
          payload, { withCredentials: true });
        setCampId(data.notification_campaign_id);
        return data.notification_campaign_id;
      } else {
        await axios.patch(
          `${API}/advertiser/notification-campaigns/${campId}`,
          payload, { withCredentials: true });
        return campId;
      }
    } catch (err) {
      setError(err?.response?.data?.detail?.code || err.message);
      return null;
    } finally { setBusy(false); }
  }

  async function uploadIcon(file) {
    let id = campId;
    if (!id) id = await saveDraft();
    if (!id) return;
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      await axios.post(
        `${API}/advertiser/notification-campaigns/${id}/creative-upload?slot=icon`,
        fd, { withCredentials: true,
                    headers: { "Content-Type": "multipart/form-data" }});
      setIconUploaded(true);
    } catch (err) {
      setError(err?.response?.data?.detail?.code || err.message);
    } finally { setBusy(false); }
  }

  async function publish() {
    setBusy(true); setError(null);
    try {
      const id = campId || await saveDraft();
      if (!id) return;
      await axios.post(
        `${API}/advertiser/notification-campaigns/${id}/publish`,
        {}, { withCredentials: true });
      onDone("Notification submitted for review.");
    } catch (err) {
      setError(err?.response?.data?.detail?.code || err.message);
    } finally { setBusy(false); }
  }

  const cardBg = light ? "bg-white" : "bg-slate-900";
  const border = light ? "border-slate-200" : "border-slate-800";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm overflow-y-auto"
              data-testid="advertiser-notification-wizard"
              onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className={`${cardBg} border ${border} rounded-2xl shadow-2xl max-w-2xl w-full my-8 ${light ? "text-slate-900" : "text-white"}`}>
        <div className={`px-6 py-4 border-b ${border} flex items-center justify-between`}>
          <div>
            <div className="text-[10px] uppercase tracking-widest font-mono text-amber-500">
              Step {step} / 5
            </div>
            <h2 className="text-lg font-black">
              {step === 1 && "Identity"}
              {step === 2 && "Creative"}
              {step === 3 && "Targeting + Delivery"}
              {step === 4 && "Budget + CPD"}
              {step === 5 && "Preview + Submit"}
            </h2>
          </div>
          <button onClick={onClose} data-testid="advertiser-notification-wizard-close"
                          className={`p-1.5 rounded-md ${light ? "hover:bg-slate-100" : "hover:bg-slate-800"}`}>
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6 space-y-4 max-h-[70vh] overflow-y-auto">
          {error && (
            <div className="rounded-lg px-4 py-2 bg-red-500/10 border border-red-500/40 text-red-400 text-sm inline-flex items-center gap-2"
                        data-testid="advertiser-notification-wizard-error">
              <AlertTriangle className="w-4 h-4" /> {String(error)}
            </div>
          )}

          {step === 1 && (
            <div data-testid="advertiser-notification-wizard-step-1" className="space-y-3">
              <div>
                <label className={labelCls}>Title *</label>
                <input value={form.title} onChange={(e) => set("title", e.target.value)}
                              data-testid="advertiser-notification-wizard-title"
                              maxLength={120}
                              className={inputCls} placeholder="Weekend Karak Special" />
              </div>
              <div>
                <label className={labelCls}>Body *</label>
                <textarea value={form.body}
                                        onChange={(e) => set("body", e.target.value)}
                                        rows={3}
                                        maxLength={500}
                                        data-testid="advertiser-notification-wizard-body"
                                        className={inputCls}
                                        placeholder="Grab a hot karak this weekend — 40% off partner cafes." />
                <div className={`text-[10px] font-mono ${light ? "text-slate-500" : "text-slate-400"} mt-1`}>
                  {(form.body || "").length}/500 characters
                </div>
              </div>
              <div>
                <label className={labelCls}>CTA text</label>
                <input value={form.cta_text}
                              onChange={(e) => set("cta_text", e.target.value)}
                              data-testid="advertiser-notification-wizard-cta"
                              maxLength={64}
                              className={inputCls} placeholder="See offer" />
              </div>
              <div>
                <label className={labelCls}>Target URL *</label>
                <input value={form.target_url}
                              onChange={(e) => set("target_url", e.target.value)}
                              data-testid="advertiser-notification-wizard-url"
                              className={inputCls} placeholder="https://..." />
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
            <div data-testid="advertiser-notification-wizard-step-2" className="space-y-3">
              <label className={labelCls}>Icon (required) — PNG/JPG/WEBP, ≤512KB</label>
              <div className={`flex items-center gap-3 p-3 rounded-lg ${light ? "bg-slate-50" : "bg-slate-950"}`}>
                {iconUploaded ? (
                  <span data-testid="advertiser-notification-wizard-icon-done"
                              className="text-[11px] font-black text-emerald-400 inline-flex items-center gap-1">
                    <CheckCircle2 className="w-4 h-4" /> Icon uploaded
                  </span>
                ) : (
                  <input type="file" ref={iconInputRef}
                                accept="image/png,image/jpeg,image/webp"
                                onChange={(e) => e.target.files?.[0] && uploadIcon(e.target.files[0])}
                                data-testid="advertiser-notification-wizard-icon"
                                className="text-xs" />
                )}
              </div>
              <p className={`text-[11px] ${light ? "text-slate-500" : "text-slate-400"}`}>
                A square icon (square PNG works best).  The icon appears at 48×48 in the inbox.
              </p>
            </div>
          )}

          {step === 3 && (
            <div data-testid="advertiser-notification-wizard-step-3" className="space-y-3">
              <div>
                <label className={labelCls}>Delivery channel</label>
                <div className="flex items-center gap-3">
                  <label className={`inline-flex items-center gap-2 px-3 py-2 rounded-lg border-2 ${
                                                      form.channel === "in_app"
                                                          ? "border-amber-500 bg-amber-500/10"
                                                          : (light ? "border-slate-200" : "border-slate-800")}
                                                  cursor-pointer`}>
                    <input type="radio" name="channel"
                                    checked={form.channel === "in_app"}
                                    onChange={() => set("channel", "in_app")}
                                    data-testid="advertiser-notification-wizard-channel-inapp"
                                    className="accent-amber-500" />
                    <span className="text-sm font-black">In-app</span>
                  </label>
                  <div className={`inline-flex items-center gap-2 px-3 py-2 rounded-lg border-2 border-dashed opacity-50 cursor-not-allowed
                                                  ${light ? "border-slate-200" : "border-slate-800"}`}
                              data-testid="advertiser-notification-wizard-channel-push-disabled"
                              title="Browser push is coming soon — in-app only for now.">
                    <input type="radio" disabled className="accent-amber-500" />
                    <span className="text-sm font-black">Browser push</span>
                    <span className="text-[9px] font-mono uppercase tracking-widest text-amber-500 bg-amber-500/10 px-1.5 py-0.5 rounded">
                      soon
                    </span>
                  </div>
                </div>
              </div>
              <div>
                <label className={labelCls}>Delivery schedule</label>
                <select value={form.delivery_schedule}
                                onChange={(e) => set("delivery_schedule", e.target.value)}
                                data-testid="advertiser-notification-wizard-schedule"
                                className={inputCls}>
                  <option value="immediate">Immediate (deliver on-approval)</option>
                  <option value="scheduled">Scheduled</option>
                  <option value="trigger_based">Trigger-based</option>
                </select>
              </div>
              {form.delivery_schedule === "trigger_based" && (
                <div>
                  <label className={labelCls}>Trigger recipe</label>
                  <TriggerRecipeSelect
                    value={form.trigger_type}
                    onChange={(v) => set("trigger_type", v)}
                    inputCls={inputCls}
                    light={light} />
                </div>
              )}
              <div>
                <label className={labelCls}>Country codes (ISO-2, comma-separated)</label>
                <input value={(form.targeting.country_codes || []).join(", ")}
                              onChange={(e) => setTargeting("country_codes",
                                                                                  e.target.value.split(",").map((s) => s.trim()).filter(Boolean))}
                              data-testid="advertiser-notification-wizard-countries"
                              className={inputCls} placeholder="AE, US" />
              </div>
              <div>
                <label className={labelCls}>Category tags (comma-separated)</label>
                <input value={(form.targeting.category_tags || []).join(", ")}
                              onChange={(e) => setTargeting("category_tags",
                                                                                  e.target.value.split(",").map((s) => s.trim()).filter(Boolean))}
                              data-testid="advertiser-notification-wizard-tags"
                              className={inputCls} placeholder="food, beverage, weekend" />
              </div>
              <div>
                <label className={labelCls}>Max deliveries (optional)</label>
                <input type="number" min="1"
                              value={form.max_deliveries || ""}
                              onChange={(e) => set("max_deliveries", Number(e.target.value) || null)}
                              className={inputCls} placeholder="1000" />
              </div>
            </div>
          )}

          {step === 4 && (
            <div data-testid="advertiser-notification-wizard-step-4" className="space-y-4">
              <div>
                <label className={labelCls}>Total budget (cents) *</label>
                <input type="number" value={form.budget_cents}
                              onChange={(e) => set("budget_cents", Number(e.target.value))}
                              min="100"
                              data-testid="advertiser-notification-wizard-budget"
                              className={inputCls} />
                <p className={`text-[11px] mt-1 ${light ? "text-slate-500" : "text-slate-400"}`}>
                  ${((form.budget_cents || 0)/100).toFixed(2)} total
                </p>
              </div>
              <div className="relative">
                <label className={`${labelCls} inline-flex items-center gap-1`}>
                  Cost per delivery (cents) *
                  <button type="button"
                                  onMouseEnter={() => setShowCpdTooltip(true)}
                                  onMouseLeave={() => setShowCpdTooltip(false)}
                                  onFocus={() => setShowCpdTooltip(true)}
                                  onBlur={() => setShowCpdTooltip(false)}
                                  data-testid="advertiser-notification-wizard-cpd-tooltip-btn"
                                  className="opacity-70 hover:opacity-100">
                    <Info className="w-3 h-3" />
                  </button>
                </label>
                <input type="number" min="1" max="100000"
                              value={form.cost_per_delivery_cents}
                              onChange={(e) => set("cost_per_delivery_cents", Number(e.target.value))}
                              data-testid="advertiser-notification-wizard-cpd"
                              className={inputCls} />
                <div className={`text-[11px] mt-1 font-mono ${light ? "text-slate-500" : "text-slate-400"}`}>
                  Estimated reach: {form.cost_per_delivery_cents > 0
                    ? Math.floor((form.budget_cents || 0) / form.cost_per_delivery_cents).toLocaleString()
                    : "—"} deliveries
                </div>
                {showCpdTooltip && (
                  <div data-testid="advertiser-notification-wizard-cpd-tooltip"
                              className={`absolute z-10 mt-2 right-0 w-72 p-3 rounded-lg shadow-2xl border ${light ? "bg-white border-slate-300" : "bg-slate-800 border-slate-700"}`}>
                    <div className="text-[10px] uppercase tracking-widest font-mono text-amber-500 mb-2">
                      Recommended CPD by category
                    </div>
                    <div className="space-y-1 text-xs">
                      {(hints?.notification_cpd_groups || []).map((g) => (
                        <div key={g.label} className="flex justify-between">
                          <span>{g.label}</span>
                          <span className="font-mono font-bold">{g.cents}¢</span>
                        </div>
                      ))}
                    </div>
                    <div className={`text-[10px] mt-2 pt-2 border-t ${light ? "border-slate-200" : "border-slate-700"} ${light ? "text-slate-500" : "text-slate-400"}`}>
                      Pick a value that lines up with your category — pricing is not auto-filled.
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {step === 5 && (
            <div data-testid="advertiser-notification-wizard-step-5" className="space-y-3">
              <div className={`rounded-xl p-4 ${light ? "bg-slate-50" : "bg-slate-950"}`}>
                <div className="text-xs font-black">{form.title}</div>
                <div className={`text-[11px] mt-1 ${light ? "text-slate-500" : "text-slate-400"}`}>
                  {form.body}
                </div>
                <div className="text-[11px] mt-2">
                  CTA: <span className="font-bold">{form.cta_text}</span>
                  {" · "}Target: {form.target_url}
                </div>
                <div className={`text-[11px] mt-1 ${light ? "text-slate-500" : "text-slate-400"}`}>
                  Channel: in-app · Budget: ${((form.budget_cents || 0)/100).toFixed(2)} · CPD: {form.cost_per_delivery_cents}¢
                </div>
                <div className={`text-[11px] ${light ? "text-slate-500" : "text-slate-400"}`}>
                  Targeting: {(form.targeting.country_codes || []).join(", ")}
                  {form.targeting.category_tags?.length ? ` · ${form.targeting.category_tags.join(", ")}` : ""}
                </div>
              </div>
              <div className={`text-xs ${light ? "text-slate-600" : "text-slate-400"}`}>
                Submitting will send this to the Ad Review Queue.  It goes live after admin approval.
              </div>
            </div>
          )}
        </div>

        <div className={`px-6 py-4 border-t ${border} flex items-center justify-between gap-2`}>
          <button onClick={() => setStep((s) => Math.max(1, s - 1))}
                          disabled={step === 1 || busy}
                          data-testid="advertiser-notification-wizard-back"
                          className={`inline-flex items-center gap-1 text-sm px-3 py-2 rounded-full ${light ? "hover:bg-slate-100" : "hover:bg-slate-800"} disabled:opacity-40`}>
            <ChevronLeft className="w-4 h-4" /> Back
          </button>
          <div className="text-[10px] font-mono opacity-60">Step {step}/5</div>
          {step < 5 ? (
            <button onClick={async () => {
                if (step === 1) await saveDraft();
                setStep((s) => Math.min(5, s + 1));
              }}
              disabled={busy || (step === 1 && (!form.title || !form.body || !form.target_url))
                                || (step === 2 && !iconUploaded)}
              data-testid="advertiser-notification-wizard-next"
              className="inline-flex items-center gap-1 text-sm font-black px-4 py-2 rounded-full bg-amber-500 text-slate-900 hover:bg-amber-400 disabled:opacity-40">
              {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
              Next <ChevronRight className="w-4 h-4" />
            </button>
          ) : (
            <button onClick={publish} disabled={busy}
                            data-testid="advertiser-notification-wizard-submit"
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


// ─── Trigger recipe selector ─────────────────────────────────────────
function TriggerRecipeSelect({ value, onChange, inputCls, light }) {
  const [recipes, setRecipes] = useState([]);
  const [mode, setMode] = useState(value && !value.startsWith("__custom__")
                                                                        ? "recipe" : "custom");

  useEffect(() => {
    axios.get(`${API}/notification-trigger-recipes`)
      .then((r) => setRecipes(r.data?.items || []))
      .catch(() => setRecipes([]));
  }, []);

  const selected = recipes.find((r) => r.id === value);

  return (
    <div className="space-y-2" data-testid="advertiser-notification-wizard-recipe-select">
      <div className="flex gap-2 text-[10px] font-mono uppercase tracking-widest">
        <button type="button"
                        onClick={() => setMode("recipe")}
                        data-testid="advertiser-notification-wizard-recipe-mode-preset"
                        className={`px-3 py-1 rounded-full ${mode === "recipe"
                                                                ? "bg-amber-500 text-slate-900"
                                                                : (light ? "bg-slate-100 text-slate-500" : "bg-slate-800 text-slate-400")}`}>
          Preset recipe
        </button>
        <button type="button"
                        onClick={() => setMode("custom")}
                        data-testid="advertiser-notification-wizard-recipe-mode-custom"
                        className={`px-3 py-1 rounded-full ${mode === "custom"
                                                                ? "bg-amber-500 text-slate-900"
                                                                : (light ? "bg-slate-100 text-slate-500" : "bg-slate-800 text-slate-400")}`}>
          Custom
        </button>
      </div>
      {mode === "recipe" ? (
        <>
          <select value={value || ""}
                          onChange={(e) => onChange(e.target.value)}
                          data-testid="advertiser-notification-wizard-recipe-dropdown"
                          className={inputCls}>
            <option value="">— Pick a trigger —</option>
            {recipes.map((r) => (
              <option key={r.id} value={r.id}>
                {r.label} · {r.category}
              </option>
            ))}
          </select>
          {selected && (
            <div data-testid="advertiser-notification-wizard-recipe-desc"
                        className={`text-[11px] p-2 rounded-lg ${light ? "bg-slate-50 text-slate-600" : "bg-slate-950 text-slate-400"}`}>
              {selected.description}
              {selected.default_delay_minutes > 0 && (
                <div className="mt-1 font-mono text-[10px]">
                  Fires after: {selected.default_delay_minutes} min delay
                </div>
              )}
            </div>
          )}
        </>
      ) : (
        <input value={value || ""}
                      onChange={(e) => onChange(e.target.value)}
                      data-testid="advertiser-notification-wizard-recipe-custom"
                      className={inputCls}
                      placeholder="Custom event name (e.g. new_user_first_purchase)" />
      )}
    </div>
  );
}

