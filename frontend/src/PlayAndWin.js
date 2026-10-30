// Phase 8a — /play-and-win listener catalog page.
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import axios from "axios";
import { Toaster, toast } from "sonner";
import {
  Sparkles, Lock, Trophy, Clock, ChevronLeft, Loader2,
  Gamepad2, Car, ShieldCheck, Coins, Gift, Aperture, Ticket, ArrowRight,
} from "lucide-react";
import { useAuth, API } from "@/AuthContext";
import { themeFor } from "@/components/games";
import { GAME_ART, GAME_HERO } from "@/assets/gameArt";
import "./PlayAndWin.css";
// Phase 42-E2.2 — Universal share button.
import ShareButton from "@/components/ShareButton";
import WinnersTicker from "@/components/games/WinnersTicker";
import StreakBadge from "@/components/games/StreakBadge";

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
            Spin · scratch · quiz · mystery box. Prizes from BigPoints, sponsor coupons, exclusive unlocks.
          </p>
        </div>
        <button
          className={`paw-driving-toggle ${drivingMode ? "on" : ""}`}
          onClick={toggleDriving}
          data-testid="driving-mode-toggle">
          <Car size={14} /> Driving mode {drivingMode ? "ON" : "OFF"}
        </button>
      </header>

      <div style={{ margin: "0 0 12px" }}>
        <StreakBadge />
      </div>
      <div style={{ margin: "0 0 18px" }}>
        <WinnersTicker />
      </div>

      <FeaturedGamesHero />

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
          <PredictWinCard />
          <SponsoredInstantGames />
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

const FEATURED = [
  { key: "spin_win", name: "Spin & Win", desc: "Spin daily, win BigPoints & rewards", to: "/games/wheel", tag: "Spin", big: true },
  { key: "predict", name: "Predict & Win", desc: "Call sports, music & events", to: "/predict-win", tag: "Predict", big: true },
  { key: "lucky_dice", name: "Lucky Dice", desc: "Roll & win a free meal for 8", to: "/dining/dice", tag: "Dice" },
  { key: "scratch_win", name: "Daily Scratch", desc: "Scratch, match & win instantly", to: "/games/scratch", tag: "Scratch" },
  { key: "trivia", name: "Trivia Live", desc: "Play live, climb the leaderboard", to: "/play", tag: "Trivia" },
  { key: "quiz", name: "Quiz Rush", desc: "Fast questions, bigger rewards", to: "/play", tag: "Quiz" },
];

