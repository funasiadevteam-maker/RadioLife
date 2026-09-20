// Phase 8b — Transient RJ Action Card that appears during the RJ voice slot.
// Polls /api/games_v2/me/active_game_announce every 60s; if the server has
// an unseen unlock/sponsored campaign in the cooldown window, the card slides
// in for ~14s, then auto-dismisses. Clicking the card logs the mention &
// deep-links to the game player.
import { useEffect, useState, useRef } from "react";
import axios from "axios";
import { Link } from "react-router-dom";
import { X, Sparkles, ChevronRight, Gift } from "lucide-react";
import { API } from "@/AuthContext";

const POLL_MS = 60_000;       // re-check every minute
const VISIBLE_MS = 14_000;    // show for 14s then auto-hide
const FIRST_DELAY_MS = 500;   // small delay so React StrictMode's
                                  // double-mount cleanup cancels duplicate runs

export default function RjActionCard({ user }) {
  // We render the card whenever `announce` is non-null. Auto-hide swaps it
  // back to null after VISIBLE_MS. Resilient to React StrictMode double-mount
  // because the impression POST is wrapped in a small first-fetch delay.
  const [announce, setAnnounce] = useState(null);
  const lastShownIdRef = useRef(null);
  const hideTimerRef = useRef(null);

  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    let firstFetchTimer = null;

    const fetchAnnounce = async () => {
      try {
        const r = await axios.get(`${API}/games_v2/me/active_game_announce`);
        if (cancelled) return;
        const a = r.data?.announce;
        if (a && a.campaign_id && lastShownIdRef.current !== a.campaign_id) {
          lastShownIdRef.current = a.campaign_id;
          setAnnounce(a);
          if (hideTimerRef.current) clearTimeout(hideTimerRef.current);
          hideTimerRef.current = setTimeout(() => setAnnounce(null), VISIBLE_MS);
          // Log the mention impression (fire-and-forget)
          axios.post(`${API}/games_v2/rj_mention_log`, {
            campaign_id: a.campaign_id,
            source_context: { source: "radio_player", surface: "action_card" },
          }).catch(() => {});
        }
      } catch (_e) { /* silent */ }
    };

    firstFetchTimer = setTimeout(fetchAnnounce, FIRST_DELAY_MS);
    const id = setInterval(fetchAnnounce, POLL_MS);
    return () => {
      cancelled = true;
      clearTimeout(firstFetchTimer);
      clearInterval(id);
      if (hideTimerRef.current) clearTimeout(hideTimerRef.current);
    };
  }, [user]);

  if (!announce) return null;
  const brand = announce.brand_colors_json?.primary || "#ff2d95";

  return (
    <div className="rj-action-card-wrap" data-testid="rj-game-action-card"
            data-campaign-id={announce.campaign_id}
            style={{ "--brand": brand }}>
      <div className="rj-action-card">
        <button className="rj-action-close"
                  data-testid="rj-action-close"
                  onClick={() => setAnnounce(null)}
                  aria-label="Dismiss">
          <X size={12} />
        </button>
        <div className="rj-action-eyebrow mono">
          <Sparkles size={11} /> RJ MENTIONED
        </div>
        <div className="rj-action-title">{announce.title}</div>
        <div className="rj-action-sub mono">
          BY {(announce.sponsor_name || "FUUSIC").toUpperCase()}
        </div>
        {announce.description && (
          <p className="rj-action-desc">{announce.description}</p>
        )}
        <Link to={`/play-and-win/${announce.campaign_id}`}
                className="rj-action-cta"
                data-testid="rj-action-cta"
                onClick={() => setAnnounce(null)}>
          <Gift size={13} /> {announce.cta_short || "Play & win"}
          <ChevronRight size={13} />
        </Link>
      </div>
    </div>
  );
}
