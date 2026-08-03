import React, { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";  // Phase 36d Turn 1 — settings link
import axios from "axios";
import {FirstEpisodeNudgeBanner} from "@/FirstEpisodeNudgeBanner";  // Phase 36e Turn 3

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

export default function Creator() {
  const [creator, setCreator] = useState(null);
  const [channels, setChannels] = useState([]);
  const [tab, setTab] = useState("dashboard");
  const [showApply, setShowApply] = useState(false);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const me = await axios.get(`${API}/podcasts/creators/me`,
                                                {withCredentials: true});
      setCreator(me.data.creator);
      if (me.data.creator?.application_status === "approved") {
        const r = await axios.get(
          `${API}/podcasts/creators/${me.data.creator.id}/channels`,
          {withCredentials: true});
        setChannels(r.data.channels || []);
      }
    } catch (_) { setCreator(null); }
  }, []);
  useEffect(() => { refresh(); }, [refresh]);

  return (
    <div style={{padding: 24, color: "#e7e7ea", background: "#0a0a0c", minHeight: "100vh"}}
            data-testid="creator-dashboard">
      <h1 style={{fontSize: 28, fontWeight: 700, marginBottom: 6}}>Creator Studio</h1>
      <p style={{color: "#9aa3af", fontSize: 13, marginBottom: 18}}>
        Manage your podcast channels, episodes, and distribution.
      </p>
      {creator?.id && creator.application_status === "approved" &&
        <FirstEpisodeNudgeBanner creatorId={creator.id} />}
      {!creator && (
        <div data-testid="creator-apply-cta">
          <button onClick={() => setShowApply(true)}
                          style={{padding: "10px 16px", background: "#f59e0b",
                                      color: "#0a0a0c", borderRadius: 8, fontWeight: 600}}>
            Apply to become a creator
          </button>
        </div>
      )}
      {creator?.application_status === "pending" && (
        <div data-testid="creator-pending"
                style={{padding: 14, borderRadius: 8, background: "rgba(245,158,11,0.1)",
                            border: "1px solid rgba(245,158,11,0.3)", color: "#f59e0b"}}>
          Your application is being reviewed. We&apos;ll email {creator.contact_email} when approved.
        </div>
      )}
      {creator?.application_status === "rejected" && (
        <div data-testid="creator-rejected"
                style={{padding: 14, borderRadius: 8, background: "rgba(239,68,68,0.1)",
                            border: "1px solid rgba(239,68,68,0.3)", color: "#ef4444"}}>
          Application not approved. {creator.rejection_reason || ""}
        </div>
      )}
      {creator?.application_status === "approved" && (
        <>
          <div style={{display: "flex", gap: 6, marginBottom: 14, marginTop: 14}}>
            {["dashboard","channels","episodes","distribution","analytics"].map((t) => (
              <button key={t} onClick={() => setTab(t)}
                              data-testid={`creator-tab-${t}`}
                              style={{padding: "6px 12px", borderRadius: 8,
                                          background: tab === t ? "#f59e0b" : "transparent",
                                          color: tab === t ? "#0a0a0c" : "#9aa3af",
                                          border: "1px solid rgba(255,255,255,0.08)"}}>
                {t}
              </button>
            ))}
          </div>
          {tab === "dashboard" && (
            <DashboardTab creator={creator} channels={channels}
                                    onSwitchTab={setTab} />
          )}
          {tab === "channels" && (
            <ChannelsTab creator={creator} channels={channels} onRefresh={refresh} />
          )}
          {tab === "episodes" && (
            <EpisodesTab channels={channels} />
          )}
          {tab === "distribution" && (
            <DistributionTab channels={channels} />
          )}
          {tab === "analytics" && (
            <div data-testid="creator-analytics-placeholder"
                    style={{padding: 24, textAlign: "center", color: "#9aa3af",
                                background: "rgba(255,255,255,0.02)", borderRadius: 12}}>
              Analytics coming in Phase 36e.
            </div>
          )}
        </>
      )}
      {showApply && <ApplyModal onClose={() => setShowApply(false)} onDone={refresh} />}
    </div>
  );
}

