// Gentle "looks like you're in {city} now — switch?" banner. Shows only when
// the IP-detected market differs from the applied market, and remembers a
// dismissal per detected city so it never nags.
import React, { useEffect, useState } from "react";
import axios from "axios";
import { MapPin, ArrowRight, X } from "lucide-react";
import { useGeoStore } from "@/store/useGeoStore";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
const DISMISS_KEY = "fuusic.geoPrompt.dismissed.v1";

export default function NewCityPrompt() {
  const market = useGeoStore((s) => s.market);
  const setMarket = useGeoStore((s) => s.setMarket);
  const supported = useGeoStore((s) => s.supported);
  const displayName = useGeoStore((s) => s.displayName);
  const [detected, setDetected] = useState(null); // {market, city}
  const [busy, setBusy] = useState(false);
  const [hidden, setHidden] = useState(false);

  useEffect(() => {
    let cancel = false;
    let tz = "";
    try { tz = Intl.DateTimeFormat().resolvedOptions().timeZone || ""; } catch (_) {}
    axios.get(`${API}/geo/me`, { params: tz ? { tz } : {}, withCredentials: true, timeout: 5000 })
      .then((r) => {
        if (cancel) return;
        const dm = r.data?.detected_market;
        const dc = r.data?.detected_city || displayName(dm);
        if (dm) setDetected({ market: dm, city: dc });
      })
      .catch(() => {});
    return () => { cancel = true; };
  }, [displayName]);

  if (hidden || !detected) return null;
  const dm = detected.market;
  if (!supported.includes(dm) || dm === market) return null;
  let dismissed = "";
  try { dismissed = localStorage.getItem(DISMISS_KEY) || ""; } catch (_) {}
  if (dismissed === dm) return null;

  const dismiss = () => {
    try { localStorage.setItem(DISMISS_KEY, dm); } catch (_) {}
    setHidden(true);
  };
  const doSwitch = async () => {
    setBusy(true);
    await setMarket(dm);
    setBusy(false);
    setHidden(true);
  };

  return (
    <div data-testid="new-city-prompt"
      className={`${"max-w-[1160px] mx-auto"} mt-3 px-4`}>
      <div className="flex items-center gap-3 rounded-2xl px-4 py-3 border"
        style={{ background: "linear-gradient(120deg, rgba(168,85,247,0.14), rgba(236,72,153,0.10))", borderColor: "rgba(168,85,247,0.35)" }}>
        <span className="grid place-items-center w-9 h-9 rounded-full shrink-0"
          style={{ background: "linear-gradient(135deg,#a855f7,#ec4899)" }}>
          <MapPin size={16} className="text-white" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-sm font-black text-white truncate">
            Looks like you're in {detected.city} now
          </div>
          <div className="text-[12px]" style={{ color: "#c7bce8" }}>
            Switch to see local stations, news and offers around you.
          </div>
        </div>
        <button type="button" onClick={doSwitch} disabled={busy} data-testid="new-city-switch"
          className="inline-flex items-center gap-1.5 h-9 px-4 rounded-full text-[13px] font-black text-white shrink-0 disabled:opacity-60"
          style={{ background: "linear-gradient(135deg,#a855f7,#ec4899)" }}>
          {busy ? "Switching…" : <>Switch to {detected.city} <ArrowRight size={14} /></>}
        </button>
        <button type="button" onClick={dismiss} data-testid="new-city-dismiss"
          className="w-8 h-8 grid place-items-center rounded-full text-[#c7bce8] hover:text-white hover:bg-white/10 shrink-0">
          <X size={16} />
        </button>
      </div>
    </div>
  );
}
