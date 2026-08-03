// Phase 18c — Conversions tab for /advertiser/campaigns/:id
import { useEffect, useState } from "react";
import axios from "axios";
const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function ConversionsTab({ advertiserId, campaignId }) {
  const [data, setData] = useState(null);
  useEffect(() => {
    if (!advertiserId || !campaignId) return;
    axios.get(`${API}/advertiser/${advertiserId}/campaigns/${campaignId}/attribution`)
            .then((r) => setData(r.data)).catch(() => {});
  }, [advertiserId, campaignId]);
  if (!data) return <div className="text-text-secondary text-sm p-4">Loading…</div>;
  return (
    <div className="space-y-4" data-testid="conversions-tab">
      <h2 className="font-display font-bold text-xl">Conversions</h2>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Card label="Impressions"  value={data.impressions}    testid="conv-impressions" />
        <Card label="Coupon saves" value={data.coupon_saves}  testid="conv-saves" />
        <Card label="Redemptions"   value={data.redemptions}    testid="conv-redemptions" />
        <Card label="Check-ins"        value={data.checkins}          testid="conv-checkins" />
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
        <Card label="Save rate"       value={`${(data.save_rate*100).toFixed(1)}%`}    testid="conv-save-rate" />
        <Card label="Redeem rate" value={`${(data.redeem_rate*100).toFixed(1)}%`} testid="conv-redeem-rate" />
        <Card label="Cost / save"      value={`$${data.cost_per_save.toFixed(2)}`}    testid="conv-cps" />
        <Card label="Cost / redeem" value={`$${data.cost_per_redeem.toFixed(2)}`} testid="conv-cpr" />
      </div>
    </div>
  );
}

const Card = ({ label, value, testid }) => (
  <div className="rounded-2xl p-4 border border-white/[0.08]" data-testid={testid}>
    <div className="text-xs text-text-secondary uppercase tracking-wide">{label}</div>
    <div className="font-display font-bold text-2xl mt-1">{value}</div>
  </div>
);
