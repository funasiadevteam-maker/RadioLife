// PHASE 36d — Channel Settings (canonical creator-side settings page).
// Later phases (Lightning Splits in Turn 3, etc.) will add sections to
// this page rather than creating a parallel surface.

import React, {useEffect, useState} from "react";
import axios from "axios";
import {useParams, useNavigate} from "react-router-dom";
import {LightningSplitsEditor} from "@/LightningSplitsEditor";
import {SubscriptionPlanSection} from "@/SubscriptionPlanSection";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
axios.defaults.withCredentials = true;

export default function CreatorChannelSettings() {
  const {channel_id} = useParams();
  const nav = useNavigate();
  const [orig, setOrig] = useState(null);
  const [draft, setDraft] = useState(null);
  const [err, setErr] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    axios.get(`${API}/podcasts/channels/${channel_id}/settings`)
            .then((r) => { setOrig(r.data); setDraft(r.data); })
            .catch((e) => setErr(e?.response?.data?.detail || e.message));
  }, [channel_id]);

  if (err) return (
    <Wrap><div data-testid="ch-settings-err"
                              style={{color: "#ef4444"}}>{String(err)}</div></Wrap>
  );
  if (!draft) return <Wrap><div data-testid="ch-settings-loading">Loading…</div></Wrap>;

  const dirty = JSON.stringify(orig) !== JSON.stringify(draft);
  const validClips = draft.magic_clips_per_episode >= 1
                                && draft.magic_clips_per_episode <= 15;

  const save = async () => {
    setSaving(true); setErr("");
    try {
      const r = await axios.patch(
        `${API}/podcasts/channels/${channel_id}/settings`,
        {magic_clips_enabled: draft.magic_clips_enabled,
          magic_clips_per_episode: Number(draft.magic_clips_per_episode)});
      setOrig(r.data); setDraft(r.data);
    } catch (e) { setErr(e?.response?.data?.detail || e.message); }
    finally { setSaving(false); }
  };

  return (
    <Wrap>
      <div style={{display: "flex", justifyContent: "space-between",
                          alignItems: "center", marginBottom: 16}}>
        <div>
          <div style={{fontSize: 11, color: "#9aa3af",
                              textTransform: "uppercase", letterSpacing: 0.5}}>
            Channel settings
          </div>
          <h1 data-testid="ch-settings-title"
                  style={{fontSize: 24, fontWeight: 800, margin: "2px 0 0"}}>
            {draft.title || draft.id}
          </h1>
        </div>
      </div>

      <section data-testid="magic-clips-section" style={card()}>
        <h2 style={sectionH()}>Magic Clips</h2>
        <label style={{display: "flex", alignItems: "center", gap: 8,
                                  marginBottom: 12, cursor: "pointer"}}>
          <input data-testid="magic-clips-enabled-toggle" type="checkbox"
                      checked={!!draft.magic_clips_enabled}
                      onChange={(e) => setDraft({...draft,
                        magic_clips_enabled: e.target.checked})} />
          <span>Generate magic clips automatically</span>
        </label>
        <div style={{marginBottom: 8}}>
          <label style={{fontSize: 12, color: "#9aa3af",
                                    display: "block", marginBottom: 4}}>
            Clips per episode (1-15)
          </label>
          <input data-testid="magic-clips-per-episode-input" type="number"
                      min={1} max={15}
                      value={draft.magic_clips_per_episode}
                      onChange={(e) => setDraft({...draft,
                        magic_clips_per_episode: Number(e.target.value)})}
                      disabled={!draft.magic_clips_enabled}
                      style={inp()} />
          {!validClips && (
            <div data-testid="magic-clips-range-err"
                    style={{color: "#ef4444", fontSize: 12, marginTop: 4}}>
              Must be between 1 and 15.
            </div>
          )}
        </div>
        <p style={{fontSize: 12, color: "#9aa3af", marginTop: 8, lineHeight: 1.5}}>
          When enabled, RadioLife auto-generates draft highlight clips after each
          episode finalizes. You'll review and publish them from the episode page.
        </p>
      </section>

      {/* Phase 36d Turn 3 — Lightning splits (placeholder schema). */}
      <section data-testid="lightning-section" style={card()}>
        <h2 style={sectionH()}>Lightning splits</h2>
        <label style={{display: "flex", alignItems: "center", gap: 8,
                                  marginBottom: 12, cursor: "pointer"}}>
          <input data-testid="lightning-enable-toggle" type="checkbox"
                      checked={!!draft.lightning_enabled}
                      onChange={(e) => setDraft({...draft,
                        lightning_enabled: e.target.checked})} />
          <span>Enable Lightning splits in RSS feed</span>
        </label>
        {draft.lightning_enabled && (
          <LightningSplitsEditor
            testIdPrefix="lightning"
            loadUrl={`${API}/podcasts/channels/${channel_id}/lightning-splits`}
            saveUrl={`${API}/podcasts/channels/${channel_id}/lightning-splits`}
            helperText={"This is a placeholder schema. RadioLife does not currently process Lightning payments — these values are emitted in the RSS feed so listeners using Podcasting 2.0 apps (Fountain, Podverse, etc.) can stream sats to your recipients directly. Real Lightning settlement is on the roadmap."}
          />
        )}
        {!draft.lightning_enabled && (
          <p data-testid="lightning-disabled-hint"
                style={{fontSize: 12, color: "#9aa3af", lineHeight: 1.5}}>
            When enabled, recipients you list here will be emitted in the
            channel's RSS feed as <code>&lt;podcast:value&gt;</code> and
            inherited by every episode that doesn't set its own override.
          </p>
        )}
      </section>

      {/* PHASE 36e Turn 1 — Subscription plan section. */}
      <hr style={{border: "none", borderTop: "1px solid rgba(255,255,255,0.06)",
                          margin: "20px 0 4px"}} />
      <div style={{fontSize: 11, color: "#9aa3af",
                          textTransform: "uppercase", letterSpacing: 0.6,
                          marginBottom: 4}}>
        Monetization
      </div>
      <SubscriptionPlanSection channelId={channel_id}
                                                            creatorId={draft.creator_id} />

      <div style={{display: "flex", gap: 8, marginTop: 20}}>
        <button data-testid="settings-save" onClick={save}
                        disabled={!dirty || saving || !validClips}
                        style={btnPrimary(!dirty || saving || !validClips)}>
          {saving ? "Saving…" : "Save"}
        </button>
        <button data-testid="settings-cancel"
                        onClick={() => setDraft(orig)}
                        disabled={!dirty || saving}
                        style={btnSec(!dirty || saving)}>
          Cancel
        </button>
        <button data-testid="settings-back" onClick={() => nav(-1)}
                        style={{...btnSec(false), marginLeft: "auto"}}>
          Back
        </button>
      </div>
    </Wrap>
  );
}

