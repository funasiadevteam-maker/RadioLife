/** Phase 42-E1.3 — Advertiser self-serve Predict & Win.
 *
 *  Route: /advertiser/predict-win
 *
 *  Flow:
 *      1. List "My campaigns" with status pills (draft / pending /
 *          approved+live / rejected).
 *      2. Create-new button opens a builder modal:
 *           - Fields: name, question, lock_time, 2-4 answer options,
 *              prize_description, expected_participants, city.
 *           - Live price quote panel reads /api/admin/predict-win/pricing
 *              (admin endpoint requires admin role — for advertisers we
 *              read it through a public-ish helper: we fall back to the
 *              built-in defaults $299/$5 if the call 403s, then the
 *              backend `/draft` call returns the canonical quote anyway).
 *           - Submit & Pay → calls POST /api/advertiser/predict-win/draft
 *              then POST /{id}/submit with a mocked payment_intent_id.
 *      3. Status banner per campaign (rejected reason surfaces).
 *
 *  This page is mounted INSIDE the existing Advertiser shell so the
 *  nav + auth gates already apply.
 */
import React, { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { Toaster, toast } from "sonner";
import {
  Plus, Trophy, Clock, CheckCircle2, XCircle, Loader2,
  CreditCard, X, AlertCircle,
} from "lucide-react";
import { API } from "@/AuthContext";

const DEFAULT_MIN = 299;
const DEFAULT_PER = 5;

function StatusPill({ status }) {
  const cfg = {
    draft:        { bg: "#1f1f28",                        fg: "#cbd5e1", label: "Draft" },
    pending:    { bg: "rgba(245,158,11,0.18)", fg: "#fbbf24", label: "Pending approval" },
    approved: { bg: "rgba(74,222,128,0.18)", fg: "#4ade80", label: "Approved · live" },
    rejected: { bg: "rgba(248,113,113,0.18)", fg: "#f87171", label: "Rejected" },
  };
  const c = cfg[status] || cfg.draft;
  return (
    <span style={{ background: c.bg, color: c.fg,
                                  padding: "3px 9px", borderRadius: 999,
                                  fontSize: 11, fontWeight: 600 }}
                data-status-pill={status}>
      {c.label}
    </span>
  );
}

function fmtDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? iso : d.toLocaleString();
}

