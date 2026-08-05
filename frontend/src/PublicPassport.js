import React, { useEffect, useState, useCallback } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import {
  Award, Star, Sparkles, Trophy, MapPin, Clock, Copy, Share2,
  AlertCircle, ArrowLeft,
} from "lucide-react";
import "@/Passport.css";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

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


function PublicBadgeCard({ badge }) {
  return (
    <div className="psp-badge-card is-earned"
          data-testid={`pub-badge-${badge.badge_id}`}>
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
        <Sparkles size={16} className="psp-earned-tick"/>
      </div>
      <div className="psp-badge-desc">
        Earned {new Date(badge.earned_at).toLocaleDateString()}
      </div>
    </div>
  );
}


function NotFound() {
  return (
    <div className="psp-page" data-testid="pub-passport-404">
      <div className="psp-empty">
        <AlertCircle size={28}/>
        <div className="psp-empty-title">Profile not available</div>
        <div className="psp-empty-sub">
          This listener hasn&apos;t made their profile public, or the link is invalid.
        </div>
        <div style={{marginTop: 16}}>
          <a href="/" className="psp-btn">
            <ArrowLeft size={12}/> Back to RadioLife
          </a>
        </div>
      </div>
    </div>
  );
}


export default function PublicPassport() {
  const { userId } = useParams();
  const [params] = useSearchParams();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/passport/${userId}`,
                                          { withCredentials: false });
      setData(r.data);
    } catch (e) {
      setError(e.response?.status || "error");
    } finally {
      setLoading(false);
    }
  }, [userId]);

  useEffect(() => { load(); }, [load]);

  // Phase 10a/b — capture `?ref=` on this public landing
  useEffect(() => {
    const rc = params.get("ref");
    if (rc) {
      // App.js ReferralCapture also fires; redundant axios call is cheap.
      const ck = document.cookie.split("; ")
        .find(c => c.startsWith("bigfm_ref="));
      if (!ck || !ck.includes(rc)) {
        axios.post(`${API}/referrals/landing`,
                      { ref_code: rc, landing_path: `/passport/${userId}` },
                      { withCredentials: true }).catch(() => {});
      }
    }
  }, [params, userId]);

  if (loading) {
    return (
      <div className="psp-page">
        <div className="psp-loading" data-testid="pub-passport-loading">
          Loading…
        </div>
      </div>
    );
  }
  if (error || !data) return <NotFound/>;

  const share = async () => {
    const u = `${window.location.origin}/passport/${userId}?ref=${data.referral_code || ""}`;
    if (navigator.share) {
      try { await navigator.share({ url: u, title: `Join ${data.display_name} on RadioLife` }); }
      catch (_) {}
    } else {
      navigator.clipboard.writeText(u);
      toast.success("Link copied");
    }
  };
  const copyRef = () => {
    const u = `${window.location.origin}/?ref=${data.referral_code || ""}`;
    navigator.clipboard.writeText(u);
    toast.success("Referral link copied");
  };

  // Group badges by category
  const byCat = {};
  (data.badges || []).forEach(b => {
    (byCat[b.category] = byCat[b.category] || []).push(b);
  });

  return (
    <div className="psp-page" data-testid="pub-passport-page">
      <div className="psp-hero" data-testid="pub-passport-hero">
        <div className="psp-avatar"
              style={{ background: TIER_GRADIENT.diamond }}>
          {data.avatar_url
              ? <img src={data.avatar_url} alt=""/>
              : <span>{data.avatar_initial}</span>}
        </div>
        <div className="psp-hero-body">
          <div className="psp-hero-name">
            {data.display_name}
            {data.is_annual_subscriber && (
              <span className="psp-city-pin"
                    style={{background: "rgba(255, 215, 94, .12)",
                              borderColor: "rgba(255, 215, 94, .35)",
                              color: "#ffd75e"}}>
                ✨ ANNUAL
              </span>
            )}
            {data.city_pin && (
              <span className="psp-city-pin">
                <MapPin size={12}/>{data.city_pin}
              </span>
            )}
          </div>
          {data.bio && (
            <div className="psp-hero-bio">{data.bio}</div>
          )}
          <div className="psp-hero-stats">
            {data.ambassador && (
              <div>
                <span className="psp-stat-num">L{data.ambassador.level}</span>
                <span className="psp-stat-lbl">{data.ambassador.level_name}</span>
              </div>
            )}
            <div>
              <span className="psp-stat-num">{data.badges_total}</span>
              <span className="psp-stat-lbl">badges</span>
            </div>
            {data.listening_stats && (
              <div>
                <span className="psp-stat-num">
                  {data.listening_stats.hours_total}h
                </span>
                <span className="psp-stat-lbl">listened</span>
              </div>
            )}
            {data.ambassador && (
              <div>
                <span className="psp-stat-num">{data.ambassador.points}</span>
                <span className="psp-stat-lbl">points</span>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Refer-and-earn CTA */}
      {data.referral_code && (
        <div className="psp-section" data-testid="pub-passport-refer-cta">
          <div className="psp-funnel" style={{justifyContent: "space-between"}}>
            <div>
              <div className="psp-feed-name">
                Refer &amp; earn <strong style={{color: "#ffd75e"}}>100 BigCoin</strong>
              </div>
              <div className="psp-feed-date">
                Sign up via {data.display_name}&apos;s link — they get 100 BC when you complete onboarding.
              </div>
            </div>
            <div className="psp-actions">
              <button className="psp-btn"
                        data-testid="pub-passport-copy-ref" onClick={copyRef}>
                <Copy size={12}/> Copy
              </button>
              <button className="psp-btn psp-btn-ghost"
                        data-testid="pub-passport-share-ref" onClick={share}>
                <Share2 size={12}/> Share
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Badge wall by category */}
      {data.badges && data.badges.length > 0 && (
        Object.entries(byCat).map(([cat, items]) => (
          <section className="psp-section" key={cat}
                      data-testid={`pub-passport-cat-${cat}`}>
            <div className="psp-sec-head">
              <Trophy size={14}/> {cat}
              <span className="psp-sec-count">{items.length}</span>
            </div>
            <div className="psp-badge-grid">
              {items.map(b => <PublicBadgeCard key={b.badge_id} badge={b}/>)}
            </div>
          </section>
        ))
      )}

      {(!data.badges || data.badges.length === 0) && (
        <div className="psp-empty">
          <Award size={24}/>
          <div className="psp-empty-title">No badges shown</div>
          <div className="psp-empty-sub">
            {data.display_name} hasn&apos;t opted to display badges publicly.
          </div>
        </div>
      )}
    </div>
  );
}
