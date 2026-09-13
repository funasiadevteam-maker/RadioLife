// Phase 23 Session 9 — parallel-install of server-resolved Play & Win.
//
// GamePlayer now drives the new /api/play/resolve + /api/wallet/save
// flow (via playApi.js) instead of /api/games_v2/sessions/.../submit.
// The 6 per-game animation components stay UNCHANGED — they continue to
// expose `onSubmit` + receive `result` + call `onAnimationComplete`
// (Session 8b gating preserved).  We adapt the resolvePlay response
// to the legacy `result` shape so animations land on the correct
// segment / symbols / prize tile, AND keep the raw response to feed
// `<WinReveal>` once the animation completes.
//
// Legacy /games_v2/sessions/{id}/submit + claim_to_wallet endpoints
// remain wired server-side for backwards compatibility (tests, mobile,
// admin preview).  The listener UI no longer calls them.
import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import axios from "axios";
import { Toaster, toast } from "sonner";
import { ChevronLeft, Loader2 } from "lucide-react";
import { useAuth, API } from "@/AuthContext";
import { GAME_DISPATCH, themeFor } from "./components/games";
import WinReveal from "./components/WinReveal";
import { resolvePlay, PlayError } from "./components/playApi";
import { wheelSegment, slotTargets } from "./components/playApi";
import ComplianceNotice from "./ComplianceNotice";
import LeadForm from "./LeadForm";
import "./PlayAndWin.css";

/**
 * Map the new /api/play/resolve outcome to the legacy `result` shape
 * the per-game animation components were built against.  This keeps
 * the 6 game components zero-change while the orchestration above
 * them switches to the new server resolution.
 */
function adaptOutcomeForGame(outcome, gameType) {
  const r = {
    session_id: outcome.playId,
    result: outcome.won ? "win" : "lose",
    prize: outcome.won
      ? {
          prize_id: outcome.prizeId,
          title: outcome.prizeTitle,
          prize_type: "coupon",
          redemption_method: "internal",
        }
      : null,
    bigcoin_earned: 0,
    quiz_meta: {},
    server_seed: outcome.playId,
    client_seed: "",
    share_text: outcome.won
      ? `I just won ${outcome.prizeTitle} on RadioLife!`
      : "",
  };
  if (gameType === "spin_wheel") {
    r.segment_index = wheelSegment(outcome);
  }
  if (gameType === "slot_machine") {
    r.symbols = slotTargets(outcome);
  }
  return r;
}

