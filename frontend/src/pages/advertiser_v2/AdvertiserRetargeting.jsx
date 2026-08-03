// Phase M — M6 Retargeting Audiences · Advertiser dashboard.
// Dual-design.  Tabs: Audiences / Campaigns.
import { useCallback, useEffect, useMemo, useState } from "react";
import axios from "axios";
import {
  Loader2, Target, Plus, X, Users, Trash2, Play, Pause, Check,
  AlertTriangle,
} from "lucide-react";
import { useAdvertiser } from "@/pages/advertiser_v2/AdvertiserShell";
import { useDesignVariant } from "@/hooks/useDesignVariant";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

const SIGNAL_TYPES = [
  { v: "listen_minutes_total",       label: "Listen minutes (any station)" },
  { v: "podcast_completions",        label: "Podcast completions" },
  { v: "trivia_games_played",        label: "Trivia games played" },
  { v: "coupons_saved",              label: "Coupons saved" },
  { v: "marketplace_saves",          label: "Marketplace saves" },
  { v: "scan_to_pay_txns",           label: "Scan-to-pay transactions" },
  { v: "location_matched_geofence",  label: "Matched any location geofence" },
  { v: "takeover_listened",          label: "Listened to a takeover" },
  { v: "predict_win_participated",   label: "Predict-win participation" },
  { v: "station_played_specific",    label: "Played a specific station",
    requires_target: true },
  { v: "merchant_visited_specific",  label: "Scan-to-pay at specific merchant",
    requires_target: true },
];

const BASE_AD_TYPES = [
  "banner", "coupon", "notification", "marketplace_slot",
  "sponsored_read", "takeover", "location_boost",
];


export default function AdvertiserRetargeting() {
  const adv = useAdvertiser();
  const business_id = adv?.active?.advertiser_id || adv?.activeId;
  const variant = useDesignVariant();
  const light = variant === "radiolife";
  const [tab, setTab] = useState("audiences");

  if (!business_id) {
    return (
      <div data-testid="advertiser-rt-no-advertiser"
           className={`p-6 ${light ? "text-slate-900" : "text-white"}`}>
        Loading advertiser context…
      </div>
    );
  }
  return (
    <div data-testid="advertiser-rt-page" data-variant={variant}>
      <div className="flex items-center gap-3 mb-2">
        <Target size={22} className="text-orange-500" />
        <h1 className={`text-2xl md:text-3xl xl:text-4xl font-black ${
                       light ? "text-slate-900" : "text-white"}`}>
          Retargeting
        </h1>
      </div>
      <p className={`text-sm mb-4 ${
                     light ? "text-slate-500" : "text-slate-400"}`}>
        Define audiences from user behavior signals, then target them
        with any of your existing ad campaigns.  Platform fee: 25%.
      </p>
      <div className="flex gap-2 mb-4">
        <TabBtn active={tab === "audiences"}
                onClick={() => setTab("audiences")}
                testid="advertiser-rt-tab-audiences" light={light}>
          Audiences
        </TabBtn>
        <TabBtn active={tab === "campaigns"}
                onClick={() => setTab("campaigns")}
                testid="advertiser-rt-tab-campaigns" light={light}>
          Campaigns
        </TabBtn>
      </div>
      {tab === "audiences"
        ? <AudiencesTab business_id={business_id} light={light} />
        : <CampaignsTab business_id={business_id} light={light} />}
    </div>
  );
}


function TabBtn({ active, onClick, testid, light, children }) {
  return (
    <button onClick={onClick} data-testid={testid}
            className={`px-4 py-1.5 rounded-full text-xs font-bold ${
              active
                ? "bg-orange-500 text-white"
                : (light
                    ? "bg-slate-100 text-slate-700 hover:bg-slate-200"
                    : "bg-white/5 text-slate-300 hover:bg-white/10")}`}>
      {children}
    </button>
  );
}


