// Sub-Phase E2 — Predict & Win consumer page.
//
// Single-file SPA shell with 3 sub-tabs (Active / My Picks / Won
// Rewards) + an Enter modal.  Listeners discover live campaigns, make
// picks before lock, and view their wins.

/* eslint-disable react-hooks/set-state-in-effect */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { Toaster, toast } from "sonner";
import {
  Trophy, Sparkles, Clock, Gift, Check, X, Loader2,
  ShieldCheck, AlertTriangle, ChevronRight, Wallet,
  Award, Star, Globe2,
} from "lucide-react";
// Phase 42-E1.1 — persistent banner ad in the Predict & Win consumer list.
import PersistentBannerSlot from "@/components/PersistentBannerSlot";
// Phase 42-E2.2 — Universal share on each Predict & Win active card.
import ShareButton from "@/components/ShareButton";
// Phase AD.11 — games banner zone.
import BannerZoneSlot from "@/components/BannerZoneSlot";
// Phase AD.3 — sponsor badge for Predict & Win cards + detail.
import PredictWinSponsorBadge from "@/components/PredictWinSponsorBadge";

const API = process.env.REACT_APP_BACKEND_URL;
// Phase PDX.1 hotfix — `REACT_APP_BACKEND_URL` is the bare origin
// (no `/api` suffix); the AuthContext.js re-export adds `/api`, but
// this file reads from the env var directly.  Earlier "E1.4 hotfix"
// comment above claimed the opposite, dropped the `/api` prefix and
// silently broke every `${PW}/…` call on the consumer page.  Restored.
const PW = `${API}/api/predict-win`;

function api(method, url, body) {
  return axios({ method, url, data: body, withCredentials: true })
    .then((r) => r.data)
    .catch((err) => {
      const detail = err?.response?.data?.detail;
      const msg = typeof detail === "string" ? detail
                              : detail?.message || err.message;
      const wrapped = new Error(msg || "Request failed");
      wrapped.detail = detail;
      wrapped.status = err?.response?.status;
      throw wrapped;
    });
}

