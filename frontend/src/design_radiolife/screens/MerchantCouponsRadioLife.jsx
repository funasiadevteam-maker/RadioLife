// RadioLife Merchant — self-serve coupon codes (create/toggle/delete). Web.
import React, { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { ChevronLeft, Tag, Plus, Trash2, Percent, DollarSign } from "lucide-react";
import { API } from "@/AuthContext";

const money = (c) => `$${(c / 100).toFixed(2)}`;
const EMPTY = { code: "", type: "percent", value: 10, min_spend_cents: 0, max_discount_cents: "", usage_limit: "", per_user_limit: 1 };

export default function MerchantCouponsRadioLife() {
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState(EMPTY);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [noProfile, setNoProfile] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/merchant/marketplace/coupons`);
      setItems(r.data.items || []);
    } catch (e) {
      if (e?.response?.status === 404) setNoProfile(true);
    } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const create = async () => {
    setBusy(true); setError(null);
    try {
      await axios.post(`${API}/merchant/marketplace/coupons`, {
        code: form.code.trim().toUpperCase(),
        type: form.type,
        value: Number(form.value),
        min_spend_cents: Math.round(Number(form.min_spend_cents || 0)),
        max_discount_cents: form.max_discount_cents ? Math.round(Number(form.max_discount_cents)) : null,
        usage_limit: form.usage_limit ? Number(form.usage_limit) : null,
        per_user_limit: Number(form.per_user_limit),
      });
      setForm(EMPTY); load();
    } catch (e) {
      setError(e?.response?.data?.detail?.code || "Could not create coupon");
    } finally { setBusy(false); }
  };

  const toggle = async (c) => {
    await axios.patch(`${API}/merchant/marketplace/coupons/${c.coupon_id}`, {
      code: c.code, type: c.type, value: c.value, min_spend_cents: c.min_spend_cents,
      max_discount_cents: c.max_discount_cents, usage_limit: c.usage_limit,
      per_user_limit: c.per_user_limit, active: !c.active,
    });
    load();
  };
  const remove = async (c) => { await axios.delete(`${API}/merchant/marketplace/coupons/${c.coupon_id}`); load(); };

  if (noProfile) {
    return <div className="px-4 pt-16 text-center text-slate-500" data-testid="merchant-coupons-noprofile">Register your shop first to create coupons.</div>;
  }

  return (
    <div className="pb-24" data-testid="rl-merchant-coupons-page">
      <div className="px-4 pt-4 flex items-center gap-2">
        <button onClick={() => navigate(-1)} data-testid="merchant-coupons-back"
          className="w-10 h-10 rounded-full bg-slate-100 flex items-center justify-center"><ChevronLeft size={22} /></button>
        <h1 className="text-2xl font-black text-slate-900">Coupons</h1>
      </div>

      <div className="px-4 mt-4 space-y-4">
        {/* Create form */}
        <div className="bg-white border border-slate-200 rounded-2xl p-4 space-y-3" data-testid="merchant-coupon-form">
          <div className="font-black text-slate-900 flex items-center gap-1.5"><Plus size={16} className="text-orange-600" />New coupon</div>
          <input value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })}
            placeholder="CODE (e.g. SAVE10)" data-testid="coupon-code-input"
            className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm font-bold uppercase" />
          <div className="flex gap-2">
            <button onClick={() => setForm({ ...form, type: "percent" })} data-testid="coupon-type-percent"
              className={`flex-1 flex items-center justify-center gap-1 rounded-xl py-2.5 text-sm font-black border ${form.type === "percent" ? "border-orange-500 bg-orange-50 text-orange-700" : "border-slate-200 text-slate-500"}`}><Percent size={14} />Percent</button>
            <button onClick={() => setForm({ ...form, type: "amount" })} data-testid="coupon-type-amount"
              className={`flex-1 flex items-center justify-center gap-1 rounded-xl py-2.5 text-sm font-black border ${form.type === "amount" ? "border-orange-500 bg-orange-50 text-orange-700" : "border-slate-200 text-slate-500"}`}><DollarSign size={14} />Amount</button>
          </div>
          <label className="block text-xs font-bold text-slate-500">{form.type === "percent" ? "Percent off (1–100)" : "Amount off (cents)"}
            <input type="number" value={form.value} onChange={(e) => setForm({ ...form, value: e.target.value })} data-testid="coupon-value-input"
              className="mt-1 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm font-bold" />
          </label>
          <label className="block text-xs font-bold text-slate-500">Minimum spend (cents, optional)
            <input type="number" value={form.min_spend_cents} onChange={(e) => setForm({ ...form, min_spend_cents: e.target.value })} data-testid="coupon-minspend-input"
              className="mt-1 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm font-bold" />
          </label>
          {error && <div className="text-rose-600 text-sm font-semibold" data-testid="merchant-coupon-error">{error}</div>}
          <button onClick={create} disabled={busy || !form.code.trim()} data-testid="coupon-create-btn"
            className="w-full bg-orange-600 text-white font-black rounded-full py-3 disabled:opacity-50">{busy ? "Saving…" : "Create coupon"}</button>
        </div>

        {/* List */}
        <h3 className="text-base font-black text-slate-900">Your coupons</h3>
        {loading ? <p className="text-slate-400 text-sm">Loading…</p>
          : !items.length ? <p className="text-slate-500 text-sm" data-testid="merchant-coupons-empty">No coupons yet.</p>
          : items.map((c) => (
            <div key={c.coupon_id} className="bg-white border border-slate-200 rounded-2xl p-4 flex items-center gap-3" data-testid={`merchant-coupon-${c.coupon_id}`}>
              <div className="w-10 h-10 rounded-xl bg-orange-100 flex items-center justify-center"><Tag size={18} className="text-orange-600" /></div>
              <div className="flex-1 min-w-0">
                <div className="font-black text-slate-900">{c.code} · {c.type === "percent" ? `${c.value}% off` : `${money(c.value)} off`}</div>
                <div className="text-xs text-slate-500">
                  {c.min_spend_cents > 0 ? `Min ${money(c.min_spend_cents)} · ` : ""}used {c.used_count}{c.usage_limit ? `/${c.usage_limit}` : ""}
                </div>
              </div>
              <button onClick={() => toggle(c)} data-testid={`coupon-toggle-${c.coupon_id}`}
                className={`text-xs font-black rounded-full px-2.5 py-1 ${c.active ? "bg-green-100 text-green-700" : "bg-slate-200 text-slate-500"}`}>{c.active ? "Active" : "Off"}</button>
              <button onClick={() => remove(c)} data-testid={`coupon-remove-${c.coupon_id}`}
                className="w-9 h-9 rounded-full bg-slate-100 flex items-center justify-center text-slate-500"><Trash2 size={16} /></button>
            </div>
          ))}
      </div>
    </div>
  );
}