// ─── Audiences tab ─────────────────────────────────────────────
function AudiencesTab({ business_id, light }) {
  const [items, setItems] = useState(null);
  const [showCreate, setShowCreate] = useState(false);
  const [err, setErr] = useState(null);

  const load = useCallback(async () => {
    setErr(null);
    try {
      const { data } = await axios.get(
        `${API}/advertiser/${business_id}/retargeting-audiences`,
        { withCredentials: true });
      setItems(data.items || []);
    } catch (e) {
      setErr(e?.response?.data?.detail?.code || e.message);
      setItems([]);
    }
  }, [business_id]);
  useEffect(() => { load(); }, [load]);

  return (
    <div>
      <button onClick={() => setShowCreate(true)}
              data-testid="advertiser-rt-audience-create"
              className="inline-flex items-center gap-2 px-4 py-2 rounded-full
                         bg-orange-500 text-white text-xs font-black
                         hover:bg-orange-400 mb-4">
        <Plus size={14} /> New audience
      </button>
      {items === null && (
        <div className={light ? "text-slate-500" : "text-slate-400"}
             data-testid="advertiser-rt-audience-loading">
          <Loader2 size={16} className="animate-spin inline" /> Loading…
        </div>
      )}
      {items?.length === 0 && (
        <div className={`text-sm ${
                        light ? "text-slate-500" : "text-slate-400"}`}
             data-testid="advertiser-rt-audience-empty">
          No audiences yet.
        </div>
      )}
      {err && (
        <div data-testid="advertiser-rt-audience-error"
             className={light ? "text-red-600" : "text-red-400"}>
          {err}
        </div>
      )}
      <div className="grid gap-3">
        {(items || []).map((a) => (
          <AudienceCard key={a.id} a={a} light={light}
                        business_id={business_id} reload={load} />
        ))}
      </div>
      {showCreate && (
        <AudienceWizard onClose={() => { setShowCreate(false); load(); }}
                        business_id={business_id} light={light} />
      )}
    </div>
  );
}


function AudienceCard({ a, light, business_id, reload }) {
  const muted = light ? "text-slate-500" : "text-slate-400";
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const action = async (path) => {
    setBusy(true); setErr(null);
    try {
      await axios.post(
        `${API}/advertiser/${business_id}/retargeting-audiences/${a.id}/${path}`,
        {}, { withCredentials: true });
      await reload();
    } catch (e) {
      setErr(e?.response?.data?.detail?.detail
             || e?.response?.data?.detail?.code
             || e.message);
    }
    setBusy(false);
  };
  return (
    <div data-testid={`advertiser-rt-audience-card-${a.id}`}
         className={`rounded-2xl p-4 border ${
           light ? "bg-white border-slate-200"
                 : "bg-white/5 border-white/10"}`}>
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <div className={`font-black text-sm ${
                          light ? "text-slate-900" : "text-white"}`}>
            {a.name}
            <span data-testid={`advertiser-rt-audience-status-${a.id}`}
                  className={`ml-2 text-[10px] px-2 py-0.5 rounded-full font-bold ${
                    a.status === "active"
                      ? "bg-emerald-500 text-white"
                      : a.status === "archived"
                          ? "bg-slate-500 text-white"
                          : "bg-amber-500 text-white"}`}>
              {a.status}
            </span>
          </div>
          <div className={`text-[11px] mt-1 ${muted}`}>
            {(a.rules || []).length} rule(s) · logic: {a.rule_logic}
            {" · size: "}
            <span data-testid={`advertiser-rt-audience-size-${a.id}`}
                  className="font-bold">
              {a.estimated_size || 0}
            </span>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <button onClick={() => action("compute")} disabled={busy}
                  data-testid={`advertiser-rt-audience-compute-${a.id}`}
                  className="text-xs px-3 py-1.5 rounded-full font-bold
                             bg-blue-500 text-white hover:bg-blue-400
                             disabled:opacity-40">
            {busy ? "…" : "Recompute"}
          </button>
          {a.status === "draft" && (
            <button onClick={() => action("activate")} disabled={busy}
                    data-testid={`advertiser-rt-audience-activate-${a.id}`}
                    className="text-xs px-3 py-1.5 rounded-full font-bold
                               bg-emerald-500 text-white hover:bg-emerald-400
                               disabled:opacity-40">
              {busy ? "…" : "Activate"}
            </button>
          )}
          {a.status !== "archived" && (
            <button onClick={() => action("archive")} disabled={busy}
                    data-testid={`advertiser-rt-audience-archive-${a.id}`}
                    className={`text-xs px-3 py-1.5 rounded-full font-bold border ${
                      light ? "border-slate-300 text-slate-700 hover:bg-slate-50"
                            : "border-white/15 text-slate-300 hover:bg-white/5"
                    } disabled:opacity-40`}>
              {busy ? "…" : "Archive"}
            </button>
          )}
        </div>
      </div>
      {err && (
        <div data-testid={`advertiser-rt-audience-error-${a.id}`}
             className={`text-[11px] mt-2 ${
               light ? "text-red-600" : "text-red-400"}`}>{err}</div>
      )}
    </div>
  );
}


