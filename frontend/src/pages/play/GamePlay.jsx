// Phase PG.1 — Consumer game player: Spin & Win + Scratch & Win.
// Public route /play/{campaign_id} (auth-required; redirects on 401).
import React, { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import { Loader2, Trophy, ArrowLeft, X, Sparkles, ChevronRight,
                  Coins, CreditCard, UtensilsCrossed, Ticket, Share2 } from "lucide-react";
import { useAuth } from "@/AuthContext";
import { useDesignVariant } from "@/hooks/useDesignVariant";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

export default function GamePlay() {
  const variant = useDesignVariant();
  const light = variant === "radiolife";
  const { campaign_id } = useParams();
  const navigate = useNavigate();
  const { user, loading: authLoading } = useAuth();

  const [meta, setMeta] = useState(null);
  const [loading, setLoading] = useState(true);
  const [playing, setPlaying] = useState(false);
  const [outcome, setOutcome] = useState(null);
  const [spinAngle, setSpinAngle] = useState(0);
  const [scratchRevealed, setScratchRevealed] = useState([]);        // cell indexes

  useEffect(() => {
    if (authLoading) return;
    if (!user) { navigate(`/login?next=/play/${campaign_id}`); return; }
    (async () => {
      try {
        const { data } = await axios.get(`${API}/games/${campaign_id}`,
                                                                          { withCredentials: true });
        setMeta(data);
      } catch (e) {
        toast.error(`Load failed: ${e?.response?.data?.detail?.code || e.message}`);
      } finally { setLoading(false); }
    })();
  }, [campaign_id, user, authLoading, navigate]);

  const bgClass = light
    ? "min-h-screen bg-gradient-to-b from-purple-50 via-white to-pink-50"
    : "min-h-screen bg-slate-950 text-slate-100";

  if (loading || authLoading) return (
    <div className={`${bgClass} flex items-center justify-center`}
              data-testid="game-play-loading">
      <Loader2 className="animate-spin" size={30}/>
    </div>);

  if (!meta) return null;

  const canPlay = meta.eligibility?.can_play;
  const prizes = meta.prizes || [];

  const play = async () => {
    if (playing) return;
    setPlaying(true);
    try {
      const { data } = await axios.post(
        `${API}/games/${campaign_id}/play`, {}, { withCredentials: true });
      // Find prize index and compute animation target
      const idx = prizes.findIndex(p => p.prize_id === data.outcome_prize_id);
      if (meta.game_type === "spin_win") {
        const wedgeAngle = 360 / prizes.length;
        // Land in the center of the winning wedge, after 6 full rotations
        const targetAngle = 360 * 6 + (360 - (idx * wedgeAngle + wedgeAngle/2));
        setSpinAngle(targetAngle);
        setTimeout(() => {
          setOutcome(data);
          setPlaying(false);
        }, 4300);
      } else {
        // scratch — reveal 3 cells sequentially, showing prize icon
        setScratchRevealed([0, 1, 2]);
        setTimeout(() => {
          setOutcome(data);
          setPlaying(false);
        }, 1500);
      }
    } catch (e) {
      const code = e?.response?.data?.detail?.code || "error";
      if (code === "max_plays_reached")
        toast.error("You've already played this game today.");
      else if (code === "sold_out")
        toast.error("All prizes claimed — better luck next time!");
      else
        toast.error(`Play failed: ${code}`);
      setPlaying(false);
    }
  };

  return (
    <div className={`${bgClass} p-4 sm:p-8`}
              data-testid="game-play-page"
              data-game-type={meta.game_type}
              data-variant={variant}>
      <div className="max-w-2xl mx-auto">
        <Link to="/" className={`inline-flex items-center gap-1 text-xs ${
          light ? "text-slate-500 hover:text-slate-800"
                  : "text-slate-500 hover:text-slate-300"}`}>
          <ArrowLeft size={12}/> Home
        </Link>

        <div className="text-center mt-4">
          {meta.merchant_name && (
            <div className={`text-[10px] font-bold uppercase tracking-widest ${
              light ? "text-purple-600" : "text-cyan-400"}`}
                  data-testid="game-play-merchant">
              {meta.merchant_name}
            </div>
          )}
          <h1 className={`mt-1 text-3xl font-black tracking-tight ${
            light ? "text-slate-900" : "text-white"}`}
                  data-testid="game-play-name">{meta.name}</h1>
          {meta.description && (
            <p className={`mt-2 text-sm ${
              light ? "text-slate-600" : "text-slate-400"}`}>{meta.description}</p>
          )}
        </div>

        {/* Phase AD.1 — Sponsor branding banner (only when this game is
              linked to an active/approved ad_campaign_v2). */}
        {meta.sponsored_by && (
          <div className={`mt-4 rounded-2xl border-2 border-amber-500/40 px-4 py-3 flex items-center gap-3 ${
                                light ? "bg-amber-50" : "bg-amber-500/10"}`}
                      data-testid="game-play-sponsor-banner"
                      data-sponsor-ad-campaign-id={meta.sponsored_by.ad_campaign_id}>
            {meta.sponsored_by.advertiser_logo_url && (
              <img src={meta.sponsored_by.advertiser_logo_url} alt=""
                            className="w-10 h-10 rounded-full object-cover flex-shrink-0" />
            )}
            <div className="min-w-0 flex-1">
              <div className="text-[10px] font-bold uppercase tracking-widest text-amber-500">
                Sponsored by
              </div>
              <div className={`font-bold text-sm truncate ${light ? "text-slate-900" : "text-white"}`}
                          data-testid="game-play-sponsor-name">
                {meta.sponsored_by.advertiser_name}
              </div>
              {meta.sponsored_by.headline && (
                <div className={`text-xs mt-0.5 truncate ${light ? "text-slate-600" : "text-slate-300"}`}
                            data-testid="game-play-sponsor-headline">
                  {meta.sponsored_by.headline}
                </div>
              )}
            </div>
            {meta.sponsored_by.click_url && (
              <a href={meta.sponsored_by.click_url} target="_blank" rel="noreferrer"
                    className="text-xs font-semibold text-amber-500 hover:underline whitespace-nowrap"
                    data-testid="game-play-sponsor-click">
                Learn more →
              </a>
            )}
          </div>
        )}

        {!canPlay && !outcome && (
          <div className={`mt-8 rounded-3xl p-6 text-center ${
            light ? "bg-white border border-slate-100 shadow-sm"
                    : "bg-slate-900 border border-slate-800"}`}
                data-testid="game-play-blocked">
            <Sparkles className="mx-auto mb-2" size={28}
                                color={light ? "#a855f7" : "#00d4ff"}/>
            <h3 className={`text-lg font-black ${
              light ? "text-slate-900" : "text-white"}`}>
              {meta.eligibility?.reason === "max_plays_reached"
                ? "You've already played this game"
                : meta.eligibility?.reason === "sold_out"
                ? "All prizes have been claimed"
                : meta.eligibility?.reason === "ended"
                ? "This game has ended"
                : meta.eligibility?.reason === "not_started"
                ? "This game hasn't started yet"
                : "You can't play this game right now"}
            </h3>
            <p className={`mt-2 text-sm ${light ? "text-slate-600" : "text-slate-400"}`}>
              {meta.merchant_slug && (
                <>Explore more from{" "}
                <Link to={`/business/${meta.merchant_slug || meta.merchant_id}`}
                            className="underline">{meta.merchant_name}</Link></>)
              }
            </p>
          </div>
        )}

        {canPlay && meta.game_type === "spin_win" && (
          <SpinWheel prizes={prizes} light={light} spinAngle={spinAngle}
                              onSpin={play} disabled={playing || !!outcome}/>
        )}

        {canPlay && meta.game_type === "scratch_win" && (
          <ScratchGrid prizes={prizes} light={light}
                                    revealed={scratchRevealed}
                                    outcome={outcome}
                                    onScratch={play}
                                    playing={playing}/>
        )}

        {outcome && (
          <ResultModal outcome={outcome} meta={meta} light={light}
                                    onClose={() => { setOutcome(null); navigate("/wallet-v2"); }}
                                    onPlayAgain={meta.eligibility?.max > 1 ? () => {
                                      setOutcome(null); setSpinAngle(0);
                                      setScratchRevealed([]);
                                    } : null}/>
        )}
      </div>
    </div>
  );
}


// ── Spin Wheel ─────────────────────────────────────────────────
function SpinWheel({ prizes, light, spinAngle, onSpin, disabled }) {
  const size = 320;
  const cx = size / 2;
  const cy = size / 2;
  const r = size / 2 - 8;
  const wedgeAngle = 360 / prizes.length;

  const wedges = prizes.map((p, i) => {
    const startAngle = i * wedgeAngle - 90;
    const endAngle = (i + 1) * wedgeAngle - 90;
    const startRad = (startAngle * Math.PI) / 180;
    const endRad = (endAngle * Math.PI) / 180;
    const x1 = cx + r * Math.cos(startRad);
    const y1 = cy + r * Math.sin(startRad);
    const x2 = cx + r * Math.cos(endRad);
    const y2 = cy + r * Math.sin(endRad);
    const large = wedgeAngle > 180 ? 1 : 0;
    const path = `M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2} Z`;
    const labelRad = ((startAngle + endAngle) / 2 * Math.PI) / 180;
    const labelX = cx + (r * 0.6) * Math.cos(labelRad);
    const labelY = cy + (r * 0.6) * Math.sin(labelRad);
    const labelAngle = (startAngle + endAngle) / 2 + 90;
    return { p, path, labelX, labelY, labelAngle };
  });

  return (
    <div className="mt-8 flex flex-col items-center"
              data-testid="game-spin-wheel">
      <div className="relative" style={{width: size, height: size + 30}}>
        {/* Pointer */}
        <div className="absolute left-1/2 -top-1 -translate-x-1/2 z-10"
                  style={{width: 0, height: 0,
                                  borderLeft: "12px solid transparent",
                                  borderRight: "12px solid transparent",
                                  borderTop: `18px solid ${light ? "#a855f7" : "#00d4ff"}`}}/>
        <svg width={size} height={size}
                  style={{transform: `rotate(${spinAngle}deg)`,
                                  transition: "transform 4.2s cubic-bezier(0.17, 0.67, 0.32, 1)"}}
                  data-testid="game-spin-svg">
          {wedges.map((w, i) => (
            <g key={i}>
              <path d={w.path} fill={w.p.display_color || "#a855f7"}
                          stroke={light ? "#fff" : "#0f172a"} strokeWidth="2"/>
              <text x={w.labelX} y={w.labelY}
                        fill="white" fontSize="12" fontWeight="900"
                        textAnchor="middle" alignmentBaseline="middle"
                        transform={`rotate(${w.labelAngle} ${w.labelX} ${w.labelY})`}>
                {(w.p.display_label || "").slice(0, 12)}
              </text>
            </g>
          ))}
          <circle cx={cx} cy={cy} r={30}
                          fill={light ? "#fff" : "#0f172a"}
                          stroke={light ? "#a855f7" : "#00d4ff"} strokeWidth="3"/>
        </svg>
      </div>
      <button type="button" onClick={onSpin} disabled={disabled}
                    data-testid="game-spin-btn"
                    className={`mt-6 h-14 rounded-full px-10 text-lg font-black text-white ${
                      disabled ? "opacity-50" : ""}`}
                    style={{background:"linear-gradient(135deg,#a855f7,#ec4899)"}}>
        {disabled ? "…" : "SPIN"}
      </button>
    </div>
  );
}


// ── Scratch Grid ───────────────────────────────────────────────
function ScratchGrid({ prizes, light, revealed, outcome, onScratch, playing }) {
  const cells = Array.from({length: 9});
  // Fill 3 cells with the winning prize icon; rest with random distractors
  const revealedIcons = outcome
    ? [outcome.outcome_label, outcome.outcome_label, outcome.outcome_label,
        ...prizes.slice(0, 6).map(p => p.display_label)]
    : cells.map((_, i) => "?");

  return (
    <div className="mt-8 flex flex-col items-center"
              data-testid="game-scratch-grid">
      <div className={`grid grid-cols-3 gap-2 p-3 rounded-2xl ${
        light ? "bg-slate-100" : "bg-slate-800"}`}>
        {cells.map((_, i) => {
          const isRev = revealed.includes(i);
          return (
            <div key={i}
                        data-testid={`game-scratch-cell-${i}`}
                        data-revealed={isRev}
                        className={`w-20 h-20 rounded-xl flex items-center justify-center text-lg font-black ${
                          isRev
                            ? (light ? "bg-white shadow-md" : "bg-slate-900")
                            : (light ? "bg-gradient-to-br from-purple-400 to-pink-400"
                                            : "bg-gradient-to-br from-cyan-500 to-purple-500")}`}>
              {isRev
                ? <span className={`text-xs text-center px-1 ${
                    light ? "text-slate-900" : "text-white"}`}>
                    {String(revealedIcons[i] || "").slice(0, 8)}
                  </span>
                : <span className="text-white opacity-70">?</span>}
            </div>
          );
        })}
      </div>
      <button type="button" onClick={onScratch} disabled={playing || revealed.length > 0}
                    data-testid="game-scratch-btn"
                    className={`mt-6 h-14 rounded-full px-10 text-lg font-black text-white ${
                      playing || revealed.length > 0 ? "opacity-50" : ""}`}
                    style={{background:"linear-gradient(135deg,#a855f7,#ec4899)"}}>
        {playing ? "..." : revealed.length > 0 ? "Revealed" : "SCRATCH!"}
      </button>
    </div>
  );
}


// ── Share your win ─────────────────────────────────────────────
function ShareWin({ outcome, meta, light }) {
  const url = typeof window !== "undefined" ? window.location.origin : "";
  const text = `I just won ${outcome.outcome_label} at ${meta.merchant_name || "RadioLife"} on RadioLife! 🎉 Play & win too:`;
  const enc = encodeURIComponent(text);
  const encUrl = encodeURIComponent(url);
  const nativeShare = async () => {
    try {
      if (navigator.share) {
        await navigator.share({ title: "I won on RadioLife!", text, url });
      } else if (navigator.clipboard) {
        await navigator.clipboard.writeText(`${text} ${url}`);
        toast.success("Copied — paste it anywhere!");
      }
    } catch (_e) { /* user dismissed */ }
  };
  const links = [
    { key: "whatsapp", label: "WhatsApp", href: `https://wa.me/?text=${enc}%20${encUrl}` },
    { key: "x", label: "X", href: `https://twitter.com/intent/tweet?text=${enc}&url=${encUrl}` },
    { key: "facebook", label: "Facebook", href: `https://www.facebook.com/sharer/sharer.php?u=${encUrl}&quote=${enc}` },
  ];
  return (
    <div className="mt-5" data-testid="game-play-share">
      <div className={`text-[10px] font-bold uppercase tracking-widest mb-2 ${
        light ? "text-slate-500" : "text-slate-500"}`}>Share your win</div>
      <div className="flex items-center justify-center gap-2 flex-wrap">
        <button type="button" onClick={nativeShare} data-testid="game-play-share-native"
                      className="inline-flex items-center gap-1.5 h-9 px-4 rounded-full text-xs font-black text-white"
                      style={{ background: "linear-gradient(135deg,#a855f7,#ec4899)" }}>
          <Share2 size={13} /> Share
        </button>
        {links.map((l) => (
          <a key={l.key} href={l.href} target="_blank" rel="noreferrer"
                data-testid={`game-play-share-${l.key}`}
                className={`inline-flex items-center h-9 px-4 rounded-full text-xs font-bold ${
                  light ? "bg-slate-100 text-slate-800 hover:bg-slate-200"
                          : "bg-slate-800 text-slate-200 hover:bg-slate-700"}`}>
            {l.label}
          </a>
        ))}
      </div>
    </div>
  );
}


// ── Result modal ───────────────────────────────────────────────
function ResultModal({ outcome, meta, light, onClose, onPlayAgain }) {
  const won = outcome.won;
  const Icon = outcome.wallet_item_type === "gift_card" ? CreditCard
    : outcome.wallet_item_type === "prepaid_meal" ? UtensilsCrossed
    : outcome.wallet_item_type === "coupon" ? Ticket
    : outcome.wallet_item_type === "points" ? Coins
    : Trophy;
  const isGiftCard = won && (outcome.outcome_type === "gift_card"
    || outcome.wallet_item_type === "gift_card");

  useEffect(() => {
    if (!won) return undefined;
    let cancelled = false;
    (async () => {
      try {
        const mod = await import("canvas-confetti");
        const confetti = mod.default;
        if (isGiftCard) {
          const end = Date.now() + 1300;
          const colors = ["#f59e0b", "#fbbf24", "#ffd700", "#ec4899", "#22d3ee"];
          const frame = () => {
            if (cancelled) return;
            confetti({ particleCount: 6, angle: 60, spread: 72, origin: { x: 0 }, colors });
            confetti({ particleCount: 6, angle: 120, spread: 72, origin: { x: 1 }, colors });
            confetti({ particleCount: 12, spread: 100, startVelocity: 45, origin: { y: 0.3 }, colors });
            if (Date.now() < end) requestAnimationFrame(frame);
          };
          frame();
        } else {
          confetti({ particleCount: 80, spread: 70, origin: { y: 0.35 } });
        }
      } catch (_e) { /* confetti is optional */ }
    })();
    return () => { cancelled = true; };
  }, [won, isGiftCard]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4"
              onClick={onClose}>
      <div onClick={e => e.stopPropagation()}
                data-testid="game-play-result-modal"
                data-outcome-type={outcome.outcome_type}
                data-won={won}
                className={`w-full max-w-md rounded-3xl p-8 text-center ${
                  light ? "bg-white" : "bg-slate-900 border border-slate-800"}`}>
        {won ? (
          <>
            <div className={`inline-flex ${isGiftCard ? "w-24 h-24" : "w-20 h-20"} rounded-full items-center justify-center mb-4 ${
              isGiftCard
                ? "bg-gradient-to-br from-amber-300 to-pink-400 shadow-lg shadow-amber-500/40 animate-bounce"
                : light ? "bg-gradient-to-br from-purple-100 to-pink-100"
                              : "bg-gradient-to-br from-cyan-500/20 to-purple-500/20"}`}>
              <Icon size={isGiftCard ? 44 : 36}
                          color={isGiftCard ? "#ffffff" : (light ? "#a855f7" : "#00d4ff")}/>
            </div>
            <div className={`text-[10px] font-black uppercase tracking-widest ${
              isGiftCard ? "text-amber-500" : light ? "text-emerald-700" : "text-emerald-400"}`}
                    data-testid="game-play-win-kicker">
              {isGiftCard ? "🎁 Jackpot — Gift Card!" : "You won!"}
            </div>
            <h2 className={`mt-1 ${isGiftCard ? "text-4xl" : "text-3xl"} font-black ${
              light ? "text-slate-900" : "text-white"}`}
                    data-testid="game-play-result-label">
              {outcome.outcome_label}
            </h2>
            {isGiftCard && (
              <div className="mt-3 inline-block rounded-full px-4 py-1.5 text-xs font-black text-slate-900"
                        style={{ background: "linear-gradient(90deg,#fbbf24,#f59e0b)" }}
                        data-testid="game-play-giftcard-banner">
                $10 gift card added to your wallet — spend it in-store
              </div>
            )}
            {outcome.code && (
              <div className={`mt-4 rounded-xl px-3 py-2 font-mono text-lg font-black ${
                light ? "bg-slate-100 text-slate-900"
                        : "bg-slate-950 text-white"}`}
                    data-testid="game-play-result-code">
                {outcome.code}
              </div>
            )}
            {outcome.wallet_item_type === "points" && outcome.points_amount > 0 && (
              <div className={`mt-4 text-sm ${
                light ? "text-slate-600" : "text-slate-400"}`}>
                {outcome.points_amount} points added to your wallet
              </div>
            )}
            <ShareWin outcome={outcome} meta={meta} light={light} />
            <button type="button" onClick={onClose}
                          data-testid="game-play-view-wallet"
                          className="mt-6 w-full h-12 rounded-full text-sm font-black text-white"
                          style={{background:"linear-gradient(135deg,#a855f7,#ec4899)"}}>
              View in Wallet <ChevronRight className="inline" size={16}/>
            </button>
            {onPlayAgain && (
              <button type="button" onClick={onPlayAgain}
                            data-testid="game-play-play-again"
                            className={`mt-2 w-full h-10 rounded-full text-xs font-bold ${
                              light ? "bg-slate-100 text-slate-800"
                                      : "bg-slate-800 text-slate-200"}`}>
                Play again
              </button>
            )}
          </>
        ) : (
          <>
            <div className={`inline-flex w-20 h-20 rounded-full items-center justify-center mb-4 ${
              light ? "bg-slate-100" : "bg-slate-800"}`}>
              <Sparkles size={36}
                              color={light ? "#94a3b8" : "#64748b"}/>
            </div>
            <div className={`text-[10px] font-bold uppercase tracking-widest ${
              light ? "text-slate-500" : "text-slate-500"}`}>So close…</div>
            <h2 className={`mt-1 text-2xl font-black ${
              light ? "text-slate-900" : "text-white"}`}
                    data-testid="game-play-result-label">
              Better luck next time!
            </h2>
            {meta.merchant_slug && (
              <Link to={`/business/${meta.merchant_slug || meta.merchant_id}`}
                          data-testid="game-play-follow-merchant"
                          className={`mt-6 block h-12 rounded-full text-sm font-black text-white leading-[48px] ${""}`}
                          style={{background:"linear-gradient(135deg,#a855f7,#ec4899)"}}>
                Follow {meta.merchant_name} for more games
              </Link>
            )}
            <button type="button" onClick={onClose}
                          data-testid="game-play-close-result"
                          className={`mt-2 w-full h-10 rounded-full text-xs font-bold ${
                            light ? "bg-slate-100 text-slate-800"
                                    : "bg-slate-800 text-slate-200"}`}>
              Close
            </button>
          </>
        )}
      </div>
    </div>
  );
}
