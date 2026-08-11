// Phase 5 — Wallet page (5 tabs: Balance, Rewards, Games, Badges, Refer).
import { useState, useEffect, useCallback, useRef } from "react";
import { Link, useNavigate } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import {
  Loader2, Coins, Gift, Gamepad2, Award, Share2, ChevronLeft, Copy,
  Sparkles, Clock, CheckCircle2, X, Flame, ArrowRight, Crown, Ticket,
} from "lucide-react";
import "./Wallet.css";
import BannerAdSlot from "@/components/BannerAdSlot";
import CouponClaimModal from "@/components/CouponClaimModal";
// Phase 42-E2.2 — Universal invite-a-friend form (mocked Mailgun).
import InviteFriendForm from "@/components/InviteFriendForm";
// Phase 42-E2.4 — OG meta for the wallet surface.
import OGMeta from "@/components/OGMeta";
import { getDeviceFingerprintSync } from "@/lib/deviceFingerprint";
// Phase AD.11 — wallet banner zone.
import BannerZoneSlot from "@/components/BannerZoneSlot";
import GiftInboxSection from "@/components/GiftInboxSection";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
axios.defaults.withCredentials = true;

const TABS = [
  { id: "balance",  label: "Balance",  Icon: Coins },
  { id: "rewards",  label: "Rewards",  Icon: Gift },
  { id: "coupons",  label: "Coupons",  Icon: Ticket },
  { id: "games",    label: "Games",    Icon: Gamepad2 },
  { id: "badges",   label: "Badges",   Icon: Award },
  { id: "refer",    label: "Refer",    Icon: Share2 },
];

const TIER_ICONS = { bronze: "🥉", silver: "🥈", gold: "🥇", platinum: "💎" };

function BCToast({ amount, label, onDone }) {
  useEffect(() => {
    const t = setTimeout(onDone, 3000);
    return () => clearTimeout(t);
  }, [onDone]);
  return (
    <div className="bc-toast" data-testid="bc-toast">
      <Sparkles size={16} /> +{amount} BigCoin {label && `· ${label}`}
    </div>
  );
}