function useCountdown(targetIso) {
  const [secs, setSecs] = useState(() =>
    targetIso ? Math.max(0,
      Math.floor((new Date(targetIso).getTime() - Date.now()) / 1000)) : 0);
  useEffect(() => {
    if (!targetIso) return;
    const tick = () => setSecs(Math.max(0,
      Math.floor((new Date(targetIso).getTime() - Date.now()) / 1000)));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [targetIso]);
  return secs;
}

function fmtCountdown(secs) {
  if (secs <= 0) return "Locked";
  const d = Math.floor(secs / 86400);
  const h = Math.floor((secs - d * 86400) / 3600);
  const m = Math.floor((secs - d * 86400 - h * 3600) / 60);
  const s = secs - d * 86400 - h * 3600 - m * 60;
  if (d > 0) return `${d}d ${h}h ${m}m`;
  if (h > 0) return `${h}h ${m}m ${s}s`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

const ENTRY_STATUS_META = {
  submitted: { label: "Locked in", color: "#3b82f6", icon: Clock },
  winner:        { label: "Won",                color: "#22c55e", icon: Trophy },
  loser:          { label: "Not this time", color: "var(--text-secondary)", icon: X },
  void:            { label: "Withdrawn", color: "#a1a1aa", icon: X },
};


// ─── Page shell ──────────────────────────────────────────────────────
export default function PredictWin() {
  const navigate = useNavigate();
  const [tab, setTab] = useState("active");
  const [enterModal, setEnterModal] = useState(null);  // campaign_id

  return (
    <div data-testid="predict-win-consumer-page"
            style={{ minHeight: "100vh", background: "var(--bg-base)",
                        color: "var(--text-primary)" }}>
      <Toaster theme="dark" position="bottom-right" richColors />
      <div style={{ maxWidth: 980, margin: "0 auto", padding: 24 }}>
        <div style={{ display: "flex", alignItems: "center",
                            gap: 12, marginBottom: 20 }}>
          <div style={{ width: 44, height: 44,
                              background: "linear-gradient(135deg,#22d3ee,#0ea5e9)",
                              borderRadius: 12,
                              display: "flex", alignItems: "center",
                              justifyContent: "center" }}>
            <Trophy size={22} color="#0a0a0c" />
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 11, color: "var(--text-secondary)",
                                letterSpacing: 0.8 }}>
              SUB-PHASE E2 · COMMUNITY PREDICTIONS
            </div>
            <h1 style={{ margin: "2px 0 0", fontSize: 24, color: "var(--text-primary)" }}>
              Predict &amp; Win
            </h1>
          </div>
        </div>
        <p style={{ fontSize: 12, color: "var(--text-secondary)",
                          marginBottom: 18, maxWidth: 700 }}>
          Free community predictions.  Make your pick before the lock,
          and if you&apos;re right you&apos;ll win prizes from the campaign sponsor.
          No purchase necessary — all entries are free.
        </p>

        {/* Phase 42-E1.1 — persistent banner ad slot for the PW list. */}
        <div style={{ display: "flex", justifyContent: "center",
                                    marginBottom: 14 }}>
          <PersistentBannerSlot placement="predict_win_list" />
        </div>

        {/* Phase AD.11 — games banner zone (970×250 leaderboard). */}
        <BannerZoneSlot zone="games" />

        {/* ─── Sub-tabs ───────────────────────── */}
        <div style={{ display: "flex", gap: 4, marginBottom: 18,
                            borderBottom: "1px solid var(--line)" }}
                data-testid="pw-subnav">
          {[
            { value: "active",  label: "Active",                  testid: "subtab-active" },
            { value: "picks",    label: "My Picks",              testid: "subtab-picks" },
            { value: "wins",      label: "Won Rewards", testid: "subtab-wins" },
          ].map((t) => (
            <button key={t.value}
                          onClick={() => setTab(t.value)}
                          data-testid={t.testid}
                          style={{
                            padding: "10px 14px", background: "transparent",
                            border: "none",
                            borderBottom: tab === t.value
                              ? "2px solid #22d3ee" : "2px solid transparent",
                            fontSize: 13, fontWeight: 600,
                            color: tab === t.value ? "#22d3ee" : "var(--text-secondary)",
                            cursor: "pointer",
                          }}>
              {t.label}            </button>
          ))}
        </div>

        {tab === "active" && <ActiveTab onPick={setEnterModal} />}
        {tab === "picks" && <MyPicksTab />}
        {tab === "wins" && <WonRewardsTab />}
      </div>

      {enterModal && (
        <EnterModal campaignId={enterModal}
                                onClose={() => setEnterModal(null)}
                                onSubmitted={() => {
                                  setEnterModal(null);
                                  setTab("picks");
                                }} />
      )}
    </div>
  );
}


// ─── Active tab ──────────────────────────────────────────────────────
// Phase PDX.1 — category chip row + points_reward badge per card.
const PDX_CAT_META = {
  sports_top:         { label: "Sports",         color: "#22d3ee" },
  stocks_top:         { label: "Stocks",         color: "#22c55e" },
  us_politics:        { label: "US Politics", color: "#a855f7" },
  national_games: { label: "Games",           color: "#f59e0b" },
};

function ActiveTab({ onPick }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [categories, setCategories] = useState([]);
  const [catFilter, setCatFilter] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const url = catFilter
        ? `${PW}/active?limit=30&category_slug=${catFilter}`
        : `${PW}/active?limit=30`;
      const r = await api("GET", url);
      setItems(r.items);
    } catch (e) { toast.error(e.message || "Failed to load"); }
    finally { setLoading(false); }
  }, [catFilter]);
  useEffect(() => { load(); }, [load]);

  // Fetch category chip metadata once.  Silent-fail — the chip row
  // just doesn't render if the fetch fails.
  useEffect(() => {
    (async () => {
      try {
        const r = await api("GET", `${PW}/categories`);
        setCategories(r.items || []);
      } catch { /* ignore */ }
    })();
  }, []);

  return (
    <>
      {categories.length > 0 && (
        <div data-testid="pw-category-chips"
                  style={{ display: "flex", flexWrap: "wrap", gap: 6,
                                    marginBottom: 14 }}>
          <button data-testid="pw-cat-chip-all"
                          onClick={() => setCatFilter("")}
                          style={pdxChipStyle(catFilter === "", "var(--text-primary)")}>
            All
          </button>
          {categories.map((c) => {
            const meta = PDX_CAT_META[c.slug] || { color: "var(--text-secondary)" };
            const active = catFilter === c.slug;
            return (
              <button key={c.slug}
                            data-testid={`pw-cat-chip-${c.slug}`}
                            onClick={() => setCatFilter(active ? "" : c.slug)}
                            style={pdxChipStyle(active, meta.color)}>
                {c.display_name}
              </button>
            );
          })}
        </div>
      )}
      {loading ? (
        <div style={emptyStyle}><Loader2 size={20} className="spin" /></div>
      ) : items.length === 0 ? (
        <div data-testid="active-empty" style={emptyStyle}>
          <Sparkles size={20} style={{ marginBottom: 8 }} />
          <div style={{ fontSize: 13 }}>
            {catFilter ? "No predictions in this category right now."
                                  : "No live predictions right now. Check back soon."}
          </div>
        </div>
      ) : (
        <div data-testid="active-list"
                  style={{ display: "grid",
                                    gridTemplateColumns: "repeat(auto-fill, minmax(310px, 1fr))",
                                    gap: 12 }}>
          {items.map((c) => <ActiveCard key={c.campaign_id}
                                                                                campaign={c}
                                                                                onPick={onPick} />)}
        </div>
      )}
    </>
  );
}

