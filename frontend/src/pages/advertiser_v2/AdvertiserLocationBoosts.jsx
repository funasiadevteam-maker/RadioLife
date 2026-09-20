// Phase J — M2 Location-Boost Ads · Advertiser dashboard.
// Dual-design (Legacy dark + FUUSIC light).  Create wizard supports
// RADIUS geofences (via lat/lng + radius slider); POLYGON entry is
// text-based ("[lat,lng]; [lat,lng]; …") — a Google Maps map drawer
// is out of scope for M2 v1 (would require GOOGLE_MAPS_API_KEY on the
// frontend + Maps JS bundle; deferred until the advertiser demand
// makes it worth the bytes).
import { useCallback, useEffect, useMemo, useState } from "react";
import axios from "axios";
import {
  Loader2, MapPin, Plus, X, Trash2, Info, Check, Target,
} from "lucide-react";
import { useAdvertiser } from "@/pages/advertiser_v2/AdvertiserShell";
import { useDesignVariant } from "@/hooks/useDesignVariant";
// Phase S — density preview panel.
import LocationBoostDensityPreview from "@/components/LocationBoostDensityPreview";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
const STATUSES = ["", "draft", "pending_admin", "active",
                                  "completed", "cancelled"];
const BASE_AD_TYPES = ["banner", "coupon", "notification", "game_sponsorship"];


export default function AdvertiserLocationBoosts() {
  const adv = useAdvertiser();
  const business_id = adv?.active?.advertiser_id || adv?.activeId;
  const variant = useDesignVariant();
  const light = variant === "radiolife";
  const [items, setItems] = useState(null);
  const [status, setStatus] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [err, setErr] = useState(null);

  const load = useCallback(async () => {
    if (!business_id) return;
    setErr(null);
    try {
      const p = new URLSearchParams();
      if (status) p.set("status", status);
      const { data } = await axios.get(
        `${API}/advertiser/${business_id}/location-boosts?${p}`,
        { withCredentials: true });
      setItems(data.items || []);
    } catch (e) {
      setErr(e?.response?.data?.detail?.code || e.message);
      setItems([]);
    }
  }, [business_id, status]);
  useEffect(() => { load(); }, [load]);

  if (!business_id) {
    return (
      <div className={`p-6 ${light ? "text-slate-900" : "text-white"}`}
                data-testid="advertiser-lb-no-advertiser">
        Loading advertiser context…
      </div>
    );
  }

  const muted = light ? "text-slate-500" : "text-slate-400";

  return (
    <div data-testid="advertiser-lb-page" data-variant={variant}>
      <div className="flex items-center justify-between mb-2">
        <h1 className={`text-2xl md:text-3xl xl:text-4xl font-black inline-flex items-center gap-2 ${
                                        light ? "text-slate-900" : "text-white"}`}>
          <MapPin className="text-fuchsia-500" size={24} />
          Location Boosts
        </h1>
        <button onClick={() => setShowCreate(true)}
                        data-testid="advertiser-lb-create"
                        className="inline-flex items-center gap-2 px-4 py-2 rounded-full
                                                bg-fuchsia-500 text-white text-xs font-black
                                                hover:bg-fuchsia-400">
          <Plus size={14} /> New location boost
        </button>
      </div>
      <p className={`text-sm ${muted} mb-6`}>
        Buy geofenced ad boosts.  When a listener&apos;s live location lands
        inside your fence, your linked ad is preferred in the auction with
        a bid multiplier.  Radius fences ≤ 50km · polygon fences ≤ 20 vertices.
        Fee: 20% of media spend.
      </p>

      <div className="flex flex-wrap gap-1.5 mb-4">
        {STATUSES.map((s) => (
          <button key={s || "all"} onClick={() => setStatus(s)}
                          data-testid={`advertiser-lb-filter-${s || "all"}`}
                          className={`text-[10px] font-mono uppercase tracking-widest
                                                      px-3 py-1.5 rounded-full border transition ${
                                                          status === s
                                                              ? "border-fuchsia-500 bg-fuchsia-500/10 text-fuchsia-500"
                                                              : light
                                                                  ? "border-slate-200 text-slate-600 hover:bg-slate-100"
                                                                  : "border-slate-800 text-slate-400 hover:bg-slate-800/40"}`}>
            {s || "All"}
          </button>
        ))}
      </div>

      {err && <div className="rounded-lg bg-red-500/10 border border-red-500/40
                                                          text-red-400 text-xs px-3 py-2 mb-3"
                                            data-testid="advertiser-lb-error">{err}</div>}

      {items === null ? (
        <div className={`inline-flex items-center gap-2 ${muted}`}
                    data-testid="advertiser-lb-loading">
          <Loader2 className="w-4 h-4 animate-spin" /> Loading…
        </div>
      ) : items.length === 0 ? (
        <EmptyPanel light={light}
                              text="No location boosts yet — click 'New location boost' to launch a geofenced campaign." />
      ) : (
        <div className="space-y-2">
          {items.map((c) => (
            <BoostCard key={c.campaign_id} c={c} light={light}
                                        business_id={business_id} onChanged={load} />
          ))}
        </div>
      )}

      {showCreate && (
        <CreateModal light={light} business_id={business_id}
                                  onClose={() => setShowCreate(false)}
                                  onDone={() => { setShowCreate(false); load(); }} />
      )}
    </div>
  );
}


