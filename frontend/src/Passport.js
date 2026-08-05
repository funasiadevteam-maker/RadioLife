import React, { useEffect, useState, useCallback, useMemo } from "react";
import axios from "axios";
import { toast } from "sonner";
import {
  Award, Star, Sparkles, Copy, Share2, Eye, EyeOff,
  MapPin, Clock, Trophy, Lock, ChevronRight, RefreshCcw,
} from "lucide-react";
import "@/Passport.css";
import BannerAdSlot from "@/components/BannerAdSlot";
// Phase 42-E2.2 — Universal share + invite-a-friend.
import ShareButton from "@/components/ShareButton";
import InviteFriendForm from "@/components/InviteFriendForm";
// Phase 42-E2.4 — OG meta for the passport surface.
import OGMeta from "@/components/OGMeta";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
axios.defaults.withCredentials = true;

const TIER_GRADIENT = {
  bronze:   "linear-gradient(135deg, #b67334, #8a5418)",
  silver:   "linear-gradient(135deg, #cfd6df, #8c97a3)",
  gold:     "linear-gradient(135deg, #ffd75e, #d18d24)",
  platinum: "linear-gradient(135deg, #d6f0ff, #79b8d6)",
  diamond:  "linear-gradient(135deg, #c4f5ff, #6fc7ff 60%, #b27cff)",
  unique:   "linear-gradient(135deg, #ff6ec4, #7873f5)",
};


function TierIcon({ tier, name }) {
  const ch = (name || "?").trim().charAt(0).toUpperCase();
  return (
    <div className="psp-tier-icon"
            style={{ background: TIER_GRADIENT[tier] || TIER_GRADIENT.bronze }}>
      <span>{ch}</span>
    </div>
  );
}


function BadgeCard({ badge, locked = false, earned = false, progressPct,
                          progressCurrent, progressTarget }) {
  return (
    <div className={"psp-badge-card" + (locked ? " is-locked" : "")
                      + (earned ? " is-earned" : "")}
          data-testid={`psp-badge-${badge.badge_id}`}>
      <div className="psp-badge-head">
        <TierIcon tier={badge.tier} name={badge.name}/>
        <div className="psp-badge-meta">
          <div className="psp-badge-name">{badge.name}</div>
          <div className="psp-badge-pts">
            <Star size={11}/> {badge.points} pts
            <span className="psp-tier-chip" data-tier={badge.tier}>
              {badge.tier}
            </span>
          </div>
        </div>
        {earned && <Sparkles className="psp-earned-tick" size={16}/>}
        {locked && <Lock className="psp-lock" size={14}/>}
      </div>
      <div className="psp-badge-desc">{badge.description}</div>
      {progressPct != null && (
        <div className="psp-bar">
          <div className="psp-bar-fill" style={{ width: `${progressPct}%` }} />
          <div className="psp-bar-label">
            {progressCurrent} / {progressTarget} &middot; {progressPct}%
          </div>
        </div>
      )}
      {!earned && progressPct == null && (
        <div className="psp-badge-criteria">{badge.criteria_summary}</div>
      )}
    </div>
  );
}


