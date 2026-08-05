// Phase L — M5 Radio Takeover Hour · Advertiser dashboard.
// Dual-design.  List + create wizard.
import { useCallback, useEffect, useMemo, useState } from "react";
import axios from "axios";
import {
  Loader2, Radio, Plus, X, Check, AlertTriangle, Ban,
} from "lucide-react";
import { useAdvertiser } from "@/pages/advertiser_v2/AdvertiserShell";
import { useDesignVariant } from "@/hooks/useDesignVariant";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
const STATUSES = ["", "draft", "pending_moderation", "pending_admin",
                  "active", "live", "completed", "cancelled", "rejected"];
const SCOPES = [
  { value: "single",  label: "Single station" },
  { value: "region",  label: "All stations in a region" },
  { value: "global",  label: "Global (all stations)" },
];
const REGIONS = ["ae", "us", "in", "sa", "eg", "gb"];


export default function AdvertiserTakeoverHours() {
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
        `${API}/advertiser/${business_id}/takeover-hours?${p}`,
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
           data-testid="advertiser-th-no-advertiser">
        Loading advertiser context…
      </div>
    );
  }

  const muted = light ? "text-slate-500" : "text-slate-400";

  return (
    <div data-testid="advertiser-th-page" data-variant={variant}>
      <div className="flex items-center justify-between mb-2">
        <h1 className={`text-2xl md:text-3xl xl:text-4xl font-black inline-flex items-center gap-2 ${
                       light ? "text-slate-900" : "text-white"}`}>
          <Radio className="text-orange-500" size={24} />
          Radio Takeover Hours
        </h1>
        <button onClick={() => setShowCreate(true)}
                data-testid="advertiser-th-create"
                className="inline-flex items-center gap-2 px-4 py-2 rounded-full
                           bg-orange-500 text-white text-xs font-black
                           hover:bg-orange-400">
          <Plus size={14} /> Buy takeover hour
        </button>
      </div>
      <p className={`text-sm ${muted} mb-6`}>
        Own a 60-minute block on RadioLife.  Your name shows in every
        player, 4 AI-RJ reads air at 0/15/30/45 min, your best deals
        surface in the marketplace panel, and listeners who stay
        20 min win a bonus.  Platform fee: 40%.
      </p>

      <div className="flex flex-wrap gap-1.5 mb-4">
        {STATUSES.map((s) => (
          <button key={s || "all"} onClick={() => setStatus(s)}
                  data-testid={`advertiser-th-filter-${s || "all"}`}
                  className={`px-3 py-1.5 rounded-full text-xs font-bold border ${
                    status === s
                      ? (light ? "bg-slate-900 text-white border-slate-900"
                              : "bg-white text-slate-900 border-white")
                      : (light ? "border-slate-300 text-slate-700"
                              : "border-white/10 text-slate-300")
                  }`}>
            {s || "All"}
          </button>
        ))}
      </div>

      {items === null && (
        <div className={`inline-flex items-center gap-2 ${muted}`}
             data-testid="advertiser-th-loading">
          <Loader2 size={16} className="animate-spin" /> Loading…
        </div>
      )}

      {items?.length === 0 && (
        <div className={`text-sm ${muted}`}
             data-testid="advertiser-th-empty">
          No takeover hours yet.  Click &quot;Buy takeover hour&quot; to create one.
        </div>
      )}

      {err && (
        <div data-testid="advertiser-th-error"
             className={`text-xs mt-2 ${
               light ? "text-red-600" : "text-red-400"}`}>{err}</div>
      )}

      <div className="grid gap-3 mt-2">
        {(items || []).map((it) => (
          <TakeoverCard key={it.id} it={it} light={light}
                        business_id={business_id} reload={load} />
        ))}
      </div>

      {showCreate && (
        <CreateWizard onClose={() => { setShowCreate(false); load(); }}
                      business_id={business_id} light={light} />
      )}
    </div>
  );
}