function pdxChipStyle(active, color) {
  return {
    fontSize: 11, fontWeight: 600, letterSpacing: 0.4,
    padding: "6px 12px", borderRadius: 999, cursor: "pointer",
    border: `1px solid ${active ? color : "var(--line)"}`,
    background: active ? `color-mix(in srgb, ${color} 14%, transparent)` : "transparent",
    color: active ? color : "var(--text-secondary)",
    transition: "background 120ms ease, color 120ms ease",
  };
}


function ActiveCard({ campaign, onPick }) {
  const remaining = useCountdown(campaign.lock_time);
  const e = campaign.eligibility || {};
  return (
    <div data-testid={`active-card-${campaign.campaign_id}`}
            style={{
              background: "var(--bg-elevated)",
              border: "1px solid var(--line)",
              borderRadius: 12, padding: 16,
              display: "flex", flexDirection: "column", gap: 8,
              position: "relative",
            }}>
      {/* Phase AD.3 — sponsor chip in top-right corner if a sponsor won the auction. */}
      <PredictWinSponsorBadge parentCampaignId={campaign.campaign_id}
                                                              variant="card" />
      <div style={{ display: "flex", gap: 6, alignItems: "center",
                          marginBottom: 4, flexWrap: "wrap" }}>
        <span style={eventPillStyle(campaign.event_type)}>
          {campaign.event_type.replace(/_/g, " ").toUpperCase()}
        </span>
        {campaign.category_slug && PDX_CAT_META[campaign.category_slug] && (
          <span data-testid={`active-card-cat-${campaign.campaign_id}`}
                        style={{ fontSize: 9, fontWeight: 700,
                                          padding: "3px 8px", borderRadius: 999,
                                          letterSpacing: 0.6, textTransform: "uppercase",
                                          background: `${PDX_CAT_META[campaign.category_slug].color}22`,
                                          color: PDX_CAT_META[campaign.category_slug].color }}>
            {PDX_CAT_META[campaign.category_slug].label}
          </span>
        )}
        {campaign.points_reward > 0 && (
          <span data-testid={`active-card-points-${campaign.campaign_id}`}
                        style={{ marginLeft: "auto",
                                          fontSize: 11, fontWeight: 700,
                                          padding: "2px 8px", borderRadius: 999,
                                          background: "linear-gradient(135deg,#a855f7,#ec4899)",
                                          color: "#0a0a0c" }}>
            +{campaign.points_reward} pts
          </span>
        )}
        {campaign.city && (
          <span style={{ fontSize: 10, color: "var(--text-secondary)" }}>
            · {campaign.city}
          </span>
        )}
      </div>
      <div style={{ fontSize: 15, color: "var(--text-primary)", fontWeight: 700 }}>
        {campaign.title}
      </div>
      {campaign.question_prompt && (
        <div style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 4 }}>
          {campaign.question_prompt}
        </div>
      )}
      {campaign.prize && (
        <div data-testid={`active-card-prize-${campaign.campaign_id}`}
                style={{ display: "flex", gap: 6, alignItems: "center",
                            background: "rgba(34,197,94,0.08)",
                            border: "1px solid rgba(34,197,94,0.25)",
                            borderRadius: 6, padding: "6px 10px" }}>
          <Gift size={12} color="#22c55e" />
          <span style={{ fontSize: 12, color: "#86efac", fontWeight: 600 }}>
            Prize: {campaign.prize.title}
            {campaign.prize.value_amount
              ? ` (${campaign.prize.value_amount} ${campaign.prize.value_currency || ""})`
              : ""}
          </span>
        </div>
      )}
      <div data-testid={`active-card-lock-${campaign.campaign_id}`}
              style={{ display: "flex", gap: 6, alignItems: "center",
                          fontSize: 12,
                          color: remaining > 600 ? "var(--text-secondary)" : "#fbbf24" }}>
        <Clock size={12} />
        {remaining > 0
          ? <>Picks close in <strong>{fmtCountdown(remaining)}</strong></>
          : <>Picks are closed</>}
      </div>
      {campaign.checkin_required && (
        <div style={{ fontSize: 10, color: "#fb923c" }}>
          <AlertTriangle size={10}
            style={{ verticalAlign: -1, marginRight: 2 }} />
          Check-in required at the venue to enter.
        </div>
      )}
      <div data-testid={`active-card-disclaimer-${campaign.campaign_id}`}
              style={{ fontSize: 10, color: "var(--text-secondary)" }}>
        <ShieldCheck size={9}
          style={{ verticalAlign: -1, marginRight: 2 }} />
        {campaign.no_purchase_necessary_text}{" "}
        <a href={`/predict-win/terms/${campaign.terms_settings_id}`}
            data-testid={`active-card-terms-${campaign.campaign_id}`}
            style={{ color: "#22d3ee", textDecoration: "underline" }}>
          Terms
        </a>
      </div>
      {campaign.user_has_entered ? (
        <button disabled
                    data-testid={`active-card-already-${campaign.campaign_id}`}
                    style={{ ...btnGhostStyle, opacity: 0.6 }}>
          <Check size={12} /> Pick locked in — see &quot;My Picks&quot;
        </button>
      ) : e.anonymous ? (
        <a href="/login"
            data-testid={`active-card-login-${campaign.campaign_id}`}
            style={{ ...btnPrimaryStyle, textAlign: "center",
                        textDecoration: "none" }}>
          <Sparkles size={12} /> Log in to pick
        </a>
      ) : e.can_enter ? (
        <button onClick={() => onPick(campaign.campaign_id)}
                    data-testid={`active-card-pick-${campaign.campaign_id}`}
                    style={btnPrimaryStyle}>
          <Sparkles size={12} /> Make your pick
        </button>
      ) : (
        <button disabled
                    data-testid={`active-card-blocked-${campaign.campaign_id}`}
                    style={{ ...btnGhostStyle, opacity: 0.6 }}
                    title={(e.block_reasons || []).join(", ")}>
          <X size={12} /> Not eligible
        </button>
      )}
      {/* Phase 42-E2.2 — share this Predict & Win campaign */}
      <div style={{ marginTop: 4, display: "flex", justifyContent: "flex-end" }}>
        <ShareButton
          compact
          featureType="predict_win"
          contentId={campaign.campaign_id}
          title={campaign.title}
          text={`I'm playing "${campaign.title}" on RadioLife — predict & win. Join me:`} />
      </div>
    </div>
  );
}


