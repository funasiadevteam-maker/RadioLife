// Phase 8a — /play-and-win listener catalog page.
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import axios from "axios";
import { Toaster, toast } from "sonner";
import {
  Sparkles, Lock, Trophy, Clock, ChevronLeft, Loader2,
  Gamepad2, Car, ShieldCheck, Coins, Gift,
} from "lucide-react";
import { useAuth, API } from "@/AuthContext";
import { themeFor } from "@/components/games";
import "./PlayAndWin.css";
// Phase 42-E2.2 — Universal share button.
import ShareButton from "@/components/ShareButton";

const TEMPLATE_ICON = {
  tpl_spin_wheel: "🎡",
  tpl_scratch_card: "🪙",
  tpl_quiz: "🎯",
  tpl_mystery_box: "🎁",
  tpl_slot_machine: "🎰",
  tpl_memory_match: "🧠",
  tpl_word_puzzle: "✒️",
};

export default function PlayAndWin() {
  const { user, loading: authLoading } = useAuth();
  const navigate = useNavigate();
  const [state, setState] = useState(null);
  const [loading, setLoading] = useState(true);
  const [drivingMode, setDrivingMode] = useState(false);

  useEffect(() => {
    if (authLoading) return;
    if (!user) { navigate("/login"); return; }
    reload();
  }, [user, authLoading]); // eslint-disable-line

  const reload = async () => {
    try {
      const r = await axios.get(`${API}/games_v2/play_and_win`);
      setState(r.data);
      setDrivingMode(!!r.data.driving_mode_on);
    } catch (_e) {
      toast.error("Failed to load games");
    } finally { setLoading(false); }
  };

  const toggleDriving = async () => {
    try {
      const r = await axios.post(`${API}/games_v2/user/driving_mode`,
        { on: !drivingMode });
      setDrivingMode(r.data.driving_mode_on);
      toast.success(r.data.driving_mode_on
        ? "Driving mode ON — games saved for later"
        : "Driving mode OFF — back to play");
    } catch (_e) { toast.error("Could not toggle"); }
  };

  if (authLoading || !user) {
    return <div className="paw-loading"><Loader2 size={28} className="spin" /></div>;
  }

  return (
    <div className="paw-wrap" data-testid="play-and-win-page">
      <Toaster theme="dark" position="bottom-right" richColors />

      <header className="paw-header">
        <div>
          <Link to="/" className="paw-back" data-testid="paw-back">
            <ChevronLeft size={14} /> back to radio
          </Link>
          <h1>Play &amp; Win</h1>
          <p className="sub">
            Spin · scratch · quiz · mystery box. Prizes from BigCoin, sponsor coupons, exclusive unlocks.
          </p>
        </div>
        <button
          className={`paw-driving-toggle ${drivingMode ? "on" : ""}`}
          onClick={toggleDriving}
          data-testid="driving-mode-toggle">
          <Car size={14} /> Driving mode {drivingMode ? "ON" : "OFF"}
        </button>
      </header>

      {drivingMode && (
        <div className="paw-driving-banner" data-testid="driving-banner">
          <ShieldCheck size={14} />
          <span>Driving mode is on — Play Now buttons are replaced by Save for later. Eyes on the road.</span>
        </div>
      )}

      {loading || !state ? (
        <div className="paw-loading"><Loader2 size={28} className="spin" /></div>
      ) : (
        <>
          <Section title="Unlocked for you" icon={<Sparkles size={14} />}
                    testId="section-unlocked"
                    items={state.unlocked_for_you}
                    drivingMode={drivingMode} />
          {state.expiring_soon.length > 0 && (
            <Section title="Expiring soon" icon={<Clock size={14} />}
                      testId="section-expiring"
                      items={state.expiring_soon}
                      drivingMode={drivingMode} />
          )}
          {state.played_history.length > 0 && (
            <PlayedHistorySection items={state.played_history} />
          )}
        </>
      )}
    </div>
  );
}

