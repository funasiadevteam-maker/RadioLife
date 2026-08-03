// Phase MER.3 — Merchant Prepaid Meal SKU management.
import React, { useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { UtensilsCrossed, Plus, Copy, Link as LinkIcon, X, Loader2,
                  Sparkles } from "lucide-react";
import { useDesignVariant } from "@/hooks/useDesignVariant";
import { useMerchant } from "./MerchantShell";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
const FMT_CENTS = (n, ccy = "AED") =>
  `${(Number(n || 0) / 100).toFixed(2)} ${ccy}`;

export default function MerchantPrepaidMeals() {
  const variant = useDesignVariant();
  const light = variant === "radiolife";
  const { merchant, hasPerm } = useMerchant();

  const [items, setItems]        = useState([]);
  const [loading, setLoading]    = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [genLinkFor, setGenLinkFor] = useState(null);
  const canEdit = hasPerm ? hasPerm("can_create_links") : true;

  const load = async () => {
    if (!merchant?.merchant_id) return;
    setLoading(true);
    try {
      const { data } = await axios.get(
        `${API}/merchant/${merchant.merchant_id}/prepaid-meal-skus`,
        { withCredentials: true });
      setItems(data.items || []);
    } catch (e) {
      toast.error(`Load failed: ${e?.response?.data?.detail?.code || e.message}`);
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [merchant?.merchant_id]);

  const bgClass = light
    ? "min-h-screen bg-gradient-to-b from-purple-50 via-white to-pink-50"
    : "min-h-screen bg-slate-950 text-slate-100";
  const cardClass = light
    ? "bg-white border border-slate-100 shadow-sm rounded-3xl"
    : "bg-slate-900 border border-slate-800 rounded-3xl";

  if (loading) {
    return <div className={`${bgClass} p-8`} data-testid="merchant-meals-loading">
      <Loader2 className="animate-spin mx-auto mt-24" size={30}/>
    </div>;
  }

  return (
    <div className={`${bgClass} p-4 sm:p-8`} data-testid="merchant-meals-page">
      <div className="max-w-5xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <div>
            <div className={`text-[10px] font-bold uppercase tracking-widest ${
              light ? "text-purple-600" : "text-cyan-400"}`}>Wallet · Phase MER.3</div>
            <h1 className={`text-3xl font-black tracking-tight ${
              light ? "text-slate-900" : "text-white"}`}>Prepaid Meal Packs</h1>
            <p className={`text-sm mt-1 ${light ? "text-slate-600" : "text-slate-400"}`}>
              Sell N-meal packs — each redemption at the counter burns 1 meal.
            </p>
          </div>
          {canEdit && (
            <button type="button" onClick={() => setShowCreate(true)}
                          data-testid="merchant-meals-create-btn"
                          className={`inline-flex items-center gap-2 h-11 rounded-full px-5 text-sm font-black text-white`}
                          style={{background:"linear-gradient(135deg,#a855f7,#ec4899)"}}>
              <Plus size={16}/> New Meal Pack SKU
            </button>
          )}
        </div>

        {items.length === 0 ? (
          <div className={`${cardClass} p-10 text-center`}
                data-testid="merchant-meals-empty">
            <UtensilsCrossed className="mx-auto mb-3"
                                                size={40} color={light ? "#a855f7" : "#00d4ff"}/>
            <h3 className={`text-lg font-black ${
              light ? "text-slate-900" : "text-white"}`}>No meal packs yet</h3>
            <p className={`text-sm mt-1 ${light ? "text-slate-600" : "text-slate-400"}`}>
              Create a pack (e.g. "5 lunches for AED 80 · save 20%") to start selling.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4"
                data-testid="merchant-meals-grid">
            {items.map(sku => (
              <SKUCard key={sku.sku_id} sku={sku} light={light} canEdit={canEdit}
                              onGenLink={() => setGenLinkFor(sku)}
                              onReload={load}/>
            ))}
          </div>
        )}
      </div>

      {showCreate && (
        <CreateModal light={light} merchant={merchant}
                                onClose={() => setShowCreate(false)}
                                onCreated={() => { setShowCreate(false); load(); }}/>
      )}
      {genLinkFor && (
        <GenLinkModal light={light} merchant={merchant} sku={genLinkFor}
                                    onClose={() => setGenLinkFor(null)}/>
      )}
    </div>
  );
}


function SKUCard({ sku, light, canEdit, onGenLink, onReload }) {
  const { merchant } = useMerchant();
  const inactive = !sku.active;
  const totalIfSeparate = (sku.meal_count || 0) * (sku.per_meal_value_cents || 0);
  const savings = Math.max(0, totalIfSeparate - (sku.total_price_cents || 0));
  const savingsPct = totalIfSeparate ? Math.round(savings / totalIfSeparate * 100) : 0;

  const deactivate = async () => {
    if (!window.confirm(`Deactivate "${sku.name}"?`)) return;
    try {
      await axios.post(
        `${API}/merchant/${merchant.merchant_id}/prepaid-meal-skus/${sku.sku_id}/deactivate`,
        null, { withCredentials: true });
      toast.success("SKU deactivated");
      onReload();
    } catch (e) {
      toast.error(`Failed: ${e?.response?.data?.detail?.code || e.message}`);
    }
  };

  return (
    <div className={`rounded-3xl p-5 ${
      light ? "bg-white border border-slate-100 shadow-sm"
                : "bg-slate-900 border border-slate-800"
    } ${inactive ? "opacity-50" : ""}`}
              data-testid={`merchant-meals-row-${sku.sku_id}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className={`text-[10px] font-bold uppercase tracking-widest ${
            light ? "text-purple-600" : "text-cyan-400"}`}>MEAL PACK SKU</div>
          <h3 className={`mt-1 text-lg font-black ${
            light ? "text-slate-900" : "text-white"}`}>{sku.name}</h3>
          {sku.description && (
            <p className={`mt-1 text-xs ${light ? "text-slate-600" : "text-slate-500"}`}>
              {sku.description}
            </p>
          )}
        </div>
        {inactive && (
          <span className={`text-[10px] font-black uppercase px-2 py-1 rounded-full ${
            light ? "bg-slate-100 text-slate-500"
                    : "bg-slate-800 text-slate-500"}`}>Inactive</span>
        )}
      </div>

      <div className="mt-4 flex items-baseline gap-2 flex-wrap">
        <span className={`text-2xl font-black tabular-nums ${
          light ? "text-slate-900" : "text-white"}`}>
          {sku.meal_count} meals
        </span>
        <span className={`text-lg font-black ${
          light ? "text-purple-600" : "text-cyan-400"}`}>
          for {FMT_CENTS(sku.total_price_cents, sku.currency)}
        </span>
        {savingsPct > 0 && (
          <span className={`text-[10px] font-black uppercase px-2 py-1 rounded-full ${
            light ? "bg-emerald-50 text-emerald-700"
                    : "bg-emerald-500/15 text-emerald-300"}`}>
            Save {savingsPct}%
          </span>
        )}
      </div>

      <div className={`mt-2 text-xs ${
        light ? "text-slate-600" : "text-slate-500"}`}>
        {FMT_CENTS(sku.per_meal_value_cents, sku.currency)} per meal · Expires {sku.expires_days}d after purchase
      </div>

      {canEdit && (
        <div className="mt-4 flex gap-2 flex-wrap">
          <button type="button" onClick={onGenLink}
                        disabled={inactive}
                        data-testid={`merchant-meals-genlink-${sku.sku_id}`}
                        className={`inline-flex items-center gap-1 h-9 rounded-full px-3 text-xs font-bold ${
                          inactive ? "opacity-40 cursor-not-allowed" :
                          (light ? "bg-purple-600 text-white hover:bg-purple-700"
                                        : "bg-cyan-500 text-slate-950 hover:bg-cyan-400")}`}>
            <LinkIcon size={12}/> Create Payment Link
          </button>
          {!inactive && (
            <button type="button" onClick={deactivate}
                          data-testid={`merchant-meals-deactivate-${sku.sku_id}`}
                          className={`h-9 rounded-full px-3 text-xs font-bold ${
                            light ? "text-rose-600 hover:bg-rose-50"
                                    : "text-rose-400 hover:bg-slate-800"}`}>
              Deactivate
            </button>
          )}
        </div>
      )}
    </div>
  );
}


function CreateModal({ light, merchant, onClose, onCreated }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [mealCount, setMealCount] = useState(5);
  const [totalPrice, setTotalPrice] = useState(80);
  const [terms, setTerms] = useState("");
  const [expiresDays, setExpiresDays] = useState(90);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  const submit = async () => {
    setErr(null);
    if (!name.trim()) { setErr("Name is required"); return; }
    if (Number(mealCount) < 2) { setErr("Meal count must be at least 2"); return; }
    if (Number(totalPrice) <= 0) { setErr("Total price required"); return; }
    setBusy(true);
    try {
      await axios.post(
        `${API}/merchant/${merchant.merchant_id}/prepaid-meal-skus`,
        { name: name.trim(),
          description: description.trim() || null,
          meal_count: Number(mealCount),
          total_price_cents: Math.round(Number(totalPrice) * 100),
          terms: terms.trim() || null,
          expires_days: Number(expiresDays) || 90 },
        { withCredentials: true });
      toast.success("Meal pack SKU created");
      onCreated();
    } catch (e) {
      setErr(e?.response?.data?.detail?.code || e.message);
    } finally { setBusy(false); }
  };

  return (
    <Modal light={light} onClose={onClose}
                testid="merchant-meals-create-modal">
      <h2 className={`text-xl font-black mb-4 ${
        light ? "text-slate-900" : "text-white"}`}>New Meal Pack SKU</h2>
      <Label light={light}>Name</Label>
      <input type="text" value={name} onChange={e => setName(e.target.value)}
                  placeholder="e.g. Weekday Lunch 5-Pack"
                  data-testid="merchant-meals-create-name"
                  className={inputClass(light)}/>
      <Label light={light} className="mt-3">Description (optional)</Label>
      <input type="text" value={description} onChange={e => setDescription(e.target.value)}
                  className={inputClass(light)}/>
      <div className="grid grid-cols-2 gap-3 mt-3">
        <div>
          <Label light={light}>Meals in pack</Label>
          <input type="number" min={2} max={100} value={mealCount}
                      onChange={e => setMealCount(e.target.value)}
                      data-testid="merchant-meals-create-meals"
                      className={inputClass(light)}/>
        </div>
        <div>
          <Label light={light}>Total price (AED)</Label>
          <input type="number" min={1} step="0.01" value={totalPrice}
                      onChange={e => setTotalPrice(e.target.value)}
                      data-testid="merchant-meals-create-price"
                      className={inputClass(light)}/>
        </div>
      </div>
      <div className={`mt-2 text-xs ${
        light ? "text-slate-500" : "text-slate-400"}`}>
        Per-meal value: {FMT_CENTS(Math.round((Number(totalPrice) / (Number(mealCount) || 1)) * 100), "AED")}
      </div>

      <Label light={light} className="mt-3">Expires (days after purchase)</Label>
      <input type="number" min={1} max={3650} value={expiresDays}
                  onChange={e => setExpiresDays(e.target.value)}
                  className={inputClass(light)}/>
      <Label light={light} className="mt-3">Terms & Conditions (optional)</Label>
      <textarea rows={3} value={terms} onChange={e => setTerms(e.target.value)}
                        className={inputClass(light)}/>

      {err && <div className={`mt-3 rounded-xl px-3 py-2 text-sm ${
        light ? "bg-rose-50 text-rose-800" : "bg-rose-500/10 text-rose-300"
      }`} data-testid="merchant-meals-create-error">{err}</div>}

      <button type="button" onClick={submit} disabled={busy}
                    data-testid="merchant-meals-create-submit"
                    className={`mt-4 w-full h-11 rounded-full font-black text-sm text-white ${
                      busy ? "opacity-50" : ""}`}
                    style={{background:"linear-gradient(135deg,#a855f7,#ec4899)"}}>
        {busy ? "Creating…" : "Create SKU"}
      </button>
    </Modal>
  );
}


function GenLinkModal({ light, merchant, sku, onClose }) {
  const [busy, setBusy] = useState(false);
  const [link, setLink] = useState(null);

  const genLink = async () => {
    setBusy(true);
    try {
      const { data } = await axios.post(
        `${API}/merchant/${merchant.merchant_id}/payment-links`,
        { link_type: "prepaid_meal",
          title: `${sku.name} — ${sku.meal_count} meals`,
          amount_cents: sku.total_price_cents,
          currency: sku.currency,
          prepaid_meal_id: sku.sku_id },
        { withCredentials: true });
      setLink(data);
      toast.success("Payment link created");
    } catch (e) {
      toast.error(`Failed: ${e?.response?.data?.detail?.code || e.message}`);
    } finally { setBusy(false); }
  };

  return (
    <Modal light={light} onClose={onClose}
                testid="merchant-meals-genlink-modal">
      <h2 className={`text-xl font-black mb-1 ${
        light ? "text-slate-900" : "text-white"}`}>
        Create Payment Link
      </h2>
      <p className={`text-sm mb-4 ${light ? "text-slate-600" : "text-slate-400"}`}>
        for <b>{sku.name}</b> ({sku.meal_count} meals @ {FMT_CENTS(sku.total_price_cents, sku.currency)})
      </p>

      {!link ? (
        <button type="button" onClick={genLink} disabled={busy}
                      data-testid="merchant-meals-genlink-submit"
                      className={`w-full h-11 rounded-full font-black text-sm text-white ${
                        busy ? "opacity-50" : ""}`}
                      style={{background:"linear-gradient(135deg,#a855f7,#ec4899)"}}>
          {busy ? "Creating…" : `Generate Payment Link for ${FMT_CENTS(sku.total_price_cents, sku.currency)}`}
        </button>
      ) : (
        <div>
          <Sparkles className="mx-auto mb-3" size={30} color={light ? "#a855f7" : "#00d4ff"}/>
          <div className={`text-sm font-black text-center ${
            light ? "text-slate-900" : "text-white"}`}>Link ready!</div>
          <div className={`mt-4 p-3 rounded-xl break-all text-xs ${
            light ? "bg-slate-50 text-slate-800" : "bg-slate-950 text-slate-300"}`}
                data-testid="merchant-meals-genlink-url">
            {link.hosted_url}
          </div>
          <div className="mt-3 flex gap-2">
            <button type="button"
                          onClick={() => { navigator.clipboard.writeText(link.hosted_url);
                                                          toast.success("Copied"); }}
                          data-testid="merchant-meals-genlink-copy"
                          className={`flex-1 h-11 rounded-full text-xs font-bold inline-flex items-center justify-center gap-1 ${
                            light ? "bg-purple-600 text-white"
                                    : "bg-cyan-500 text-slate-950"}`}>
            <Copy size={14}/> Copy URL
            </button>
            <button type="button" onClick={onClose}
                          className={`flex-1 h-11 rounded-full text-xs font-bold ${
                            light ? "bg-slate-100 text-slate-700"
                                    : "bg-slate-800 text-slate-300"}`}>
              Done
            </button>
          </div>
        </div>
      )}
    </Modal>
  );
}

function Modal({ light, onClose, testid, children }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
              onClick={onClose}>
      <div onClick={e => e.stopPropagation()}
                data-testid={testid}
                className={`w-full max-w-md rounded-3xl p-6 max-h-[90vh] overflow-y-auto ${
                  light ? "bg-white" : "bg-slate-900 border border-slate-800"}`}>
        <div className="flex justify-end mb-2">
          <button type="button" onClick={onClose}
                        className={light ? "text-slate-500" : "text-slate-500"}>
            <X size={20}/>
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

function Label({ children, light, className = "" }) {
  return <div className={`text-[10px] font-bold uppercase tracking-widest mb-1 ${
    light ? "text-slate-500" : "text-slate-500"} ${className}`}>{children}</div>;
}

function inputClass(light) {
  return `w-full h-11 rounded-xl px-3 text-sm outline-none ${
    light
      ? "bg-slate-50 border border-slate-200 text-slate-900 focus:border-purple-500"
      : "bg-slate-950 border border-slate-800 text-slate-100 focus:border-cyan-500"}`;
}