// ─── Enter modal ─────────────────────────────────────────────────────
function EnterModal({ campaignId, onClose, onSubmitted }) {
  const [detail, setDetail] = useState(null);
  const [picked, setPicked] = useState(null);
  const [confidence, setConfidence] = useState(5);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    api("GET", `${PW}/campaigns/${campaignId}`).then(setDetail)
      .catch((e) => { toast.error(e.message); onClose(); });
  }, [campaignId, onClose]);

  async function submit() {
    if (!picked) {
      toast.error("Pick an option first.");
      return;
    }
    setSubmitting(true);
    try {
      const r = await api("POST", `${PW}/campaigns/${campaignId}/enter`, {
        selected_option_id: picked,
        confidence,
        source_context: "app",
      });
      // Phase AD.3 — fire an entry impression for the active sponsor (if any).
      // Silent-on-error so a broken auction never blocks entry.
      try {
        const sp = await api("GET", `/predict-win/${campaignId}/active-sponsorship`);
        if (sp?.sponsorship?.sponsorship_id) {
          api("POST", `/predict-win/sponsorships/impression`, {
            sponsorship_id: sp.sponsorship.sponsorship_id,
            parent_campaign_id: campaignId,
            event_type: "entry",
          }).catch(() => {});
        }
      } catch (_e) { /* silent */ }
      toast.success(
        `Pick locked in!  Picks close in ${fmtCountdown(
            r.lock_seconds_remaining || 0)}.`);
      onSubmitted();
    } catch (e) {
      if (e.detail?.code === "already_entered") {
        toast.error("You've already submitted a pick for this prediction.");
      } else if (e.detail?.code === "entries_closed") {
        toast.error("Picks are closed for this prediction.");
      } else if (e.detail?.code === "geo_blocked") {
        toast.error("This prediction isn't available in your region.");
      } else if (e.detail?.code === "age_blocked") {
        toast.error("You don't meet the minimum age for this prediction.");
      } else {
        toast.error(e.message || "Submit failed");
      }
    } finally { setSubmitting(false); }
  }

  if (!detail) {
    return (
      <div style={backdropStyle} data-testid="enter-modal-backdrop">
        <div style={{ ...modalStyle, padding: 32, textAlign: "center" }}>
          <Loader2 size={20} className="spin" color="var(--text-secondary)" />
        </div>
      </div>
    );
  }

  const c = detail.campaign;
  const prize = detail.prizes?.[0];
  const dist = detail.option_pick_distribution;
  const compliance = detail.compliance_summary;

  return (
    <div style={backdropStyle}
            onClick={onClose}
            data-testid="enter-modal-backdrop">
      <div onClick={(e) => e.stopPropagation()}
              data-testid="enter-modal"
              style={modalStyle}>
        <div style={modalHeaderStyle}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 10, color: "var(--text-secondary)",
                                letterSpacing: 0.5 }}>
              {c.event_type.replace(/_/g, " ").toUpperCase()}
              {c.city ? ` · ${c.city}` : ""}
            </div>
            <h2 style={{ margin: "4px 0 0", color: "var(--text-primary)",
                                fontSize: 18, fontWeight: 700 }}>
              {c.title}
            </h2>
          </div>
          <button onClick={onClose} data-testid="enter-modal-close"
                      style={iconBtnStyle}><X size={16} /></button>
        </div>
        <div style={modalBodyStyle}>
          <div style={{ fontSize: 14, color: "var(--text-primary)",
                              marginBottom: 14, fontWeight: 600 }}>
            {c.question?.prompt}
          </div>
          {/* Phase AD.3 — active sponsor banner on the entry modal. */}
          <PredictWinSponsorBadge parentCampaignId={campaignId}
                                                                variant="detail" />
          <div data-testid="enter-modal-options"
                  style={{ display: "flex", flexDirection: "column",
                              gap: 8, marginBottom: 14 }}>
            {(c.question?.answer_options || []).map((o) => {
              const isSel = picked === o.option_id;
              const distRow = (dist || []).find(
                (d) => d.option_id === o.option_id);
              return (
                <button key={o.option_id}
                              onClick={() => setPicked(o.option_id)}
                              data-testid={`enter-option-${o.option_id}`}
                              style={{
                                background: isSel
                                  ? "rgba(34,211,238,0.10)" : "var(--bg-elevated)",
                                border: `1px solid ${isSel
                                  ? "#22d3ee" : "var(--line)"}`,
                                borderRadius: 8, padding: 12,
                                cursor: "pointer", color: "inherit",
                                textAlign: "left",
                                display: "flex", gap: 10, alignItems: "center",
                              }}>
                  <input type="radio" checked={isSel} readOnly
                              style={{ accentColor: "#22d3ee" }} />
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 13, color: "var(--text-primary)",
                                          fontWeight: 600 }}>
                      {o.label}
                    </div>
                    {distRow && (
                      <div style={{ fontSize: 10, color: "var(--text-secondary)",
                                            marginTop: 2 }}>
                        Community pick: {distRow.pct}% ({distRow.count})
                      </div>
                    )}
                  </div>
                </button>
              );
            })}
          </div>
          {dist === null && (
            <div data-testid="enter-modal-dist-hidden"
                    style={{ fontSize: 11, color: "var(--text-secondary)",
                                marginBottom: 14 }}>
              Community pick percentages will appear after picks close.
            </div>
          )}

          {prize && (
            <div data-testid="enter-modal-prize-summary"
                    style={{ background: "rgba(34,197,94,0.08)",
                                border: "1px solid rgba(34,197,94,0.25)",
                                borderRadius: 6, padding: 10,
                                marginBottom: 12 }}>
              <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <Gift size={12} color="#22c55e" />
                <span style={{ fontSize: 12, color: "#86efac",
                                          fontWeight: 600 }}>
                  Prize: {prize.title}
                  {prize.value_amount
                    ? ` (${prize.value_amount} ${prize.value_currency || ""})`
                    : ""}
                </span>
              </div>
              {prize.description && (
                <div style={{ fontSize: 11, color: "#86efac",
                                    marginTop: 4, opacity: 0.85 }}>
                  {prize.description}
                </div>
              )}
            </div>
          )}

          <Field label="Confidence (1–10) — helps break ties">
            <input type="range" min={1} max={10}
                        value={confidence}
                        onChange={(e) => setConfidence(parseInt(e.target.value))}
                        data-testid="enter-modal-confidence"
                        style={{ width: "100%", accentColor: "#22d3ee" }} />
            <div style={{ fontSize: 11, color: "var(--text-secondary)",
                                marginTop: 4, display: "flex",
                                justifyContent: "space-between" }}>
              <span>low</span>
              <strong style={{ color: "#22d3ee" }}>{confidence}</strong>
              <span>high</span>
            </div>
          </Field>

          <div data-testid="enter-modal-disclaimer"
                  style={{ fontSize: 10, color: "var(--text-secondary)",
                              borderTop: "1px solid var(--line)",
                              paddingTop: 10, marginTop: 14 }}>
            <ShieldCheck size={10}
              style={{ verticalAlign: -1, marginRight: 2 }} />
            {compliance?.no_purchase_necessary_text}{" "}
            <a href={`/predict-win/terms/${compliance?.settings_id}`}
                data-testid="enter-modal-terms-link"
                style={{ color: "#22d3ee", textDecoration: "underline" }}>
              Read full terms
            </a>
          </div>
        </div>
        <div style={modalFooterStyle}>
          <button onClick={onClose} style={btnGhostStyle}
                      data-testid="enter-modal-cancel">Cancel</button>
          <button onClick={submit} disabled={submitting || !picked}
                      data-testid="enter-modal-submit"
                      style={{ ...btnPrimaryStyle,
                                  opacity: (submitting || !picked) ? 0.6 : 1 }}>
            {submitting ? <Loader2 size={12} className="spin" /> : <Sparkles size={12} />}
            Lock in my pick
          </button>
        </div>
      </div>
    </div>
  );
}