export default function Wallet() {
  const navigate = useNavigate();
  const [tab, setTab] = useState("balance");
  const [me, setMe] = useState(null);
  const [loading, setLoading] = useState(true);
  const [toastQueue, setToastQueue] = useState([]);

  const reloadMe = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/bigcoin/me`);
      setMe(r.data);
    } catch (e) {
      if (e?.response?.status === 401) navigate("/login");
      else toast.error("Failed to load wallet");
    } finally { setLoading(false); }
  }, [navigate]);

  useEffect(() => { reloadMe(); }, [reloadMe]);

  const pushBCToast = (amount, label) => {
    if (!amount) return;
    setToastQueue((q) => [...q, { id: Date.now() + Math.random(), amount, label }]);
  };

  if (loading) return (
    <div className="wallet-wrap" data-testid="wallet-loading">
      <Loader2 className="spin" size={28} />
    </div>
  );

  return (
    <div className="wallet-wrap" data-testid="wallet">
      <header className="wallet-header">
        <div>
          <Link to="/" style={{ color: "#888", fontSize: 12, textDecoration: "none" }} data-testid="back-to-radio">
            <ChevronLeft size={11} /> back to radio
          </Link>
          <h1>BigCoin Wallet</h1>
          <p className="sub">Earn by listening · Spend on rewards · Refer friends · Play games</p>
        </div>
      </header>

      {/* Phase 42-E2.4 — OG meta for the Wallet surface. */}
      <OGMeta entityType="wallet" entityId="me"
                          title="My RadioLife Wallet"
                          description="Listen more. Earn more. Cash in rewards on RadioLife." />

      <BalanceCard me={me} />

      {/* Gift Inbox — gifts received (packages, memberships, gift cards). */}
      <GiftInboxSection />

      {/* Phase AD.11 — wallet banner zone. */}
      <BannerZoneSlot zone="wallet" />

      <nav className="wallet-tabs" data-testid="wallet-tabs">
        {TABS.map((t) => {
          const Icon = t.Icon;
          return (
            <button key={t.id}
              className={`wallet-tab ${tab === t.id ? "active" : ""}`}
              onClick={() => setTab(t.id)}
              data-testid={`tab-${t.id}`}>
              <Icon size={14} /> {t.label}
            </button>
          );
        })}
      </nav>

      {tab === "balance" && <BalanceTab me={me} />}
      {tab === "rewards" && <RewardsTab me={me} onRedeemed={reloadMe} />}
      {tab === "coupons" && <CouponsTab />}
      {tab === "games" && <GamesTab onWin={(amount, label) => { pushBCToast(amount, label); reloadMe(); }} />}
      {tab === "badges" && <BadgesTab />}
      {tab === "refer" && <ReferTab me={me} />}

      {toastQueue.map((t) => (
        <BCToast key={t.id} amount={t.amount} label={t.label}
          onDone={() => setToastQueue((q) => q.filter((x) => x.id !== t.id))} />
      ))}
    </div>
  );
}

// ===============================================================
function BalanceCard({ me }) {
  return (
    <div className="bc-balance-card" data-testid="balance-card">
      <div className="bc-coin-icon">₿</div>
      <div style={{ flex: 1 }}>
        <div className="bc-meta-label">CURRENT BALANCE</div>
        <div className="bc-amount" data-testid="bc-balance">{me?.balance ?? 0}</div>
        <div style={{ display: "flex", gap: 16, marginTop: 12, flexWrap: "wrap", alignItems: "center" }}>
          <span className="bc-tier-badge" style={{ color: me?.tier_color }} data-testid="bc-tier">
            {TIER_ICONS[me?.tier] || "🥉"} {me?.tier_label}
          </span>
          <span style={{ fontSize: 12, color: "#aaa" }}>
            <Flame size={11} style={{ verticalAlign: "-1px", color: "#fdb756" }} />{" "}
            <b style={{ color: "#fff" }}>{me?.streak_days || 0}</b>-day streak
          </span>
          <span style={{ fontSize: 12, color: "#aaa" }}>
            Lifetime <b style={{ color: "#fff" }} data-testid="bc-lifetime">{me?.lifetime_earned || 0}</b>
          </span>
          {me?.adfree_until && new Date(me.adfree_until) > new Date() && (
            <span style={{ fontSize: 11, color: "#4ade80" }}>
              <Clock size={11} /> Ad-free active
            </span>
          )}
        </div>
      </div>
      <div style={{ minWidth: 200 }}>
        <div className="bc-meta-label">
          NEXT MILESTONE
          {me?.next_milestone && (
            <span style={{ float: "right", color: "var(--bc-pink)" }}>
              {me.balance}/{me.next_milestone}
            </span>
          )}
        </div>
        <div className="bc-milestone-bar">
          <div className="bc-milestone-fill" style={{ width: `${Math.min(100, me?.milestone_progress || 0)}%` }} />
        </div>
        <div style={{ fontSize: 10, color: "#888", marginTop: 6 }}>
          {me?.next_milestone
            ? `${me.next_milestone - me.lifetime_earned} BC to milestone`
            : "Max milestone reached!"}
        </div>
      </div>
    </div>
  );
}

// ===============================================================
function BalanceTab({ me }) {
  const [txns, setTxns] = useState([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    (async () => {
      try {
        const r = await axios.get(`${API}/bigcoin/transactions?limit=50`);
        setTxns(r.data.items || []);
      } catch (e) { toast.error("Failed to load transactions"); }
      finally { setLoading(false); }
    })();
  }, []);
  return (
    <section data-testid="tab-balance-content">
      <h3 style={{ fontSize: 14, color: "#888", letterSpacing: "0.05em", textTransform: "uppercase", marginBottom: 12 }}>
        Recent Activity
      </h3>
      {loading && <Loader2 className="spin" size={22} />}
      {!loading && txns.length === 0 && (
        <p style={{ color: "#888", padding: 24, textAlign: "center" }}>
          No transactions yet. Start listening to earn BigCoin!
        </p>
      )}
      <div className="txn-list">
        {txns.map((t) => (
          <div key={t.id} className="txn-row" data-testid={`txn-${t.id}`}>
            <div>
              <div className="txn-src">{prettySource(t.source)}</div>
              <div className="txn-sub">{new Date(t.created_at).toLocaleString()}</div>
            </div>
            <div style={{ textAlign: "right" }}>
              <div className={`txn-amount ${t.amount > 0 ? "earn" : "spend"}`}>
                {t.amount > 0 ? "+" : ""}{t.amount} BC
              </div>
              <div className="txn-sub">→ {t.balance_after}</div>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function prettySource(s) {
  return ({
    "listening": "🎧 Listening",
    "onboarding": "🎉 Welcome bonus",
    "streak": "🔥 Daily streak",
    "streak_milestone": "🏆 Streak milestone",
    "low_skip_bonus": "🎵 No-skip bonus",
    "referral": "✉️ Referral reward",
    "ad_click": "📣 Ad click",
    "ad_save": "🎟️ Coupon saved",
    "ad_redemption": "✅ Coupon redeemed",
    "game_win": "🎮 Game win",
    "redemption": "🛍️ Reward redeemed",
    "admin_adjust": "⚙️ Admin adjustment",
  })[s] || s;
}

// ===============================================================
function RewardsTab({ me, onRedeemed }) {
  const [rewards, setRewards] = useState([]);
  const [loading, setLoading] = useState(true);
  const [redeeming, setRedeeming] = useState(null);
  const load = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/bigcoin/rewards`);
      setRewards(r.data.items || []);
    } catch (e) { toast.error("Failed to load rewards"); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const redeem = async (id, name, cost) => {
    if ((me?.balance || 0) < cost) return toast.error("Not enough BigCoin");
    if (!window.confirm(`Redeem "${name}" for ${cost} BC?`)) return;
    setRedeeming(id);
    try {
      const r = await axios.post(`${API}/bigcoin/redeem/${id}`);
      toast.success(`Redeemed: ${name}`);
      onRedeemed?.();
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Redemption failed");
    } finally { setRedeeming(null); }
  };

  if (loading) return <Loader2 className="spin" size={22} />;
  return (
    <section data-testid="tab-rewards-content">
      <div className="reward-grid">
        {rewards.map((r) => {
          const canAfford = (me?.balance || 0) >= r.cost_bigcoin;
          const soldOut = r.stock_left !== null && r.stock_left <= 0;
          return (
            <div key={r.reward_id} className="reward-card" data-testid={`reward-${r.reward_id}`}>
              <div className="reward-cost"><Coins size={11} /> {r.cost_bigcoin} BC</div>
              <div className="reward-name" style={{ marginTop: 12 }}>{r.name}</div>
              <div className="reward-desc">{r.description}</div>
              {r.stock_left !== null && (
                <div style={{ fontSize: 10, color: soldOut ? "#fb7185" : "#888", marginBottom: 6 }}>
                  {soldOut ? "SOLD OUT" : `${r.stock_left} left`}
                </div>
              )}
              <button className="reward-btn"
                onClick={() => redeem(r.reward_id, r.name, r.cost_bigcoin)}
                disabled={!canAfford || soldOut || redeeming === r.reward_id}
                data-testid={`redeem-${r.reward_id}`}>
                {redeeming === r.reward_id ? <Loader2 className="spin" size={14} /> :
                  canAfford ? "Redeem" : `Need ${r.cost_bigcoin - (me?.balance || 0)} more BC`}
              </button>
            </div>
          );
        })}
      </div>
    </section>
  );
}

