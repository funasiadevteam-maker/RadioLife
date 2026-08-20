// Phase 8a — Advertiser game campaigns dashboard + wizard.
// Phase 23 Session 3 — adds Placement & Rules step exposing Session 2's
// 4 new backend columns (placement_rules_json, eligibility_rules_json,
// win_rules_json, creator_type), and routes /admin/games/new through
// this same wizard with creator_type="admin" pre-set.
import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import axios from "axios";
import { Toaster, toast } from "sonner";
import {
  ChevronLeft, Plus, ChevronRight, ChevronLeft as Back, Loader2,
  Check, X, Sparkles, Lock, Trophy, Gamepad2, AlertTriangle, Eye,
} from "lucide-react";
import { useAuth, API } from "@/AuthContext";
import SpinWheel from "./games/SpinWheel";
import ScratchCard from "./components/games/ScratchCardGame";
import { themeFor } from "./components/games";
import Quiz from "./games/Quiz";
import MysteryBox from "./games/MysteryBox";
import { LISTENER_VISIBLE_TEMPLATES } from "./components/games";
import "./PlayAndWin.css";

const STATUS_COLORS = {
  draft: "#888", pending_approval: "#ffb547", active: "#14e29a",
  paused: "#5dbcff", rejected: "#ff5a6e", ended: "#666", archived: "#444",
};