function AudienceWizard({ onClose, business_id, light }) {
  const [name, setName] = useState("");
  const [logic, setLogic] = useState("AND");
  const [rules, setRules] = useState([{
    signal_type: "coupons_saved", comparator: ">=",
    value: 1, lookback_days: 30, target_id: "",
  }]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [created, setCreated] = useState(null);

  const addRule = () => {
    if (rules.length >= 5) return;
    setRules([...rules, {
      signal_type: "coupons_saved", comparator: ">=",
      value: 1, lookback_days: 30, target_id: "",
    }]);
  };
  const removeRule = (i) => setRules(rules.filter((_, idx) => idx !== i));
  const patchRule = (i, patch) => setRules(rules.map((r, idx) =>
    idx === i ? { ...r, ...patch } : r));

  const submit = async () => {
    setBusy(true); setErr(null);
    try {
      const payload = {
        name: name.trim() || "Untitled audience",
        rules: rules.map((r) => ({
          signal_type: r.signal_type,
          comparator: r.comparator,
          value: Number(r.value) || 0,
          lookback_days: Number(r.lookback_days) || 30,
          target_id: (r.target_id || "").trim() || null,
        })),
        rule_logic: logic,
      };
      const { data } = await axios.post(
        `${API}/advertiser/${business_id}/retargeting-audiences`,
        payload, { withCredentials: true });
      setCreated(data);
    } catch (e) {
      setErr(e?.response?.data?.detail?.detail
             || e?.response?.data?.detail?.code
             || e.message);
    }
    setBusy(false);
  };

  return (
    <div data-testid="advertiser-rt-audience-modal"
         className="fixed inset-0 z-40 bg-black/60 flex items-center
                    justify-center p-4">
      <div className={`w-full max-w-2xl rounded-3xl p-6 max-h-[85vh]
                       overflow-y-auto ${
                       light ? "bg-white" : "bg-slate-900"} shadow-2xl`}>
        <div className="flex items-center justify-between mb-3">
          <div className={`font-black text-lg ${
                          light ? "text-slate-900" : "text-white"}`}>
            New retargeting audience
          </div>
          <button onClick={onClose}
                  data-testid="advertiser-rt-audience-modal-close"
                  className={light ? "text-slate-500" : "text-slate-300"}>
            <X size={18} />
          </button>
        </div>

        {!created ? (
          <div className="space-y-3">
            <Field light={light} label="Name">
              <input value={name} onChange={(e) => setName(e.target.value)}
                     data-testid="advertiser-rt-audience-name"
                     className={inputCls(light)} />
            </Field>
            <Field light={light} label="Combine rules with">
              <select value={logic} onChange={(e) => setLogic(e.target.value)}
                      data-testid="advertiser-rt-audience-logic"
                      className={inputCls(light)}>
                <option value="AND">AND (user must match ALL)</option>
                <option value="OR">OR (user must match ANY)</option>
              </select>
            </Field>
            <div className={`text-[11px] font-bold uppercase tracking-wide
                              ${light ? "text-slate-600" : "text-slate-300"}`}>
              Rules ({rules.length} / 5)
            </div>
            {rules.map((r, i) => {
              const sig = SIGNAL_TYPES.find((s) => s.v === r.signal_type);
              return (
                <div key={i}
                     data-testid={`advertiser-rt-rule-${i}`}
                     className={`p-3 rounded-xl grid grid-cols-6 gap-2 ${
                       light ? "bg-slate-50"
                              : "bg-white/5 border border-white/10"}`}>
                  <select value={r.signal_type}
                          onChange={(e) => patchRule(i, {
                            signal_type: e.target.value })}
                          data-testid={`advertiser-rt-rule-${i}-signal`}
                          className={inputCls(light) + " col-span-3"}>
                    {SIGNAL_TYPES.map((s) => (
                      <option key={s.v} value={s.v}>{s.label}</option>
                    ))}
                  </select>
                  <select value={r.comparator}
                          onChange={(e) => patchRule(i, {
                            comparator: e.target.value })}
                          data-testid={`advertiser-rt-rule-${i}-cmp`}
                          className={inputCls(light)}>
                    <option value=">=">{"≥"}</option>
                    <option value=">">{">"}</option>
                    <option value="==">{"="}</option>
                  </select>
                  <input type="number" min={0} value={r.value}
                         onChange={(e) => patchRule(i, {
                           value: e.target.value })}
                         data-testid={`advertiser-rt-rule-${i}-value`}
                         className={inputCls(light)} />
                  <input type="number" min={1} max={90}
                         value={r.lookback_days}
                         onChange={(e) => patchRule(i, {
                           lookback_days: e.target.value })}
                         data-testid={`advertiser-rt-rule-${i}-lookback`}
                         className={inputCls(light)} />
                  {sig?.requires_target && (
                    <input placeholder="Target ID (station or merchant)"
                           value={r.target_id}
                           onChange={(e) => patchRule(i, {
                             target_id: e.target.value })}
                           data-testid={`advertiser-rt-rule-${i}-target`}
                           className={inputCls(light) + " col-span-5"} />
                  )}
                  {rules.length > 1 && (
                    <button onClick={() => removeRule(i)}
                            data-testid={`advertiser-rt-rule-${i}-remove`}
                            className={`col-span-6 text-[11px] font-bold text-red-500
                                        text-right hover:text-red-400`}>
                      Remove rule
                    </button>
                  )}
                </div>
              );
            })}
            {rules.length < 5 && (
              <button onClick={addRule}
                      data-testid="advertiser-rt-audience-add-rule"
                      className={`text-xs px-3 py-1.5 rounded-full font-bold
                                  border-2 border-dashed w-full ${
                        light ? "border-slate-300 text-slate-500"
                              : "border-white/15 text-slate-300"}`}>
                + Add rule
              </button>
            )}
            {err && (
              <div data-testid="advertiser-rt-audience-modal-error"
                   className={`text-xs ${
                     light ? "text-red-600" : "text-red-400"}`}>{err}</div>
            )}
            <button onClick={submit} disabled={busy}
                    data-testid="advertiser-rt-audience-submit"
                    className="w-full mt-2 rounded-full py-2.5 font-black
                               text-sm bg-orange-500 text-white
                               hover:bg-orange-400 disabled:opacity-40">
              {busy ? "Computing…" : "Create audience"}
            </button>
          </div>
        ) : (
          <div className="text-center py-8">
            <div className={`inline-flex items-center gap-2 font-black ${
                            light ? "text-emerald-600" : "text-emerald-400"}`}>
              <Check size={16} />
              Audience created — {created.estimated_size || 0} users
            </div>
            <div className={`text-[11px] mt-2 ${
                            light ? "text-slate-500" : "text-slate-400"}`}
                 data-testid="advertiser-rt-audience-success-id">
              {created.id}
            </div>
            <button onClick={onClose}
                    data-testid="advertiser-rt-audience-success-done"
                    className="mt-4 px-4 py-1.5 rounded-full text-xs font-bold
                               bg-slate-200 text-slate-900 hover:bg-slate-300">
              Activate + attach a campaign next
            </button>
          </div>
        )}
      </div>
    </div>
  );
}


// ─── Campaigns tab ─────────────────────────────────────────────
function CampaignsTab({ business_id, light }) {
  const [items, setItems] = useState(null);
  const [audiences, setAudiences] = useState([]);
  const [showCreate, setShowCreate] = useState(false);
  const [err, setErr] = useState(null);

  const load = useCallback(async () => {
    setErr(null);
    try {
      const [c, a] = await Promise.all([
        axios.get(
          `${API}/advertiser/${business_id}/retargeting-campaigns`,
          { withCredentials: true }),
        axios.get(
          `${API}/advertiser/${business_id}/retargeting-audiences?status=active`,
          { withCredentials: true }),
      ]);
      setItems(c.data.items || []);
      setAudiences(a.data.items || []);
    } catch (e) {
      setErr(e?.response?.data?.detail?.code || e.message);
      setItems([]);
    }
  }, [business_id]);
  useEffect(() => { load(); }, [load]);

  return (
    <div>
      <button onClick={() => setShowCreate(true)}
              data-testid="advertiser-rt-campaign-create"
              className="inline-flex items-center gap-2 px-4 py-2 rounded-full
                         bg-orange-500 text-white text-xs font-black
                         hover:bg-orange-400 mb-4">
        <Plus size={14} /> New campaign
      </button>
      {items === null && (
        <div className={light ? "text-slate-500" : "text-slate-400"}
             data-testid="advertiser-rt-campaign-loading">
          <Loader2 size={16} className="animate-spin inline" /> Loading…
        </div>
      )}
      {items?.length === 0 && (
        <div className={`text-sm ${
                        light ? "text-slate-500" : "text-slate-400"}`}
             data-testid="advertiser-rt-campaign-empty">
          No campaigns yet.  Create an audience first, then attach a
          campaign to it.
        </div>
      )}
      {err && (
        <div data-testid="advertiser-rt-campaign-error"
             className={light ? "text-red-600" : "text-red-400"}>
          {err}
        </div>
      )}
      <div className="grid gap-3">
        {(items || []).map((c) => (
          <CampaignCard key={c.id} c={c} light={light}
                        business_id={business_id} reload={load} />
        ))}
      </div>
      {showCreate && (
        <CampaignWizard onClose={() => { setShowCreate(false); load(); }}
                        business_id={business_id} light={light}
                        audiences={audiences} />
      )}
    </div>
  );
}


function CampaignCard({ c, light, business_id, reload }) {
  const muted = light ? "text-slate-500" : "text-slate-400";
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const act = async (path, body = {}) => {
    setBusy(true); setErr(null);
    try {
      await axios.post(
        `${API}/advertiser/${business_id}/retargeting-campaigns/${c.id}/${path}`,
        body, { withCredentials: true });
      await reload();
    } catch (e) {
      setErr(e?.response?.data?.detail?.detail
             || e?.response?.data?.detail?.code
             || e.message);
    }
    setBusy(false);
  };
  return (
    <div data-testid={`advertiser-rt-campaign-card-${c.id}`}
         className={`rounded-2xl p-4 border ${
           light ? "bg-white border-slate-200"
                 : "bg-white/5 border-white/10"}`}>
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <div className={`text-sm font-black ${
                          light ? "text-slate-900" : "text-white"}`}>
            {c.base_ad_type} · {c.base_ad_id}
            <span data-testid={`advertiser-rt-campaign-status-${c.id}`}
                  className={`ml-2 text-[10px] px-2 py-0.5 rounded-full font-bold ${
                    c.status === "active"
                      ? "bg-emerald-500 text-white"
                      : c.status === "cancelled"
                          ? "bg-slate-500 text-white"
                          : "bg-amber-500 text-white"}`}>
              {c.status}
            </span>
          </div>
          <div className={`text-[11px] mt-1 ${muted}`}>
            audience {c.audience_id} · boost ×{c.boost_multiplier} · cpi{" "}
            {c.cost_per_impression_cents}¢
          </div>
        </div>
        <div className={`text-right text-sm ${
                        light ? "text-slate-900" : "text-white"}`}>
          <div className="font-black">
            ${((c.remaining_budget_cents || 0) / 100).toFixed(2)}
            {" / "}
            ${((c.total_budget_cents || 0) / 100).toFixed(2)}
          </div>
          <div className={`text-[10px] ${muted}`}>
            fee ${((c.platform_fee_cents || 0) / 100).toFixed(2)} ·{" "}
            served {c.plays_delivered || 0}
          </div>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {c.status === "draft" && (
          <button onClick={() => act("confirm-payment")} disabled={busy}
                  data-testid={`advertiser-rt-campaign-pay-${c.id}`}
                  className="text-xs px-3 py-1.5 rounded-full font-bold
                             bg-emerald-500 text-white hover:bg-emerald-400
                             disabled:opacity-40">
            {busy ? "…" : "Prepay & activate"}
          </button>
        )}
        {["draft", "pending_admin", "active", "paused"]
          .includes(c.status) && (
          <button onClick={() => act("cancel", {
                    reason: "advertiser_cancelled" })} disabled={busy}
                  data-testid={`advertiser-rt-campaign-cancel-${c.id}`}
                  className={`text-xs px-3 py-1.5 rounded-full font-bold border ${
                    light ? "border-slate-300 text-slate-700 hover:bg-slate-50"
                          : "border-white/15 text-slate-300 hover:bg-white/5"
                  } disabled:opacity-40`}>
            {busy ? "…" : "Cancel + refund"}
          </button>
        )}
      </div>
      {err && (
        <div data-testid={`advertiser-rt-campaign-error-${c.id}`}
             className={`text-[11px] mt-2 ${
               light ? "text-red-600" : "text-red-400"}`}>{err}</div>
      )}
    </div>
  );
}


function CampaignWizard({ onClose, business_id, light, audiences }) {
  const [audienceId, setAudienceId] = useState(audiences[0]?.id || "");
  const [baseAdType, setBaseAdType] = useState("banner");
  const [baseAdId, setBaseAdId] = useState("");
  const [boost, setBoost] = useState(2.0);
  const [cpi, setCpi] = useState(50);
  const [budget, setBudget] = useState(5000);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [created, setCreated] = useState(null);

  const total = useMemo(() => {
    const b = Math.max(Number(budget) || 0, 100);
    return b + Math.floor(b * 0.25);
  }, [budget]);

  const submit = async () => {
    setBusy(true); setErr(null);
    try {
      const { data } = await axios.post(
        `${API}/advertiser/${business_id}/retargeting-campaigns`,
        {
          audience_id: audienceId,
          base_ad_type: baseAdType,
          base_ad_id: baseAdId,
          boost_multiplier: Number(boost),
          cost_per_impression_cents: Number(cpi),
          total_budget_cents: Number(budget),
        },
        { withCredentials: true });
      setCreated(data);
    } catch (e) {
      setErr(e?.response?.data?.detail?.detail
             || e?.response?.data?.detail?.code
             || e.message);
    }
    setBusy(false);
  };

  return (
    <div data-testid="advertiser-rt-campaign-modal"
         className="fixed inset-0 z-40 bg-black/60 flex items-center
                    justify-center p-4">
      <div className={`w-full max-w-lg rounded-3xl p-6 ${
                       light ? "bg-white" : "bg-slate-900"} shadow-2xl`}>
        <div className="flex items-center justify-between mb-4">
          <div className={`font-black text-lg ${
                          light ? "text-slate-900" : "text-white"}`}>
            New retargeting campaign
          </div>
          <button onClick={onClose}
                  data-testid="advertiser-rt-campaign-modal-close"
                  className={light ? "text-slate-500" : "text-slate-300"}>
            <X size={18} />
          </button>
        </div>

        {!created ? (
          <div className="space-y-3">
            <Field light={light} label="Audience (must be active)">
              <select value={audienceId}
                      onChange={(e) => setAudienceId(e.target.value)}
                      data-testid="advertiser-rt-campaign-audience"
                      className={inputCls(light)}>
                <option value="">— pick an active audience —</option>
                {audiences.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name} · {a.estimated_size || 0} users
                  </option>
                ))}
              </select>
            </Field>
            <Field light={light} label="Base ad type (yours)">
              <select value={baseAdType}
                      onChange={(e) => setBaseAdType(e.target.value)}
                      data-testid="advertiser-rt-campaign-base-type"
                      className={inputCls(light)}>
                {BASE_AD_TYPES.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </Field>
            <Field light={light} label="Base ad ID">
              <input value={baseAdId}
                     onChange={(e) => setBaseAdId(e.target.value)}
                     placeholder="bnr_… / cpn_… / etc."
                     data-testid="advertiser-rt-campaign-base-id"
                     className={inputCls(light)} />
            </Field>
            <Field light={light} label="Boost multiplier (1.0–5.0)">
              <input type="number" min={1} max={5} step={0.1}
                     value={boost}
                     onChange={(e) => setBoost(e.target.value)}
                     data-testid="advertiser-rt-campaign-boost"
                     className={inputCls(light)} />
            </Field>
            <Field light={light} label="Cost per impression (¢)">
              <input type="number" min={1} value={cpi}
                     onChange={(e) => setCpi(e.target.value)}
                     data-testid="advertiser-rt-campaign-cpi"
                     className={inputCls(light)} />
            </Field>
            <Field light={light} label="Total budget (¢)">
              <input type="number" min={100} value={budget}
                     onChange={(e) => setBudget(e.target.value)}
                     data-testid="advertiser-rt-campaign-budget"
                     className={inputCls(light)} />
            </Field>
            <div className={`text-xs ${
                            light ? "text-slate-600" : "text-slate-300"}`}
                 data-testid="advertiser-rt-campaign-total">
              Total incl. 25% platform fee:{" "}
              <span className="font-black">
                ${(total / 100).toFixed(2)}
              </span>
              {total >= 50000 && (
                <span data-testid="advertiser-rt-campaign-admin-warning"
                      className={`ml-2 inline-flex items-center gap-1 text-[10px] font-bold ${
                                  light ? "text-amber-600" : "text-amber-400"}`}>
                  <AlertTriangle size={11} /> ≥ $500 requires admin
                  approval
                </span>
              )}
            </div>
            {err && (
              <div data-testid="advertiser-rt-campaign-modal-error"
                   className={`text-xs ${
                     light ? "text-red-600" : "text-red-400"}`}>{err}</div>
            )}
            <button onClick={submit}
                    disabled={busy || !audienceId || !baseAdId}
                    data-testid="advertiser-rt-campaign-submit"
                    className="w-full mt-2 rounded-full py-2.5 font-black
                               text-sm bg-orange-500 text-white
                               hover:bg-orange-400 disabled:opacity-40">
              {busy ? "Creating…" : "Create campaign draft"}
            </button>
          </div>
        ) : (
          <div className="text-center py-8">
            <div className={`inline-flex items-center gap-2 font-black ${
                            light ? "text-emerald-600" : "text-emerald-400"}`}>
              <Check size={16} /> Draft created
            </div>
            <div className={`text-[11px] mt-2 ${
                            light ? "text-slate-500" : "text-slate-400"}`}
                 data-testid="advertiser-rt-campaign-success-id">
              {created.id}
            </div>
            <button onClick={onClose}
                    data-testid="advertiser-rt-campaign-success-done"
                    className="mt-4 px-4 py-1.5 rounded-full text-xs font-bold
                               bg-slate-200 text-slate-900 hover:bg-slate-300">
              Done — click &quot;Prepay &amp; activate&quot; on the card
            </button>
          </div>
        )}
      </div>
    </div>
  );
}


function Field({ label, light, children }) {
  return (
    <label className="block">
      <span className={`text-[11px] font-bold uppercase tracking-wide ${
                       light ? "text-slate-600" : "text-slate-300"}`}>
        {label}
      </span>
      <div className="mt-1">{children}</div>
    </label>
  );
}


function inputCls(light) {
  return light
    ? "w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 bg-white"
    : "w-full rounded-lg border border-white/10 px-3 py-2 text-sm text-white bg-white/5";
}