// ─── My picks tab ────────────────────────────────────────────────────
function MyPicksTab() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("all");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api("GET",
        `${PW}/my-picks?status=${filter}&limit=50`);
      setItems(r.items);
    } catch (e) { toast.error(e.message || "Failed to load"); }
    finally { setLoading(false); }
  }, [filter]);
  useEffect(() => { load(); }, [load]);

  const filters = [
    { value: "all", label: "All" },
    { value: "submitted", label: "Locked in" },
    { value: "winner", label: "Won" },
    { value: "loser", label: "Not this time" },
    { value: "void", label: "Withdrawn" },
  ];

  return (
    <>
      <div style={{ display: "flex", gap: 6, marginBottom: 14,
                          flexWrap: "wrap" }} data-testid="picks-filter-row">
        {filters.map((f) => (
          <button key={f.value}
                        onClick={() => setFilter(f.value)}
                        data-testid={`picks-filter-${f.value}`}
                        style={{
                          padding: "5px 12px", borderRadius: 999,
                          border: `1px solid ${filter === f.value
                            ? "#22d3ee" : "var(--line)"}`,
                          background: filter === f.value
                            ? "rgba(34,211,238,0.10)" : "var(--bg-elevated)",
                          color: filter === f.value ? "#22d3ee" : "var(--text-secondary)",
                          fontSize: 11, fontWeight: 600, cursor: "pointer",
                          textTransform: "uppercase", letterSpacing: 0.4,
                        }}>
            {f.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div style={emptyStyle}><Loader2 size={20} className="spin" /></div>
      ) : items.length === 0 ? (
        <div data-testid="picks-empty" style={emptyStyle}>
          <Trophy size={20} style={{ marginBottom: 8 }} />
          <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>
            No picks yet.  Head to the <strong>Active</strong> tab and
            make your first pick.
          </div>
        </div>
      ) : (
        <div data-testid="picks-list"
                style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {items.map((it) => <PickRow key={it.entry.entry_id} item={it} />)}
        </div>
      )}
    </>
  );
}


function PickRow({ item }) {
  const e = item.entry;
  const c = item.campaign;
  const meta = ENTRY_STATUS_META[e.status] || ENTRY_STATUS_META.submitted;
  const Icon = meta.icon;
  return (
    <div data-testid={`pick-row-${e.entry_id}`}
            style={{ background: "var(--bg-elevated)",
                        border: "1px solid var(--line)",
                        borderRadius: 10, padding: 14,
                        display: "flex", gap: 12, alignItems: "flex-start" }}>
      <div style={{ width: 32, height: 32, borderRadius: 8,
                          background: `color-mix(in srgb, ${meta.color} 14%, transparent)`,
                          display: "flex", alignItems: "center",
                          justifyContent: "center", flexShrink: 0 }}>
        <Icon size={16} color={meta.color} />
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 13, color: "var(--text-primary)", fontWeight: 600 }}>
          {c.title}
        </div>
        {c.question_prompt && (
          <div style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 2 }}>
            {c.question_prompt}
          </div>
        )}
        <div style={{ fontSize: 10, color: "var(--text-secondary)", marginTop: 6,
                            display: "flex", gap: 6, alignItems: "center" }}>
          <span style={{ color: meta.color, fontWeight: 700,
                                  letterSpacing: 0.4, textTransform: "uppercase" }}>
            {meta.label}
          </span>
          {e.confidence && <span>· confidence {e.confidence}/10</span>}
          {e.submitted_at && <span>· {new Date(e.submitted_at)
            .toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}</span>}
        </div>
      </div>
      {item.award && (
        <a href="#"
            onClick={(e) => { e.preventDefault(); window.location.hash = "wins"; }}
            data-testid={`pick-row-wallet-${e.entry_id}`}
            style={{ ...btnGhostStyle, fontSize: 11,
                        textDecoration: "none", width: "auto",
                        flexShrink: 0, padding: "6px 10px" }}>
          <Wallet size={11} /> View
        </a>
      )}
    </div>
  );
}