export default function GamePlayer() {
  const { campaign_id } = useParams();
  const { user, loading: authLoading } = useAuth();
  const navigate = useNavigate();
  const [campaign, setCampaign] = useState(null);
  // We still hit /api/games_v2/campaigns/{id} for branding/compliance
  // metadata + the render_config (used so each game knows its type +
  // visual config like wheel segments / slot reels / num_cards).
  const [renderConfig, setRenderConfig] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null);        // legacy-shaped, feeds the game
  const [outcome, setOutcome] = useState(null);  // raw server response, feeds WinReveal
  // Phase 23 Session 8b — `shownResult` gates the result surface so
  // it only renders AFTER the animation completes.
  const [shownResult, setShownResult] = useState(null);
  const [needsLead, setNeedsLead] = useState(false);
  const [ageValue, setAgeValue] = useState("");

  // Idempotency key: stable across retries of one play attempt; reset
  // on Play Again.  crypto.randomUUID is available in all modern
  // browsers + jsdom 22+.
  const idempotencyKeyRef = useRef(
    (typeof crypto !== "undefined" && crypto.randomUUID)
      ? crypto.randomUUID()
      : `idem-${Date.now()}-${Math.random().toString(36).slice(2)}`);

  const loadCampaign = async () => {
    try {
      const r = await axios.get(`${API}/games_v2/campaigns/${campaign_id}`);
      setCampaign(r.data);
      // Build a minimal render_config from the campaign's template/config
      // so the per-game component has its visual setup.  We mirror what
      // the legacy /sessions/{id}/start used to return as render_config.
      const cfg = r.data?.game_config_json || {};
      const gameType = (r.data?.template?.game_type)
        || (r.data?.template_id || "").replace(/^tpl_/, "")
        || "spin_wheel";
      setRenderConfig({ type: gameType, ...cfg });
    } catch (err) {
      const code = err?.response?.status;
      if (code === 412 && err?.response?.data?.detail === "lead_form_required") {
        setNeedsLead(true);
        return;
      }
      toast.error("Could not load campaign");
      navigate("/play-and-win");
    }
  };

  useEffect(() => {
    if (authLoading) return;
    if (!user) { navigate("/login"); return; }
    if (!campaign_id) return;
    loadCampaign();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, authLoading, campaign_id]);

  /**
   * The per-game `onSubmit` callback.  Was a POST to
   * /api/games_v2/sessions/{id}/submit; now calls resolvePlay() to get
   * the WinReveal-ready outcome.  The same callback signature keeps
   * the 6 game components zero-change.
   */
  const submitGame = async (_clientPayload) => {
    if (submitting || result) return;
    setSubmitting(true);
    try {
      const r = await resolvePlay(campaign_id, idempotencyKeyRef.current);
      setOutcome(r);
      setResult(adaptOutcomeForGame(r, renderConfig?.type));
    } catch (err) {
      // Phase 23 S9-hotfix — surface the actual reason instead of a
      // generic toast, so the wheel's "not spinning" symptom doesn't
      // mask an auth/eligibility/network root cause.
      if (err instanceof PlayError) {
        if (err.code === "AUTH") {
          toast.error("Session expired — please log in again");
          navigate("/login");
        } else if (err.code === "LIMIT") {
          toast.error(err.message || "You've hit today's play limit — come back tomorrow.");
          navigate("/play-and-win");
        } else {
          toast.error(`Spin failed: ${err.message}`);
        }
      } else {
        toast.error(`Spin failed: ${err?.message || "unknown error"}`);
      }
    } finally {
      setSubmitting(false);
    }
  };

  /**
   * "Play Again" — rotate the idempotency key (fresh attempt) and clear
   * result state so the game component re-enters its idle state.
   */
  const resetGame = () => {
    idempotencyKeyRef.current =
      (typeof crypto !== "undefined" && crypto.randomUUID)
        ? crypto.randomUUID()
        : `idem-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    setResult(null);
    setOutcome(null);
    setShownResult(null);
  };

  // Phase 23 UX-Hotfix B1 — ESC key dismisses the WinReveal modal.
  // Only active while the reveal is shown.  Save-to-Wallet idempotency
  // on the backend means a saved coupon survives the close.
  useEffect(() => {
    if (!shownResult) return;
    const h = (e) => { if (e.key === "Escape") resetGame(); };
    document.addEventListener("keydown", h);
    return () => document.removeEventListener("keydown", h);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shownResult]);

  if (authLoading || !user || !campaign) {
    return <div className="paw-loading"
                    data-testid="game-player-loading">
      <Loader2 size={28} className="spin" />
    </div>;
  }

  if (needsLead) {
    const brand = campaign.brand_colors_json?.primary || "#ff2d95";
    return (
      <div className="game-player" data-testid="game-player-lead-gate"
              style={{ "--brand": brand }}>
        <Toaster theme="dark" position="bottom-right" richColors />
        <header className="game-player-header">
          <button onClick={() => navigate("/play-and-win")}
                    className="paw-back" data-testid="exit-game-btn">
            <ChevronLeft size={14} /> exit
          </button>
          <div className="gp-title">
            <div className="mono sub">{campaign.sponsor_name?.toUpperCase()}</div>
            <h1>{campaign.title}</h1>
          </div>
        </header>
        <main className="game-stage">
          <ComplianceNotice compliance={campaign.compliance}
                                    prizes={campaign.prizes}
                                    ageGateValue={ageValue}
                                    onAgeChange={setAgeValue} />
          <LeadForm campaignId={campaign_id}
                        onSubmitted={() => { setNeedsLead(false); loadCampaign(); }} />
        </main>
      </div>
    );
  }

  if (!renderConfig) {
    return <div className="paw-loading"
                    data-testid="game-player-loading">
      <Loader2 size={28} className="spin" />
    </div>;
  }

  const brand = campaign.brand_colors_json?.primary || "#ff2d95";
  const theme = themeFor(renderConfig.type);
  const accent = brand || theme.accent;

  return (
    <div className="game-player" data-testid="game-player"
            style={{ "--brand": brand }}>
      <Toaster theme="dark" position="bottom-right" richColors />
      <header className="game-player-header">
        <button onClick={() => navigate("/play-and-win")}
                  className="paw-back" data-testid="exit-game-btn">
          <ChevronLeft size={14} /> exit
        </button>
        <div className="gp-title">
          <div className="mono sub">{campaign.sponsor_name?.toUpperCase()}</div>
          <h1>{campaign.title}</h1>
        </div>
      </header>

      <main className="game-stage" data-testid="game-stage">
        <ComplianceNotice compliance={campaign.compliance}
                                  prizes={campaign.prizes}
                                  ageGateValue={ageValue}
                                  onAgeChange={setAgeValue} />
        {(() => {
          const GameComponent = GAME_DISPATCH[renderConfig.type];
          if (!GameComponent) return null;
          return <GameComponent config={renderConfig}
                                                onSubmit={submitGame}
                                                submitting={submitting}
                                                result={result}
                                                brand={accent}
                                                onAnimationComplete={(r) => setShownResult(r)} />;
        })()}
      </main>

      {shownResult && outcome && (
        <div className="result-modal-bg" data-testid="result-modal"
                onClick={(e) => {
                  // Phase 23 UX-Hotfix B1 — backdrop click dismisses.
                  if (e.target === e.currentTarget) resetGame();
                }}>
          <div className="result-modal" data-testid="win-reveal-container"
                  style={{ position: "relative" }}>
            <button
              data-testid="win-reveal-close-btn"
              onClick={resetGame}
              aria-label="Close result"
              style={{
                position: "absolute", top: 12, right: 12, zIndex: 10,
                width: 32, height: 32, borderRadius: "50%",
                border: "none", cursor: "pointer",
                background: "rgba(0,0,0,0.55)",
                color: "#fff", fontSize: 18, lineHeight: 1,
                display: "flex", alignItems: "center", justifyContent: "center",
              }}>×</button>
            <WinReveal outcome={outcome}
                              accent={accent}
                              onPlayAgain={resetGame} />
          </div>
        </div>
      )}
    </div>
  );
}
