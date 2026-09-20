// Phase SC.4 — Merchant Payment Links portal.  Both design variants.
// Owner-auth-gated (requires merchant_status ∈ {approved, active}).
//
// Screens in one page:
//    - List (filter chips + table + row actions)
//    - New Link modal (3-step: type → fields → preview & create)
//    - Edit Link modal
//    - Analytics drawer
//    - Success card after create (copy URL + download QR)
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import {
  ArrowLeft, ArrowRight, BarChart3, Check, Coins, Copy, CreditCard,
  Download, Gift, Loader2, MapPin, Package, PartyPopper, Plus, Radio,
  Ticket, Trash2, Utensils, Wallet, X, Edit3, ExternalLink, Link2,
  Megaphone, Sparkles, Store, Table2, Ban,
} from "lucide-react";
import { useAuth } from "@/AuthContext";
import { useDesignVariant } from "@/hooks/useDesignVariant";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

const LINK_TYPES = [
  { id: "general_payment",        label: "General Payment",        icon: Wallet,
      hint: "Customer enters amount",             txn: "payment" },
  { id: "location_payment",      label: "Location Payment",      icon: Store,
      hint: "Fixed to a location",                    txn: "payment" },
  { id: "table_qr",                        label: "Table QR",                        icon: Table2,
      hint: "Table-side ordering",                    txn: "payment" },
  { id: "offer_payment",            label: "Offer / Coupon",              icon: Gift,
      hint: "Discounted offer sold up-front", txn: "paid_coupon" },
  { id: "prepaid_meal",              label: "Prepaid Meal",                icon: Utensils,
      hint: "Meal package prepaid",                txn: "prepaid_meal" },
  { id: "gift_card",                    label: "Gift Card",                        icon: CreditCard,
      hint: "Digital gift card",                        txn: "gift_card" },
  { id: "product_checkout",      label: "Product",                          icon: Package,
      hint: "Physical or digital product",    txn: "payment" },
  { id: "event_ticket",              label: "Event Ticket",                icon: Ticket,
      hint: "Ticketed event",                            txn: "event_ticket" },
  { id: "appointment_deposit", label: "Appointment Deposit", icon: Coins,
      hint: "Booking deposit",                          txn: "appointment_deposit" },
  { id: "campaign_payment",        label: "Campaign / Promo",        icon: Megaphone,
      hint: "Ad-campaign attribution",            txn: "payment" },
];


