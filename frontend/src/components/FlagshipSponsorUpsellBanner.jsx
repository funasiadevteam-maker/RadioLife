// Phase O — Flagship Sponsor CTA (upsell funnel).
// Dual-design.  Mounted at the top of high-traffic advertiser pages.
// Fetches eligibility → shows a dismissable banner when qualified.
import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { useNavigate } from "react-router-dom";
import { Sparkles, X } from "lucide-react";
import { useDesignVariant } from "@/hooks/useDesignVariant";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
const _SEEN_KEY = "bigfm_flagship_upsell_seen_v1";


export default function FlagshipSponsorUpsellBanner({ business_id,
                                                       source_page }) {
  const variant = useDesignVariant();
  const light = variant === "radiolife";
  const nav = useNavigate();
  const [state, setState] = useState(null);
  const [busy, setBusy] = useState(false);
  const [hidden, setHidden] = useState(false);

  const fetchState = useCallback(async () => {
    if (!business_id) return;
    try {
      const { data } = await axios.get(
        `${API}/advertiser/${business_id}/upsell/flagship-sponsor`,
        { withCredentials: true });
      setState(data);
    } catch (e) {
      setState(null);
    }
  }, [business_id]);
  useEffect(() => { fetchState(); }, [fetchState]);

  const track = useCallback(async (event_type) => {
    if (!business_id) return;
    try {
      await axios.post(
        `${API}/advertiser/${business_id}/upsell/flagship-sponsor/event`,
        { event_type,
          context: {
            source_page: source_page || "unknown",
            referrer_slot_id: state?.recommended_slot?.slot_id,
          } },
        { withCredentials: true });
    } catch (e) { /* silent */ }
  }, [business_id, source_page, state]);

  // Fire `seen` once per page-load per (advertiser, source).
  useEffect(() => {
    if (!state?.eligible || !business_id) return;
    const key = `${_SEEN_KEY}:${business_id}:${source_page || ""}`;
    if (sessionStorage.getItem(key)) return;
    sessionStorage.setItem(key, "1");
    track("seen");
  }, [state, business_id, source_page, track]);

  const doClick = async () => {
    setBusy(true);
    await track("clicked");
    setBusy(false);
    const qs = new URLSearchParams({ upsell_source: "cta_banner" });
    if (state?.recommended_slot?.slot_id) {
      qs.set("recommended_slot_id", state.recommended_slot.slot_id);
    }
    nav(`/advertiser/dashboard/flagship-boosts?${qs.toString()}`);
  };

  const doDismiss = async () => {
    setBusy(true); setHidden(true);
    await track("dismissed");
    setBusy(false);
  };

  const doDismissPermanent = async () => {
    if (!window.confirm(
        "Hide this upsell forever?  We won't remind you again.")) return;
    setBusy(true); setHidden(true);
    await track("dismissed_permanently");
    setBusy(false);
  };

  if (!state?.eligible || hidden) return null;

  const slot = state.recommended_slot;
  const dollars = slot
    ? (slot.floor_price_cents / 100).toFixed(2)
    : null;

  return (
    <div data-testid="flagship-upsell-banner"
         data-variant={variant}
         className={`w-full mb-4 rounded-2xl overflow-hidden
                     ${light
                        ? "border border-amber-200 bg-amber-50"
                        : "border border-amber-500/30 bg-amber-500/10"}`}>
      <div className="flex flex-col sm:flex-row items-start sm:items-center
                      gap-3 p-4">
        <div className={`shrink-0 rounded-full p-2 ${
                        light ? "bg-amber-100 text-amber-700"
                              : "bg-amber-500/20 text-amber-300"}`}>
          <Sparkles size={18} />
        </div>
        <div className="flex-1 min-w-0">
          <div className={`text-sm font-black ${
                          light ? "text-amber-900" : "text-amber-200"}`}
               data-testid="flagship-upsell-banner-title">
            You&apos;re spending big — want your brand on a flagship
            station?
          </div>
          <div className={`text-xs mt-0.5 ${
                          light ? "text-amber-800/80"
                                : "text-amber-200/80"}`}
               data-testid="flagship-upsell-banner-copy">
            {slot
              ? <>Cheapest open slot in{" "}
                  <b className="uppercase">{slot.region_code}</b>{" "}·{" "}
                  <b>{slot.station_slot}</b> —{" "}
                  <b>${dollars}</b> floor.</>
              : <>Your reach is ready for a full-station takeover.
                  Explore all open flagship slots.</>}
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button onClick={doClick} disabled={busy}
                  data-testid="flagship-upsell-banner-cta"
                  className={`text-xs font-black px-4 py-2 rounded-full
                              inline-flex items-center gap-2
                              ${light
                                ? "bg-amber-500 text-white hover:bg-amber-400"
                                : "bg-amber-500 text-slate-900 hover:bg-amber-400"}
                              disabled:opacity-40`}>
            {busy ? "…" : "Sponsor a Flagship"}
          </button>
          <button onClick={doDismiss} disabled={busy}
                  data-testid="flagship-upsell-banner-dismiss"
                  title="Hide for 24 hours"
                  className={`p-1.5 rounded-full ${
                    light ? "text-amber-700 hover:bg-amber-100"
                          : "text-amber-300 hover:bg-white/5"}`}>
            <X size={14} />
          </button>
        </div>
      </div>
      <div className={`flex justify-end px-4 pb-2 ${
                      light ? "text-amber-700/70" : "text-amber-200/60"}`}>
        <button onClick={doDismissPermanent} disabled={busy}
                data-testid="flagship-upsell-banner-dismiss-forever"
                className="text-[10px] hover:underline">
          Don&apos;t show this again
        </button>
      </div>
    </div>
  );
}