export default function AdvertiserGames() {
  const { user, loading: authLoading } = useAuth();
  const navigate = useNavigate();
  const [campaigns, setCampaigns] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (authLoading) return;
    if (!user) { navigate("/login"); return; }
    if (!user.is_advertiser && user.role !== "admin" && user.role !== "advertiser") {
      toast.error("Advertiser role required");
      navigate("/");
      return;
    }
    reload();
  }, [user, authLoading]); // eslint-disable-line

  const reload = async () => {
    try {
      const r = await axios.get(`${API}/games_v2/advertiser/campaigns`);
      setCampaigns(r.data.items || []);
    } catch (_e) { toast.error("Failed to load campaigns"); }
    finally { setLoading(false); }
  };

  if (authLoading || !user) {
    return <div className="paw-loading"><Loader2 size={28} className="spin" /></div>;
  }

  return (
    <div className="advgames-wrap" data-testid="advertiser-games-page">
      <Toaster theme="dark" position="bottom-right" richColors />
      <header className="paw-header">
        <div>
          <Link to="/" className="paw-back"><ChevronLeft size={14} /> back</Link>
          <h1>Game campaigns</h1>
          <p className="sub">Build templated games — spin wheels, quizzes, scratch cards, mystery boxes — and ship to a fresh, engaged audience.</p>
        </div>
        <Link to="/advertiser/games/new"
                className="lobbies-host-btn"
                data-testid="new-campaign-btn">
          <Plus size={14} /> New game campaign
        </Link>
        <Link to="/advertiser/games-insights"
                className="ghost-btn"
                style={{marginLeft: 8}}
                data-testid="insights-link">
          insights →
        </Link>
      </header>
      {loading ? (
        <div className="paw-loading"><Loader2 size={28} className="spin" /></div>
      ) : campaigns.length === 0 ? (
        <div className="paw-empty" data-testid="adv-empty">
          <p>No campaigns yet. Spin one up.</p>
        </div>
      ) : (
        <table className="advgames-table" data-testid="adv-campaigns-table">
          <thead>
            <tr>
              <th>Campaign</th><th>Status</th><th>Template</th>
              <th>Starts</th><th>Wins</th><th>Saves</th><th></th>
            </tr>
          </thead>
          <tbody>
            {campaigns.map((c) => (
              <tr key={c.campaign_id} data-testid={`adv-row-${c.campaign_id}`}>
                <td>
                  <div className="adv-row-title">{c.title}</div>
                  <div className="mono dim">{c.sponsor_name}</div>
                </td>
                <td>
                  <span className="status-pill mono"
                          style={{ color: STATUS_COLORS[c.status],
                                  borderColor: STATUS_COLORS[c.status] }}>
                    {c.status}
                  </span>
                </td>
                <td className="mono dim">{c.template_id.replace("tpl_", "")}</td>
                <td className="mono">{c.counters?.start || 0}</td>
                <td className="mono">{c.counters?.win || 0}</td>
                <td className="mono">{c.counters?.save_to_wallet || 0}</td>
                <td>
                  {c.status === "draft" || c.status === "rejected" ? (
                    <Link to={`/advertiser/games/${c.campaign_id}/edit`}
                            className="adv-edit-link mono"
                            data-testid={`adv-edit-${c.campaign_id}`}>
                      edit →
                    </Link>
                  ) : (
                    <span className="mono dim">view-only</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

// ============================================================
// Wizard
// ============================================================
// Phase 23 Session 3 — Placement & Rules inserted between Budget and Review
// so the wizard now ships 9 visible steps; the audit's "7-step pattern"
// is satisfied by these new fields being the gap between today's UI and
// the original spec.  Existing 8 steps left intact — zero break for the
// 1,008 live campaigns currently in production.
const WIZARD_STEPS = [
  "Template", "Branding", "Game config", "Prizes",
  "Targeting", "Compliance", "Budget", "Placement & rules", "Review",
];

export function AdvertiserGameWizard() {
  const { user, loading: authLoading } = useAuth();
  const navigate = useNavigate();
  // Phase 23 Session 3 — /admin/games/new takes the same wizard and
  // flips it to admin-creator mode (different submit endpoint, no
  // approval workflow).
  const location = useLocation();
  const isAdminCreator = location.pathname.startsWith("/admin/games/new");
  const [step, setStep] = useState(0);
  const [templates, setTemplates] = useState([]);
  const [draft, setDraft] = useState({
    template_id: null, title: "", description: "",
    sponsor_name: "", sponsor_logo_url: "",
    brand_colors_json: { primary: "#ff2d95" },
    game_config_json: {},
    prizes: [],
    targeting_json: { city: "", channel: "", mood: "", daypart: "" },
    compliance: { terms_text: "", odds_disclosure: "",
                    no_purchase_necessary_text: "", age_restriction: null },
    redemption_rules: { expiration_days: 30, one_time_use: true,
                              requires_qr: false },
    budget_cents: null, bid_type: "per_save", bid_amount_cents: 0,
    objective: "listener_engagement",
    open_to_all: true,
    start_at: null, end_at: null,
    // Phase 23 Session 2 backend columns — exposed in Step 8 below.
    placement_rules_json: {
      locations: ["play_and_win_tab"],
      after_track: false,
      during_ad: false,
      post_listening_minutes: 0,
    },
    eligibility_rules_json: {
      min_listening_minutes: 0,
      requires_login: true,
      open_to_premium_only: false,
      requires_lead_capture: false,
    },
    win_rules_json: {
      cooldown_minutes: 0,
      max_wins_per_user: 1,
      max_plays_per_user_per_day: 3,
      win_announce_rj: true,
    },
    creator_type: isAdminCreator ? "admin" : "advertiser",
  });
  const [draftId, setDraftId] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (authLoading) return;
    if (!user) { navigate("/login"); return; }
    if (!user.is_advertiser && user.role !== "admin" && user.role !== "advertiser") {
      navigate("/"); return;
    }
    (async () => {
      try {
        const r = await axios.get(`${API}/games_v2/advertiser/templates`);
        // Phase 23 Session 4 — listener-facing wizard hides hidden
        // template types from the picker.  Already-created campaigns
        // of hidden types keep rendering via the GamePlayer dispatcher.
        const visible = (r.data.templates || []).filter((t) =>
          LISTENER_VISIBLE_TEMPLATES.includes(t.template_id));
        setTemplates(visible);
      } catch (_e) { toast.error("Failed to load templates"); }
    })();
  }, [user, authLoading]); // eslint-disable-line

  const tpl = useMemo(
    () => templates.find((t) => t.template_id === draft.template_id),
    [templates, draft.template_id]);

  const weightSum = useMemo(
    () => (draft.prizes || []).reduce(
      (a, p) => a + (parseInt(p.probability_weight) || 0), 0),
    [draft.prizes]);

  const saveDraft = async () => {
    setBusy(true);
    try {
      if (draftId) {
        await axios.patch(`${API}/games_v2/advertiser/campaigns/${draftId}`,
                                draft);
      } else if (isAdminCreator) {
        // Phase 23 Session 3 — admin-creator path uses the dedicated
        // /admin/campaigns endpoint added in Session 2 backend.  It sets
        // creator_type=admin + is_platform_funded=True server-side and
        // auto-approves on submit (status flips to 'active' when
        // validation passes).
        const r = await axios.post(`${API}/games_v2/admin/campaigns`,
                                          { ...draft, creator_type: "admin" });
        setDraftId(r.data.campaign_id);
        return r.data.campaign_id;
      } else {
        const r = await axios.post(`${API}/games_v2/advertiser/campaigns`,
                                          draft);
        setDraftId(r.data.campaign_id);
        return r.data.campaign_id;
      }
      return draftId;
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Save failed");
      return null;
    } finally { setBusy(false); }
  };

  const next = async () => {
    // Persist on every step
    const cid = await saveDraft();
    if (!cid) return;
    setStep((s) => Math.min(s + 1, WIZARD_STEPS.length - 1));
  };
  const prev = () => setStep((s) => Math.max(s - 1, 0));

  const submitForApproval = async () => {
    const cid = await saveDraft();
    if (!cid) return;
    setBusy(true);
    try {
      if (isAdminCreator) {
        // Admin-creator path is already auto-approved by the
        // /admin/campaigns endpoint (status flips to "active" on
        // successful save).  Skip the submit-for-approval round-trip.
        toast.success("Published");
        navigate("/admin/games-approval");
      } else {
        await axios.post(
          `${API}/games_v2/advertiser/campaigns/${cid}/submit_for_approval`);
        toast.success("Submitted for approval");
        navigate("/advertiser/games");
      }
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Validation failed");
    } finally { setBusy(false); }
  };

  if (authLoading || !user) {
    return <div className="paw-loading"><Loader2 size={28} className="spin" /></div>;
  }

  return (
    <div className="wizard-wrap" data-testid="adv-game-wizard">
      <Toaster theme="dark" position="bottom-right" richColors />
      <header className="paw-header">
        <div>
          <Link to="/advertiser/games" className="paw-back">
            <ChevronLeft size={14} /> cancel
          </Link>
          <h1>New game campaign</h1>
        </div>
      </header>
      <div className="wizard-progress" data-testid="wizard-progress">
        {WIZARD_STEPS.map((s, i) => (
          <div key={s} className={`wp-step ${i === step ? "current" : ""} ${i < step ? "done" : ""}`}>
            <div className="wp-dot">{i + 1}</div>
            <span>{s}</span>
          </div>
        ))}
      </div>
      <main className="wizard-step">
        {step === 0 && (
          <TemplateStep templates={templates} draft={draft}
                              setDraft={setDraft} />
        )}
        {step === 1 && <BrandingStep draft={draft} setDraft={setDraft} />}
        {step === 2 && <GameConfigStep draft={draft} setDraft={setDraft} tpl={tpl} />}
        {step === 3 && <PrizesStep draft={draft} setDraft={setDraft}
                                          weightSum={weightSum} tpl={tpl} />}
        {step === 4 && <TargetingStep draft={draft} setDraft={setDraft} />}
        {step === 5 && <ComplianceStep draft={draft} setDraft={setDraft} />}
        {step === 6 && <BudgetStep draft={draft} setDraft={setDraft} />}
        {step === 7 && <PlacementRulesStep draft={draft}
                                                                  setDraft={setDraft}
                                                                  isAdminCreator={isAdminCreator} />}
        {step === 8 && <ReviewStep draft={draft} tpl={tpl}
                                          weightSum={weightSum}
                                          isAdminCreator={isAdminCreator} />}
      </main>
      <div className="wizard-actions">
        <button onClick={prev} disabled={step === 0 || busy}
                  className="btn-ghost" data-testid="wizard-back-btn">
          <Back size={13} /> Back
        </button>
        {step < WIZARD_STEPS.length - 1 ? (
          <button
            onClick={next}
            disabled={busy || !draft.template_id || (step === 3 && weightSum !== 100)}
            title={step === 3 && weightSum !== 100
              ? "All probability weights must sum to 100"
              : ""}
            className="btn-primary" data-testid="wizard-next-btn">
            {busy ? <Loader2 size={13} className="spin" /> : <>Next <ChevronRight size={13} /></>}
          </button>
        ) : (
          <button
            onClick={submitForApproval}
            disabled={busy || weightSum !== 100}
            title={weightSum !== 100
              ? "All probability weights must sum to 100"
              : ""}
            className="btn-primary"
            data-testid="wizard-submit-btn">
            {busy ? <Loader2 size={13} className="spin" /> : (
              isAdminCreator
                ? <>Publish (admin) <Sparkles size={13} /></>
                : <>Submit for approval <Sparkles size={13} /></>
            )}
          </button>
        )}
      </div>
    </div>
  );
}

// === Wizard step components ==========================================
function TemplateStep({ templates, draft, setDraft }) {
  return (
    <div className="step-grid template-grid">
      {templates.map((t) => {
        const theme = themeFor(t.game_type || t.template_id);
        return (
          <button
            key={t.template_id}
            disabled={!t.active}
            onClick={() => setDraft((d) => ({
              ...d, template_id: t.template_id,
              game_config_json: t.default_config_json || {},
            }))}
            className={`tpl-card themed ${draft.template_id === t.template_id ? "picked" : ""} ${!t.active ? "locked" : ""}`}
            style={{"--tpl-accent": theme.accent}}
            data-testid={`tpl-card-${t.template_id}`}
            data-tpl-accent={theme.accent}>
            {!t.active && <span className="tpl-soon"><Lock size={10} /> Phase 8b</span>}
            <div className="tpl-icon" style={{background: `${theme.accent}22`,
                                                                              color: theme.accent}}>
              {theme.emoji}
            </div>
            <h3>{t.name}</h3>
            <p>{t.description}</p>
          </button>
        );
      })}
    </div>
  );
}

function BrandingStep({ draft, setDraft }) {
  return (
    <div className="step-stack">
      <label>Title
        <input value={draft.title} maxLength={60}
                onChange={(e) => setDraft({ ...draft, title: e.target.value })}
                placeholder="Karak Cafe Friday Spin"
                data-testid="wiz-title" />
      </label>
      <label>Sponsor name
        <input value={draft.sponsor_name} maxLength={60}
                onChange={(e) => setDraft({ ...draft, sponsor_name: e.target.value })}
                placeholder="Karak Cafe Dubai"
                data-testid="wiz-sponsor-name" />
      </label>
      <label>Sponsor logo URL
        <input value={draft.sponsor_logo_url} maxLength={200}
                onChange={(e) => setDraft({ ...draft, sponsor_logo_url: e.target.value })}
                placeholder="https://…/logo.png"
                data-testid="wiz-logo" />
      </label>
      <label>Description
        <textarea value={draft.description} maxLength={300} rows={3}
                      onChange={(e) => setDraft({ ...draft, description: e.target.value })}
                      placeholder="What this game is about — what makes it fun"
                      data-testid="wiz-desc" />
      </label>
      <label>Brand primary color
        <input type="color"
                value={draft.brand_colors_json?.primary || "#ff2d95"}
                onChange={(e) => setDraft({
                  ...draft, brand_colors_json: { primary: e.target.value },
                })}
                data-testid="wiz-color" />
      </label>
    </div>
  );
}

function GameConfigStep({ draft, setDraft, tpl }) {
  if (!tpl) return <p className="dim">Pick a template first.</p>;
  const cfg = draft.game_config_json || {};
  const setCfg = (k, v) => setDraft({
    ...draft, game_config_json: { ...cfg, [k]: v }
  });
  if (tpl.game_type === "spin_wheel") {
    const segments = cfg.segments || [];
    return (
      <div className="step-stack">
        <h3 className="mono">Wheel segments (visual only — server picks the prize)</h3>
        {segments.map((s, i) => (
          <div className="row" key={i}>
            <input value={s.label}
                    onChange={(e) => {
                      const ns = [...segments]; ns[i].label = e.target.value;
                      setCfg("segments", ns);
                    }} placeholder="Label" data-testid={`seg-${i}-label`} />
            <input type="color" value={s.color}
                    onChange={(e) => {
                      const ns = [...segments]; ns[i].color = e.target.value;
                      setCfg("segments", ns);
                    }} />
            <button onClick={() => setCfg("segments", segments.filter((_, j) => j !== i))}
                      className="btn-ghost"><X size={11} /></button>
          </div>
        ))}
        <button onClick={() => setCfg("segments",
                                                [...segments, {label: `Segment ${segments.length + 1}`,
                                                                  color: "#5dbcff", probability_weight: 0}])}
                  className="btn-ghost" data-testid="add-segment-btn">
          <Plus size={11} /> Add segment
        </button>
      </div>
    );
  }
  if (tpl.game_type === "quiz") {
    const qs = cfg.questions || [];
    return (
      <div className="step-stack">
        <label>Time per question (s)
          <input type="number" value={cfg.time_per_question_s || 15}
                  onChange={(e) => setCfg("time_per_question_s", parseInt(e.target.value))} />
        </label>
        <label>Min correct to win
          <input type="number" value={cfg.min_correct_to_win || 1}
                  onChange={(e) => setCfg("min_correct_to_win", parseInt(e.target.value))} />
        </label>
        {qs.map((q, i) => (
          <div className="quiz-q-builder" key={i}>
            <strong className="mono">Q{i + 1}</strong>
            <input value={q.prompt}
                    onChange={(e) => {
                      const nq = [...qs]; nq[i] = { ...q, prompt: e.target.value };
                      setCfg("questions", nq);
                    }} placeholder="Prompt"
                    data-testid={`quizq-${i}-prompt`} />
            {(q.options || ["", "", "", ""]).map((opt, j) => (
              <div className="row" key={j}>
                <input type="radio"
                        checked={q.correct_idx === j}
                        onChange={() => {
                          const nq = [...qs]; nq[i] = { ...q, correct_idx: j };
                          setCfg("questions", nq);
                        }} />
                <input value={opt}
                        onChange={(e) => {
                          const nq = [...qs];
                          const nop = [...(q.options || ["", "", "", ""])];
                          nop[j] = e.target.value;
                          nq[i] = { ...q, options: nop };
                          setCfg("questions", nq);
                        }} placeholder={`Option ${String.fromCharCode(65 + j)}`} />
              </div>
            ))}
            <button onClick={() => setCfg("questions", qs.filter((_, k) => k !== i))}
                      className="btn-ghost"><X size={11} /> remove</button>
          </div>
        ))}
        <button onClick={() => setCfg("questions",
                                                [...qs, { prompt: "", options: ["", "", "", ""], correct_idx: 0 }])}
                  className="btn-ghost" data-testid="add-question-btn">
          <Plus size={11} /> Add question
        </button>
      </div>
    );
  }
  if (tpl.game_type === "scratch_card") {
    return (
      <div className="step-stack">
        <label>Scratch threshold (0-1)
          <input type="number" step="0.05" min="0.2" max="0.9"
                  value={cfg.scratch_threshold || 0.5}
                  onChange={(e) => setCfg("scratch_threshold", parseFloat(e.target.value))} />
        </label>
        <p className="dim">Foil cover + reveal background images use defaults in 8a; image upload comes in 8b.</p>
      </div>
    );
  }
  if (tpl.game_type === "mystery_box") {
    return (
      <div className="step-stack">
        <label>Number of boxes (3-9)
          <input type="number" min="3" max="9"
                  value={cfg.num_boxes || 3}
                  onChange={(e) => setCfg("num_boxes", parseInt(e.target.value))} />
        </label>
        <p className="dim">Box labels default to "Box 1..N". Custom labels + images coming in 8b.</p>
      </div>
    );
  }
  return null;
}

function PrizesStep({ draft, setDraft, weightSum, tpl }) {
  const prizes = draft.prizes || [];
  const set = (i, key, val) => {
    const np = [...prizes];
    np[i] = { ...np[i], [key]: val };
    setDraft({ ...draft, prizes: np });
  };
  const remove = (i) => setDraft({ ...draft, prizes: prizes.filter((_, j) => j !== i) });
  const add = () => setDraft({
    ...draft, prizes: [...prizes, {
      title: "", prize_type: "bigcoin", value_amount: 0,
      probability_weight: 0, inventory_total: 100,
      max_per_user: 0, redemption_method: "in_app_wallet",
    }]
  });
  return (
    <div className="step-stack">
      <div className={`weights-pill mono ${weightSum === 100 ? "ok" : "bad"}`}
              data-testid="weights-sum">
        Probability weights sum: <b>{weightSum}</b> / 100
        {weightSum !== 100 && (
          <span style={{ marginLeft: 10, opacity: 0.75 }}>
            (Next is disabled until sum = 100)
          </span>
        )}
      </div>
      <div className="mono dim" style={{ fontSize: "0.66rem", marginTop: -6 }}>
        Tip: weight 0 = inactive (won't be drawn). Use for placeholder prizes.
      </div>
      {tpl && <div className="mono dim">
        {tpl.name} accepts {tpl.min_prizes}-{tpl.max_prizes} prizes.
      </div>}
      {prizes.map((p, i) => (
        <div className="prize-row" key={i} data-testid={`prize-row-${i}`}>
          <input value={p.title}
                  onChange={(e) => set(i, "title", e.target.value)}
                  placeholder="Prize title"
                  data-testid={`prize-${i}-title`} />
          <select value={p.prize_type}
                    onChange={(e) => set(i, "prize_type", e.target.value)}
                    data-testid={`prize-${i}-type`}>
            <option value="bigcoin">BigPoints</option>
            <option value="coupon">Coupon</option>
            <option value="gift_card">Gift card</option>
            <option value="free_item">Free item</option>
            <option value="sample">Sample</option>
            <option value="ticket_entry">Ticket entry</option>
            <option value="badge">Badge</option>
            <option value="exclusive_unlock">Exclusive unlock</option>
            <option value="premium_credit_days">Premium days</option>
            <option value="sponsor_collectible">Collectible</option>
          </select>
          <input type="number" value={p.value_amount}
                  onChange={(e) => set(i, "value_amount", parseInt(e.target.value))}
                  placeholder="Value"
                  data-testid={`prize-${i}-value`} />
          <input type="number" value={p.probability_weight}
                  onChange={(e) => set(i, "probability_weight", parseInt(e.target.value))}
                  placeholder="Weight"
                  data-testid={`prize-${i}-weight`} />
          <input type="number" value={p.inventory_total}
                  onChange={(e) => set(i, "inventory_total", parseInt(e.target.value))}
                  placeholder="Inventory"
                  data-testid={`prize-${i}-inv`} />
          {/* Phase 9c — link a coupon-type prize to a real Offer so the
              award flow knows which physical offer to consume. */}
          {p.prize_type === "coupon" && (
            <LinkedOfferSelect
              value={p.linked_offer_id || ""}
              onChange={(v) => set(i, "linked_offer_id", v || null)}
              testId={`prize-${i}-linked-offer`} />
          )}          <select value={p.redemption_method}
                    onChange={(e) => set(i, "redemption_method", e.target.value)}>
            <option value="in_app_wallet">In-app wallet</option>
            <option value="qr_code">QR code</option>
            <option value="promo_code">Promo code</option>
            <option value="sms_link">SMS link</option>
            <option value="partner_pos">Partner POS</option>
          </select>
          <button onClick={() => remove(i)} className="btn-ghost"><X size={11} /></button>
        </div>
      ))}
      <button onClick={add} className="btn-ghost" data-testid="add-prize-btn">
        <Plus size={11} /> Add prize
      </button>
    </div>
  );
}


// Phase 23 Session 8a — CouponToolsTemplateField removed.  Wins use
// internal coupons only.  Schema fields on game_campaigns
// (coupontools_template_id) and user_wallet_items (coupontools_*)
// are kept nullable for backwards compat but never read/written.

function TargetingStep({ draft, setDraft }) {
  const t = draft.targeting_json || {};
  const set = (k, v) => setDraft({ ...draft, targeting_json: { ...t, [k]: v } });
  return (
    <div className="step-stack">
      <div className="row">
        <label>City <input value={t.city || ""}
                                onChange={(e) => set("city", e.target.value)}
                                placeholder="dubai" data-testid="target-city" /></label>
        <label>Channel <input value={t.channel || ""}
                                    onChange={(e) => set("channel", e.target.value)}
                                    placeholder="bollywood_mehfil" data-testid="target-channel" /></label>
      </div>
      <div className="row">
        <label>Mood <input value={t.mood || ""}
                                onChange={(e) => set("mood", e.target.value)}
                                placeholder="chill" /></label>
        <label>Daypart <input value={t.daypart || ""}
                                  onChange={(e) => set("daypart", e.target.value)}
                                  placeholder="evening_drive" /></label>
      </div>
      <div className="dim">
        <AlertTriangle size={11} /> Route corridor + weather targeting available with Phase 9 (Maps).
      </div>
      <label className="row" style={{ alignItems: "center" }}>
        <input type="checkbox" checked={draft.open_to_all !== false}
                onChange={(e) => setDraft({ ...draft, open_to_all: e.target.checked })}
                data-testid="target-open-toggle" />
        <span>Open to all listeners (no milestone unlock required)</span>
      </label>
    </div>
  );
}

function ComplianceStep({ draft, setDraft }) {
  const c = draft.compliance || {};
  const set = (k, v) => setDraft({ ...draft, compliance: { ...c, [k]: v } });
  return (
    <div className="step-stack">
      <label>Terms & conditions
        <textarea value={c.terms_text || ""} rows={4}
                      onChange={(e) => set("terms_text", e.target.value)}
                      placeholder="Standard sponsor terms apply…"
                      data-testid="comp-terms" />
      </label>
      <label>Odds disclosure
        <input value={c.odds_disclosure || ""}
                onChange={(e) => set("odds_disclosure", e.target.value)}
                placeholder="Odds: 1 in 10"
                data-testid="comp-odds" />
      </label>
      <label>No-purchase-necessary text
        <input value={c.no_purchase_necessary_text || ""}
                onChange={(e) => set("no_purchase_necessary_text", e.target.value)}
                placeholder="No purchase necessary; void where prohibited."
                data-testid="comp-npn" />
      </label>
      <label>Age restriction (optional)
        <input type="number" value={c.age_restriction || ""}
                onChange={(e) => set("age_restriction", parseInt(e.target.value) || null)}
                placeholder="18" data-testid="comp-age" />
      </label>
    </div>
  );
}

function BudgetStep({ draft, setDraft }) {
  return (
    <div className="step-stack">
      <label>Objective
        <select value={draft.objective}
                  onChange={(e) => setDraft({ ...draft, objective: e.target.value })}>
          <option value="listener_engagement">Listener engagement</option>
          <option value="coupon_save">Coupon saves</option>
          <option value="drive_visit">Drive in-store visits</option>
          <option value="brand_awareness">Brand awareness</option>
          <option value="lead_generation">Lead generation</option>
          <option value="app_install">App installs</option>
        </select>
      </label>
      <label>Bid type
        <select value={draft.bid_type}
                  onChange={(e) => setDraft({ ...draft, bid_type: e.target.value })}>
          <option value="per_save">Per save</option>
          <option value="per_play">Per play</option>
          <option value="per_win">Per win</option>
          <option value="per_redemption">Per redemption</option>
          <option value="flat">Flat fee</option>
        </select>
      </label>
      <label>Bid amount (cents)
        <input type="number" value={draft.bid_amount_cents}
                onChange={(e) => setDraft({ ...draft, bid_amount_cents: parseInt(e.target.value) })} />
      </label>
      <label>Total budget (cents — optional)
        <input type="number" value={draft.budget_cents || ""}
                onChange={(e) => setDraft({ ...draft, budget_cents: parseInt(e.target.value) || null })} />
      </label>
      <div className="row">
        <label>Start <input type="datetime-local"
                                value={draft.start_at || ""}
                                onChange={(e) => setDraft({ ...draft, start_at: e.target.value })} /></label>
        <label>End <input type="datetime-local"
                              value={draft.end_at || ""}
                              onChange={(e) => setDraft({ ...draft, end_at: e.target.value })} /></label>
      </div>
    </div>
  );
}

// Phase 23 Session 3 — Placement & Rules step exposes the 4 wizard
// columns shipped in Session 2 backend (placement_rules_json,
// eligibility_rules_json, win_rules_json + creator_type display).
function PlacementRulesStep({ draft, setDraft, isAdminCreator }) {
  const pr  = draft.placement_rules_json  || {};
  const er  = draft.eligibility_rules_json || {};
  const wr  = draft.win_rules_json              || {};
  const setPR = (k, v) => setDraft({
    ...draft, placement_rules_json: { ...pr, [k]: v } });
  const setER = (k, v) => setDraft({
    ...draft, eligibility_rules_json: { ...er, [k]: v } });
  const setWR = (k, v) => setDraft({
    ...draft, win_rules_json: { ...wr, [k]: v } });

  const locations = Array.isArray(pr.locations) ? pr.locations : [];
  const toggleLoc = (loc) => {
    const has = locations.includes(loc);
    setPR("locations", has ? locations.filter((l) => l !== loc)
                                          : [...locations, loc]);
  };
  const LOC_OPTIONS = [
    ["play_and_win_tab", "Play & Win tab"],
    ["post_listening",      "After listening session"],
    ["during_ad",            "During ad slot"],
    ["channel_intermission", "Channel intermission"],
    ["share_link",            "Shareable QR / link"],
  ];

  return (
    <div className="step-stack" data-testid="placement-rules-step">
      <div className="mono dim" style={{marginBottom: 6}}>
        Creator type: <b>{draft.creator_type || "advertiser"}</b>
        {isAdminCreator && (
          <span data-testid="creator-type-admin-pill"
                  style={{marginLeft: 8, padding: "2px 8px", borderRadius: 999,
                              background: "rgba(245,158,11,0.15)",
                              color: "#fbbf24", fontSize: 11}}>
            admin · auto-publishes on submit
          </span>
        )}
      </div>

      <h3 className="mono">Where can listeners find this game?</h3>
      <div className="row" style={{flexWrap: "wrap", gap: 8}}>
        {LOC_OPTIONS.map(([val, label]) => (
          <label key={val}
                      className="row" style={{alignItems: "center"}}>
            <input type="checkbox"
                          checked={locations.includes(val)}
                          onChange={() => toggleLoc(val)}
                          data-testid={`place-loc-${val}`} />
            <span style={{marginLeft: 4}}>{label}</span>
          </label>
        ))}
      </div>

      <h3 className="mono" style={{marginTop: 14}}>Eligibility rules</h3>
      <div className="row">
        <label>Min listening time before unlock (minutes)
          <input type="number" min="0" max="120"
                  value={er.min_listening_minutes ?? 0}
                  onChange={(e) => setER("min_listening_minutes",
                                                          parseInt(e.target.value) || 0)}
                  data-testid="elig-min-min" />
        </label>
        <label className="row" style={{alignItems: "center"}}>
          <input type="checkbox"
                          checked={er.open_to_premium_only === true}
                          onChange={(e) => setER("open_to_premium_only",
                                                                  e.target.checked)}
                          data-testid="elig-premium-only" />
          <span style={{marginLeft: 4}}>Premium subscribers only</span>
        </label>
      </div>
      <label className="row" style={{alignItems: "center"}}>
        <input type="checkbox"
                      checked={er.requires_lead_capture === true}
                      onChange={(e) => setER("requires_lead_capture",
                                                              e.target.checked)}
                      data-testid="elig-lead-capture" />
        <span style={{marginLeft: 4}}>
          Require lead capture form before play (uses Phase 8c lead step)
        </span>
      </label>

      <h3 className="mono" style={{marginTop: 14}}>Win rules</h3>
      <div className="row">
        <label>Max wins per user
          <input type="number" min="0" max="999"
                  value={wr.max_wins_per_user ?? 1}
                  onChange={(e) => setWR("max_wins_per_user",
                                                          parseInt(e.target.value) || 0)}
                  data-testid="win-max-per-user" />
        </label>
        <label>Max plays / user / day
          <input type="number" min="0" max="50"
                  value={wr.max_plays_per_user_per_day ?? 3}
                  onChange={(e) => setWR("max_plays_per_user_per_day",
                                                          parseInt(e.target.value) || 0)}
                  data-testid="win-max-plays" />
        </label>
        <label>Cooldown between plays (min)
          <input type="number" min="0" max="1440"
                  value={wr.cooldown_minutes ?? 0}
                  onChange={(e) => setWR("cooldown_minutes",
                                                          parseInt(e.target.value) || 0)}
                  data-testid="win-cooldown" />
        </label>
      </div>
      <label className="row" style={{alignItems: "center"}}>
        <input type="checkbox"
                      checked={wr.win_announce_rj !== false}
                      onChange={(e) => setWR("win_announce_rj",
                                                              e.target.checked)}
                      data-testid="win-announce-rj" />
        <span style={{marginLeft: 4}}>
          Let the AI RJ shout out winners on-air
        </span>
      </label>
    </div>
  );
}

function ReviewStep({ draft, tpl, weightSum }) {
  return (
    <div className="review-step" data-testid="review-step">
      <h2>{draft.title || "(no title)"}</h2>
      <p className="dim">{draft.sponsor_name} · {tpl?.name}</p>
      <div className="review-grid">
        <div><span className="mono dim">Prizes</span>
          <ul className="review-prizes">
            {draft.prizes.map((p, i) => (
              <li key={i}>{p.title} ({p.prize_type}, {p.probability_weight}%)</li>
            ))}
          </ul>
        </div>
        <div>
          <span className="mono dim">Weights sum</span>
          <p className={weightSum === 100 ? "ok" : "bad"}>{weightSum}/100</p>
          <span className="mono dim">Targeting</span>
          <p>{Object.values(draft.targeting_json || {}).filter(Boolean).join(" · ") || "open"}</p>
          <span className="mono dim">Compliance</span>
          <p>{draft.compliance.terms_text ? "✓ terms" : "⚠ terms missing"} ·
              {draft.compliance.odds_disclosure ? " ✓ odds" : " ⚠ odds missing"} ·
              {draft.compliance.no_purchase_necessary_text ? " ✓ NPN" : " ⚠ NPN missing"}</p>
        </div>
      </div>
      <h3>Live preview</h3>
      <div className="review-preview" data-testid="wizard-preview">
        {tpl?.game_type === "spin_wheel" && (
          <SpinWheel config={draft.game_config_json} onSubmit={() => {}} submitting={false} result={null} brand={draft.brand_colors_json?.primary} />
        )}
        {tpl?.game_type === "quiz" && (
          <Quiz config={draft.game_config_json} onSubmit={() => {}} submitting={false} result={null} brand={draft.brand_colors_json?.primary} />
        )}
        {tpl?.game_type === "scratch_card" && (
          <ScratchCard config={draft.game_config_json} onSubmit={() => {}} submitting={false} result={null} brand={draft.brand_colors_json?.primary} />
        )}
        {tpl?.game_type === "mystery_box" && (
          <MysteryBox config={draft.game_config_json} onSubmit={() => {}} submitting={false} result={null} brand={draft.brand_colors_json?.primary} />
        )}
      </div>
    </div>
  );
}

// Phase 9c — Lookup the partner's owned businesses' offers and let the
// game-prize editor link a coupon-type prize to a real Offer row.  When
// linked, awarding this prize will mint a coupon against the linked
// offer at fulfilment time (linked_offer_id on the prize doc).
function LinkedOfferSelect({ value, onChange, testId }) {
  const [offers, setOffers] = useState([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    (async () => {
      try {
        const bizR = await axios.get(`${API}/partner/businesses/me`);
        const bizes = bizR.data.items || [];
        const all = [];
        for (const b of bizes) {
          try {
            const oR = await axios.get(
              `${API}/partner/businesses/${b.business_id}/offers`);
            (oR.data.items || []).forEach((o) => {
              if (o.status === "active" || o.status === "draft") {
                all.push({ ...o, business_name: b.name });
              }
            });
          } catch { /* ignore */ }
        }
        setOffers(all);
      } catch { /* not a partner */ }
      finally { setLoading(false); }
    })();
  }, []);
  return (
    <select className="prize-linked-offer"
              data-testid={testId}
              value={value || ""}
              onChange={(e) => onChange(e.target.value)}
              style={{ gridColumn: "1 / -1", marginTop: 4 }}>
      <option value="">Link to Offer… (optional)</option>
      {loading
        ? <option disabled>Loading…</option>
        : offers.length === 0
          ? <option disabled>No offers yet — create one in /partner</option>
          : offers.map((o) => (
              <option key={o.offer_id} value={o.offer_id}>
                {o.title} ({o.business_name}) · {o.status}
              </option>
            ))}
    </select>
  );
}