export default function AdvertiserPredictWin() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/advertiser/predict-win/mine`,
                                                          { withCredentials: true });
      setItems(r.data?.items || []);
    } catch (e) {
      toast.error("Failed to load campaigns");
    }
    setLoading(false);
  }, []);
  useEffect(() => { reload(); }, [reload]);

  return (
    <div data-testid="advertiser-predict-win-page"
              style={{ padding: "28px 32px", color: "#cbd5e1",
                          background: "#070710", minHeight: "100vh" }}>
      <Toaster richColors position="top-right" />
      <header style={{ display: "flex", justifyContent: "space-between",
                                  alignItems: "center", marginBottom: 22 }}>
        <h1 style={{ display: "inline-flex", alignItems: "center", gap: 10,
                                  color: "#fff", margin: 0, fontSize: 22 }}>
          <Trophy size={20} color="#fbbf24" /> Predict & Win Campaigns
        </h1>
        <button onClick={() => setCreateOpen(true)}
                        data-testid="advertiser-pw-open-create"
                        style={{
                          display: "inline-flex", alignItems: "center", gap: 6,
                          background: "#fbbf24", color: "#0b0b0b",
                          border: 0, borderRadius: 8,
                          padding: "9px 16px", fontSize: 12,
                          fontWeight: 600, cursor: "pointer",
                        }}>
          <Plus size={14} /> New campaign
        </button>
      </header>

      {loading ? (
        <div style={{ color: "#9aa3af", padding: 40,
                                  textAlign: "center" }}
                data-testid="advertiser-pw-loading">Loading…</div>
      ) : items.length === 0 ? (
        <div data-testid="advertiser-pw-empty"
                  style={{ color: "#9aa3af", padding: 40,
                                  textAlign: "center",
                                  border: "1px dashed #25252f",
                                  borderRadius: 8 }}>
          No campaigns yet. Click "New campaign" to create your first
          Predict & Win.
        </div>
      ) : (
        <div data-testid="advertiser-pw-list"
                  style={{ display: "grid",
                              gridTemplateColumns: "repeat(auto-fill,minmax(360px,1fr))",
                              gap: 12 }}>
          {items.map(c => (
            <div key={c._id}
                      data-testid={`advertiser-pw-row-${c._id}`}
                      style={{ background: "#0f0f15",
                                  border: "1px solid #1f1f28",
                                  borderRadius: 10, padding: 14 }}>
              <div style={{ display: "flex",
                                          justifyContent: "space-between",
                                          alignItems: "start", gap: 10,
                                          marginBottom: 8 }}>
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{ color: "#fff", fontWeight: 600,
                                              fontSize: 14, overflow: "hidden",
                                              textOverflow: "ellipsis",
                                              whiteSpace: "nowrap" }}>
                    {c.title}
                  </div>
                  <div style={{ color: "#9aa3af", fontSize: 11,
                                              marginTop: 2 }}>
                    Locks {fmtDate(c.lock_time)}
                  </div>
                </div>
                <StatusPill status={c.approval_status || "draft"} />
              </div>
              {c.pricing_snapshot && (
                <div style={{ color: "#cbd5e1", fontSize: 12,
                                            marginTop: 8, padding: "8px 10px",
                                            background: "#16161f",
                                            borderRadius: 6 }}>
                  Quote: <strong style={{ color: "#fbbf24" }}>
                    ${c.pricing_snapshot.total_quoted_usd}
                  </strong> · {c.pricing_snapshot.expected_participants} participants
                </div>
              )}
              {c.approval_status === "rejected" && c.approval_reason && (
                <div style={{ marginTop: 10, padding: "8px 10px",
                                            background: "rgba(248,113,113,0.08)",
                                            border: "1px solid rgba(248,113,113,0.3)",
                                            borderRadius: 6, color: "#f87171",
                                            fontSize: 12 }}>
                  <AlertCircle size={11} style={{ verticalAlign: "-1px",
                                                                        marginRight: 4 }} />
                  {c.approval_reason}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {createOpen && (
        <CreateModal onClose={() => setCreateOpen(false)}
                                  onCreated={() => { setCreateOpen(false); reload(); }} />
      )}
    </div>
  );
}

// ─── Builder modal ─────────────────────────────────────────────
function CreateModal({ onClose, onCreated }) {
  const [form, setForm] = useState({
    campaign_name: "",
    question: "",
    lock_time_iso: new Date(Date.now() + 24 * 60 * 60 * 1000)
                                .toISOString().slice(0, 16),
    answer_a: "Yes",
    answer_b: "No",
    prize_description: "",
    expected_participants: 100,
    city: "Dubai",
  });
  const [pricing, setPricing] = useState({
    min_campaign_price_usd: DEFAULT_MIN,
    per_participant_price_usd: DEFAULT_PER,
  });
  const [busy, setBusy] = useState(false);

  // The admin endpoint is admin-gated.  Advertisers can read the
  // current pricing via the canonical quote returned from /draft,
  // but for the live preview we use the defaults until /draft returns.
  // If pricing was changed by admin, the actual invoice will reflect
  // the canonical /draft response.
  useEffect(() => {
    (async () => {
      try {
        const r = await axios.get(`${API}/admin/predict-win/pricing`,
                                                          { withCredentials: true });
        setPricing({
          min_campaign_price_usd: r.data?.min_campaign_price_usd || DEFAULT_MIN,
          per_participant_price_usd: r.data?.per_participant_price_usd || DEFAULT_PER,
        });
      } catch (_) { /* admin-only — keep defaults */ }
    })();
  }, []);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const minU = Number(pricing.min_campaign_price_usd) || DEFAULT_MIN;
  const perU = Number(pricing.per_participant_price_usd) || DEFAULT_PER;
  const pp     = Number(form.expected_participants) || 0;
  const quote = Math.max(minU, perU * pp);

  const submit = async () => {
    if (!form.campaign_name.trim() || !form.question.trim()
                  || !form.prize_description.trim()) {
      toast.error("Fill in name, question, and prize");
      return;
    }
    if (!form.lock_time_iso) {
      toast.error("Set a lock time");
      return;
    }
    setBusy(true);
    try {
      const draft = await axios.post(`${API}/advertiser/predict-win/draft`, {
        campaign_name:                form.campaign_name.trim(),
        event_type:                      "advertiser_custom",
        question:                            form.question.trim(),
        answer_options: [
          { id: "opt_a", label: form.answer_a.trim() || "Yes" },
          { id: "opt_b", label: form.answer_b.trim() || "No" },
        ],
        lock_time_iso:                form.lock_time_iso,
        prize_description:        form.prize_description.trim(),
        expected_participants: Number(form.expected_participants),
        city:                                  form.city,
        language:                          "en",
      }, { withCredentials: true });
      const campaignId = draft.data?.campaign_id;
      // Phase 42-E1.3 — mocked Stripe checkout.  In production we'd
      // open Stripe Checkout in a new tab and listen for the webhook;
      // for now we synthesise a payment_intent_id and submit.
      const mockPI = `pi_mock_${Math.random().toString(36).slice(2, 14)}`;
      await axios.post(`${API}/advertiser/predict-win/${campaignId}/submit`,
                                          { payment_intent_id: mockPI },
                                          { withCredentials: true });
      toast.success(`Submitted! Awaiting admin approval. Invoice $${draft.data?.quote_usd}.`);
      onCreated();
    } catch (e) {
      toast.error(e?.response?.data?.detail?.code || "Submit failed");
    }
    setBusy(false);
  };

  return (
    <div data-testid="advertiser-pw-create-modal"
              onClick={onClose}
              style={{ position: "fixed", inset: 0,
                          background: "rgba(0,0,0,0.7)", zIndex: 70,
                          display: "flex", alignItems: "center",
                          justifyContent: "center", padding: 16 }}>
      <div onClick={(e) => e.stopPropagation()}
                style={{ background: "#0f0f15",
                          border: "1px solid #1f1f28",
                          borderRadius: 12, padding: 22,
                          width: "min(560px,96vw)",
                          maxHeight: "92vh", overflowY: "auto" }}>
        <div style={{ display: "flex",
                                  justifyContent: "space-between",
                                  alignItems: "center", marginBottom: 14 }}>
          <h2 style={{ color: "#fff", margin: 0, fontSize: 16,
                                      display: "inline-flex", alignItems: "center", gap: 8 }}>
            <Trophy size={14} color="#fbbf24" /> New Predict & Win
          </h2>
          <button onClick={onClose}
                          data-testid="advertiser-pw-create-cancel"
                          style={{ background: "transparent",
                                      border: 0, color: "#9aa3af",
                                      cursor: "pointer" }}>
            <X size={16} />
          </button>
        </div>

        <div style={{ display: "grid", gap: 10 }}>
          <Field label="Campaign name"
                        value={form.campaign_name}
                        onChange={(v) => set("campaign_name", v)}
                        testid="advertiser-pw-campaign-name" />
          <Field label="Question prompt"
                        placeholder="e.g. Who will win tonight's match?"
                        value={form.question}
                        onChange={(v) => set("question", v)}
                        testid="advertiser-pw-question" />
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr",
                                      gap: 10 }}>
            <Field label="Answer A" value={form.answer_a}
                          onChange={(v) => set("answer_a", v)}
                          testid="advertiser-pw-answer-a" />
            <Field label="Answer B" value={form.answer_b}
                          onChange={(v) => set("answer_b", v)}
                          testid="advertiser-pw-answer-b" />
          </div>
          <Field label="Prize description"
                        value={form.prize_description}
                        onChange={(v) => set("prize_description", v)}
                        testid="advertiser-pw-prize" />
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr",
                                      gap: 10 }}>
            <Field label="Lock time" type="datetime-local"
                          value={form.lock_time_iso}
                          onChange={(v) => set("lock_time_iso", v)}
                          testid="advertiser-pw-lock-time" />
            <Field label="Expected participants" type="number"
                          value={form.expected_participants}
                          onChange={(v) => set("expected_participants", v)}
                          testid="advertiser-pw-expected" />
          </div>
          <Field label="City" value={form.city}
                        onChange={(v) => set("city", v)}
                        testid="advertiser-pw-city" />
        </div>

        {/* Live quote */}
        <div data-testid="advertiser-pw-quote-panel"
                  style={{ marginTop: 14, padding: "10px 14px",
                              background: "rgba(251,191,36,0.08)",
                              border: "1px solid rgba(251,191,36,0.25)",
                              borderRadius: 8 }}>
          <div style={{ color: "#fbbf24", fontSize: 11,
                                      textTransform: "uppercase",
                                      letterSpacing: 1.3, marginBottom: 4 }}>
            Quoted price
          </div>
          <div style={{ color: "#fff", fontSize: 28, fontWeight: 700,
                                      fontVariantNumeric: "tabular-nums" }}
                  data-testid="advertiser-pw-quote-amount">
            ${quote}
          </div>
          <div style={{ color: "#9aa3af", fontSize: 11, marginTop: 2 }}>
            ${minU} min, ${perU}/participant × {pp} participants
          </div>
        </div>

        <div style={{ display: "flex", justifyContent: "flex-end",
                                  gap: 8, marginTop: 14 }}>
          <button onClick={onClose}
                          style={{ background: "transparent",
                                      color: "#cbd5e1",
                                      border: "1px solid #25252f",
                                      borderRadius: 8, padding: "9px 14px",
                                      fontSize: 12, cursor: "pointer" }}>
            Cancel
          </button>
          <button onClick={submit} disabled={busy}
                          data-testid="advertiser-pw-submit"
                          style={{ display: "inline-flex",
                                      alignItems: "center", gap: 6,
                                      background: "#fbbf24",
                                      color: "#0b0b0b", border: 0,
                                      borderRadius: 8, padding: "9px 16px",
                                      fontSize: 12, fontWeight: 600,
                                      cursor: busy ? "wait" : "pointer" }}>
            {busy
              ? <Loader2 size={12} className="spin" />
              : <CreditCard size={12} />}
            Submit & Pay
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, value, onChange, placeholder, type = "text", testid }) {
  return (
    <label style={{ display: "block", fontSize: 11, color: "#9aa3af" }}>
      {label}
      <input type={type} value={value}
                    placeholder={placeholder || ""}
                    onChange={(e) => onChange(e.target.value)}
                    data-testid={testid}
                    style={{ width: "100%", marginTop: 4,
                                background: "#0b0b0f",
                                border: "1px solid #25252f",
                                borderRadius: 6, padding: "8px 10px",
                                color: "#fff", fontSize: 12,
                                outline: "none" }} />
    </label>
  );
}