// ─── Won rewards tab ─────────────────────────────────────────────────
function WonRewardsTab() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api("GET", `${PW}/my-wins?limit=50`);
      setItems(r.items);
    } catch (e) { toast.error(e.message || "Failed to load"); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  if (loading) {
    return <div style={emptyStyle}><Loader2 size={20} className="spin" /></div>;
  }
  if (items.length === 0) {
    return (
      <div data-testid="wins-empty" style={emptyStyle}>
        <Award size={20} style={{ marginBottom: 8 }} />
        <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>
          No wins yet.  Make picks in the <strong>Active</strong> tab —
          when a campaign resolves, your prizes show here.
        </div>
      </div>
    );
  }

  return (
    <div data-testid="wins-list"
            style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {items.map((it) => <WinCard key={it.entry.entry_id} item={it} />)}
    </div>
  );
}


function WinCard({ item }) {
  const c = item.campaign;
  const award = item.award;
  const prize = item.prize;
  const wallet = item.wallet_item;
  return (
    <div data-testid={`win-card-${item.entry.entry_id}`}
            style={{ background: "linear-gradient(135deg, rgba(34,197,94,0.10), rgba(22,163,74,0.05))",
                        border: "1px solid rgba(34,197,94,0.30)",
                        borderRadius: 12, padding: 16,
                        display: "flex", gap: 12, alignItems: "flex-start" }}>
      <div style={{ width: 48, height: 48, borderRadius: 12,
                          background: "rgba(34,197,94,0.15)",
                          display: "flex", alignItems: "center",
                          justifyContent: "center", flexShrink: 0 }}>
        <Trophy size={22} color="#22c55e" />
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: 0.6,
                            color: "#22c55e", textTransform: "uppercase" }}>
          You won
        </div>
        {prize && (
          <div data-testid={`win-card-prize-${item.entry.entry_id}`}
                  style={{ fontSize: 16, color: "var(--text-primary)",
                              fontWeight: 700, marginTop: 2 }}>
            {prize.title}
            {prize.value_amount && (
              <span style={{ marginLeft: 6, color: "#86efac",
                                          fontWeight: 600, fontSize: 14 }}>
                ({prize.value_amount} {prize.value_currency || ""})
              </span>
            )}
          </div>
        )}
        {prize?.description && (
          <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 4 }}>
            {prize.description}
          </div>
        )}
        <div style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 8,
                            display: "flex", gap: 6, alignItems: "center",
                            flexWrap: "wrap" }}>
          <span>from <strong style={{ color: "var(--text-primary)" }}>{c.title}</strong></span>
          {award?.awarded_at && (
            <span>· {new Date(award.awarded_at).toLocaleDateString()}</span>
          )}
          <span data-testid={`win-card-delivery-${item.entry.entry_id}`}
                  style={{ background: award?.delivery_status === "delivered"
                              ? "rgba(34,197,94,0.15)" : "rgba(251,191,36,0.15)",
                              color: award?.delivery_status === "delivered"
                                ? "#22c55e" : "#fbbf24",
                              padding: "2px 8px", borderRadius: 999,
                              fontWeight: 700, fontSize: 9,
                              letterSpacing: 0.5, textTransform: "uppercase" }}>
            {award?.delivery_status === "delivered"
              ? "Credited"
              : award?.delivery_status === "in_wallet"
                ? "In your wallet"
                : award?.delivery_status || "pending"}
          </span>
        </div>
        {wallet && (
          <a href="/wallet/items"
              data-testid={`win-card-wallet-link-${item.entry.entry_id}`}
              style={{ display: "inline-flex", gap: 4, alignItems: "center",
                          marginTop: 8, fontSize: 11, color: "#22d3ee",
                          textDecoration: "underline" }}>
            <Wallet size={11} /> View in wallet
          </a>
        )}
      </div>
    </div>
  );
}