function Section({ title, icon, items, testId, drivingMode }) {
  return (
    <section className="paw-section" data-testid={testId}>
      <h2 className="mono">{icon} {title} <span className="badge">{items.length}</span></h2>
      <div className="paw-grid">
        {items.map((c) => (
          <CampaignCard key={c.campaign_id} campaign={c} drivingMode={drivingMode} />
        ))}
        {items.length === 0 && (
          <div className="paw-empty">No campaigns here yet.</div>
        )}
      </div>
    </section>
  );
}

function PlayedHistorySection({ items }) {
  return (
    <section className="paw-section" data-testid="section-played-history">
      <h2 className="mono"><Trophy size={14} /> Played history <span className="badge">{items.length}</span></h2>
      <div className="paw-history-grid">
        {items.slice(0, 10).map((h) => (
          <div className="paw-history-card" key={h.session_id} data-testid={`history-${h.session_id}`}>
            <div className={`result-tag ${h.result === "win" ? "win" : ""}`}>
              {h.result === "win" ? <><Trophy size={11} /> WIN</> : "LOSE"}
            </div>
            <div className="hcid">{h.campaign_id.replace("cmp_", "").slice(0, 10)}…</div>
            <div className="mono dim">{new Date(h.started_at).toLocaleString()}</div>
          </div>
        ))}
      </div>
    </section>
  );
}

function CampaignCard({ campaign, drivingMode }) {
  const navigate = useNavigate();
  // Phase 23 Session 4.5e — per-template visual identity.  The
  // template accent drives the card's top stripe + play CTA;
  // advertiser brand color stays as a small corner swatch.
  const tmplKey = (campaign.template_id || "").replace(/^tpl_/, "");
  const theme    = themeFor(tmplKey);
  const accent  = theme.accent;
  const brand    = campaign.brand_colors_json?.primary || accent;
  const onPlay = () => navigate(`/play-and-win/${campaign.campaign_id}`);
  return (
    <div
      className="paw-card themed-card"
      data-testid={`paw-card-${campaign.campaign_id}`}
      data-tpl-accent={accent}
      data-template-type={tmplKey}
      style={{ "--brand": brand, "--tpl-accent": accent,
                      borderTop: `3px solid ${accent}`,
                      position: "relative" }}>
      <div className="paw-tpl-pill"
              data-testid={`tpl-pill-${campaign.campaign_id}`}
              style={{ background: `${accent}22`, color: accent }}>
        <span>{theme.emoji}</span> {theme.label}
      </div>
      <div className="paw-card-icon"
              style={{ background: accent }}>
        <span>{theme.emoji}</span>
      </div>
      <div className="paw-card-body">
        <div className="paw-card-sponsor mono">
          <Gift size={9} /> {campaign.sponsor_name}
          {brand !== accent && (
            <span className="paw-brand-swatch"
                      style={{background: brand}}
                      title="Advertiser brand"
                      data-testid={`brand-swatch-${campaign.campaign_id}`}/>
          )}
        </div>
        <h3 className="paw-card-title">{campaign.title}</h3>
        {campaign.top_prize_title && (
          <div className="paw-card-prize">
            <Coins size={11} /> {campaign.top_prize_title}
          </div>
        )}
        {campaign.description && (
          <p className="paw-card-desc">{campaign.description}</p>
        )}
        {campaign.is_platform_funded && (
          <span className="paw-house-tag mono">RADIOLIFE HOUSE</span>
        )}
      </div>
      <button
        className="paw-play-btn"
        onClick={onPlay}
        disabled={drivingMode}
        style={{ background: accent }}
        data-testid={`play-btn-${campaign.campaign_id}`}>
        {drivingMode ? (
          <>Save for later <Car size={12} /></>
        ) : (
          <>Play now <Gamepad2 size={12} /></>
        )}
      </button>
      {/* Phase 42-E2.2 — share this game */}
      <div style={{ position: "absolute", top: 8, right: 8 }}>
        <ShareButton
          compact
          featureType="game"
          contentId={campaign.campaign_id}
          title={`${campaign.title} on RadioLife`}
          text={`Play "${campaign.title}" on RadioLife and win ${campaign.top_prize_title || "rewards"} →`} />
      </div>
    </div>
  );
}