function FeaturedGamesHero() {
  const navigate = useNavigate();
  const [ov, setOv] = useState(null);
  useEffect(() => {
    let alive = true;
    axios.get(`${API}/games/appearance`, { withCredentials: true })
      .then((r) => { if (alive) setOv(r.data?.games || []); })
      .catch(() => { if (alive) setOv([]); });
    return () => { alive = false; };
  }, []);
  const featured = useMemo(() => {
    if (!ov) return FEATURED.map((g) => ({ ...g, _img: GAME_ART[g.key] }));
    const byKey = {};
    ov.forEach((g) => { if (g.web_key) byKey[g.web_key] = g; });
    return FEATURED
      .filter((g) => byKey[g.key])            // hidden games drop out
      .map((g) => {
        const o = byKey[g.key];
        return { ...g, name: o.label || g.name,
                      _img: o.image_url || GAME_ART[g.key],
                      _accent: o.color,
                      _order: typeof o.order === "number" ? o.order : 999 };
      })
      .sort((a, b) => a._order - b._order);
  }, [ov]);
  return (
    <div data-testid="paw-featured">
      {/* Cinematic hero */}
      <div data-testid="paw-hero" onClick={() => navigate("/games/wheel")}
        style={{ position: "relative", borderRadius: 24, overflow: "hidden", cursor: "pointer",
          minHeight: 190, display: "flex", alignItems: "flex-end", padding: 22, marginBottom: 18,
          backgroundImage: `linear-gradient(90deg, rgba(14,8,34,.92) 0%, rgba(14,8,34,.55) 45%, rgba(14,8,34,.15) 100%), url(${GAME_HERO})`,
          backgroundSize: "cover", backgroundPosition: "center right",
          boxShadow: "0 20px 50px rgba(0,0,0,.5)" }}>
        <div style={{ maxWidth: 460 }}>
          <span style={{ display: "inline-block", fontSize: 11, fontWeight: 900, letterSpacing: ".1em",
            color: "#fff", background: "linear-gradient(135deg,#a855f7,#ec4899)", padding: "4px 12px", borderRadius: 999 }}>
            PLAY · WIN · EARN
          </span>
          <h2 style={{ fontSize: 30, fontWeight: 900, color: "#fff", margin: "10px 0 6px", lineHeight: 1.05 }}>
            Play, Win &amp; Earn BigPoints!
          </h2>
          <p style={{ color: "#d8cdf5", fontSize: 14, margin: "0 0 14px" }}>Fun games. Real rewards. Play solo or with friends.</p>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 8, background: "linear-gradient(135deg,#a855f7,#ec4899)",
            color: "#fff", fontWeight: 800, fontSize: 14, padding: "11px 22px", borderRadius: 999 }}>
            Play Now <ArrowRight size={16} />
          </span>
        </div>
      </div>

      {/* Featured games grid */}
      <section className="paw-section" data-testid="paw-featured-grid">
        <h2 className="mono"><Sparkles size={14} /> Featured Games</h2>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(240px,1fr))", gap: 14 }}>
          {featured.map((g) => (
            <button key={g.key} onClick={() => navigate(g.to)}
              data-testid={`paw-featured-${g.key}`}
              style={{ position: "relative", textAlign: "left", cursor: "pointer", border: "none", padding: 0,
                borderRadius: 20, overflow: "hidden", minHeight: 150,
                backgroundImage: `linear-gradient(180deg, rgba(14,8,34,.15) 0%, rgba(14,8,34,.55) 55%, rgba(14,8,34,.95) 100%), url(${g._img || GAME_ART[g.key]})`,
                backgroundSize: "cover", backgroundPosition: "center",
                boxShadow: "0 12px 30px rgba(0,0,0,.4)", color: "#fff" }}>
              <span style={{ position: "absolute", top: 12, left: 12, fontSize: 10, fontWeight: 900, letterSpacing: ".08em",
                background: g._accent || "rgba(0,0,0,.45)", backdropFilter: "blur(4px)", padding: "4px 10px", borderRadius: 999 }}>
                {g.tag.toUpperCase()}
              </span>
              <div style={{ position: "absolute", left: 14, right: 14, bottom: 14 }}>
                <div style={{ fontSize: 18, fontWeight: 900 }}>{g.name}</div>
                <div style={{ fontSize: 12.5, color: "#e3d9fb", marginTop: 2 }}>{g.desc}</div>
                <span style={{ display: "inline-flex", alignItems: "center", gap: 6, marginTop: 10,
                  background: "linear-gradient(135deg,#a855f7,#ec4899)", padding: "7px 16px", borderRadius: 999,
                  fontSize: 13, fontWeight: 800 }}>
                  Play Now <ArrowRight size={14} />
                </span>
              </div>
            </button>
          ))}
        </div>
      </section>
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
  // Daily-play policy surfaced from the backend: sponsored games are
  // unlimited; free/house games allow one play per type per day.
  const pe = campaign.play_eligibility || {};
  const sponsored = !!pe.sponsored;
  const playedToday = pe.can_play === false;
  const disabled = drivingMode || playedToday;
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
        {sponsored ? (
          <span className="paw-house-tag mono" data-testid={`sponsored-tag-${campaign.campaign_id}`}
                style={{ background: "#0aa54b22", color: "#0aa54b" }}>
            SPONSORED · UNLIMITED
          </span>
        ) : campaign.is_platform_funded ? (
          <span className="paw-house-tag mono">FUUSIC HOUSE · 1/DAY</span>
        ) : null}
      </div>
      <button
        className="paw-play-btn"
        onClick={onPlay}
        disabled={disabled}
        style={{ background: disabled && playedToday ? "#6b7280" : accent }}
        data-testid={`play-btn-${campaign.campaign_id}`}>
        {drivingMode ? (
          <>Save for later <Car size={12} /></>
        ) : playedToday ? (
          <>Come back tomorrow <Clock size={12} /></>
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
          title={`${campaign.title} on FUUSIC`}
          text={`Play "${campaign.title}" on FUUSIC and win ${campaign.top_prize_title || "rewards"} →`} />
      </div>
    </div>
  );
}