function HeroCard({ data }) {
  const a = data.ambassador || {};
  const ls = data.listening_stats || {};
  const display = data.settings.display_name;
  const initial = display.trim().charAt(0).toUpperCase();
  return (
    <div className="psp-hero" data-testid="psp-hero">
      <div className="psp-avatar"
            style={{ background: TIER_GRADIENT.diamond }}>
        {data.settings.avatar_url
            ? <img src={data.settings.avatar_url} alt=""/>
            : <span>{initial}</span>}
      </div>
      <div className="psp-hero-body">
        <div className="psp-hero-name">
          {display}
          {data.settings.city_pin && (
            <span className="psp-city-pin">
              <MapPin size={12}/>{data.settings.city_pin}
            </span>
          )}
        </div>
        {data.settings.bio && (
          <div className="psp-hero-bio">{data.settings.bio}</div>
        )}
        <div className="psp-hero-stats">
          <div>
            <span className="psp-stat-num">{a.level || 1}</span>
            <span className="psp-stat-lbl">{a.level_name || "Listener"}</span>
          </div>
          <div>
            <span className="psp-stat-num">{data.badges_total}</span>
            <span className="psp-stat-lbl">badges</span>
          </div>
          <div>
            <span className="psp-stat-num">{data.badges_total_points}</span>
            <span className="psp-stat-lbl">points</span>
          </div>
          <div>
            <span className="psp-stat-num">{ls.hours_total ?? 0}h</span>
            <span className="psp-stat-lbl">listened</span>
          </div>
        </div>
        {a.next_level_threshold != null && (
          <div className="psp-amb-progress">
            <div className="psp-bar"
                  data-testid="psp-amb-progress-bar">
              <div className="psp-bar-fill"
                    style={{ width: `${a.progress_to_next_pct ?? 0}%` }} />
            </div>
            <div className="psp-amb-progress-label">
              {a.points} / {a.next_level_threshold} pts &rarr;
              <strong> {a.next_level_name}</strong>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}


function BadgesTab({ data, catalog, onRefresh }) {
  // Earned grid grouped by category
  const earnedByCat = data.badges_by_category || {};
  const earnedIds = useMemo(() => {
    const s = new Set();
    Object.values(earnedByCat).forEach(arr => arr.forEach(b => s.add(b.badge_id)));
    return s;
  }, [earnedByCat]);
  const inProg = data.badges_in_progress || [];
  const inProgIds = useMemo(() => new Set(inProg.map(b => b.badge_id)),
                                       [inProg]);
  const locked = (catalog || []).filter(
    b => !earnedIds.has(b.badge_id) && !inProgIds.has(b.badge_id));

  if (data.badges_total === 0 && inProg.length === 0) {
    return (
      <div className="psp-empty" data-testid="psp-badges-empty">
        <Trophy size={28}/>
        <div className="psp-empty-title">No badges yet.</div>
        <div className="psp-empty-sub">
          Listen, host a lobby, win a game, or claim an offer to start earning.
        </div>
      </div>
    );
  }

  return (
    <div className="psp-badges-tab" data-testid="psp-badges-tab">
      {Object.entries(earnedByCat).map(([cat, items]) => (
        <section className="psp-section" key={cat}
                    data-testid={`psp-earned-${cat}`}>
          <div className="psp-sec-head">
            <Trophy size={14}/> Earned &middot; {cat}
            <span className="psp-sec-count">{items.length}</span>
          </div>
          <div className="psp-badge-grid">
            {items.map(b => <BadgeCard key={b.badge_id} badge={b} earned/>)}
          </div>
        </section>
      ))}
      {inProg.length > 0 && (
        <section className="psp-section" data-testid="psp-in-progress">
          <div className="psp-sec-head">
            <Sparkles size={14}/> In progress
            <span className="psp-sec-count">{inProg.length}</span>
          </div>
          <div className="psp-badge-grid">
            {inProg.map(b => (
              <BadgeCard key={b.badge_id} badge={b}
                              progressPct={b.pct}
                              progressCurrent={b.current_value}
                              progressTarget={b.target_value}/>
            ))}
          </div>
        </section>
      )}
      {locked.length > 0 && (
        <section className="psp-section" data-testid="psp-locked">
          <div className="psp-sec-head">
            <Lock size={14}/> Locked &middot; discover
            <span className="psp-sec-count">{locked.length}</span>
            <button className="psp-ghost"
                      data-testid="psp-refresh-locked" onClick={onRefresh}>
              <RefreshCcw size={11}/>
            </button>
          </div>
          <div className="psp-badge-grid">
            {locked.slice(0, 24).map(b => (
              <BadgeCard key={b.badge_id} badge={b} locked/>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}


function StatsTab({ data }) {
  const ls = data.listening_stats || {};
  const feed = data.recent_feed || [];
  return (
    <div className="psp-stats-tab" data-testid="psp-stats-tab">
      <div className="psp-stat-grid">
        <div className="psp-stat-card">
          <Clock size={16}/>
          <div className="psp-stat-card-num">{ls.minutes_today ?? 0}</div>
          <div className="psp-stat-card-lbl">minutes today</div>
        </div>
        <div className="psp-stat-card">
          <Clock size={16}/>
          <div className="psp-stat-card-num">{ls.hours_total ?? 0}h</div>
          <div className="psp-stat-card-lbl">lifetime</div>
        </div>
        <div className="psp-stat-card">
          <Award size={16}/>
          <div className="psp-stat-card-num">{data.badges_total}</div>
          <div className="psp-stat-card-lbl">badges</div>
        </div>
        <div className="psp-stat-card">
          <Trophy size={16}/>
          <div className="psp-stat-card-num">
            {(data.ambassador || {}).level || 1}
          </div>
          <div className="psp-stat-card-lbl">level</div>
        </div>
      </div>
      <section className="psp-section">
        <div className="psp-sec-head">
          <Sparkles size={14}/> Recent badge feed
        </div>
        {feed.length === 0 && (
          <div className="psp-empty-small">No badges earned yet.</div>
        )}
        <ul className="psp-feed">
          {feed.map((f, i) => (
            <li key={i} data-testid={`psp-feed-${f.badge_id}`}>
              <TierIcon tier={f.tier} name={f.name}/>
              <div>
                <div className="psp-feed-name">{f.name}</div>
                <div className="psp-feed-date">
                  {new Date(f.earned_at).toLocaleDateString()}
                </div>
              </div>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}


function ReferralsTab({ data, onUpdate }) {
  const stats = data.referral_stats || { funnel: {}, recent: [] };
  const ref_code = data.referral_code || "—";
  const shareUrl = `${window.location.origin}/?ref=${ref_code}`;

  const copy = () => {
    navigator.clipboard.writeText(shareUrl);
    toast.success("Copied!");
  };
  const share = async () => {
    if (navigator.share) {
      try { await navigator.share({ url: shareUrl, title: "Join me on RadioLife" }); }
      catch (_) {}
    } else copy();
  };

  return (
    <div className="psp-referrals-tab" data-testid="psp-referrals-tab">
      {/* Phase 42-E2.2 — Universal invite-a-friend (Mailgun mocked,
            voucher minted, 5 pts via social_share). */}
      <section className="psp-section" style={{ padding: 0, background: "transparent", border: "none" }}>
        <InviteFriendForm />
      </section>

      <section className="psp-section">
        <div className="psp-sec-head">
          <Share2 size={14}/> Your referral link
        </div>
        <div className="psp-ref-link"
              data-testid="psp-ref-link">{shareUrl}</div>
        <div className="psp-actions">
          <button className="psp-btn"
                    data-testid="psp-copy-ref" onClick={copy}>
            <Copy size={12}/> Copy
          </button>
          <button className="psp-btn psp-btn-ghost"
                    data-testid="psp-share-ref" onClick={share}>
            <Share2 size={12}/> Share
          </button>
          {/* Phase 42-E2.2 — universal share (multi-channel + points). */}
          <ShareButton
            featureType="passport"
            contentId={ref_code}
            title="Join me on RadioLife"
            text="Listen to AI-curated radio, earn rewards, and collect city stamps with me on RadioLife:"
            url={shareUrl} />
        </div>
      </section>

      <section className="psp-section">
        <div className="psp-sec-head">
          <Trophy size={14}/> Attribution funnel
        </div>
        <div className="psp-funnel" data-testid="psp-funnel">
          <div className="psp-funnel-step">
            <div className="psp-funnel-num">{stats.funnel?.clicked || 0}</div>
            <div className="psp-funnel-lbl">clicked</div>
          </div>
          <ChevronRight size={14} className="psp-funnel-arrow"/>
          <div className="psp-funnel-step">
            <div className="psp-funnel-num">{stats.funnel?.signed_up || 0}</div>
            <div className="psp-funnel-lbl">signed up</div>
          </div>
          <ChevronRight size={14} className="psp-funnel-arrow"/>
          <div className="psp-funnel-step is-conv">
            <div className="psp-funnel-num">{stats.funnel?.engaged || 0}</div>
            <div className="psp-funnel-lbl">engaged</div>
          </div>
        </div>
        <div className="psp-funnel-conv">
          {stats.conversion_to_engaged_pct ?? 0}% engaged conversion
        </div>
      </section>

      {(stats.recent || []).length > 0 && (
        <section className="psp-section">
          <div className="psp-sec-head">
            <Clock size={14}/> Recent activity
          </div>
          <ul className="psp-ref-recent">
            {stats.recent.map((r, i) => (
              <li key={i}>
                <span className="psp-ref-status" data-st={r.status}>
                  {r.status}
                </span>
                <span className="psp-ref-path">{r.landing_path}</span>
                <span className="psp-ref-time">
                  {new Date(r.landing_at).toLocaleDateString()}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}


function SettingsTab({ data, onUpdate }) {
  const [draft, setDraft] = useState(data.settings);
  const [saving, setSaving] = useState(false);
  useEffect(() => setDraft(data.settings), [data.settings]);

  const save = async () => {
    setSaving(true);
    try {
      const res = await axios.patch(`${API}/passport/me/settings`, draft);
      onUpdate(res.data.settings);
      toast.success("Settings saved");
    } catch (e) {
      toast.error(e.response?.data?.detail || "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const tog = (key) => (
    <button className={"psp-toggle" + (draft[key] ? " is-on" : "")}
              onClick={() => setDraft({ ...draft, [key]: !draft[key] })}
              data-testid={`psp-toggle-${key}`}>
      {draft[key] ? <Eye size={12}/> : <EyeOff size={12}/>}
      {draft[key] ? "ON" : "OFF"}
    </button>
  );

  return (
    <div className="psp-settings-tab" data-testid="psp-settings-tab">
      <section className="psp-section">
        <div className="psp-sec-head">Profile</div>
        <label className="psp-field">
          <span>Display name</span>
          <input type="text" value={draft.display_name || ""}
                  data-testid="psp-display-name"
                  onChange={e => setDraft({ ...draft,
                                                      display_name: e.target.value })}/>
        </label>
        <label className="psp-field">
          <span>Bio</span>
          <textarea rows={3} maxLength={280} value={draft.bio || ""}
                        data-testid="psp-bio"
                        onChange={e => setDraft({ ...draft,
                                                            bio: e.target.value })}/>
        </label>
        <label className="psp-field">
          <span>City pin</span>
          <input type="text" value={draft.city_pin || ""}
                  data-testid="psp-city-pin"
                  placeholder="Dubai, Frisco TX, …"
                  onChange={e => setDraft({ ...draft,
                                                      city_pin: e.target.value })}/>
        </label>
        <label className="psp-field">
          <span>Avatar URL</span>
          <input type="text" value={draft.avatar_url || ""}
                  data-testid="psp-avatar-url"
                  onChange={e => setDraft({ ...draft,
                                                      avatar_url: e.target.value })}/>
        </label>
      </section>

      <section className="psp-section">
        <div className="psp-sec-head">Privacy</div>
        <div className="psp-priv-row">
          <div>
            <div className="psp-priv-name">Public profile</div>
            <div className="psp-priv-help">
              Anyone with the link can view your /passport/[id] page.
            </div>
          </div>
          {tog("is_public")}
        </div>
        <div className="psp-priv-row">
          <div>
            <div className="psp-priv-name">Show badges publicly</div>
            <div className="psp-priv-help">
              Badges are listed on your public profile.
            </div>
          </div>
          {tog("show_badges_publicly")}
        </div>
        <div className="psp-priv-row">
          <div>
            <div className="psp-priv-name">Show listening stats</div>
            <div className="psp-priv-help">
              Hours total + top genres show on your public profile.
            </div>
          </div>
          {tog("show_listening_stats_publicly")}
        </div>
        <div className="psp-priv-row">
          <div>
            <div className="psp-priv-name">Show leaderboard position</div>
            <div className="psp-priv-help">
              Your city leaderboard rank is visible to others.
            </div>
          </div>
          {tog("show_leaderboard_position_publicly")}
        </div>
        <div className="psp-priv-row">
          <div>
            <div className="psp-priv-name">Show ambassador level</div>
            <div className="psp-priv-help">
              Your level + points are visible on your public profile.
            </div>
          </div>
          {tog("show_ambassador_level_publicly")}
        </div>
      </section>

      <div className="psp-save-row">
        <button className="psp-btn psp-btn-primary"
                  data-testid="psp-save-settings"
                  disabled={saving} onClick={save}>
          {saving ? "Saving…" : "Save settings"}
        </button>
      </div>
    </div>
  );
}


export default function Passport() {
  const [data, setData] = useState(null);
  const [catalog, setCatalog] = useState([]);
  const [tab, setTab] = useState("badges");
  const [loading, setLoading] = useState(true);
  const [celebrations, setCelebrations] = useState([]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [me, cat, cel] = await Promise.all([
        axios.get(`${API}/passport/me`),
        axios.get(`${API}/passport/badges/catalog`),
        axios.get(`${API}/passport/me/celebrations`).catch(() => ({data: {items: []}})),
      ]);
      setData(me.data);
      setCatalog(cat.data.items || []);
      setCelebrations(cel.data.items || []);
    } catch (e) {
      toast.error("Could not load passport");
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  const dismissCelebration = async () => {
    const levels = celebrations.map(c => c.to_level);
    setCelebrations([]);   // optimistic close
    try {
      await axios.post(`${API}/passport/me/celebrations/ack`, { levels });
    } catch (_) {}
  };

  if (loading || !data) {
    return (
      <div className="psp-page">
        <div className="psp-loading" data-testid="psp-loading">
          Loading passport…
        </div>
      </div>
    );
  }

  return (
    <div className="psp-page" data-testid="psp-page">
      {/* Phase 42-E2.4 — OG meta for the Social Passport. */}
      <OGMeta entityType="passport" entityId="me"
                          title="My RadioLife Passport"
                          description="Collect cities. Earn stamps. Climb the RadioLife leaderboard." />
      {celebrations.length > 0 && (
        <div className="psp-celebration-overlay"
              data-testid="psp-celebration-modal">
          <div className="psp-celebration-card">
            <div className="psp-celebration-burst">
              <Sparkles size={32}/>
            </div>
            <div className="psp-celebration-eyebrow">
              You leveled up to
            </div>
            <div className="psp-celebration-level">
              L{celebrations[celebrations.length - 1].to_level}
              {" · "}
              {celebrations[celebrations.length - 1].rewards?.chip
                ?.replace(/_chip$/, "").replace(/_/g, " ")}
            </div>
            <ul className="psp-celebration-rewards">
              {celebrations.flatMap(c => Object.entries(c.rewards || {})
                  .filter(([k, _v]) => !k.includes("chip"))
                  .map(([k, v]) => (
                    <li key={`${c.to_level}-${k}`}
                          data-testid={`psp-celeb-reward-${k}`}>
                      {k === "bigcoin" && (
                        <span><Star size={12}/> +{v} BigCoin</span>
                      )}
                      {k === "premium_days" && v > 0 && (
                        <span>👑 {v} days of Premium</span>
                      )}
                      {k === "exclusive_channel" && (
                        <span>🎵 Exclusive channel access ({c.rewards.exclusive_channel_days}d)</span>
                      )}
                      {k === "vip_lobby_host_chip" && (
                        <span>★ VIP host chip in lobbies</span>
                      )}
                      {k === "early_access_giveaways" && (
                        <span>✨ Early-access giveaways</span>
                      )}
                    </li>
                  )))}
            </ul>
            <button className="psp-btn psp-btn-primary"
                      data-testid="psp-celeb-continue"
                      onClick={dismissCelebration}>
              Continue
            </button>
          </div>
        </div>
      )}
      <HeroCard data={data}/>
      <nav className="psp-tabs" data-testid="psp-tabs">
        {["badges", "stats", "referrals", "settings"].map(t => (
          <button key={t}
                    className={"psp-tab" + (tab === t ? " is-active" : "")}
                    data-testid={`psp-tab-${t}`}
                    onClick={() => setTab(t)}>
            {t}
          </button>
        ))}
      </nav>
      <div className="psp-tabbody">
        {tab === "badges" && (
          <BadgesTab data={data} catalog={catalog} onRefresh={load}/>
        )}
        {tab === "stats" && <StatsTab data={data}/>}
        {tab === "referrals" && (
          <ReferralsTab data={data} onUpdate={load}/>
        )}
        {tab === "settings" && (
          <SettingsTab data={data}
                            onUpdate={(s) => setData({ ...data, settings: s })}/>
        )}
      </div>
    </div>
  );
}
