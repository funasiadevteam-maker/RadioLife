// Sell on RadioLife — business registration (web).
import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import { ChevronLeft, Coins, CheckCircle2 } from "lucide-react";
import { API } from "@/AuthContext";
import { RLChip } from "../DesignSystem";

const POINT_COST_CENTS = 3;
const SELL_OPTIONS = [
  ["menu", "Restaurant Menu"], ["products", "Products"], ["services", "Services"],
  ["appointments", "Appointments"], ["memberships", "Memberships"],
  ["gift_cards", "Gift Cards"], ["events", "Events"],
];

export default function SellOnRadioLife() {
  const navigate = useNavigate();
  const [cats, setCats] = useState([]);
  const [existing, setExisting] = useState(null);
  const [busy, setBusy] = useState(false);
  const [f, setF] = useState({ legal_name: "", public_name: "", description: "", phone: "", city: "", category: "", default_points: "150", points_per_dollar: "2" });
  const [sells, setSells] = useState([]);
  const [commissionAgreed, setCommissionAgreed] = useState(false);
  const [parity, setParity] = useState(false);

  useEffect(() => {
    axios.get(`${API}/shop/categories`).then((r) => setCats(r.data.items || [])).catch(() => {});
    axios.get(`${API}/merchant/marketplace/profile`).then((r) => setExisting(r.data.profile)).catch(() => {});
  }, []);

  const set = (k, v) => setF((p) => ({ ...p, [k]: v }));
  const toggle = (k) => setSells((p) => p.includes(k) ? p.filter((x) => x !== k) : [...p, k]);
  const pts = parseInt(f.default_points || "0", 10) || 0;
  const cost = `$${((pts * POINT_COST_CENTS) / 100).toFixed(2)}`;
  const cat = cats.find((c) => c.key === f.category);
  const minPts = cat?.min_bigpoints || 0;
  const isRestaurant = f.category === "restaurant";
  const canSubmit = f.legal_name && f.public_name && f.category && sells.length > 0 && pts >= minPts && commissionAgreed && (!isRestaurant || parity);

  const submit = async () => {
    if (!canSubmit) return;
    setBusy(true);
    try {
      const r = await axios.post(`${API}/merchant/marketplace/onboarding`, {
        business_type: f.category, legal_name: f.legal_name, public_name: f.public_name,
        description: f.description || null, phone: f.phone || null,
        category: f.category, locations: f.city ? [{ city: f.city, address: "" }] : [],
        sells, bigpoints: { mode: "default", default_points: pts, points_per_dollar: parseFloat(f.points_per_dollar) || 2 },
        funding_mode: "auto_deduct", commission_agreed: commissionAgreed, price_parity_certified: parity,
      });
      if (r.data.ok) { toast.success("Submitted for approval!"); navigate("/shop"); }
    } catch (e) {
      toast.error(e?.response?.data?.detail?.code || "Submission failed");
    } finally { setBusy(false); }
  };

  const input = "w-full bg-white border border-slate-200 rounded-xl px-3 py-2.5 text-sm text-slate-800 outline-none focus:border-orange-400";
  const label = "text-[11px] font-black tracking-wide text-slate-400 mt-4 mb-1.5 block";

  return (
    <div className="px-4 pt-4 pb-10" data-testid="rl-sell-page">
      <div className="flex items-center gap-2 mb-2">
        <button onClick={() => navigate(-1)} data-testid="sell-back"><ChevronLeft size={24} className="text-slate-800" /></button>
        <h1 className="text-xl font-black text-slate-900">Sell on RadioLife</h1>
      </div>

      {existing && (
        <div className="flex items-center gap-2 bg-orange-50 border border-orange-200 rounded-xl p-3 text-sm text-slate-700" data-testid="sell-existing">
          You already have a listing ({existing.status}). Submitting again updates it.
        </div>
      )}

      <label className={label}>BUSINESS NAME (PUBLIC)</label>
      <input className={input} value={f.public_name} onChange={(e) => set("public_name", e.target.value)} data-testid="sell-public-name" placeholder="e.g. The Grill House" />
      <label className={label}>LEGAL BUSINESS NAME</label>
      <input className={input} value={f.legal_name} onChange={(e) => set("legal_name", e.target.value)} data-testid="sell-legal-name" placeholder="e.g. Grill House LLC" />

      <label className={label}>CATEGORY</label>
      <div className="flex gap-2 overflow-x-auto pb-1">
        {cats.map((c) => (
          <RLChip key={c.key} active={f.category === c.key} onClick={() => set("category", c.key)}
            data-testid={`sell-cat-${c.key}`} className="whitespace-nowrap">{c.name}</RLChip>
        ))}
      </div>

      <label className={label}>WHAT DO YOU SELL?</label>
      <div className="flex flex-wrap gap-2">
        {SELL_OPTIONS.map(([k, l]) => (
          <RLChip key={k} active={sells.includes(k)} onClick={() => toggle(k)} data-testid={`sell-offer-${k}`}>{l}</RLChip>
        ))}
      </div>

      <label className={label}>CITY</label>
      <input className={input} value={f.city} onChange={(e) => set("city", e.target.value)} data-testid="sell-city" placeholder="e.g. Dubai" />
      <label className={label}>PHONE (OPTIONAL)</label>
      <input className={input} value={f.phone} onChange={(e) => set("phone", e.target.value)} data-testid="sell-phone" placeholder="+971 ..." />
      <label className={label}>DESCRIPTION (OPTIONAL)</label>
      <textarea className={input} rows={3} value={f.description} onChange={(e) => set("description", e.target.value)} data-testid="sell-desc" placeholder="Tell customers about your business" />

      <h2 className="text-lg font-black text-slate-900 mt-6">BigPoints Reward</h2>
      <p className="text-slate-500 text-xs mt-1">Choose how many BigPoints customers earn. BigPoints help attract & retain RadioLife customers.</p>
      <label className={label}>BIGPOINTS PER TRANSACTION</label>
      <input className={input} type="number" value={f.default_points} onChange={(e) => set("default_points", e.target.value)} data-testid="sell-points" />
      {minPts > 0 && pts < minPts && <div className="text-orange-600 text-xs font-bold mt-1">Minimum for {cat?.name} is {minPts} BigPoints.</div>}

      <div className="flex items-center justify-between bg-amber-100 rounded-2xl p-4 mt-4" data-testid="sell-cost-preview">
        <div>
          <div className="text-[10px] font-black tracking-wide text-amber-800">YOUR BIGPOINTS COST</div>
          <div className="text-sm font-bold text-amber-900 flex items-center gap-1"><Coins size={13} />{pts} × $0.03</div>
        </div>
        <div className="text-2xl font-black text-amber-950">{cost}</div>
      </div>

      <button onClick={() => setCommissionAgreed((v) => !v)} data-testid="sell-commission-agree"
        className="flex items-start gap-2 mt-4 text-left">
        <CheckCircle2 size={22} className={commissionAgreed ? "text-orange-600" : "text-slate-300"} />
        <span className="text-sm text-slate-600">I agree to the RadioLife commission for my category{cat ? ` (${cat.commission_pct}%)` : ""}.</span>
      </button>

      {isRestaurant && (
        <button onClick={() => setParity((v) => !v)} data-testid="sell-parity" className="flex items-start gap-2 mt-3 text-left">
          <CheckCircle2 size={22} className={parity ? "text-orange-600" : "text-slate-300"} />
          <span className="text-sm text-slate-600">I certify my RadioLife menu prices match my own website&apos;s prices.</span>
        </button>
      )}

      <button onClick={submit} disabled={busy || !canSubmit} data-testid="sell-submit"
        className={`w-full mt-6 rounded-full py-3 font-black text-white ${canSubmit ? "bg-orange-600 hover:bg-orange-700" : "bg-slate-300"}`}>
        {busy ? "Submitting…" : "Submit for Approval"}
      </button>
    </div>
  );
}