// Predict & Win entry — surfaces the community prediction game on the Play tab.
function PredictWinCard() {
  const navigate = useNavigate();
  return (
    <section className="paw-section" data-testid="section-predict-win">
      <h2 className="mono"><Trophy size={14} /> Predict &amp; Win</h2>
      <button
        onClick={() => navigate("/predict-win")}
        data-testid="predict-win-card"
        style={{
          width: "100%", textAlign: "left", display: "flex", alignItems: "center",
          gap: 16, padding: 18, borderRadius: 20, cursor: "pointer",
          background: "linear-gradient(120deg,#1a1038,#3a1148)",
          border: "1px solid rgba(245,158,11,0.35)",
        }}>
        <span style={{ display: "grid", placeItems: "center", width: 52, height: 52,
          borderRadius: 16, background: "rgba(245,158,11,0.15)", color: "#f59e0b" }}>
          <Trophy size={24} />
        </span>
        <span style={{ flex: 1, minWidth: 0 }}>
          <span style={{ display: "block", fontWeight: 900, fontSize: 18, color: "#fff" }}>
            Predict &amp; Win
          </span>
          <span style={{ display: "block", fontSize: 13, color: "#c4b5fd", marginTop: 2 }}>
            Free community predictions — make your pick and win prizes.
          </span>
        </span>
        <ArrowRight size={20} color="#c4b5fd" />
      </button>
    </section>
  );
}

// Merchant-sponsored instant games (2.5D Wheel / Scratch) — discovery rail so
// players find them without a direct link. Self-fetches; renders nothing when
// there are no sponsor games.
function SponsoredInstantGames() {
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  useEffect(() => {
    axios.get(`${API}/games/sponsor/discover`, { withCredentials: true })
      .then((r) => setItems(r.data?.items || []))
      .catch(() => {});
  }, []);
  if (items.length === 0) return null;
  return (
    <section className="paw-section" data-testid="section-sponsored-instant">
      <h2 className="mono">
        <Gift size={14} /> Sponsored by local stores <span className="badge">{items.length}</span>
      </h2>
      <div className="paw-grid">
        {items.map((g) => {
          const isWheel = g.game_type === "wheel";
          const accent = isWheel ? "#a855f7" : "#6366F1";
          const out = g.spins_left <= 0;
          const go = () => navigate(`/games/${isWheel ? "wheel" : "scratch"}?game_id=${g.game_id}`);
          return (
            <div key={g.game_id} className="paw-card themed-card"
              data-testid={`sponsor-discover-card-${g.game_id}`}
              style={{ borderTop: `3px solid ${accent}`, position: "relative" }}>
              <div className="paw-card-icon"
                style={{ background: accent, overflow: "hidden" }}>
                {g.logo_url
                  ? <img src={g.logo_url} alt={g.sponsor_name} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                  : (isWheel ? <Aperture size={22} color="#fff" /> : <Ticket size={22} color="#fff" />)}
              </div>
              <div className="paw-card-body">
                <div className="paw-card-sponsor mono">
                  <Gift size={9} /> {g.sponsor_name}
                </div>
                <h3 className="paw-card-title">{isWheel ? "Wheel of Fortune" : "Scratch & Win"}</h3>
                {g.top_prize && (
                  <div className="paw-card-prize"><Coins size={11} /> Top prize: {g.top_prize}</div>
                )}
                <span className="paw-house-tag mono"
                  style={{ background: `${accent}22`, color: accent }}>
                  {out ? "COME BACK TOMORROW" : `${g.spins_left} PLAY${g.spins_left === 1 ? "" : "S"} LEFT TODAY`}
                </span>
              </div>
              <button className="paw-play-btn" onClick={go} disabled={out}
                style={{ background: out ? "#6b7280" : accent }}
                data-testid={`sponsor-discover-play-${g.game_id}`}>
                {out ? <>Out of plays <Clock size={12} /></> : <>Play now <ArrowRight size={12} /></>}
              </button>
            </div>
          );
        })}
      </div>
    </section>
  );
}