// ===============================================================
// Phase 18 — GamesTab now renders the games_v2 catalogue (Phase 8a)
// via the legacy /api/games/state shim, with a friendly empty state.
// Tapping a game routes to /play-and-win (the canonical play surface).
function GamesTab() {
  const [games, setGames] = useState([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/games/state`);
      setGames(r.data?.items || []);
    } catch {
      setGames([]);
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  if (loading) return <Loader2 className="spin" size={22} />;

  if (games.length === 0) {
    return (
      <section data-testid="tab-games-content" className="text-center py-12 px-6">
        <div className="text-5xl mb-3" data-testid="games-empty-icon">🎮</div>
        <div className="font-display font-bold text-xl tracking-display-tight mb-2"
              data-testid="games-empty-title">
          No games available right now
        </div>
        <p className="text-text-secondary text-sm max-w-md mx-auto mb-5">
          Check back soon — fresh games drop every week. Meanwhile, try
          tonight's trivia for live BigCoin earnings.
        </p>
        <button
          type="button"
          className="reward-btn"
          onClick={() => navigate("/trivia")}
          data-testid="games-empty-trivia-cta">
          Play Trivia <ArrowRight size={12} />
        </button>
      </section>
    );
  }

  return (
    <section data-testid="tab-games-content">
      <div className="game-grid">
        {games.map((g) => (
          <div key={g.game_id}
                className="game-card"
                onClick={() => navigate(`/play-and-win?game=${encodeURIComponent(g.game_id)}`)}
                data-testid={`game-${g.game_id}`}>
            <div className="game-icon">{g.icon}</div>
            <div style={{ fontSize: 18, fontWeight: 700, color: "#fff" }}>{g.title}</div>
            <p style={{ color: "#888", fontSize: 12, margin: "8px 0", lineHeight: 1.5 }}>
              {g.description || (g.sponsor_name ? `Sponsored by ${g.sponsor_name}` : "")}
            </p>
            <button
              type="button"
              className="reward-btn"
              style={{ marginTop: 12 }}
              data-testid={`play-${g.game_id}`}
              onClick={(e) => { e.stopPropagation(); navigate(`/play-and-win?game=${encodeURIComponent(g.game_id)}`); }}>
              Play <ArrowRight size={12} />
            </button>
          </div>
        ))}
      </div>
    </section>
  );
}

function formatCooldown(sec) {
  if (sec < 60) return `${sec}s`;
  if (sec < 3600) return `${Math.ceil(sec / 60)}m`;
  return `${Math.floor(sec / 3600)}h ${Math.ceil((sec % 3600) / 60)}m`;
}

// ===============================================================
// Spin & Win modal
function SpinModal({ onClose }) {
  const [spinning, setSpinning] = useState(false);
  const [result, setResult] = useState(null);
  const [rotation, setRotation] = useState(0);
  const SLICES = [
    { label: "5 BC", color: "#ff2d95" }, { label: "20 BC", color: "#7BD3F7" },
    { label: "50 BC", color: "#fdb756" }, { label: "100 BC", color: "#a78bfa" },
    { label: "200 BC", color: "#4ade80" }, { label: "Coupon", color: "#fb7185" },
  ];
  const handleSpin = async () => {
    setSpinning(true);
    try {
      const r = await axios.post(`${API}/games/spin/play`,
        { client_seed: `c_${Math.random().toString(36).slice(2)}` });
      const slice = r.data.slice_index;
      const sliceSize = 360 / SLICES.length;
      const target = 360 * 6 + (360 - (slice * sliceSize + sliceSize / 2));
      setRotation(target);
      setTimeout(() => {
        setResult(r.data);
        setSpinning(false);
      }, 3100);
    } catch (e) {
      setSpinning(false);
      toast.error(e?.response?.data?.detail || "Spin failed");
    }
  };
  return (
    <div className="spin-modal" data-testid="spin-modal">
      <div className="spin-stage">
        <button className="spin-close" onClick={() => onClose(result?.bigcoin_earned, result?.label)}
          data-testid="spin-close"><X size={20} /></button>
        <h2 style={{ fontSize: 22, color: "#fff", marginBottom: 8 }}>🎡 Spin & Win</h2>
        <p style={{ color: "#888", fontSize: 13, marginBottom: 20 }}>
          One spin every 4 hours. May the luck be with you.
        </p>
        <div className="wheel-frame">
          <div className="wheel-pointer" />
          <svg viewBox="0 0 200 200" className="wheel" style={{ transform: `rotate(${rotation}deg)` }}>
            {SLICES.map((s, i) => {
              const angle = 360 / SLICES.length;
              const start = i * angle - 90;
              const end = start + angle;
              const r = 100;
              const x1 = 100 + r * Math.cos((start * Math.PI) / 180);
              const y1 = 100 + r * Math.sin((start * Math.PI) / 180);
              const x2 = 100 + r * Math.cos((end * Math.PI) / 180);
              const y2 = 100 + r * Math.sin((end * Math.PI) / 180);
              const labelAngle = start + angle / 2;
              const lx = 100 + 65 * Math.cos((labelAngle * Math.PI) / 180);
              const ly = 100 + 65 * Math.sin((labelAngle * Math.PI) / 180);
              return (
                <g key={i}>
                  <path d={`M100,100 L${x1},${y1} A${r},${r} 0 0,1 ${x2},${y2} Z`}
                    fill={s.color} stroke="#15151e" strokeWidth="2" />
                  <text x={lx} y={ly} fill="#1a1a24" fontSize="11" fontWeight="700"
                    textAnchor="middle" dominantBaseline="middle"
                    transform={`rotate(${labelAngle + 90}, ${lx}, ${ly})`}>
                    {s.label}
                  </text>
                </g>
              );
            })}
            <circle cx="100" cy="100" r="12" fill="#15151e" stroke="#fdb756" strokeWidth="2" />
          </svg>
        </div>
        {!result && !spinning && (
          <button className="reward-btn" onClick={handleSpin} data-testid="do-spin">
            <Sparkles size={14} /> Spin!
          </button>
        )}
        {spinning && <p style={{ color: "#888" }}><Loader2 className="spin" size={14} /> Spinning...</p>}
        {result && (
          <div data-testid="spin-result" style={{ marginTop: 16 }}>
            <div style={{ fontSize: 22, color: "var(--bc-gold)", fontWeight: 800 }}>
              You won: {result.label}!
            </div>
            <button className="reward-btn" onClick={() => onClose(result.bigcoin_earned, result.label)}
              style={{ marginTop: 14 }} data-testid="spin-close-after">
              <CheckCircle2 size={14} /> Awesome!
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// ===============================================================
function TriviaModal({ onClose }) {
  const [q, setQ] = useState(null);
  const [chosen, setChosen] = useState(null);
  const [result, setResult] = useState(null);
  const [streak, setStreak] = useState(0);
  const [busy, setBusy] = useState(true);

  const startNew = useCallback(async () => {
    setBusy(true); setQ(null); setResult(null); setChosen(null);
    try {
      const r = await axios.post(`${API}/games/trivia/start`);
      setQ(r.data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Cannot start trivia");
      onClose(0, null);
    } finally { setBusy(false); }
  }, [onClose]);

  useEffect(() => { startNew(); }, [startNew]);

  const answer = async (idx) => {
    if (chosen !== null) return;
    setChosen(idx);
    try {
      const r = await axios.post(`${API}/games/trivia/answer`,
        { question_id: q.question_id, chosen_idx: idx, streak_in: streak });
      setResult(r.data);
      setStreak(r.data.new_streak);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Answer failed");
    }
  };

  return (
    <div className="spin-modal" data-testid="trivia-modal">
      <div className="spin-stage">
        <button className="spin-close"
          onClick={() => onClose(result?.bigcoin_earned, "Trivia")}
          data-testid="trivia-close"><X size={20} /></button>
        <h2 style={{ fontSize: 22, color: "#fff" }}>🎶 Music Trivia</h2>
        {streak > 0 && (
          <div style={{ color: "#fdb756", fontSize: 13, marginTop: 6 }}>
            <Flame size={11} /> Streak: {streak} consecutive correct
          </div>
        )}
        {busy && <Loader2 className="spin" size={20} style={{ marginTop: 20 }} />}
        {q && (
          <>
            <p className="trivia-question">{q.question}</p>
            <div className="trivia-options">
              {q.options.map((opt, i) => {
                const isChosen = chosen === i;
                const isCorrect = result && i === result.correct_idx;
                const classes = ["trivia-option"];
                if (chosen !== null) classes.push("disabled");
                if (result && isCorrect) classes.push("correct");
                else if (isChosen && result && !isCorrect) classes.push("wrong");
                return (
                  <button key={i} className={classes.join(" ")}
                    onClick={() => answer(i)}
                    data-testid={`trivia-option-${i}`}>
                    {opt}
                  </button>
                );
              })}
            </div>
            {result && (
              <div style={{ marginTop: 20, textAlign: "center" }}>
                {result.correct ? (
                  <div style={{ color: "var(--bc-green)" }}>
                    <CheckCircle2 size={20} /> +{result.bigcoin_earned} BigCoin!
                  </div>
                ) : (
                  <div style={{ color: "#fb7185" }}>
                    <X size={20} /> Wrong answer
                  </div>
                )}
                <div style={{ display: "flex", gap: 8, justifyContent: "center", marginTop: 14 }}>
                  <button className="reward-btn" style={{ width: "auto", padding: "8px 18px" }}
                    onClick={startNew} data-testid="trivia-next">
                    Next question
                  </button>
                  <button className="reward-btn" style={{ width: "auto", padding: "8px 18px", background: "#2a2a36" }}
                    onClick={() => onClose(result.bigcoin_earned, "Trivia")}
                    data-testid="trivia-done">Done</button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

// ===============================================================
function LyricModal({ onClose }) {
  const [q, setQ] = useState(null);
  const [chosen, setChosen] = useState(null);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(true);
  const startNew = useCallback(async () => {
    setBusy(true); setQ(null); setResult(null); setChosen(null);
    try {
      const r = await axios.post(`${API}/games/lyric/start`);
      setQ(r.data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Cannot start lyric");
      onClose(0, null);
    } finally { setBusy(false); }
  }, [onClose]);
  useEffect(() => { startNew(); }, [startNew]);

  const answer = async (idx) => {
    if (chosen !== null) return;
    setChosen(idx);
    try {
      const r = await axios.post(`${API}/games/lyric/answer`,
        { puzzle_id: q.puzzle_id, chosen_idx: idx });
      setResult(r.data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Answer failed");
    }
  };
  return (
    <div className="spin-modal" data-testid="lyric-modal">
      <div className="spin-stage">
        <button className="spin-close"
          onClick={() => onClose(result?.bigcoin_earned, "Lyric")}
          data-testid="lyric-close"><X size={20} /></button>
        <h2 style={{ fontSize: 22, color: "#fff" }}>🎤 Complete the Lyric</h2>
        {q && (
          <>
            <p style={{ color: "#888", fontSize: 11, marginTop: 8 }}>{q.song} — {q.artist}</p>
            <p style={{ fontSize: 18, color: "#fff", margin: "18px 0 4px", lineHeight: 1.5,
                          fontStyle: "italic" }}>"{q.first_half}..."</p>
            <p style={{ color: "#888", fontSize: 12, marginBottom: 18 }}>What comes next?</p>
            <div className="trivia-options">
              {q.options.map((opt, i) => {
                const classes = ["trivia-option"];
                if (chosen !== null) classes.push("disabled");
                if (result && i === result.correct_idx) classes.push("correct");
                else if (chosen === i && result && i !== result.correct_idx) classes.push("wrong");
                return (
                  <button key={i} className={classes.join(" ")}
                    onClick={() => answer(i)}
                    data-testid={`lyric-option-${i}`}>{opt}</button>
                );
              })}
            </div>
            {result && (
              <div style={{ marginTop: 18, textAlign: "center" }}>
                {result.correct ? (
                  <div style={{ color: "var(--bc-green)" }}>
                    <CheckCircle2 size={20} /> +{result.bigcoin_earned} BigCoin!
                  </div>
                ) : (
                  <div style={{ color: "#fb7185" }}>
                    <X size={20} /> Better luck next time
                  </div>
                )}
                <div style={{ display: "flex", gap: 8, justifyContent: "center", marginTop: 14 }}>
                  <button className="reward-btn" style={{ width: "auto", padding: "8px 18px" }}
                    onClick={startNew} data-testid="lyric-next">Next puzzle</button>
                  <button className="reward-btn" style={{ width: "auto", padding: "8px 18px", background: "#2a2a36" }}
                    onClick={() => onClose(result.bigcoin_earned, "Lyric")}
                    data-testid="lyric-done">Done</button>
                </div>
              </div>
            )}
          </>
        )}
        {busy && <Loader2 className="spin" size={20} style={{ marginTop: 20 }} />}
      </div>
    </div>
  );
}

// ===============================================================
function CouponsTab() {
  const [items, setItems]   = useState([]);
  const [loading, setLoad]  = useState(true);
  const [modalRow, setModal] = useState(null);

  useEffect(() => {
    let cancel = false;
    (async () => {
      try {
        const device = getDeviceFingerprintSync();
        const params = {};
        if (device) params.device_fingerprint = device;
        const r = await axios.get(`${API}/me/coupons`, { params });
        if (!cancel) setItems(r.data?.items || []);
      } catch {
        if (!cancel) setItems([]);
      } finally {
        if (!cancel) setLoad(false);
      }
    })();
    return () => { cancel = true; };
  }, []);

  if (loading) return <Loader2 className="spin" size={22} />;

  if (items.length === 0) {
    return (
      <section data-testid="tab-coupons-content"
                className="text-center py-12 px-6">
        <div style={{ fontSize: 40, marginBottom: 10 }}
              data-testid="coupons-empty-icon">🎟</div>
        <div style={{ fontSize: 18, fontWeight: 700, color: "#fff",
                        marginBottom: 6 }}
              data-testid="coupons-empty-title">
          No coupons yet
        </div>
        <p style={{ color: "#9aa3af", fontSize: 13,
                     maxWidth: 380, margin: "0 auto" }}>
          Claim offers from stations you follow — they&apos;ll show up here
          with QR codes ready to scan at the venue.
        </p>
      </section>
    );
  }

  return (
    <section data-testid="tab-coupons-content">
      <p style={{ color: "#888", fontSize: 12, marginBottom: 16 }}>
        <b style={{ color: "#fff" }} data-testid="coupons-count">{items.length}</b>{" "}
        coupon{items.length === 1 ? "" : "s"} claimed
      </p>
      <div className="reward-grid">
        {items.map((c) => (
          <CouponCard key={c.redemption_id}
                       coupon={c}
                       onOpen={() => setModal(c)} />
        ))}
      </div>
      <CouponClaimModal open={!!modalRow}
                          redemption={modalRow}
                          onClose={() => setModal(null)} />
    </section>
  );
}

function CouponCard({ coupon, onOpen }) {
  const isExpired = coupon.is_expired;
  const discount = coupon.discount_pct
    ? `${coupon.discount_pct}% OFF`
    : coupon.discount_amount_cents
      ? `$${(coupon.discount_amount_cents/100).toFixed(2)} OFF`
      : "Reward";
  const expiresText = coupon.expires_at
    ? new Date(coupon.expires_at).toLocaleDateString(undefined,
        { month: "short", day: "numeric", year: "numeric" })
    : null;
  return (
    <div data-testid={`wallet-coupon-${coupon.redemption_id}`}
         data-expired={isExpired ? "true" : "false"}
         onClick={onOpen}
         className="reward-card"
         style={{ cursor: isExpired ? "default" : "pointer",
                   opacity: isExpired ? 0.55 : 1,
                   border: "1px solid rgba(0,217,255,0.25)" }}>
      <div style={{ display: "inline-flex", alignItems: "center", gap: 4,
                     background: "rgba(0,217,255,0.12)", color: "#00d9ff",
                     border: "1px solid rgba(0,217,255,0.4)",
                     borderRadius: 999, padding: "3px 8px",
                     fontSize: 10, fontWeight: 700,
                     letterSpacing: "0.04em", textTransform: "uppercase",
                     marginBottom: 10 }}>
        <Ticket size={11} /> {discount}
      </div>
      <div style={{ fontSize: 16, fontWeight: 700, color: "#fff",
                     marginBottom: 4,
                     overflow: "hidden", textOverflow: "ellipsis",
                     whiteSpace: "nowrap" }}>
        {coupon.station_name || coupon.station_slug}
      </div>
      <div style={{ fontFamily: "monospace", fontSize: 12,
                     color: "#00d9ff",
                     background: "rgba(0,217,255,0.06)",
                     border: "1px solid rgba(0,217,255,0.2)",
                     padding: "3px 8px", borderRadius: 4,
                     letterSpacing: "0.06em",
                     display: "inline-block", marginBottom: 8 }}>
        {coupon.coupon_code}
      </div>
      {expiresText && (
        <div style={{ fontSize: 10, color: isExpired ? "#fb7185" : "#888" }}>
          {isExpired ? `Expired ${expiresText}` : `Expires ${expiresText}`}
        </div>
      )}
      {!isExpired && (
        <div style={{ marginTop: 10, fontSize: 11, color: "#00d9ff",
                       fontWeight: 600,
                       display: "inline-flex", alignItems: "center", gap: 4 }}>
          Show QR <ArrowRight size={11} />
        </div>
      )}
    </div>
  );
}

// ===============================================================
function BadgesTab() {
  const [data, setData] = useState(null);
  useEffect(() => {
    (async () => {
      try {
        const r = await axios.get(`${API}/bigcoin/badges`);
        setData(r.data);
      } catch (e) { toast.error("Failed to load badges"); }
    })();
  }, []);
  if (!data) return <Loader2 className="spin" size={22} />;
  return (
    <section data-testid="tab-badges-content">
      <p style={{ color: "#888", fontSize: 12, marginBottom: 16 }}>
        Unlocked <b style={{ color: "#fff" }}>{data.unlocked_count}</b> of {data.total} badges
      </p>
      <div className="badge-grid">
        {data.items.map((b) => (
          <div key={b.badge_id}
            className={`badge-card ${b.unlocked ? "" : "locked"} ${b.tier || ""}`}
            data-testid={`badge-${b.slug}`}>
            <div className="icon">{b.icon || "🏅"}</div>
            <div className="name">{b.name}</div>
            <div className="desc">{b.description}</div>
            {b.tier && <span className="tier-tag">{b.tier}</span>}
          </div>
        ))}
      </div>
    </section>
  );
}

// ===============================================================
function ReferTab({ me }) {
  const [data, setData] = useState(null);
  const code = me?.referrer_code;
  const inviteUrl = `${window.location.origin}/invite/${code}`;
  useEffect(() => {
    (async () => {
      try {
        const r = await axios.get(`${API}/bigcoin/referrals`);
        setData(r.data);
      } catch (e) {}
    })();
  }, []);
  const copy = () => {
    navigator.clipboard.writeText(inviteUrl);
    toast.success("Invite link copied!");
  };
  const share = async () => {
    if (navigator.share) {
      try { await navigator.share({
        title: "Join me on RadioLife",
        text: "Listen to AI-curated radio with me. Sign up via my link and we both earn BigCoin:",
        url: inviteUrl,
      }); } catch {}
    } else copy();
  };
  return (
    <section data-testid="tab-refer-content">
      {/* Phase 42-E2.2 — universal "Invite a Friend" form (email + name
            + note → mocked Mailgun + referral voucher).  Sits on top of
            the legacy referral-link card so listeners get both flows. */}
      <div style={{ marginBottom: 16 }}>
        <InviteFriendForm />
      </div>
      <div className="refer-card">
        <p style={{ color: "#aaa", fontSize: 13 }}>Share this link. When a friend signs up + completes onboarding:</p>
        <p style={{ color: "var(--bc-gold)", fontWeight: 800, fontSize: 18, margin: "8px 0" }}>
          You earn <Coins size={16} /> +100 BigCoin
        </p>
        <div className="refer-code" data-testid="referrer-code">{code}</div>
        <p style={{ color: "#888", fontSize: 11, fontFamily: "monospace", wordBreak: "break-all" }}>
          {inviteUrl}
        </p>
        <div style={{ display: "flex", gap: 10, justifyContent: "center", marginTop: 18 }}>
          <button className="refer-copy-btn" onClick={copy} data-testid="copy-invite">
            <Copy size={14} /> Copy link
          </button>
          <button className="refer-copy-btn" onClick={share}
            style={{ background: "#2a2a36" }} data-testid="share-invite">
            <Share2 size={14} /> Share
          </button>
        </div>
        {data && (
          <div style={{ display: "flex", gap: 32, justifyContent: "center", marginTop: 24, fontSize: 13, color: "#aaa" }}>
            <div data-testid="refer-stat-invited">
              <div style={{ fontSize: 22, color: "#fff", fontWeight: 700 }}>{data.total_invited}</div>
              <div className="bc-meta-label">INVITED</div>
            </div>
            <div data-testid="refer-stat-completed">
              <div style={{ fontSize: 22, color: "var(--bc-green)", fontWeight: 700 }}>{data.completed}</div>
              <div className="bc-meta-label">COMPLETED</div>
            </div>
            <div data-testid="refer-stat-earned">
              <div style={{ fontSize: 22, color: "var(--bc-gold)", fontWeight: 700 }}>{data.bigcoin_earned}</div>
              <div className="bc-meta-label">BC EARNED</div>
            </div>
          </div>
        )}
        <p style={{ color: "#666", fontSize: 10, marginTop: 18 }}>
          Monthly cap: 1000 BC (10 successful invites)
        </p>
      </div>
    </section>
  );
}