// ─── Helpers ─────────────────────────────────────────────────────────
function Field({ label, children }) {
  return (
    <label style={{ fontSize: 11, color: "var(--text-secondary)",
                          display: "block", marginBottom: 12 }}>
      {label}{children}
    </label>
  );
}

function eventPillStyle(eventType) {
  const colors = {
    sports_game: "#ef4444",
    restaurant_bar: "#f59e0b",
    club_event: "#a855f7",
    movie_entertainment: "#22d3ee",
    business_custom: "#3b82f6",
    bigfm_admin: "#86efac",
  };
  const color = colors[eventType] || "var(--text-secondary)";
  return {
    fontSize: 9, fontWeight: 700, letterSpacing: 0.5,
    padding: "2px 6px", borderRadius: 4,
    background: `color-mix(in srgb, ${color} 14%, transparent)`, color,
  };
}


// ─── Style tokens ────────────────────────────────────────────────────
const btnPrimaryStyle = {
  display: "inline-flex", alignItems: "center", justifyContent: "center",
  gap: 6, padding: "8px 12px", background: "#22d3ee",
  border: "none", borderRadius: 6, color: "#0a0a0c", fontSize: 12,
  fontWeight: 700, cursor: "pointer", letterSpacing: 0.3, width: "100%",
};
const btnGhostStyle = {
  display: "inline-flex", alignItems: "center", justifyContent: "center",
  gap: 6, padding: "8px 12px", background: "transparent",
  border: "1px solid var(--line)", borderRadius: 6,
  color: "var(--text-primary)", fontSize: 12, cursor: "pointer", width: "100%",
};
const iconBtnStyle = {
  display: "inline-flex", alignItems: "center", gap: 6,
  padding: "5px 6px", background: "transparent",
  border: "1px solid var(--line)", borderRadius: 5,
  color: "var(--text-primary)", fontSize: 12, cursor: "pointer", minWidth: 28,
};
const emptyStyle = {
  padding: 40, textAlign: "center", color: "var(--text-secondary)",
  border: "1px dashed var(--line)", borderRadius: 10,
};
const backdropStyle = {
  position: "fixed", inset: 0, background: "rgba(0,0,0,0.65)",
  display: "flex", alignItems: "center", justifyContent: "center",
  zIndex: 50, padding: 16,
};
const modalStyle = {
  width: "100%", maxWidth: 540, background: "var(--bg-elevated)",
  border: "1px solid var(--line)", borderRadius: 12,
  maxHeight: "90vh", display: "flex", flexDirection: "column",
};
const modalHeaderStyle = {
  padding: 16, borderBottom: "1px solid var(--line)",
  display: "flex", gap: 12, alignItems: "flex-start",
};
const modalBodyStyle = {
  flex: 1, overflowY: "auto", padding: 16,
};
const modalFooterStyle = {
  display: "flex", gap: 8, padding: 12,
  borderTop: "1px solid var(--line)",
};
