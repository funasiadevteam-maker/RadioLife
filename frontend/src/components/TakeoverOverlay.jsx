// Phase L — M5 Radio Takeover Hour · Listener overlay.
// Non-invasive: mounts once at App root, polls /api/takeovers/current
// every 30s using current session + station context, shows a persistent
// "Presented by {advertiser}" chip, plays block audio via its own
// <audio> element at each 15-min boundary (without touching
// GlobalAudio), and dispatches listener pings + bonus toasts.
import { useEffect, useMemo, useRef, useState } from "react";
import axios from "axios";
import { Radio } from "lucide-react";
import { toast } from "sonner";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
const POLL_MS = 30_000;

function _getSessionId() {
  try {
    let s = sessionStorage.getItem("bigfm_takeover_session");
    if (!s) {
      s = `sess_${Math.random().toString(36).slice(2)}${Date.now().toString(36)}`;
      sessionStorage.setItem("bigfm_takeover_session", s);
    }
    return s;
  } catch { return `sess_${Date.now()}`; }
}


export default function TakeoverOverlay() {
  const [takeover, setTakeover] = useState(null);
  const sessionId = useMemo(() => _getSessionId(), []);
  const audioRef = useRef(null);
  const lastBlockPlayedRef = useRef(-1);
  const ctxRef = useRef({ station_id: null, region_code: null });

  // Derive current station + region from a lightweight event or DOM
  // heuristic.  For MVP we probe window.__BIGFM_STATION_CONTEXT if set
  // by the player, else fall back to a URL param.
  useEffect(() => {
    const pick = () => {
      const w = typeof window !== "undefined" ? window : {};
      const c = w.__BIGFM_STATION_CONTEXT || {};
      ctxRef.current = {
        station_id: c.station_id || null,
        region_code: c.region_code
                      || (localStorage.getItem("bigfm_user_market") || null)
                      || null,
      };
    };
    pick();
    const t = setInterval(pick, 15000);
    return () => clearInterval(t);
  }, []);

  const poll = async () => {
    const { station_id, region_code } = ctxRef.current;
    try {
      const p = new URLSearchParams();
      if (station_id)  p.set("station_id", station_id);
      if (region_code) p.set("region_code", region_code);
      p.set("session_id", sessionId);
      const { data } = await axios.get(
        `${API}/takeovers/current?${p}`, { withCredentials: true });
      const t = data?.takeover || null;
      setTakeover(t);
      if (t?.block_audio_url_if_due
          && t.block_audio_url_if_due.audio_url
          && audioRef.current
          && lastBlockPlayedRef.current
             < (t.block_audio_url_if_due.block_index ?? -1)) {
        const b = t.block_audio_url_if_due;
        try {
          audioRef.current.src = b.audio_url;
          await audioRef.current.play();
          lastBlockPlayedRef.current = b.block_index;
          axios.post(
            `${API}/takeovers/${t.takeover_id}/block-played`,
            { session_id: sessionId, block_index: b.block_index },
            { withCredentials: true }).catch(() => {});
        } catch (e) { /* browser autoplay block — fine */ }
      }
      if (t?.takeover_id) {
        // Fire-and-forget listener ping.
        axios.post(
          `${API}/takeovers/${t.takeover_id}/listener-ping`,
          { session_id: sessionId,
            station_id: station_id || undefined,
            ping_seconds: 30 },
          { withCredentials: true })
          .then(({ data: r }) => {
            if (r?.bonus_minted?.wallet_item_id
                && !window.__bigfm_takeover_bonus_shown) {
              window.__bigfm_takeover_bonus_shown = true;
              toast.success(
                `+${r.bonus_minted.prize_amount}` +
                ` ${r.bonus_minted.prize_type === "bc"
                    ? "BigCoin" : "USD (cents) voucher"}` +
                ` for staying tuned!`,
                { duration: 6000 });
            }
          }).catch(() => {});
      }
    } catch { /* silent */ }
  };

  useEffect(() => {
    let stopped = false;
    const loop = async () => {
      if (stopped) return;
      await poll();
      if (!stopped) setTimeout(loop, POLL_MS);
    };
    loop();
    return () => { stopped = true; };
  }, [sessionId]);

  if (!takeover) return null;
  const ov = takeover.branded_overlay || {};
  return (
    <>
      <div data-testid="takeover-overlay-chip"
           className="fixed left-1/2 -translate-x-1/2 bottom-24 z-30
                      px-4 py-1.5 rounded-full font-bold text-xs
                      inline-flex items-center gap-2 shadow-2xl
                      bg-orange-500 text-white">
        <Radio size={12} />
        <span data-testid="takeover-overlay-advertiser">
          Presented by {ov.advertiser_name || "sponsor"}
        </span>
        {ov.tagline && (
          <span className="opacity-90">· {ov.tagline}</span>
        )}
      </div>
      <audio ref={audioRef} data-testid="takeover-overlay-audio"
             preload="none" />
    </>
  );
}
