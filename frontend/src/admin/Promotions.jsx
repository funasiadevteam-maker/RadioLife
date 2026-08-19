// Marketplace Promotions review (admin) — approve/reject merchant shop-boost
// requests (Phase F). Approving activates the promotion for its window and
// bumps the shop in Shop search + the Promoted rail. Admins can also comp a
// promotion for any business.
import React, { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { Loader2, Rocket, Check, X, Gift } from "lucide-react";
import { toast } from "sonner";
import { API } from "@/AuthContext";
import { Card, Button } from "@/shell/primitives";

const money = (c) => `$${((c || 0) / 100).toFixed(2)}`;
const TABS = [
  ["pending_review", "In review"],
  ["active", "Active"],
  ["rejected", "Rejected"],
  ["all", "All"],
];

export default function Promotions() {
  const [status, setStatus] = useState("pending_review");
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [actingId, setActingId] = useState(null);
  const [grantBiz, setGrantBiz] = useState("");
  const [grantTier, setGrantTier] = useState("spotlight_7");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/admin/marketplace/promotions`, { params: { status } });
      setItems(r.data.items || []);
    } catch { toast.error("Failed to load — admin only."); }
    finally { setLoading(false); }
  }, [status]);
  useEffect(() => { load(); }, [load]);

  const act = async (id, action, body) => {
    setActingId(id);
    try {
      await axios.post(`${API}/admin/marketplace/promotions/${id}/${action}`, body || {});
      toast.success(action === "approve" ? "Promotion is live" : "Rejected");
      load();
    } catch { toast.error("Action failed"); }
    finally { setActingId(null); }
  };

  const grant = async () => {
    if (!grantBiz.trim()) { toast.error("Enter a business_id"); return; }
    setActingId("grant");
    try {
      await axios.post(`${API}/admin/marketplace/promotions/grant`,
        { business_id: grantBiz.trim(), tier: grantTier });
      toast.success("Comped promotion is live");
      setGrantBiz("");
      load();
    } catch { toast.error("Grant failed — check business_id"); }
    finally { setActingId(null); }
  };

  return (
    <div className="p-6 max-w-4xl mx-auto" data-testid="admin-promotions-page">
      <div className="flex items-center gap-2 mb-1">
        <Rocket className="text-orange-500" size={22} />
        <h1 className="text-2xl font-black">Promoted Marketplace</h1>
      </div>
      <p className="text-sm text-white/50 mb-4">Approve merchant shop-boost requests. Approving activates the promotion and ranks the shop higher in Shop search + the Promoted rail.</p>

      <Card className="p-4 mb-4">
        <div className="flex items-center gap-2 mb-2 font-bold text-sm"><Gift size={15} className="text-orange-400" />Comp a promotion (free)</div>
        <div className="flex flex-wrap gap-2 items-center">
          <input value={grantBiz} onChange={(e) => setGrantBiz(e.target.value)} placeholder="business_id"
            data-testid="promo-grant-biz"
            className="rounded-token-md bg-white/[0.04] border border-white/[0.08] px-3 py-2 text-sm flex-1 min-w-[180px]" />
          <select value={grantTier} onChange={(e) => setGrantTier(e.target.value)} data-testid="promo-grant-tier"
            className="rounded-token-md bg-white/[0.04] border border-white/[0.08] px-3 py-2 text-sm">
            <option value="spotlight_7">Spotlight · 7d</option>
            <option value="boost_14">Boost · 14d</option>
            <option value="premium_30">Premium · 30d</option>
          </select>
          <Button onClick={grant} disabled={actingId === "grant"} data-testid="promo-grant-btn">Grant</Button>
        </div>
      </Card>

      <div className="flex gap-2 mb-4">
        {TABS.map(([k, l]) => (
          <button key={k} onClick={() => setStatus(k)} data-testid={`promo-tab-${k}`}
            className={`px-3 py-1.5 rounded-full text-sm font-bold ${status === k ? "bg-orange-500 text-white" : "bg-white/[0.05] text-white/60"}`}>{l}</button>
        ))}
      </div>

      {loading ? (
        <div className="flex justify-center py-16"><Loader2 className="animate-spin text-white/40" /></div>
      ) : items.length === 0 ? (
        <div className="text-center text-white/40 py-16" data-testid="promo-empty">No promotions in &quot;{status}&quot;.</div>
      ) : (
        <div className="space-y-2">
          {items.map((p) => (
            <Card key={p.promotion_id} className="p-4 flex items-center justify-between" data-testid={`promo-row-${p.promotion_id}`}>
              <div>
                <div className="font-bold flex items-center gap-2">
                  {p.public_name || p.business_id}
                  {p.via_partner && (
                    <span data-testid={`promo-via-partner-${p.promotion_id}`}
                      className="text-[10px] font-black px-2 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300">
                      via API{p.partner_name ? ` · ${p.partner_name}` : ""}
                    </span>
                  )}
                </div>
                <div className="text-xs text-white/50 mt-0.5">
                  {p.name} · {p.days}d · {p.price_cents ? money(p.price_cents) : "COMP"} · {p.paid ? "paid" : "unpaid"}
                  {p.admin_note ? ` · ${p.admin_note}` : ""}
                </div>
              </div>
              {p.status === "pending_review" ? (
                <div className="flex gap-2">
                  <Button onClick={() => act(p.promotion_id, "approve")} disabled={actingId === p.promotion_id}
                    data-testid={`promo-approve-${p.promotion_id}`}><Check size={15} /> Approve</Button>
                  <Button variant="ghost" onClick={() => act(p.promotion_id, "reject", { note: "Rejected by admin" })}
                    disabled={actingId === p.promotion_id} data-testid={`promo-reject-${p.promotion_id}`}><X size={15} /> Reject</Button>
                </div>
              ) : (
                <span className={`text-[11px] font-black px-2.5 py-1 rounded-full ${p.status === "active" ? "bg-green-500/20 text-green-300" : "bg-white/10 text-white/50"}`}>{p.status}</span>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