const Wrap = ({children}) => (
  <div style={{minHeight: "100vh", background: "#0a0a14", color: "#e7e7ea",
                      padding: 24}}>
    <div style={{maxWidth: 720, margin: "0 auto"}}>{children}</div>
  </div>
);
const card = () => ({padding: 18, borderRadius: 10, background: "#101018",
  border: "1px solid rgba(255,255,255,0.06)", marginBottom: 12});
const sectionH = () => ({fontSize: 16, fontWeight: 700, margin: "0 0 12px"});
const inp = () => ({padding: "6px 10px", borderRadius: 6, background: "#0a0a14",
  color: "#fff", border: "1px solid rgba(255,255,255,0.1)", width: 100});
const btnPrimary = (disabled) => ({padding: "8px 16px", borderRadius: 6,
  fontWeight: 700, cursor: disabled ? "not-allowed" : "pointer",
  background: disabled ? "#3f3f46" : "#f59e0b",
  color: disabled ? "#a1a1aa" : "#0a0a0c", border: "none"});
const btnSec = (disabled) => ({padding: "8px 16px", borderRadius: 6,
  fontWeight: 700, cursor: disabled ? "not-allowed" : "pointer",
  background: "rgba(255,255,255,0.04)", color: "#e7e7ea",
  border: "1px solid rgba(255,255,255,0.1)"});