function TakeoverCard({ it, light, business_id, reload }) {
  const muted = light ? "text-slate-500" : "text-slate-400";
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  const doSubmit = async () => {
    setBusy(true); setErr(null);
    try {
      await axios.post(
        `${API}/advertiser/${business_id}/takeover-hours/${it.id}/submit`,
        {}, { withCredentials: true });
      await reload();
    } catch (e) { setErr(e?.response?.data?.detail?.detail || e.message); }
    setBusy(false);
  };

  const doConfirm = async () => {
    setBusy(true); setErr(null);
    try {
      await axios.post(
        `${API}/advertiser/${business_id}/takeover-hours/${it.id}/confirm-payment`,
        {}, { withCredentials: true });
      await reload();
    } catch (e) { setErr(e?.response?.data?.detail?.detail || e.message); }
    setBusy(false);
  };

  const doCancel = async () => {
    setBusy(true); setErr(null);
    try {
      await axios.post(
        `${API}/advertiser/${business_id}/takeover-hours/${it.id}/cancel`,
        { reason: "advertiser_cancelled" }, { withCredentials: true });
      await reload();
    } catch (e) { setErr(e?.response?.data?.detail?.detail || e.message); }
    setBusy(false);
  };

  return (
    <div data-testid={`advertiser-th-card-${it.id}`}
         className={`rounded-2xl p-4 border ${
           light ? "bg-white border-slate-200"
                : "bg-white/5 border-white/10"}`}>
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <div className={`text-sm font-black ${
                          light ? "text-slate-900" : "text-white"}`}>
            {it.branded_overlay?.advertiser_name || "Takeover"}
            <span data-testid={`advertiser-th-status-${it.id}`}
                  className={`ml-2 text-[10px] font-bold px-2 py-0.5 rounded-full ${
                    it.status === "live"
                      ? "bg-orange-500 text-white"
                      : it.status === "active"
                          ? "bg-emerald-500 text-white"
                          : it.status === "cancelled"
                              ? "bg-slate-500 text-white"
                              : "bg-amber-500 text-white"}`}>
              {it.status}
            </span>
          </div>
          <div className={`text-xs mt-1 ${muted}`}>
            {it.station_scope} · {it.station_id || it.region_code || "global"}
            {" · "}
            {new Date(it.start_at).toLocaleString()}
          </div>
        </div>
        <div className={`text-right text-sm ${
                        light ? "text-slate-900" : "text-white"}`}>
          <div data-testid={`advertiser-th-cost-${it.id}`}
               className="font-black">
            ${((it.total_cost_cents || 0) / 100).toFixed(2)}
          </div>
          <div className={`text-[10px] ${muted}`}>
            media ${((it.media_cost_cents || 0) / 100).toFixed(2)}
            {" · "}fee ${((it.platform_fee_cents || 0) / 100).toFixed(2)}
          </div>
        </div>
      </div>

      <div className={`mt-2 text-[11px] ${muted}`}>
        {(it.rj_scripts || []).length} RJ blocks
        {" · "}{(it.featured_deal_refs || []).length} featured deals
        {" · "}bonus: {it.bonus_giveaway?.prize_type || "—"}
        {it.bonus_giveaway?.prize_amount
          ? ` (${it.bonus_giveaway.prize_amount})`
          : ""}
        {" · "}delivered listeners: {it.actual_listeners_delivered || 0}
        {" · "}bonuses awarded: {it.bonus_awards_delivered || 0}
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        {it.status === "draft" && (
          <button onClick={doSubmit} disabled={busy}
                  data-testid={`advertiser-th-submit-${it.id}`}
                  className="text-xs px-3 py-1.5 rounded-full
                             bg-blue-500 text-white font-bold
                             hover:bg-blue-400 disabled:opacity-40">
            {busy ? "…" : "Submit for moderation"}
          </button>
        )}
        {it.status === "pending_moderation" && (
          <button onClick={doConfirm} disabled={busy}
                  data-testid={`advertiser-th-confirm-${it.id}`}
                  className="text-xs px-3 py-1.5 rounded-full
                             bg-emerald-500 text-white font-bold
                             hover:bg-emerald-400 disabled:opacity-40">
            {busy ? "…" : "Confirm & pay"}
          </button>
        )}
        {["draft", "pending_moderation", "pending_admin",
          "active"].includes(it.status) && (
          <button onClick={doCancel} disabled={busy}
                  data-testid={`advertiser-th-cancel-${it.id}`}
                  className={`text-xs px-3 py-1.5 rounded-full font-bold
                              border ${
                    light ? "border-slate-300 text-slate-700 hover:bg-slate-50"
                          : "border-white/15 text-slate-200 hover:bg-white/5"
                  } disabled:opacity-40`}>
            {busy ? "…" : "Cancel"}
          </button>
        )}
        {it.status === "live" && (
          <span data-testid={`advertiser-th-live-badge-${it.id}`}
                className="text-[11px] px-2 py-1 rounded-full
                           bg-orange-500/10 text-orange-500 font-bold">
            LIVE ON AIR
          </span>
        )}
      </div>

      {err && (
        <div data-testid={`advertiser-th-error-${it.id}`}
             className={`text-[11px] mt-2 ${
               light ? "text-red-600" : "text-red-400"}`}>
          {err}
        </div>
      )}
    </div>
  );
}