function ApplyModal({ onClose, onDone }) {
  const [form, setForm] = useState({display_name: "", bio: "", contact_email: "",
                                                          market: "dubai"});
  const submit = async () => {
    await axios.post(`${API}/podcasts/creators/apply`, form,
                                {withCredentials: true});
    onClose(); onDone();
  };
  return (
    <div onClick={onClose}
            style={{position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)",
                        display: "flex", alignItems: "center", justifyContent: "center", zIndex: 50}}>
      <div onClick={(e) => e.stopPropagation()}
              style={{background: "#13131a", padding: 24, borderRadius: 12,
                          maxWidth: 480, width: "92%"}}
              data-testid="creator-apply-modal">
        <h2 style={{fontSize: 18, fontWeight: 700, marginBottom: 12}}>
          Apply to become a creator
        </h2>
        {["display_name","contact_email","bio","market"].map((k) => (
          <div key={k} style={{marginBottom: 10}}>
            <label style={{fontSize: 11, color: "#9aa3af"}}>{k.replace(/_/g, " ")}</label>
            <input data-testid={`creator-apply-${k}`}
                      value={form[k]} onChange={(e) => setForm({...form, [k]: e.target.value})}
                      style={{width: "100%", padding: 8, marginTop: 4, borderRadius: 6,
                                  background: "#0a0a0c", color: "#e7e7ea",
                                  border: "1px solid rgba(255,255,255,0.08)"}} />
          </div>
        ))}
        <button data-testid="creator-apply-submit" onClick={submit}
                        style={{padding: "8px 16px", background: "#f59e0b", color: "#0a0a0c",
                                    borderRadius: 8, fontWeight: 600, marginTop: 8}}>
          Submit application
        </button>
      </div>
    </div>
  );
}