export default function MerchantPaymentLinks() {
  const { user, loading: authLoading } = useAuth();
  const variant = useDesignVariant();
  const navigate = useNavigate();
  const light = variant === "radiolife";

  const [merchant, setMerchant] = useState(null);
  const [links, setLinks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filterActive, setFilterActive] = useState("");        // "" | "true" | "false"
  const [filterType, setFilterType] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [editing, setEditing] = useState(null);
  const [analyzing, setAnalyzing] = useState(null);
  const [createdLink, setCreatedLink] = useState(null);

  useEffect(() => {
    if (!authLoading && !user) {
      navigate(`/login?next=${encodeURIComponent("/merchant/payment-links")}`,
                    { replace: true });
    }
  }, [authLoading, user, navigate]);

  // Resolve the merchant + load links
  const loadMerchant = useCallback(async () => {
    if (!user) return;
    try {
      const { data } = await axios.get(`${API}/merchant/mine`,
                                                                { withCredentials: true });
      const items = data.items || [];
      const priority = { active: 5, approved: 4, submitted: 3,
                                          verification_pending: 2,
                                          stripe_onboarding_pending: 1, draft: 0 };
      items.sort((a, b) => (priority[b.merchant_status] || 0)
                                        - (priority[a.merchant_status] || 0));
      const chosen = items.find((m) => m.merchant_status === "approved"
                                                            || m.merchant_status === "active")
                                  || items[0];
      setMerchant(chosen || null);
    } catch (e) {
      toast.error(`Merchant load failed: ${e?.response?.data?.detail || e.message}`);
    }
  }, [user]);

  const loadLinks = useCallback(async () => {
    if (!merchant?.merchant_id) return;
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set("limit", "100");
      if (filterActive) params.set("active", filterActive);
      if (filterType) params.set("link_type", filterType);
      const { data } = await axios.get(
        `${API}/merchant/${merchant.merchant_id}/payment-links?${params.toString()}`,
        { withCredentials: true });
      setLinks(data.items || []);
    } catch (e) {
      toast.error(`Links load failed: ${e?.response?.data?.detail || e.message}`);
    } finally { setLoading(false); }
  }, [merchant, filterActive, filterType]);

  useEffect(() => { loadMerchant(); }, [loadMerchant]);
  useEffect(() => { loadLinks(); }, [loadLinks]);

  const isApproved = merchant?.merchant_status === "approved"
                                          || merchant?.merchant_status === "active";

  const deactivate = async (link) => {
    if (!merchant?.merchant_id) return;
    try {
      await axios.post(
        `${API}/merchant/${merchant.merchant_id}/payment-links/${link.link_id}/deactivate`,
        {}, { withCredentials: true });
      toast.success("Link deactivated");
      await loadLinks();
    } catch (e) {
      toast.error(`Deactivate failed: ${e?.response?.data?.detail || e.message}`);
    }
  };

  const copyUrl = async (url) => {
    try {
      await navigator.clipboard.writeText(url);
      toast.success("Link copied to clipboard");
    } catch {
      toast.error("Copy failed — please select and copy manually");
    }
  };

  const downloadQr = async (link) => {
    try {
      const res = await fetch(link.qr_url);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `bigfm-pay-${link.token}.png`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      toast.error(`QR download failed: ${e.message}`);
    }
  };

  if (authLoading || !user) {
    return <FullscreenSpinner light={light} />;
  }

  return (
    <div className={light
                          ? "min-h-screen bg-gradient-to-b from-purple-50 via-white to-pink-50 text-slate-900"
                          : "min-h-screen bg-slate-950 text-slate-100"}
              data-testid="merchant-payment-links-page"
              data-variant={variant}>
      <div className="max-w-5xl mx-auto px-5 py-8 sm:py-10">
        <button type="button" onClick={() => navigate("/merchant/dashboard")}
                      className={light
                                                ? "flex items-center gap-1.5 text-sm text-purple-700 hover:text-purple-900 font-medium mb-6"
                                                : "flex items-center gap-1.5 text-sm text-slate-400 hover:text-cyan-400 mb-6"}
                      data-testid="merchant-payment-links-back">
          <ArrowLeft size={16}/> Back to dashboard
        </button>

        <div className="flex items-start justify-between gap-4 mb-8">
          <div>
            <div className={`text-[11px] font-bold uppercase tracking-widest mb-2 ${
              light ? "text-purple-600" : "text-cyan-400"
            }`}>Phase SC.4</div>
            <h1 className={`text-3xl sm:text-4xl font-black tracking-tight ${
              light ? "text-slate-900" : "text-white"
            }`}>Payment Links &amp; QR</h1>
            <p className={`mt-1 text-sm ${light ? "text-slate-600" : "text-slate-400"}`}>
              Create shareable links + printable QR codes for 10 use cases.
              {merchant && ` For "${merchant.name}".`}
            </p>
          </div>
          <button type="button"
                        disabled={!isApproved}
                        onClick={() => setShowCreate(true)}
                        data-testid="merchant-payment-links-new-btn"
                        className={`inline-flex items-center gap-1.5 h-11 px-5 rounded-full text-sm font-bold ${
                          isApproved
                            ? "text-white shadow-lg shadow-purple-500/25"
                            : "text-slate-500 bg-slate-200/40 cursor-not-allowed"
                        }`}
                        style={isApproved
                          ? { background: "linear-gradient(135deg,#a855f7,#ec4899)" }
                          : undefined}
                        title={isApproved ? "" : "Available after approval"}>
            <Plus size={16}/> New Link
          </button>
        </div>

        {!isApproved && merchant && (
          <div className={`rounded-2xl p-5 mb-6 ${
            light ? "bg-amber-50 border border-amber-200 text-amber-900"
                    : "bg-amber-500/10 border border-amber-500/30 text-amber-200"
          }`} data-testid="merchant-payment-links-not-approved">
            <b>Approval required.</b> Payment links unlock once your merchant
            application is approved. Current status: <code>{merchant.merchant_status}</code>.
          </div>
        )}

        {/* Filter chips */}
        <div className="flex flex-wrap gap-2 mb-4"
                  data-testid="merchant-payment-links-filters">
          <Chip light={light}
                      active={filterActive === ""}
                      onClick={() => setFilterActive("")}
                      testId="mplf-status-all">All</Chip>
          <Chip light={light}
                      active={filterActive === "true"}
                      onClick={() => setFilterActive("true")}
                      testId="mplf-status-active">Active</Chip>
          <Chip light={light}
                      active={filterActive === "false"}
                      onClick={() => setFilterActive("false")}
                      testId="mplf-status-inactive">Deactivated</Chip>
          <select value={filterType}
                      onChange={(e) => setFilterType(e.target.value)}
                      data-testid="mplf-type-select"
                      className={`h-8 rounded-full px-3 text-xs font-semibold border ${
                        light ? "bg-white border-slate-200 text-slate-700"
                                : "bg-slate-900 border-slate-700 text-slate-200"
                      }`}>
            <option value="">All types</option>
            {LINK_TYPES.map((t) => (
              <option key={t.id} value={t.id}>{t.label}</option>
            ))}
          </select>
        </div>

        {/* Table */}
        <div className={`rounded-3xl overflow-hidden ${
          light ? "bg-white shadow-sm border border-slate-100"
                  : "bg-slate-900 border border-slate-800"
        }`}>
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="merchant-payment-links-table">
              <thead>
                <tr className={light ? "bg-slate-50" : "bg-slate-950/60"}>
                  <Th light={light}>Title</Th>
                  <Th light={light}>Type</Th>
                  <Th light={light}>Amount</Th>
                  <Th light={light}>Usage</Th>
                  <Th light={light}>Impr</Th>
                  <Th light={light}>Status</Th>
                  <Th light={light}>Actions</Th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr><td colSpan={7} className="p-8 text-center opacity-70">
                    Loading…</td></tr>
                ) : links.length === 0 ? (
                  <tr><td colSpan={7} className="p-8 text-center opacity-70"
                                    data-testid="merchant-payment-links-empty">
                    {isApproved ? "No links yet — click New Link to create your first."
                                              : "Approval required to create links."}
                  </td></tr>
                ) : (
                  links.map((l) => (
                    <LinkRow key={l.link_id} link={l} light={light}
                                    onCopy={() => copyUrl(l.hosted_url)}
                                    onQr={() => downloadQr(l)}
                                    onAnalytics={() => setAnalyzing(l)}
                                    onEdit={() => setEditing(l)}
                                    onDeactivate={() => deactivate(l)}/>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {showCreate && isApproved && (
        <NewLinkModal light={light} merchant={merchant}
                                  onClose={() => setShowCreate(false)}
                                  onCreated={async (created) => {
                                    setShowCreate(false);
                                    setCreatedLink(created);
                                    await loadLinks();
                                  }}/>
      )}
      {editing && (
        <EditLinkModal light={light} merchant={merchant} link={editing}
                                    onClose={() => setEditing(null)}
                                    onSaved={async () => { setEditing(null); await loadLinks(); }}/>
      )}
      {analyzing && (
        <AnalyticsDrawer light={light} merchant={merchant} link={analyzing}
                                        onClose={() => setAnalyzing(null)}/>
      )}
      {createdLink && (
        <SuccessCard light={light} link={createdLink}
                                onCopy={() => copyUrl(createdLink.hosted_url)}
                                onQr={() => downloadQr(createdLink)}
                                onClose={() => setCreatedLink(null)}/>
      )}
    </div>
  );
}


// ─── Bits ─────────────────────────────────────────────────────────
function FullscreenSpinner({ light }) {
  return (
    <div className={light ? "min-h-screen bg-white flex items-center justify-center"
                                          : "min-h-screen bg-slate-950 flex items-center justify-center"}>
      <Loader2 className="animate-spin" size={28}
                        color={light ? "#a855f7" : "#00d4ff"}/>
    </div>
  );
}

function Chip({ light, active, onClick, testId, children }) {
  return (
    <button type="button" onClick={onClick} data-testid={testId}
                data-active={active ? "true" : "false"}
                className={`h-8 rounded-full px-3.5 text-xs font-bold uppercase tracking-wider transition-all ${
                  active
                    ? (light ? "text-white shadow-sm"
                                    : "text-slate-950")
                    : (light ? "bg-white text-slate-600 border border-slate-200 hover:bg-slate-50"
                                    : "bg-slate-900 text-slate-400 border border-slate-800 hover:border-cyan-500/40")
                }`}
                style={active
                  ? (light
                      ? { background: "linear-gradient(135deg,#a855f7,#ec4899)" }
                      : { background: "linear-gradient(135deg,#00d4ff,#6366f1)" })
                  : undefined}>
      {children}
    </button>
  );
}

function Th({ light, children }) {
  return (
    <th className={`text-left px-4 py-3 text-[10px] font-bold uppercase tracking-widest ${
      light ? "text-slate-500" : "text-slate-500"
    }`}>
      {children}
    </th>
  );
}

function LinkRow({ link, light, onCopy, onQr, onAnalytics, onEdit,
                                    onDeactivate }) {
  const typeInfo = LINK_TYPES.find((t) => t.id === link.link_type)
                                || { label: link.link_type, icon: Link2 };
  const Icon = typeInfo.icon;
  const amountDisplay = link.amount_cents == null
    ? "Customer sets"
    : `${(link.amount_cents / 100).toFixed(2)} ${link.currency}`;
  const statusTone = !link.active
    ? { bg: light ? "bg-slate-100" : "bg-slate-800",
          fg: light ? "text-slate-600" : "text-slate-400", label: "Deactivated" }
    : link.expires_at && new Date(link.expires_at) < new Date()
      ? { bg: light ? "bg-amber-100" : "bg-amber-500/10",
            fg: light ? "text-amber-700" : "text-amber-300", label: "Expired" }
      : (link.max_uses && link.usage_count >= link.max_uses)
        ? { bg: light ? "bg-amber-100" : "bg-amber-500/10",
              fg: light ? "text-amber-700" : "text-amber-300", label: "Max reached" }
        : { bg: light ? "bg-emerald-100" : "bg-emerald-500/10",
              fg: light ? "text-emerald-700" : "text-emerald-300", label: "Active" };

  return (
    <tr data-testid={`mpl-row-${link.link_id}`}
              className={`border-t ${light ? "border-slate-100" : "border-slate-800"} ${
                !link.active ? "opacity-60" : ""
              }`}>
      <td className="px-4 py-3">
        <div className={`font-semibold ${light ? "text-slate-900" : "text-slate-100"}`}>
          {link.title || <span className="opacity-60 italic">Untitled</span>}
        </div>
        <div className={`text-xs mt-0.5 font-mono ${
          light ? "text-slate-400" : "text-slate-500"
        }`}>{link.token}</div>
      </td>
      <td className="px-4 py-3">
        <div className="flex items-center gap-1.5">
          <Icon size={14} className={light ? "text-purple-600" : "text-cyan-400"}/>
          <span className={light ? "text-slate-700 text-xs" : "text-slate-300 text-xs"}>
            {typeInfo.label}
          </span>
        </div>
      </td>
      <td className="px-4 py-3 tabular-nums text-xs">{amountDisplay}</td>
      <td className="px-4 py-3 text-xs">
        {link.usage_count}{link.max_uses ? ` / ${link.max_uses}` : ""}
      </td>
      <td className="px-4 py-3 text-xs">{link.impressions}</td>
      <td className="px-4 py-3">
        <span className={`inline-block text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full ${statusTone.bg} ${statusTone.fg}`}
                    data-testid={`mpl-status-${link.link_id}`}>
          {statusTone.label}
        </span>
      </td>
      <td className="px-4 py-3">
        <div className="flex items-center gap-1">
          <IconBtn light={light} onClick={onCopy} title="Copy link"
                          testId={`mpl-copy-${link.link_id}`}><Copy size={14}/></IconBtn>
          <IconBtn light={light} onClick={onQr} title="Download QR"
                          testId={`mpl-qr-${link.link_id}`}><Download size={14}/></IconBtn>
          <IconBtn light={light} onClick={onAnalytics} title="Analytics"
                          testId={`mpl-analytics-${link.link_id}`}><BarChart3 size={14}/></IconBtn>
          <IconBtn light={light} onClick={onEdit} title="Edit"
                          testId={`mpl-edit-${link.link_id}`}><Edit3 size={14}/></IconBtn>
          {link.active && (
            <IconBtn light={light} onClick={onDeactivate} title="Deactivate"
                            danger testId={`mpl-deactivate-${link.link_id}`}><Ban size={14}/></IconBtn>
          )}
        </div>
      </td>
    </tr>
  );
}

function IconBtn({ light, onClick, title, danger, children, testId }) {
  return (
    <button type="button" onClick={onClick} title={title}
                data-testid={testId}
                className={`h-8 w-8 rounded-full flex items-center justify-center transition-all ${
                  light
                    ? (danger ? "text-rose-600 hover:bg-rose-50"
                                    : "text-slate-600 hover:bg-slate-100")
                    : (danger ? "text-rose-400 hover:bg-rose-500/10"
                                    : "text-slate-400 hover:bg-slate-800 hover:text-cyan-400")
                }`}>
      {children}
    </button>
  );
}


// ─── New Link modal ───────────────────────────────────────────────
function NewLinkModal({ light, merchant, onClose, onCreated }) {
  const [step, setStep] = useState(1);
  const [type, setType] = useState(null);
  const [form, setForm] = useState({
    title: "", description: "", amount_cents: "", currency: "AED",
    max_uses: "", expires_at: "", table_number: "",
    min_amount_cents: "", max_amount_cents: "",
    offer_id: "", product_id: "", event_id: "", service_id: "",
  });
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState(null);

  const pickType = (t) => { setType(t); setStep(2); };
  const set = (k, v) => setForm((p) => ({ ...p, [k]: v }));

  const needsAmount = type && !["general_payment"].includes(type.id);
  const optionalAmount = type && type.id === "general_payment";

  const fetchPreview = useCallback(async () => {
    if (!type || !merchant?.merchant_id) return;
    const amount = parseInt(form.amount_cents || "0", 10);
    if (!amount || amount <= 0) { setPreview(null); return; }
    try {
      const { data } = await axios.get(
        `${API}/commissions/preview?category=${encodeURIComponent(merchant.category_id || "other")}&transaction_type=${type.txn}&amount_cents=${amount}&merchant_id=${merchant.merchant_id}`,
        { withCredentials: true });
      setPreview(data);
    } catch (e) {
      setPreview(null);
    }
  }, [type, form.amount_cents, merchant]);

  useEffect(() => {
    if (step === 3) fetchPreview();
  }, [step, fetchPreview]);

  const submit = async () => {
    setBusy(true);
    try {
      const body = {
        link_type:                    type.id,
        title:                            form.title || null,
        description:                form.description || null,
        currency:                      form.currency || "AED",
        transaction_type:      type.txn,
        amount_cents:              form.amount_cents ? parseInt(form.amount_cents, 10) : null,
        min_amount_cents:      form.min_amount_cents ? parseInt(form.min_amount_cents, 10) : null,
        max_amount_cents:      form.max_amount_cents ? parseInt(form.max_amount_cents, 10) : null,
        max_uses:                      form.max_uses ? parseInt(form.max_uses, 10) : null,
        expires_at:                  form.expires_at ? new Date(form.expires_at).toISOString() : null,
        table_number:              form.table_number || null,
        offer_id:                      form.offer_id || null,
        product_id:                  form.product_id || null,
        event_id:                      form.event_id || null,
        service_id:                  form.service_id || null,
      };
      const { data } = await axios.post(
        `${API}/merchant/${merchant.merchant_id}/payment-links`, body,
        { withCredentials: true });
      toast.success("Payment link created");
      onCreated(data);
    } catch (e) {
      toast.error(`Create failed: ${e?.response?.data?.detail || e.message}`);
    } finally { setBusy(false); }
  };

  return (
    <ModalShell light={light} onClose={onClose}
                            testId="mpl-new-link-modal">
      <div className="flex items-center justify-between mb-4">
        <h3 className={`text-xl font-black ${light ? "text-slate-900" : "text-white"}`}>
          {step === 1 ? "Choose a link type"
                            : step === 2 ? "Link details"
                                                  : "Preview & create"}
        </h3>
        <button type="button" onClick={onClose}
                      className={light ? "text-slate-500" : "text-slate-500"}
                      data-testid="mpl-new-link-close">
          <X size={20}/>
        </button>
      </div>

      {/* Step 1 — type grid */}
      {step === 1 && (
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5"
                  data-testid="mpl-new-link-type-grid">
          {LINK_TYPES.map((t) => {
            const Icon = t.icon;
            return (
              <button key={t.id} type="button" onClick={() => pickType(t)}
                            data-testid={`mpl-new-link-type-${t.id}`}
                            className={`flex flex-col items-center gap-1.5 rounded-2xl p-4 border transition-all ${
                              light
                                ? "bg-white border-slate-200 text-slate-700 hover:border-purple-400 hover:bg-purple-50"
                                : "bg-slate-800/40 border-slate-800 text-slate-300 hover:border-cyan-500/40"
                            }`}>
                <Icon size={22} className={light ? "text-purple-600" : "text-cyan-400"}/>
                <span className="text-[12px] font-semibold text-center">{t.label}</span>
                <span className={`text-[10px] text-center ${
                  light ? "text-slate-500" : "text-slate-500"
                }`}>{t.hint}</span>
              </button>
            );
          })}
        </div>
      )}

      {/* Step 2 — fields */}
      {step === 2 && type && (
        <div className="space-y-3">
          <ModalField label="Title" testId="mpl-title-field">
            <ModalInput light={light} value={form.title}
                                    onChange={(e) => set("title", e.target.value)}
                                    placeholder={`e.g. "${type.label}"`}
                                    data-testid="mpl-title-input"/>
          </ModalField>
          <ModalField label="Description">
            <ModalTextarea light={light} value={form.description} rows={3}
                                          onChange={(e) => set("description", e.target.value)}
                                          placeholder="Optional customer-facing description"
                                          data-testid="mpl-description-input"/>
          </ModalField>
          <div className="grid grid-cols-2 gap-3">
            <ModalField label={optionalAmount ? "Amount (blank = customer sets)" : "Amount"}
                                    testId="mpl-amount-field">
              <div className="flex items-center gap-1">
                <ModalInput light={light} type="number" min={0}
                                        value={form.amount_cents}
                                        onChange={(e) => set("amount_cents", e.target.value)}
                                        placeholder="cents"
                                        data-testid="mpl-amount-input"/>
                <span className={`text-xs font-semibold ${
                  light ? "text-slate-500" : "text-slate-500"
                }`}>¢</span>
              </div>
            </ModalField>
            <ModalField label="Currency">
              <ModalInput light={light} value={form.currency} maxLength={4}
                                      onChange={(e) => set("currency", e.target.value.toUpperCase())}/>
            </ModalField>
          </div>
          {optionalAmount && (
            <div className="grid grid-cols-2 gap-3">
              <ModalField label="Min ¢ (optional)">
                <ModalInput light={light} type="number" min={0}
                                        value={form.min_amount_cents}
                                        onChange={(e) => set("min_amount_cents", e.target.value)}/>
              </ModalField>
              <ModalField label="Max ¢ (optional)">
                <ModalInput light={light} type="number" min={0}
                                        value={form.max_amount_cents}
                                        onChange={(e) => set("max_amount_cents", e.target.value)}/>
              </ModalField>
            </div>
          )}
          <div className="grid grid-cols-2 gap-3">
            <ModalField label="Max uses (optional)">
              <ModalInput light={light} type="number" min={1}
                                      value={form.max_uses}
                                      onChange={(e) => set("max_uses", e.target.value)}/>
            </ModalField>
            <ModalField label="Expires at (optional)">
              <ModalInput light={light} type="datetime-local"
                                      value={form.expires_at}
                                      onChange={(e) => set("expires_at", e.target.value)}/>
            </ModalField>
          </div>
          {type.id === "table_qr" && (
            <ModalField label="Table number">
              <ModalInput light={light} value={form.table_number}
                                      onChange={(e) => set("table_number", e.target.value)}
                                      placeholder="e.g. 12A"
                                      data-testid="mpl-table-input"/>
            </ModalField>
          )}
          {(type.id === "offer_payment" || type.id === "product_checkout" ||
              type.id === "event_ticket" || type.id === "appointment_deposit") && (
            <ModalField label={`Linked ID (${type.id.replace("_payment","").replace("_"," ")})`}>
              <ModalInput light={light}
                                      value={form.offer_id || form.product_id || form.event_id || form.service_id}
                                      onChange={(e) => {
                                        const key = type.id === "offer_payment" ? "offer_id"
                                                                : type.id === "product_checkout" ? "product_id"
                                                                : type.id === "event_ticket" ? "event_id"
                                                                : "service_id";
                                        set(key, e.target.value);
                                      }}
                                      placeholder="Optional — links payment to an item"/>
            </ModalField>
          )}
          <div className="flex justify-between mt-6">
            <ModalGhost light={light} onClick={() => setStep(1)}>Back</ModalGhost>
            <ModalPrimary light={light} onClick={() => setStep(3)}
                                        disabled={!form.title || (needsAmount && !form.amount_cents)}
                                        testId="mpl-step2-next">Next →</ModalPrimary>
          </div>
        </div>
      )}

      {/* Step 3 — preview + commission */}
      {step === 3 && type && (
        <div>
          <div className={`rounded-2xl p-4 mb-4 ${
            light ? "bg-purple-50 border border-purple-100"
                    : "bg-slate-800/60 border border-slate-700"
          }`}>
            <div className={`text-[11px] font-bold uppercase tracking-widest mb-1 ${
              light ? "text-purple-700" : "text-cyan-400"
            }`}>Summary</div>
            <div className={`font-semibold ${light ? "text-slate-900" : "text-white"}`}>
              {form.title || "Untitled"}
            </div>
            <div className={`text-xs mt-0.5 ${light ? "text-slate-600" : "text-slate-400"}`}>
              {type.label} · {form.amount_cents
                ? `${(parseInt(form.amount_cents,10)/100).toFixed(2)} ${form.currency}`
                : "Customer sets amount"}
            </div>
          </div>

          {preview && (
            <div className={`rounded-2xl p-4 mb-4 ${
              light ? "bg-white border border-slate-200"
                      : "bg-slate-900 border border-slate-800"
            }`} data-testid="mpl-preview-commission">
              <div className={`text-[11px] font-bold uppercase tracking-widest mb-2 ${
                light ? "text-slate-500" : "text-slate-500"
              }`}>Commission preview (for you — hidden from customers)</div>
              <div className="grid grid-cols-3 gap-2 text-sm">
                <div>
                  <div className={light ? "text-slate-500 text-xs" : "text-slate-500 text-xs"}>Charge</div>
                  <div className={`font-black tabular-nums ${light ? "text-slate-900" : "text-white"}`}>
                    {(parseInt(form.amount_cents,10) / 100).toFixed(2)} {form.currency}
                  </div>
                </div>
                <div>
                  <div className={light ? "text-slate-500 text-xs" : "text-slate-500 text-xs"}>Fee ({preview.computed_percent}%)</div>
                  <div className={`font-black tabular-nums ${light ? "text-purple-700" : "text-cyan-400"}`}
                            data-testid="mpl-preview-commission-cents">
                    -{(preview.commission_cents/100).toFixed(2)}
                  </div>
                </div>
                <div>
                  <div className={light ? "text-slate-500 text-xs" : "text-slate-500 text-xs"}>You get</div>
                  <div className={`font-black tabular-nums ${light ? "text-emerald-700" : "text-emerald-400"}`}>
                    {(preview.merchant_net_cents/100).toFixed(2)}
                  </div>
                </div>
              </div>
              <div className={`text-[10px] mt-2 ${light ? "text-slate-400" : "text-slate-500"}`}>
                Source: {preview.source}
                {preview.override_id ? ` · override ${preview.override_id.slice(0,10)}…`
                                                    : preview.rule_id ? ` · rule ${preview.rule_id.slice(0,10)}…` : ""}
              </div>
            </div>
          )}

          <div className={`text-xs ${light ? "text-slate-500" : "text-slate-500"} mb-4`}>
            After creation you&apos;ll get a hosted URL + printable QR.
          </div>
          <div className="flex justify-between">
            <ModalGhost light={light} onClick={() => setStep(2)}>Back</ModalGhost>
            <ModalPrimary light={light} onClick={submit} disabled={busy}
                                        testId="mpl-create-btn">
              {busy ? <><Loader2 size={14} className="animate-spin"/> Creating…</>
                          : <>Create link <Check size={14}/></>}
            </ModalPrimary>
          </div>
        </div>
      )}
    </ModalShell>
  );
}


// ─── Edit Link modal ──────────────────────────────────────────────
function EditLinkModal({ light, merchant, link, onClose, onSaved }) {
  const [form, setForm] = useState({
    title:                                (link.title || ""),
    description:                    (link.description || ""),
    amount_cents:                (link.amount_cents ?? "").toString(),
    currency:                          (link.currency || "AED"),
    max_uses:                          (link.max_uses ?? "").toString(),
    expires_at:                      link.expires_at
                                                ? link.expires_at.slice(0, 16) : "",
    active:                              !!link.active,
  });
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setForm((p) => ({ ...p, [k]: v }));

  const submit = async () => {
    setBusy(true);
    try {
      const body = {
        title:                          form.title || null,
        description:              form.description || null,
        amount_cents:            form.amount_cents === "" ? null : parseInt(form.amount_cents, 10),
        currency:                    form.currency,
        max_uses:                    form.max_uses === "" ? null : parseInt(form.max_uses, 10),
        expires_at:                form.expires_at ? new Date(form.expires_at).toISOString() : null,
        active:                        !!form.active,
      };
      await axios.put(
        `${API}/merchant/${merchant.merchant_id}/payment-links/${link.link_id}`,
        body, { withCredentials: true });
      toast.success("Link updated");
      onSaved();
    } catch (e) {
      toast.error(`Update failed: ${e?.response?.data?.detail || e.message}`);
    } finally { setBusy(false); }
  };

  return (
    <ModalShell light={light} onClose={onClose}
                            testId="mpl-edit-modal">
      <div className="flex items-center justify-between mb-4">
        <h3 className={`text-xl font-black ${light ? "text-slate-900" : "text-white"}`}>
          Edit link
        </h3>
        <button type="button" onClick={onClose}
                      className={light ? "text-slate-500" : "text-slate-500"}>
          <X size={20}/>
        </button>
      </div>
      <div className="space-y-3">
        <ModalField label="Title">
          <ModalInput light={light} value={form.title}
                                  onChange={(e) => set("title", e.target.value)}/>
        </ModalField>
        <ModalField label="Description">
          <ModalTextarea light={light} value={form.description} rows={3}
                                        onChange={(e) => set("description", e.target.value)}/>
        </ModalField>
        <div className="grid grid-cols-2 gap-3">
          <ModalField label="Amount (¢)">
            <ModalInput light={light} type="number" min={0}
                                    value={form.amount_cents}
                                    onChange={(e) => set("amount_cents", e.target.value)}/>
          </ModalField>
          <ModalField label="Currency">
            <ModalInput light={light} value={form.currency} maxLength={4}
                                    onChange={(e) => set("currency", e.target.value.toUpperCase())}/>
          </ModalField>
          <ModalField label="Max uses">
            <ModalInput light={light} type="number" min={1}
                                    value={form.max_uses}
                                    onChange={(e) => set("max_uses", e.target.value)}/>
          </ModalField>
          <ModalField label="Expires at">
            <ModalInput light={light} type="datetime-local"
                                    value={form.expires_at}
                                    onChange={(e) => set("expires_at", e.target.value)}/>
          </ModalField>
        </div>
        <label className={`flex items-center gap-2 text-xs font-semibold ${
          light ? "text-slate-700" : "text-slate-300"
        }`}>
          <input type="checkbox" checked={form.active}
                        onChange={(e) => set("active", e.target.checked)}
                        data-testid="mpl-edit-active-toggle"/>
          Active
        </label>
        <div className="flex justify-end mt-4">
          <ModalPrimary light={light} onClick={submit} disabled={busy}
                                      testId="mpl-edit-save-btn">
            {busy ? "Saving…" : "Save changes"}
          </ModalPrimary>
        </div>
      </div>
    </ModalShell>
  );
}


// ─── Analytics drawer ─────────────────────────────────────────────
function AnalyticsDrawer({ light, merchant, link, onClose }) {
  const [tab, setTab] = useState("analytics");   // analytics | transactions
  const [stats, setStats] = useState(null);
  const [txns, setTxns] = useState(null);
  const [refunding, setRefunding] = useState(null);   // tx being refunded

  useEffect(() => {
    axios.get(
      `${API}/merchant/${merchant.merchant_id}/payment-links/${link.link_id}/analytics`,
      { withCredentials: true }
    ).then((r) => setStats(r.data))
      .catch((e) => toast.error(`Load: ${e?.response?.data?.detail || e.message}`));
  }, [link, merchant]);

  const loadTxns = async () => {
    try {
      const { data } = await axios.get(
        `${API}/merchant/${merchant.merchant_id}/payment-links/${link.link_id}/transactions`,
        { withCredentials: true });
      setTxns(data.rows || []);
    } catch (e) {
      toast.error(`Txns: ${e?.response?.data?.detail || e.message}`);
    }
  };
  useEffect(() => { if (tab === "transactions" && !txns) loadTxns();
                          /* eslint-disable-next-line */ }, [tab]);

  return (
    <>
      <div onClick={onClose}
                className="fixed inset-0 bg-black/60 z-40"/>
      <div data-testid="mpl-analytics-drawer"
                className={`fixed top-0 right-0 bottom-0 w-full sm:w-[500px] z-50 overflow-y-auto p-6 sm:p-7 ${
                  light ? "bg-white border-l border-slate-100"
                          : "bg-slate-900 border-l border-slate-800"
                }`}>
        <div className="flex items-start justify-between gap-2 mb-4">
          <div>
            <div className={`text-[11px] font-bold uppercase tracking-widest ${
              light ? "text-purple-600" : "text-cyan-400"
            }`}>Link details</div>
            <h3 className={`mt-1 text-xl font-black ${
              light ? "text-slate-900" : "text-white"
            }`}>{link.title || "Untitled"}</h3>
            <div className={`text-xs font-mono ${
              light ? "text-slate-500" : "text-slate-500"
            }`}>{link.token}</div>
          </div>
          <button type="button" onClick={onClose}
                        className={light ? "text-slate-500" : "text-slate-500"}
                        data-testid="mpl-analytics-close">
            <X size={20}/>
          </button>
        </div>

        {/* Tabs */}
        <div className={`flex gap-2 mb-5 border-b ${
          light ? "border-slate-100" : "border-slate-800"
        }`}>
          {[
            { k: "analytics",      label: "Analytics" },
            { k: "transactions", label: "Transactions" },
          ].map((t) => {
            const active = tab === t.k;
            return (
              <button key={t.k}
                            onClick={() => setTab(t.k)}
                            data-testid={`mpl-${t.k}-tab`}
                            className={`px-3 pb-2 -mb-px text-xs font-bold uppercase tracking-wider border-b-2 ${
                              active
                                ? (light ? "text-purple-700 border-purple-600"
                                                : "text-cyan-300 border-cyan-500")
                                : (light ? "text-slate-500 border-transparent hover:text-slate-700"
                                                : "text-slate-500 border-transparent hover:text-slate-300")
                            }`}>
                {t.label}
              </button>
            );
          })}
        </div>

        {tab === "analytics" ? (stats ? (
          <div className="space-y-3">
            <Stat light={light} label="Impressions" value={stats.impressions}
                        testId="mpl-analytics-impressions"/>
            <Stat light={light} label="Unique visitors" value={stats.unique_visitors}
                        testId="mpl-analytics-uniques"/>
            <Stat light={light} label="Transactions" value={stats.transactions}
                        sub="Populated in SC.5" testId="mpl-analytics-txns"/>
            <Stat light={light} label="Revenue" value={`${(stats.revenue_cents/100).toFixed(2)} ${link.currency}`}
                        sub="Populated in SC.5" testId="mpl-analytics-revenue"/>
            <Stat light={light} label="Last impression"
                        value={stats.last_impression_at
                                          ? new Date(stats.last_impression_at).toLocaleString()
                                          : "—"}/>
          </div>
        ) : (
          <div className={light ? "text-slate-500 text-sm" : "text-slate-500 text-sm"}>
            Loading…
          </div>
        )) : (
          <TransactionsList light={light}
                                            txns={txns}
                                            onRefund={setRefunding}/>
        )}

        {refunding && (
          <RefundModal light={light}
                                      merchantId={merchant.merchant_id}
                                      tx={refunding}
                                      onClose={() => setRefunding(null)}
                                      onSuccess={() => { setRefunding(null); loadTxns(); }}/>
        )}
      </div>
    </>
  );
}


// Transactions list (per-link)
function TransactionsList({ light, txns, onRefund }) {
  if (txns === null) {
    return <div className={light ? "text-slate-500 text-sm" : "text-slate-500 text-sm"}>
      Loading…
    </div>;
  }
  if (txns.length === 0) {
    return <div className={`rounded-2xl p-6 text-center text-sm ${
      light ? "bg-slate-50 text-slate-500 border border-slate-100"
              : "bg-slate-950 text-slate-500 border border-slate-800"
    }`} data-testid="mpl-txns-empty">
      No transactions yet for this link.
    </div>;
  }
  return (
    <div className="space-y-2" data-testid="mpl-txns-list">
      {txns.map((tx) => {
        const succeeded = tx.status === "succeeded";
        const refunded = tx.status === "refunded";
        const failed      = tx.status === "failed" || tx.status === "canceled";
        const partial  = succeeded && tx.refunded_cents > 0;
        const remaining = tx.amount_cents - (tx.refunded_cents || 0);
        return (
          <div key={tx.transaction_id}
                    data-testid={`mpl-tx-row-${tx.transaction_id}`}
                    className={`rounded-xl p-3 ${
                      light ? "bg-white border border-slate-100"
                              : "bg-slate-950 border border-slate-800"
                    }`}>
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className={`text-[11px] font-mono truncate ${
                  light ? "text-slate-500" : "text-slate-500"
                }`}>{tx.transaction_id}</div>
                <div className={`mt-1 text-sm font-bold ${
                  light ? "text-slate-900" : "text-white"
                }`}>
                  {(tx.amount_cents / 100).toFixed(2)}
                  <span className={`ml-1 text-[10px] font-normal ${
                    light ? "text-slate-500" : "text-slate-500"
                  }`}>{tx.currency}</span>
                  {partial && (
                    <span className={`ml-2 text-[10px] font-bold ${
                      light ? "text-amber-700" : "text-amber-300"
                    }`}>-{(tx.refunded_cents/100).toFixed(2)} refunded</span>
                  )}
                </div>
                <div className={`text-[10px] ${
                  light ? "text-slate-500" : "text-slate-500"
                }`}>
                  {tx.customer_email || "guest"} · {(tx.payment_method_type || "").replace(/_/g, " ")}
                </div>
                <div className={`text-[10px] ${
                  light ? "text-slate-500" : "text-slate-500"
                }`}>
                  {tx.succeeded_at
                    ? new Date(tx.succeeded_at).toLocaleString(undefined,
                          { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })
                    : (tx.created_at ? new Date(tx.created_at).toLocaleString() : "")}
                </div>
              </div>
              <div className="flex flex-col items-end gap-1.5">
                <span className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${
                  refunded ? (light ? "bg-slate-100 text-slate-700"
                                                  : "bg-slate-500/15 text-slate-300")
                    : failed ? (light ? "bg-rose-100 text-rose-700"
                                                    : "bg-rose-500/15 text-rose-300")
                    : (light ? "bg-emerald-100 text-emerald-700"
                                    : "bg-emerald-500/15 text-emerald-300")
                }`}>
                  {tx.status}
                </span>
                {succeeded && remaining > 0 && (
                  <button onClick={() => onRefund(tx)}
                                data-testid={`mpl-tx-refund-btn-${tx.transaction_id}`}
                                className={`text-[10px] font-bold uppercase tracking-wider px-2 py-1 rounded-full ${
                                  light ? "bg-purple-100 text-purple-700 hover:bg-purple-200"
                                                  : "bg-cyan-500/15 text-cyan-300 hover:bg-cyan-500/25"
                                }`}>
                    Refund
                  </button>
                )}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}


// Refund modal (merchant-initiated — does NOT refund the platform commission)
function RefundModal({ light, merchantId, tx, onClose, onSuccess }) {
  const remaining = (tx.amount_cents - (tx.refunded_cents || 0)) / 100;
  const [amount, setAmount] = useState(remaining.toFixed(2));
  const [reason, setReason] = useState("requested_by_customer");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  const submit = async () => {
    setBusy(true); setErr(null);
    try {
      const body = { transaction_id: tx.transaction_id, reason };
      if (amount) body.amount_cents = Math.round(parseFloat(amount) * 100);
      if (note.trim()) body.note = note.trim();
      const { data } = await axios.post(
        `${API}/merchant/${merchantId}/refunds`, body,
        { withCredentials: true });
      toast.success(`Refund ${data.refund_id.substring(0, 12)}… · ${data.status}`);
      onSuccess();
    } catch (e) {
      const det = e?.response?.data?.detail;
      setErr(det?.detail || det?.code || det || e.message);
    } finally { setBusy(false); }
  };

  return (
    <div onClick={onClose}
              data-testid="mpl-refund-modal-backdrop"
              className="fixed inset-0 z-[60] bg-black/70 flex items-end sm:items-center justify-center p-0 sm:p-4">
      <div onClick={(e) => e.stopPropagation()}
                data-testid="mpl-refund-modal"
                className={`w-full sm:max-w-md rounded-t-3xl sm:rounded-3xl p-6 ${
                  light ? "bg-white" : "bg-slate-900 border border-slate-800"
                }`}>
        <div className="flex items-center justify-between mb-4">
          <h3 className={`text-lg font-black ${
            light ? "text-slate-900" : "text-white"
          }`}>Issue refund</h3>
          <button onClick={onClose} className={
            light ? "text-slate-500" : "text-slate-500"}>
            <X size={20}/>
          </button>
        </div>

        <div className={`text-xs mb-4 ${
          light ? "text-slate-500" : "text-slate-500"
        }`}>
          Refunding to <span className={
            light ? "font-mono text-slate-700" : "font-mono text-slate-300"
          }>{tx.transaction_id}</span>.  Remaining refundable: <b>{remaining.toFixed(2)} {tx.currency}</b>.
        </div>

        <label className={`block text-[10px] font-bold uppercase tracking-widest mb-1 ${
          light ? "text-slate-500" : "text-slate-500"
        }`}>Amount ({tx.currency})</label>
        <input type="number" step="0.01" min="0.01"
                    max={remaining.toFixed(2)}
                    value={amount}
                    onChange={(e) => setAmount(e.target.value)}
                    data-testid="mpl-refund-amount"
                    className={`w-full h-11 rounded-xl px-3 mb-3 text-sm outline-none ${
                      light ? "bg-slate-50 border border-slate-200 focus:border-purple-500"
                              : "bg-slate-950 border border-slate-800 focus:border-cyan-500"
                    }`}/>

        <label className={`block text-[10px] font-bold uppercase tracking-widest mb-1 ${
          light ? "text-slate-500" : "text-slate-500"
        }`}>Reason</label>
        <select value={reason} onChange={(e) => setReason(e.target.value)}
                        data-testid="mpl-refund-reason"
                        className={`w-full h-11 rounded-xl px-3 mb-3 text-sm outline-none ${
                          light ? "bg-slate-50 border border-slate-200"
                                  : "bg-slate-950 border border-slate-800 text-slate-200"
                        }`}>
          <option value="requested_by_customer">Requested by customer</option>
          <option value="duplicate">Duplicate</option>
          <option value="fraudulent">Fraudulent</option>
          <option value="expired_uncaptured_charge">Expired uncaptured</option>
        </select>

        <label className={`block text-[10px] font-bold uppercase tracking-widest mb-1 ${
          light ? "text-slate-500" : "text-slate-500"
        }`}>Note (optional)</label>
        <textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)}
                            data-testid="mpl-refund-note"
                            placeholder="Internal note"
                            className={`w-full rounded-xl px-3 py-2 mb-3 text-sm outline-none resize-y ${
                              light ? "bg-slate-50 border border-slate-200"
                                      : "bg-slate-950 border border-slate-800 text-slate-200"
                            }`}/>

        <div className={`text-[10px] p-2 rounded-lg mb-3 ${
          light ? "bg-amber-50 text-amber-700 border border-amber-100"
                  : "bg-amber-500/10 text-amber-300 border border-amber-500/20"
        }`}>
          Note: FUUSIC commission on the refunded portion is retained by
          the platform.  Ask an admin if you need a full fee reversal.
        </div>

        {err && (
          <div className={`text-xs rounded-lg p-2 mb-3 ${
            light ? "bg-rose-50 text-rose-700 border border-rose-100"
                    : "bg-rose-500/10 text-rose-300 border border-rose-500/20"
          }`} data-testid="mpl-refund-error">{err}</div>
        )}

        <button onClick={submit} disabled={busy}
                      data-testid="mpl-refund-submit"
                      className={`w-full h-12 rounded-full font-black text-sm text-white ${
                        busy ? "bg-slate-400 cursor-not-allowed"
                              : ""
                      }`}
                      style={!busy ? { background: "linear-gradient(135deg,#a855f7,#ec4899)"}
                                                : undefined}>
          {busy ? "Processing…" : `Refund ${amount || "0"} ${tx.currency}`}
        </button>
      </div>
    </div>
  );
}


function Stat({ light, label, value, sub, testId }) {
  return (
    <div className={`rounded-2xl p-4 ${
      light ? "bg-slate-50 border border-slate-100"
              : "bg-slate-950 border border-slate-800"
    }`} data-testid={testId}>
      <div className={`text-[10px] font-bold uppercase tracking-widest ${
        light ? "text-slate-500" : "text-slate-500"
      }`}>{label}</div>
      <div className={`mt-1 text-2xl font-black tabular-nums ${
        light ? "text-slate-900" : "text-white"
      }`}>{value}</div>
      {sub && (
        <div className={`text-[10px] mt-0.5 ${
          light ? "text-slate-400" : "text-slate-500"
        }`}>{sub}</div>
      )}
    </div>
  );
}


// ─── Success card (post-create) ───────────────────────────────────
function SuccessCard({ light, link, onCopy, onQr, onClose }) {
  return (
    <ModalShell light={light} onClose={onClose}
                            testId="mpl-success-card">
      <div className="text-center pt-2">
        <div className={`inline-flex h-14 w-14 rounded-full items-center justify-center mb-3 ${
          light ? "bg-emerald-100 text-emerald-700"
                  : "bg-emerald-500/20 text-emerald-300"
        }`}>
          <Check size={28}/>
        </div>
        <h3 className={`text-2xl font-black ${light ? "text-slate-900" : "text-white"}`}>
          Link created
        </h3>
        <p className={`mt-1 text-sm ${light ? "text-slate-600" : "text-slate-400"}`}>
          Share it below or download the QR to print for your storefront.
        </p>
      </div>
      <div className={`mt-6 rounded-2xl p-4 flex items-center justify-between gap-3 ${
        light ? "bg-slate-50 border border-slate-200"
                : "bg-slate-800/60 border border-slate-700"
      }`}>
        <code className={`text-xs font-mono truncate flex-1 ${
          light ? "text-slate-800" : "text-slate-200"
        }`} data-testid="mpl-success-hosted-url">{link.hosted_url}</code>
        <button type="button" onClick={onCopy}
                      className={`h-9 px-3 rounded-full text-xs font-bold uppercase tracking-widest ${
                        light ? "bg-white border border-slate-200 text-slate-700"
                                : "bg-slate-900 border border-slate-700 text-slate-200"
                      }`}
                      data-testid="mpl-success-copy-btn">
          <Copy size={13}/> Copy
        </button>
      </div>

      <div className="mt-4 flex items-center gap-4">
        <img src={link.qr_url} alt="QR"
                  data-testid="mpl-success-qr-img"
                  className="w-32 h-32 rounded-2xl bg-white p-1 border border-slate-200"/>
        <div className="flex-1">
          <div className={`text-xs mb-3 ${light ? "text-slate-600" : "text-slate-400"}`}>
            Scan this QR to open the pay page.  Right-click to save, or use
            the button below to download a print-ready 512×512 PNG.
          </div>
          <button type="button" onClick={onQr}
                        className="inline-flex items-center gap-1.5 h-10 px-4 rounded-full text-xs font-bold uppercase tracking-widest text-white"
                        style={{ background: "linear-gradient(135deg,#a855f7,#ec4899)" }}
                        data-testid="mpl-success-download-qr">
            <Download size={13}/> Download QR
          </button>
        </div>
      </div>

      <div className="mt-6 flex justify-end">
        <ModalGhost light={light} onClick={onClose}>Done</ModalGhost>
      </div>
    </ModalShell>
  );
}


// ─── Modal primitives ─────────────────────────────────────────────
function ModalShell({ light, onClose, testId, children }) {
  return (
    <div className="fixed inset-0 bg-black/60 z-40 flex items-center justify-center p-4"
              onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()}
                data-testid={testId}
                className={`rounded-3xl w-full max-w-lg max-h-[92vh] overflow-y-auto p-6 sm:p-7 ${
                  light ? "bg-white shadow-xl"
                          : "bg-slate-900 border border-slate-800"
                }`}>
        {children}
      </div>
    </div>
  );
}
function ModalField({ label, children, testId }) {
  return (
    <div data-testid={testId}>
      <div className="text-[10px] font-bold uppercase tracking-widest mb-1 text-slate-500">
        {label}
      </div>
      {children}
    </div>
  );
}
function ModalInput({ light, className, ...props }) {
  return (
    <input {...props}
                className={`w-full h-10 rounded-xl px-3 text-sm outline-none ${
                  light
                    ? "bg-white border border-slate-200 text-slate-900 focus:border-purple-500"
                    : "bg-slate-950 border border-slate-800 text-slate-100 focus:border-cyan-500"
                } ${className || ""}`}/>
  );
}
function ModalTextarea({ light, className, ...props }) {
  return (
    <textarea {...props}
                    className={`w-full rounded-xl px-3 py-2 text-sm outline-none resize-none ${
                      light
                        ? "bg-white border border-slate-200 text-slate-900 focus:border-purple-500"
                        : "bg-slate-950 border border-slate-800 text-slate-100 focus:border-cyan-500"
                    } ${className || ""}`}/>
  );
}
function ModalGhost({ light, onClick, children }) {
  return (
    <button type="button" onClick={onClick}
                className={`inline-flex items-center gap-1.5 h-10 px-4 rounded-full text-xs font-bold uppercase tracking-widest ${
                  light ? "bg-white border border-slate-200 text-slate-700"
                          : "bg-slate-800 border border-slate-700 text-slate-200"
                }`}>{children}</button>
  );
}
function ModalPrimary({ light, onClick, disabled, testId, children }) {
  return (
    <button type="button" onClick={onClick} disabled={disabled}
                data-testid={testId}
                className={`inline-flex items-center gap-1.5 h-10 px-5 rounded-full text-xs font-bold uppercase tracking-widest text-white ${
                  disabled ? "opacity-40 cursor-not-allowed" : "shadow-md"
                }`}
                style={{ background: disabled
                  ? (light ? "#cbd5e1" : "#334155")
                  : (light
                      ? "linear-gradient(135deg,#a855f7,#ec4899)"
                      : "linear-gradient(135deg,#00d4ff,#6366f1)"),
                              color: light ? "#fff" : "#0d0d18" }}>
      {children}
    </button>
  );
}