function CreateWizard({ onClose, business_id, light }) {
  const [scope, setScope] = useState("region");
  const [stationId, setStationId] = useState("");
  const [regionCode, setRegionCode] = useState("ae");
  const [startAt, setStartAt] = useState("");
  const [advertiserName, setAdvertiserName] = useState("RadioLife Sponsor");
  const [tagline, setTagline] = useState("");
  const [theme, setTheme] = useState("");
  const [personaId, setPersonaId] = useState("");
  const [personas, setPersonas] = useState([]);
  const [mediaDollars, setMediaDollars] = useState(50);
  const [bonusType, setBonusType] = useState("bc");
  const [bonusAmount, setBonusAmount] = useState(500);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [createdId, setCreatedId] = useState(null);

  useEffect(() => {
    axios.get(`${API}/rj/personas`, { withCredentials: true })
      .then(({ data }) => setPersonas(
        (data.items || data.personas || data || []).slice(0, 20)))
      .catch(() => {});
  }, []);

  useEffect(() => {
    // Default start-at to next full hour, formatted for datetime-local input.
    const d = new Date();
    d.setMinutes(0, 0, 0);
    d.setHours(d.getHours() + 1);
    const p = (n) => String(n).padStart(2, "0");
    setStartAt(
      `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T` +
      `${p(d.getHours())}:${p(d.getMinutes())}`);
  }, []);

  const startAtISO = useMemo(() => {
    if (!startAt) return null;
    const d = new Date(startAt);
    return isNaN(d.getTime()) ? null : d.toISOString();
  }, [startAt]);

  const endAtISO = useMemo(() => {
    if (!startAtISO) return null;
    const d = new Date(startAtISO);
    d.setMinutes(d.getMinutes() + 60);
    return d.toISOString();
  }, [startAtISO]);

  const totalCents = useMemo(() => {
    const m = Math.max(50, Number(mediaDollars) || 0) * 100;
    return m + Math.floor(m * 0.4);
  }, [mediaDollars]);

  const submit = async () => {
    setErr(null); setBusy(true);
    try {
      const payload = {
        station_scope: scope,
        station_id: scope === "single" ? stationId : null,
        region_code: scope === "region" ? regionCode : null,
        start_at: startAtISO,
        end_at: endAtISO,
        rj_persona_id: personaId,
        rj_scripts: [],           // auto-draft
        advertiser_name: advertiserName,
        tagline,
        overall_theme: theme,
        branded_overlay: { badge_color: "orange" },
        featured_deal_refs: [],
        bonus_giveaway: {
          threshold_listen_seconds: 1200,
          prize_type: bonusType,
          prize_amount: Number(bonusAmount) || 0,
          max_winners: 0,
        },
        media_cost_cents: Math.max(5000, Number(mediaDollars) * 100),
        listener_reach_estimate: 0,
      };
      const { data } = await axios.post(
        `${API}/advertiser/${business_id}/takeover-hours`,
        payload, { withCredentials: true });
      setCreatedId(data?.id);
    } catch (e) {
      setErr(e?.response?.data?.detail?.detail
             || e?.response?.data?.detail?.code
             || e.message);
    }
    setBusy(false);
  };

  return (
    <div data-testid="advertiser-th-create-modal"
         className="fixed inset-0 z-40 bg-black/60 flex items-center
                    justify-center p-4">
      <div className={`w-full max-w-lg rounded-3xl p-6 ${
                       light ? "bg-white" : "bg-slate-900"} shadow-2xl`}>
        <div className="flex items-center justify-between mb-4">
          <div className={`text-lg font-black ${
                          light ? "text-slate-900" : "text-white"}`}>
            Buy Radio Takeover Hour
          </div>
          <button onClick={onClose}
                  data-testid="advertiser-th-create-close"
                  className={light ? "text-slate-500" : "text-slate-300"}>
            <X size={18} />
          </button>
        </div>

        {!createdId ? (
          <div className="space-y-3">
            <Field label="Advertiser name" light={light}>
              <input value={advertiserName}
                     onChange={(e) => setAdvertiserName(e.target.value)}
                     data-testid="advertiser-th-create-advertiser-name"
                     className={inputCls(light)} />
            </Field>
            <Field label="Tagline (optional)" light={light}>
              <input value={tagline}
                     onChange={(e) => setTagline(e.target.value)}
                     data-testid="advertiser-th-create-tagline"
                     className={inputCls(light)} />
            </Field>
            <Field label="Hour theme (optional, guides auto-drafted scripts)"
                   light={light}>
              <input value={theme}
                     onChange={(e) => setTheme(e.target.value)}
                     data-testid="advertiser-th-create-theme"
                     className={inputCls(light)} />
            </Field>

            <Field label="Station scope" light={light}>
              <select value={scope}
                      onChange={(e) => setScope(e.target.value)}
                      data-testid="advertiser-th-create-scope"
                      className={inputCls(light)}>
                {SCOPES.map((s) => (
                  <option key={s.value} value={s.value}>{s.label}</option>
                ))}
              </select>
            </Field>
            {scope === "single" && (
              <Field label="Station ID" light={light}>
                <input value={stationId}
                       onChange={(e) => setStationId(e.target.value)}
                       data-testid="advertiser-th-create-station-id"
                       placeholder="imp_fun_big_1062_uae"
                       className={inputCls(light)} />
              </Field>
            )}
            {scope === "region" && (
              <Field label="Region code" light={light}>
                <select value={regionCode}
                        onChange={(e) => setRegionCode(e.target.value)}
                        data-testid="advertiser-th-create-region"
                        className={inputCls(light)}>
                  {REGIONS.map((r) => (
                    <option key={r} value={r}>{r.toUpperCase()}</option>
                  ))}
                </select>
              </Field>
            )}

            <Field label="Start time (snap to hour boundaries — 60 min duration)"
                   light={light}>
              <input type="datetime-local"
                     value={startAt}
                     onChange={(e) => setStartAt(e.target.value)}
                     data-testid="advertiser-th-create-start"
                     className={inputCls(light)} />
            </Field>

            <Field label="RJ persona" light={light}>
              <select value={personaId}
                      onChange={(e) => setPersonaId(e.target.value)}
                      data-testid="advertiser-th-create-persona"
                      className={inputCls(light)}>
                <option value="">— pick a persona —</option>
                {personas.map((p) => (
                  <option key={p.id} value={p.id}>{p.name || p.id}</option>
                ))}
              </select>
            </Field>

            <Field label="Media spend ($ — min $50)" light={light}>
              <input type="number" min={50} step={10}
                     value={mediaDollars}
                     onChange={(e) => setMediaDollars(e.target.value)}
                     data-testid="advertiser-th-create-media"
                     className={inputCls(light)} />
            </Field>

            <div className={`text-xs ${
                            light ? "text-slate-600" : "text-slate-300"}`}
                 data-testid="advertiser-th-create-total">
              Total (incl. 40% platform fee):{" "}
              <span className="font-black">
                ${(totalCents / 100).toFixed(2)}
              </span>
              {totalCents >= 50000 && (
                <span data-testid="advertiser-th-create-admin-warning"
                      className={`ml-2 inline-flex items-center gap-1 text-[10px] font-bold ${
                                  light ? "text-amber-600" : "text-amber-400"}`}>
                  <AlertTriangle size={11} /> ≥ $500 requires admin approval
                </span>
              )}
            </div>

            <Field label="Bonus giveaway" light={light}>
              <div className="flex gap-2">
                <select value={bonusType}
                        onChange={(e) => setBonusType(e.target.value)}
                        data-testid="advertiser-th-create-bonus-type"
                        className={inputCls(light) + " w-1/2"}>
                  <option value="bc">BigCoin</option>
                  <option value="usd_voucher">USD voucher (cents)</option>
                </select>
                <input type="number" min={1}
                       value={bonusAmount}
                       onChange={(e) => setBonusAmount(e.target.value)}
                       data-testid="advertiser-th-create-bonus-amount"
                       className={inputCls(light) + " w-1/2"} />
              </div>
            </Field>

            {err && (
              <div data-testid="advertiser-th-create-error"
                   className={`text-xs ${
                     light ? "text-red-600" : "text-red-400"}`}>
                {err}
              </div>
            )}

            <button onClick={submit} disabled={busy || !personaId}
                    data-testid="advertiser-th-create-submit"
                    className="w-full mt-2 rounded-full py-2.5 font-black
                               text-sm bg-orange-500 text-white
                               hover:bg-orange-400 disabled:opacity-40">
              {busy ? "Creating…" : "Create draft"}
            </button>
          </div>
        ) : (
          <div className="text-center py-8">
            <div className={`inline-flex items-center gap-2 font-black ${
                            light ? "text-emerald-600" : "text-emerald-400"}`}>
              <Check size={16} /> Draft created
            </div>
            <div className={`text-xs mt-2 ${
                            light ? "text-slate-500" : "text-slate-400"}`}
                 data-testid="advertiser-th-create-success-id">
              {createdId}
            </div>
            <button onClick={onClose}
                    data-testid="advertiser-th-create-done"
                    className="mt-4 px-4 py-1.5 rounded-full text-xs font-bold
                               bg-slate-200 text-slate-900 hover:bg-slate-300">
              Done — go submit for moderation
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