function BoostCard({ c, light, business_id, onChanged }) {
  const card = light ? "bg-white border border-slate-200 shadow-sm"
                                          : "bg-slate-900/60 border border-slate-800";
  const muted = light ? "text-slate-500" : "text-slate-400";
  const statusColor = {
    draft:              muted,
    pending_admin: "text-fuchsia-500",
    active:            "text-emerald-500",
    completed:      muted,
    cancelled:      "text-red-500",
  }[c.status] || muted;
  const [busy, setBusy] = useState(null);
  const [err, setErr] = useState(null);

  const act = async (verb) => {
    setBusy(verb); setErr(null);
    try {
      if (verb === "confirm-payment") {
        await axios.post(
          `${API}/advertiser/${business_id}/location-boosts/${c.campaign_id}/confirm-payment`,
          {}, { withCredentials: true });
      } else if (verb === "cancel") {
        if (!window.confirm(
              `Cancel and refund $${((c.remaining_budget_cents || 0) * 1.2 / 100).toFixed(2)}?`))
          { setBusy(null); return; }
        await axios.post(
          `${API}/advertiser/${business_id}/location-boosts/${c.campaign_id}/cancel`,
          { reason: "advertiser_cancelled" },
          { withCredentials: true });
      }
      onChanged();
    } catch (e) {
      setErr(e?.response?.data?.detail?.code || e.message);
    } finally { setBusy(null); }
  };

  const progress = c.plays_target > 0
    ? Math.round((c.plays_delivered / c.plays_target) * 100) : 0;

  return (
    <div className={`${card} rounded-xl p-4`}
              data-testid={`advertiser-lb-card-${c.campaign_id}`}>
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <span className={`text-[10px] font-mono uppercase tracking-widest ${statusColor}`}
                        data-testid={`advertiser-lb-status-${c.campaign_id}`}>
              {c.status}
            </span>
            <span className={`text-[10px] font-mono uppercase tracking-widest ${muted}`}>
              · {c.base_ad_type}
            </span>
            <span className={`text-[10px] font-mono uppercase tracking-widest ${muted}`}>
              · {(c.geofences || []).length} fence{(c.geofences || []).length !== 1 ? "s" : ""}
            </span>
            <span className={`text-[10px] font-mono uppercase tracking-widest ${muted}`}>
              · ×{c.boost_multiplier?.toFixed(2)}
            </span>
          </div>
          <div className="text-sm font-black truncate inline-flex items-center gap-1.5">
            <Target size={12} className="text-fuchsia-500" />
            {c.display_name}
          </div>
          <div className={`text-[11px] ${muted} mt-1 font-mono truncate`}>
            {(c.geofences || []).slice(0, 2).map((g, i) => (
              g.type === "radius"
                ? `radius@${g.center_lat?.toFixed(3)},${g.center_lng?.toFixed(3)} r=${g.radius_meters}m`
                : `polygon(${g.vertices?.length || 0})`
            )).join(" · ")}
          </div>
        </div>
        <div className="text-right shrink-0">
          <div className={`text-[10px] font-mono uppercase tracking-widest ${muted}`}>
            Total charge
          </div>
          <div className="text-sm font-black"
                      data-testid={`advertiser-lb-cost-${c.campaign_id}`}>
            ${(c.total_budget_cents / 100).toFixed(2)}
          </div>
        </div>
      </div>

      <div className="mt-3">
        <div className={`flex justify-between text-[10px] font-mono ${muted}`}>
          <span>{c.plays_delivered}/{c.plays_target} impressions</span>
          <span>${(c.remaining_budget_cents / 100).toFixed(2)} remaining</span>
        </div>
        <div className={`h-1.5 rounded-full mt-1 overflow-hidden ${
                                        light ? "bg-slate-100" : "bg-slate-800"}`}>
          <div className="h-full bg-gradient-to-r from-fuchsia-500 to-emerald-500"
                      style={{ width: `${progress}%` }} />
        </div>
      </div>

      {err && <div className="mt-2 text-xs text-red-400"
                                  data-testid={`advertiser-lb-error-${c.campaign_id}`}>{err}</div>}

      <div className="flex flex-wrap gap-2 mt-3">
        {c.status === "draft" && (
          <button onClick={() => act("confirm-payment")} disabled={!!busy}
                          data-testid={`advertiser-lb-confirm-${c.campaign_id}`}
                          className="text-[11px] font-mono uppercase tracking-widest
                                                px-3 py-1.5 rounded-full bg-fuchsia-500 text-white
                                                hover:bg-fuchsia-400 inline-flex items-center gap-1">
            {busy === "confirm-payment" && <Loader2 className="w-3 h-3 animate-spin" />}
            Pay + activate (${(c.total_budget_cents / 100).toFixed(2)})
          </button>
        )}
        {["pending_admin", "active", "paused"].includes(c.status) && (
          <button onClick={() => act("cancel")} disabled={!!busy}
                          data-testid={`advertiser-lb-cancel-${c.campaign_id}`}
                          className="text-[11px] font-mono uppercase tracking-widest
                                                px-3 py-1.5 rounded-full border border-red-500/40
                                                text-red-400 hover:bg-red-500/10
                                                inline-flex items-center gap-1">
            {busy === "cancel" ? <Loader2 className="w-3 h-3 animate-spin" /> :
                            <Trash2 className="w-3 h-3" />} Cancel + refund
          </button>
        )}
        {c.status === "cancelled" && c.refunded_amount_cents > 0 && (
          <div className={`text-[10px] font-mono ${muted}`}
                      data-testid={`advertiser-lb-refunded-${c.campaign_id}`}>
            Refunded ${(c.refunded_amount_cents / 100).toFixed(2)}
          </div>
        )}
      </div>
    </div>
  );
}