function ChannelsTab({ creator, channels, onRefresh }) {
  const [showNew, setShowNew] = useState(false);
  const [form, setForm] = useState({title: "", description: "", category: "tech",
                                                          language: "en", script_preference: "auto"});
  const create = async () => {
    await axios.post(`${API}/podcasts/creators/${creator.id}/channels`, form,
                                {withCredentials: true});
    setShowNew(false); onRefresh();
  };
  return (
    <div data-testid="creator-channels-tab">
      <button onClick={() => setShowNew(true)} data-testid="creator-new-channel"
                      style={{padding: "8px 14px", background: "#f59e0b", color: "#0a0a0c",
                                  borderRadius: 8, fontWeight: 600, marginBottom: 14}}>
        + New Channel
      </button>
      {channels.length === 0 && (
        <div style={{color: "#9aa3af"}}>No channels yet.</div>
      )}
      {channels.map((c) => (
        <div key={c.id} data-testid={`channel-row-${c.id}`}
                style={{padding: 14, marginBottom: 8, borderRadius: 10,
                            background: "rgba(255,255,255,0.02)",
                            border: "1px solid rgba(255,255,255,0.06)",
                            display: "flex", justifyContent: "space-between",
                            alignItems: "center"}}>
          <div>
            <div style={{fontWeight: 600, fontSize: 15}}>{c.title}</div>
            <div style={{fontSize: 11, color: "#9aa3af", marginTop: 4}}>
              {c.category} · {c.language} · {c.approval_status}
              {c.active ? " · LIVE" : " · pending review"}
            </div>
          </div>
          {/* Phase 36d Turn 1 — link to canonical channel settings page. */}
          <Link to={`/creator/channels/${c.id}/settings`}
                    data-testid={`channel-settings-link-${c.id}`}
                    style={{fontSize: 12, color: "#f59e0b", textDecoration: "none",
                                padding: "4px 10px", borderRadius: 6,
                                border: "1px solid rgba(245,158,11,0.3)"}}>
            Settings
          </Link>
        </div>
      ))}
      {showNew && (
        <div onClick={() => setShowNew(false)}
                style={{position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)",
                            display: "flex", alignItems: "center", justifyContent: "center",
                            zIndex: 50}}>
          <div onClick={(e) => e.stopPropagation()}
                  style={{background: "#13131a", padding: 20, borderRadius: 12,
                              maxWidth: 480, width: "92%"}}>
            <h3 style={{fontSize: 16, fontWeight: 700, marginBottom: 10}}>New channel</h3>
            <input placeholder="Channel title" value={form.title}
                      data-testid="channel-form-title"
                      onChange={(e) => setForm({...form, title: e.target.value})}
                      style={{width: "100%", padding: 8, borderRadius: 6, marginBottom: 8,
                                  background: "#0a0a0c", color: "#e7e7ea",
                                  border: "1px solid #333"}} />
            <textarea placeholder="Description" value={form.description}
                          onChange={(e) => setForm({...form, description: e.target.value})}
                          style={{width: "100%", padding: 8, borderRadius: 6, marginBottom: 8,
                                      background: "#0a0a0c", color: "#e7e7ea",
                                      border: "1px solid #333", minHeight: 60}} />
            <div style={{fontSize: 11, color: "#9aa3af", marginBottom: 4}}>
              Script preference (used by AI title generation)
            </div>
            <select data-testid="channel-form-script-preference"
                          value={form.script_preference}
                          onChange={(e) => setForm({...form, script_preference: e.target.value})}
                          style={{width: "100%", padding: 8, borderRadius: 6, marginBottom: 10,
                                      background: "#0a0a0c", color: "#e7e7ea",
                                      border: "1px solid #333"}}>
              <option value="auto">Auto (default — hi → Devanagari, others → Latin)</option>
              <option value="latin">Latin (recommended for Hinglish)</option>
              <option value="devanagari">Devanagari (Hindi-script titles)</option>
            </select>
            <button onClick={create} data-testid="channel-form-submit"
                            style={{padding: "8px 16px", background: "#f59e0b",
                                        color: "#0a0a0c", borderRadius: 8, fontWeight: 600}}>
              Create
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function EpisodesTab({ channels }) {
  return (
    <div data-testid="creator-episodes-tab" style={{color: "#9aa3af"}}>
      {channels.length === 0 ? "Create a channel first." :
       "Use the creator API to upload episodes. UI wiring lands next iteration."}
    </div>
  );
}

function DistributionTab({ channels }) {
  const [ch, setCh] = useState(channels[0]?.id || null);
  const [list, setList] = useState([]);
  useEffect(() => {
    if (!ch) return;
    axios.get(`${API}/podcasts/channels/${ch}/distribution`,
                  {withCredentials: true})
            .then((r) => setList(r.data.checklist || []));
  }, [ch]);
  return (
    <div data-testid="creator-distribution-tab">
      <select value={ch || ""} onChange={(e) => setCh(e.target.value)}
                  style={{padding: 8, borderRadius: 6, marginBottom: 12,
                              background: "#0a0a0c", color: "#e7e7ea",
                              border: "1px solid #333"}}>
        {channels.map((c) => <option key={c.id} value={c.id}>{c.title}</option>)}
      </select>
      {list.map((p) => (
        <div key={p.platform_name} data-testid={`distrib-${p.platform_name}`}
                style={{display: "flex", justifyContent: "space-between", padding: 10,
                            background: "rgba(255,255,255,0.02)", borderRadius: 8,
                            marginBottom: 6}}>
          <span>{p.platform_name.replace(/_/g, " ")}</span>
          <span style={{color: p.platform_status === "live" ? "#22c55e" : "#9aa3af",
                              fontSize: 12}}>
            {p.platform_status}
          </span>
        </div>
      ))}
    </div>
  );
}


// Phase 19a Part 3 — Creator Studio dashboard.  Components extracted to
// module-level to satisfy react/no-unstable-nested-components.

function DashStat({label, value, testid, hint}) {
  return (
    <div data-testid={testid}
            style={{flex: 1, minWidth: 140, padding: 14, borderRadius: 12,
                        background: "rgba(255,255,255,0.03)",
                        border: "1px solid rgba(255,255,255,0.06)"}}>
      <div style={{fontSize: 11, color: "#9aa3af",
                            textTransform: "uppercase",
                            letterSpacing: 0.5, marginBottom: 6}}>{label}</div>
      <div style={{fontSize: 24, fontWeight: 700}}>{value}</div>
      {hint && (
        <div style={{fontSize: 11, color: "#6b7280", marginTop: 4}}>{hint}</div>
      )}
    </div>
  );
}

function DashQuickLink({label, href, testid, primary}) {
  return (
    <Link to={href} data-testid={testid}
              style={{display: "block", padding: 14, borderRadius: 10,
                          background: primary ? "rgba(245,158,11,0.12)"
                                                : "rgba(255,255,255,0.03)",
                          border: `1px solid ${primary
                              ? "rgba(245,158,11,0.4)"
                              : "rgba(255,255,255,0.06)"}`,
                          color: primary ? "#f59e0b" : "#e7e7ea",
                          textDecoration: "none", fontWeight: 600,
                          fontSize: 13}}>
      {label}
    </Link>
  );
}

function DashboardTab({ creator, channels, onSwitchTab }) {
  const channelCount = (channels || []).length;
  const episodeCount = (channels || []).reduce(
    (n, c) => n + (c.episode_count || 0), 0);
  const firstChannelId = channels?.[0]?.id;

  return (
    <div data-testid="creator-dashboard-tab"
            style={{display: "flex", flexDirection: "column", gap: 18}}>
      <div style={{padding: 20, borderRadius: 14,
                            background:
                              "linear-gradient(135deg, rgba(245,158,11,0.12), rgba(245,158,11,0.04))",
                            border: "1px solid rgba(245,158,11,0.3)"}}>
        <div style={{fontSize: 13, color: "#9aa3af", marginBottom: 4}}>
          Welcome back{creator?.display_name ? `, ${creator.display_name}` : ""}
        </div>
        <div style={{fontSize: 22, fontWeight: 700, marginBottom: 12}}>
          Ready to record?
        </div>
        <div style={{display: "flex", gap: 10, flexWrap: "wrap"}}>
          <Link to="/creator/studio/new"
                    data-testid="creator-hero-new-session"
                    style={{padding: "10px 18px", background: "#f59e0b",
                                color: "#0a0a0c", borderRadius: 10,
                                fontWeight: 700, textDecoration: "none",
                                fontSize: 14}}>
            + New Recording Session
          </Link>
          <button data-testid="creator-hero-new-channel"
                          onClick={() => onSwitchTab("channels")}
                          style={{padding: "10px 18px",
                                      background: "transparent",
                                      color: "#e7e7ea",
                                      border: "1px solid rgba(255,255,255,0.15)",
                                      borderRadius: 10, fontWeight: 600,
                                      fontSize: 14, cursor: "pointer"}}>
            + New Channel
          </button>
        </div>
      </div>

      <div style={{display: "flex", gap: 10, flexWrap: "wrap"}}>
        <DashStat label="Channels" value={channelCount}
                  testid="creator-stat-channels"
                  hint={channelCount === 0 ? "Create your first channel" : null} />
        <DashStat label="Episodes" value={episodeCount}
                  testid="creator-stat-episodes" />
        <DashStat label="Plays this week" value="—"
                  testid="creator-stat-plays" hint="Funnel view →" />
        <DashStat label="Pending nudges" value="—"
                  testid="creator-stat-nudges" hint="Mailgun-backed" />
      </div>

      <div>
        <div style={{fontSize: 11, color: "#9aa3af",
                              textTransform: "uppercase", letterSpacing: 0.5,
                              marginBottom: 8}}>
          Quick links
        </div>
        <div style={{display: "grid",
                              gridTemplateColumns: "repeat(auto-fill, minmax(200px,1fr))",
                              gap: 10}}>
          <DashQuickLink label="Recording Studio →"
                              href="/creator/studio/new" primary
                              testid="creator-ql-studio" />
          <DashQuickLink label="My Channels"
                              href={firstChannelId
                                ? `/creator/channels/${firstChannelId}/settings`
                                : "/creator"}
                              testid="creator-ql-channels" />
          <DashQuickLink label="Conversion Funnel"
                              href={creator?.id
                                ? `/creator/funnel/${creator.id}`
                                : "/creator/funnel"}
                              testid="creator-ql-funnel" />
          <DashQuickLink label="Lightning Splits"
                              href={firstChannelId
                                ? `/creator/channels/${firstChannelId}/settings`
                                : "/creator"}
                              testid="creator-ql-lightning" />
          <DashQuickLink label="Subscription Plan"
                              href={creator?.id
                                ? `/creator/${creator.id}/subscription`
                                : "/creator"}
                              testid="creator-ql-subscription" />
        </div>
      </div>

      {channelCount > 0 && (
        <div data-testid="creator-dashboard-recent-channels">
          <div style={{fontSize: 11, color: "#9aa3af",
                                textTransform: "uppercase", letterSpacing: 0.5,
                                marginBottom: 8}}>
            Your channels
          </div>
          <div style={{display: "flex", flexDirection: "column", gap: 8}}>
            {(channels || []).slice(0, 5).map((ch) => (
              <Link to={`/creator/channels/${ch.id}/settings`}
                        key={ch.id}
                        data-testid={`dashboard-channel-${ch.id}`}
                        style={{padding: 12, borderRadius: 10,
                                    background: "rgba(255,255,255,0.03)",
                                    border: "1px solid rgba(255,255,255,0.06)",
                                    textDecoration: "none", color: "#e7e7ea",
                                    display: "flex", justifyContent: "space-between",
                                    alignItems: "center"}}>
                <div>
                  <div style={{fontWeight: 600}}>{ch.title}</div>
                  <div style={{fontSize: 11, color: "#9aa3af", marginTop: 2}}>
                    {ch.category || "uncategorized"} · {ch.language || "—"}
                    {ch.approval_status ? ` · ${ch.approval_status}` : ""}
                  </div>
                </div>
                <div style={{color: "#9aa3af", fontSize: 12}}>Manage →</div>
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