function CreateModal({ light, business_id, onClose, onDone }) {
  const [f, setF] = useState({
    display_name:                  "",
    base_ad_type:                "banner",
    base_ad_id:                    "",
    inline_title:                  "",
    inline_cta:                    "",
    boost_multiplier:          1.5,
    cost_per_impression_cents: 5,
    plays_target:                100,
    start_at:                        new Date(Date.now() - 60_000).toISOString().slice(0, 16),
    end_at:                            new Date(Date.now() + 14 * 24 * 3600_000).toISOString().slice(0, 16),
  });
  const [fences, setFences] = useState([
    { type: "radius", center_lat: 25.2522, center_lng: 55.3026, radius_meters: 500 },
  ]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [created, setCreated] = useState(null);

  const budget = useMemo(() => {
    const media = Number(f.plays_target || 0) * Number(f.cost_per_impression_cents || 0);
    const fee = Math.floor(media * 0.2);
    return {
      media, fee, total: media + fee,
      needsAdmin: (media + fee) >= 50_000,
    };
  }, [f.plays_target, f.cost_per_impression_cents]);

  const addFence = () => {
    if (fences.length >= 3) return;
    setFences([...fences, { type: "radius", center_lat: 25.25,
                                                          center_lng: 55.30, radius_meters: 1000 }]);
  };
  const removeFence = (i) => {
    if (fences.length <= 1) return;
    setFences(fences.filter((_, idx) => idx !== i));
  };
  const updateFence = (i, patch) => {
    const copy = [...fences];
    copy[i] = { ...copy[i], ...patch };
    setFences(copy);
  };

  const submit = async () => {
    setBusy(true); setErr(null);
    try {
      const body = {
        display_name:                  f.display_name.trim(),
        base_ad_type:                f.base_ad_type,
        base_ad_id:                    f.base_ad_id.trim() || null,
        inline_creative:            (!f.base_ad_id.trim() && (f.inline_title || f.inline_cta))
                                                          ? { title: f.inline_title.trim(),
                                                                cta:      f.inline_cta.trim() }
                                                          : null,
        boost_multiplier:          Number(f.boost_multiplier),
        cost_per_impression_cents: Number(f.cost_per_impression_cents),
        plays_target:                Number(f.plays_target),
        start_at:                        new Date(f.start_at).toISOString(),
        end_at:                            new Date(f.end_at).toISOString(),
        geofences:                      fences.map((g) => g.type === "radius"
          ? { type: "radius",
                center_lat: Number(g.center_lat),
                center_lng: Number(g.center_lng),
                radius_meters: Number(g.radius_meters) }
          : { type: "polygon",
                vertices: (g.vertices_text || "").split(";")
                    .map((p) => p.trim().replace(/[[\]]/g, "").split(",").map(Number))
                    .filter((pt) => pt.length === 2 && !isNaN(pt[0]) && !isNaN(pt[1])) }),
      };
      const { data: c } = await axios.post(
        `${API}/advertiser/${business_id}/location-boosts`,
        body, { withCredentials: true });
      const { data: paid } = await axios.post(
        `${API}/advertiser/${business_id}/location-boosts/${c.campaign_id}/confirm-payment`,
        {}, { withCredentials: true });
      setCreated(paid);
    } catch (e) {
      setErr(e?.response?.data?.detail?.code || e.message);
    } finally { setBusy(false); }
  };

  const shell = light ? "bg-white text-slate-900 border border-slate-200"
                                          : "bg-slate-900 text-white border border-slate-800";
  const muted = light ? "text-slate-500" : "text-slate-400";
  const input = light ? "bg-white border border-slate-200 text-slate-900"
                                            : "bg-slate-950 border border-slate-800 text-white";

  return (
    <div className="fixed inset-0 z-[80] bg-black/70 backdrop-blur
                                  flex items-start sm:items-center justify-center p-4 overflow-auto"
              data-testid="advertiser-lb-create-modal">
      <div className={`${shell} rounded-2xl w-full max-w-lg shadow-2xl`}>
        <div className={`flex items-center justify-between px-5 py-4 border-b
                                        ${light ? "border-slate-200" : "border-slate-800"}`}>
          <h3 className="text-sm font-black uppercase tracking-widest inline-flex items-center gap-2">
            <MapPin className="text-fuchsia-500" size={14} />
            {created ? "Location boost live" : "New location boost"}
          </h3>
          <button onClick={onClose}
                          data-testid="advertiser-lb-create-close"
                          className={muted}><X size={18} /></button>
        </div>

        {!created && (
          <div className="p-5 space-y-3 text-sm">
            <Field label="Campaign name" light={light}>
              <input type="text" value={f.display_name}
                            onChange={(e) => setF({ ...f, display_name: e.target.value })}
                            maxLength={80}
                            data-testid="advertiser-lb-create-name"
                            className={`w-full px-3 py-2 rounded-lg ${input}`} />
            </Field>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Base ad type" light={light}>
                <select value={f.base_ad_type}
                                onChange={(e) => setF({ ...f, base_ad_type: e.target.value })}
                                data-testid="advertiser-lb-create-type"
                                className={`w-full px-3 py-2 rounded-lg ${input}`}>
                  {BASE_AD_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
              </Field>
              <Field label="Base ad ID (optional)" light={light}>
                <input type="text" value={f.base_ad_id}
                              onChange={(e) => setF({ ...f, base_ad_id: e.target.value })}
                              placeholder="banner_xxx (or leave blank)"
                              data-testid="advertiser-lb-create-base-id"
                              className={`w-full px-3 py-2 rounded-lg ${input}`} />
              </Field>
            </div>

            {!f.base_ad_id.trim() && (
              <div className="grid grid-cols-2 gap-2">
                <Field label="Inline title" light={light}>
                  <input type="text" value={f.inline_title}
                                onChange={(e) => setF({ ...f, inline_title: e.target.value })}
                                maxLength={60}
                                data-testid="advertiser-lb-create-inline-title"
                                className={`w-full px-3 py-2 rounded-lg ${input}`} />
                </Field>
                <Field label="Inline CTA" light={light}>
                  <input type="text" value={f.inline_cta}
                                onChange={(e) => setF({ ...f, inline_cta: e.target.value })}
                                maxLength={40}
                                data-testid="advertiser-lb-create-inline-cta"
                                className={`w-full px-3 py-2 rounded-lg ${input}`} />
                </Field>
              </div>
            )}

            <div className="grid grid-cols-2 gap-2">
              <Field label="Plays target" light={light}>
                <input type="number" min="10" value={f.plays_target}
                              onChange={(e) => setF({ ...f, plays_target: e.target.value })}
                              data-testid="advertiser-lb-create-plays"
                              className={`w-full px-3 py-2 rounded-lg ${input}`} />
              </Field>
              <Field label="Cost per impression (¢)" light={light}>
                <input type="number" min="5" value={f.cost_per_impression_cents}
                              onChange={(e) => setF({ ...f, cost_per_impression_cents: e.target.value })}
                              data-testid="advertiser-lb-create-cpi"
                              className={`w-full px-3 py-2 rounded-lg ${input}`} />
              </Field>
            </div>
            <Field label="Boost multiplier (1.0 – 5.0)" light={light}>
              <input type="number" step="0.1" min="1" max="5" value={f.boost_multiplier}
                            onChange={(e) => setF({ ...f, boost_multiplier: e.target.value })}
                            data-testid="advertiser-lb-create-boost"
                            className={`w-full px-3 py-2 rounded-lg ${input}`} />
            </Field>

            <div>
              <div className="flex items-center justify-between mb-1">
                <label className={`text-[10px] font-mono uppercase tracking-widest ${muted}`}>
                  Geofences ({fences.length}/3)
                </label>
                <button onClick={addFence} disabled={fences.length >= 3}
                                data-testid="advertiser-lb-create-add-fence"
                                className="text-[10px] font-mono uppercase tracking-widest
                                                      px-2 py-0.5 rounded-full border border-fuchsia-500/40
                                                      text-fuchsia-500 hover:bg-fuchsia-500/10 disabled:opacity-40">
                  + Add fence
                </button>
              </div>
              <div className="space-y-2">
                {fences.map((g, i) => (
                  <FenceRow key={i} i={i} g={g} input={input} light={light}
                                          onChange={(patch) => updateFence(i, patch)}
                                          onRemove={() => removeFence(i)}
                                          removable={fences.length > 1} />
                ))}
              </div>
              {/* Phase S — density preview for the current fences. */}
              <LocationBoostDensityPreview
                business_id={business_id}
                fences={fences}
                days={30}
                light={light} />
            </div>

            <div className="grid grid-cols-2 gap-2">
              <Field label="Start at" light={light}>
                <input type="datetime-local" value={f.start_at}
                              onChange={(e) => setF({ ...f, start_at: e.target.value })}
                              data-testid="advertiser-lb-create-start"
                              className={`w-full px-3 py-2 rounded-lg ${input}`} />
              </Field>
              <Field label="End at" light={light}>
                <input type="datetime-local" value={f.end_at}
                              onChange={(e) => setF({ ...f, end_at: e.target.value })}
                              data-testid="advertiser-lb-create-end"
                              className={`w-full px-3 py-2 rounded-lg ${input}`} />
              </Field>
            </div>

            <div className={`rounded-lg px-3 py-2 text-xs ${
                                            light ? "bg-slate-50 border border-slate-200"
                                                        : "bg-slate-950/60 border border-slate-800"}`}
                        data-testid="advertiser-lb-create-summary">
              <div className="flex justify-between">
                <span className={muted}>Media spend</span>
                <span>${(budget.media / 100).toFixed(2)}</span>
              </div>
              <div className="flex justify-between">
                <span className={muted}>Platform fee (20%)</span>
                <span>${(budget.fee / 100).toFixed(2)}</span>
              </div>
              <div className={`flex justify-between mt-1 pt-1 border-t ${
                                              light ? "border-slate-200" : "border-slate-800"}`}>
                <span className="font-black">Total Stripe charge</span>
                <span className="font-black text-lg"
                            data-testid="advertiser-lb-create-total">
                  ${(budget.total / 100).toFixed(2)}
                </span>
              </div>
              {budget.needsAdmin && (
                <div className="mt-1 text-amber-500 text-[11px] inline-flex items-center gap-1"
                            data-testid="advertiser-lb-create-admin-warning">
                  <Info size={11} /> Budget ≥ $500 — admin approval required after payment.
                </div>
              )}
            </div>
            {err && <div className="rounded-lg bg-red-500/10 border border-red-500/40
                                                              text-red-400 text-xs px-3 py-2"
                                                data-testid="advertiser-lb-create-error">{err}</div>}
            <button onClick={submit}
                            disabled={busy || !f.display_name.trim() || budget.total === 0}
                            data-testid="advertiser-lb-create-submit"
                            className="w-full py-3 rounded-full text-sm font-black
                                                  bg-fuchsia-500 text-white hover:bg-fuchsia-400
                                                  disabled:opacity-40 inline-flex items-center
                                                  justify-center gap-2">
              {busy && <Loader2 className="w-4 h-4 animate-spin" />}
              Pay ${(budget.total / 100).toFixed(2)} + activate
            </button>
          </div>
        )}

        {created && (
          <div className="p-5" data-testid="advertiser-lb-create-success">
            <div className="w-14 h-14 mx-auto rounded-full grid place-items-center
                                        bg-emerald-500/15 border-2 border-emerald-500 mb-3">
              <Check className="w-7 h-7 text-emerald-500" />
            </div>
            <div className="text-center text-sm font-black">
              {created.campaign?.status === "active"
                ? "Campaign live" : "Awaiting admin approval"}
            </div>
            <div className={`text-center text-[11px] font-mono ${muted} mt-1`}
                        data-testid="advertiser-lb-create-id">
              {created.campaign?.campaign_id}
            </div>
            <div className={`text-center text-xs ${muted} mt-3`}>
              Charged ${(created.campaign?.total_budget_cents / 100).toFixed(2)} · Transaction {created.transaction_id}
            </div>
            <button onClick={onDone}
                            data-testid="advertiser-lb-create-done"
                            className="w-full mt-4 py-2.5 rounded-full text-xs font-black
                                                  border border-fuchsia-500 text-fuchsia-500
                                                  hover:bg-fuchsia-500/10">
              Done
            </button>
          </div>
        )}
      </div>
    </div>
  );
}


function FenceRow({ i, g, input, light, onChange, onRemove, removable }) {
  const muted = light ? "text-slate-500" : "text-slate-400";
  const isRadius = g.type === "radius";
  return (
    <div className={`rounded-lg p-2 ${light ? "bg-slate-50" : "bg-slate-950/40"}`}
              data-testid={`advertiser-lb-create-fence-${i}`}>
      <div className="flex items-center gap-2 mb-1">
        <select value={g.type}
                        onChange={(e) => onChange({ type: e.target.value })}
                        data-testid={`advertiser-lb-create-fence-${i}-type`}
                        className={`text-xs px-2 py-1 rounded ${input}`}>
          <option value="radius">Radius</option>
          <option value="polygon">Polygon</option>
        </select>
        {removable && (
          <button onClick={onRemove}
                          data-testid={`advertiser-lb-create-fence-${i}-remove`}
                          className="ml-auto text-red-400 hover:text-red-300">
            <Trash2 size={12} />
          </button>
        )}
      </div>
      {isRadius ? (
        <div className="grid grid-cols-3 gap-1.5">
          <input type="number" step="0.0001" value={g.center_lat}
                        onChange={(e) => onChange({ center_lat: e.target.value })}
                        placeholder="lat"
                        data-testid={`advertiser-lb-create-fence-${i}-lat`}
                        className={`col-span-1 px-2 py-1 text-xs rounded ${input}`} />
          <input type="number" step="0.0001" value={g.center_lng}
                        onChange={(e) => onChange({ center_lng: e.target.value })}
                        placeholder="lng"
                        data-testid={`advertiser-lb-create-fence-${i}-lng`}
                        className={`col-span-1 px-2 py-1 text-xs rounded ${input}`} />
          <input type="number" step="10" min="10" max="50000" value={g.radius_meters}
                        onChange={(e) => onChange({ radius_meters: e.target.value })}
                        placeholder="metres"
                        data-testid={`advertiser-lb-create-fence-${i}-radius`}
                        className={`col-span-1 px-2 py-1 text-xs rounded ${input}`} />
        </div>
      ) : (
        <div>
          <textarea rows={2} value={g.vertices_text || ""}
                                  onChange={(e) => onChange({ vertices_text: e.target.value })}
                                  placeholder="[25.24,55.29]; [25.24,55.32]; [25.27,55.32]; [25.27,55.29]"
                                  data-testid={`advertiser-lb-create-fence-${i}-vertices`}
                                  className={`w-full px-2 py-1 text-xs rounded ${input}`} />
          <div className={`text-[10px] font-mono ${muted} mt-0.5`}>
            format: `[lat,lng]; [lat,lng]; …` · 3-20 vertices
          </div>
        </div>
      )}
    </div>
  );
}


function EmptyPanel({ light, text }) {
  return (
    <div className={`rounded-2xl p-8 text-center text-sm ${
                                    light ? "bg-slate-50 border border-slate-200 text-slate-500"
                                                : "bg-slate-900/60 border border-slate-800 text-slate-400"}`}
              data-testid="advertiser-lb-empty">
      {text}
    </div>
  );
}
function Field({ label, light, children }) {
  const muted = light ? "text-slate-500" : "text-slate-400";
  return (
    <div>
      <label className={`block text-[10px] font-mono uppercase tracking-widest
                                          mb-1 ${muted}`}>{label}</label>
      {children}
    </div>
  );
}
