// /admin/rj-quality — Phase 3.7 RJ Quality Dashboard.
// Lists recent RJ segments with draft + rewritten scripts side-by-side,
// audio player, banned-phrase issue badges, and 3-axis admin rating.

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import {
  ArrowLeft, Loader2, Crown, Volume2, AlertTriangle, Star, Filter, BarChart3, Award,
} from "lucide-react";
import { Toaster, toast } from "sonner";
import { API } from "@/AuthContext";

const PROFILE_COLOR = {
  morning_drive: "#f59e0b",
  lunch:         "#22c55e",
  evening_drive: "#ec4899",
  nightlife:     "#a78bfa",
  chill_late_night: "#06b6d4",
  talk_news:     "#9ca3af",
};

function RatingControl({ segmentId, onRated }) {
  const [scores, setScores] = useState({ naturalness: 4, hinglish: 4, energy: 4 });
  const [submitting, setSubmitting] = useState(false);

  const submit = async () => {
    setSubmitting(true);
    try {
      await axios.post(
        `${API}/admin/rj-quality/${segmentId}/rate?` +
        `naturalness_1_5=${scores.naturalness}&` +
        `hinglish_quality_1_5=${scores.hinglish}&` +
        `radio_energy_1_5=${scores.energy}`
      );
      toast.success("Rated");
      onRated?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Rating failed");
    } finally { setSubmitting(false); }
  };
  return (
    <div className="rate-row" data-testid={`rate-row-${segmentId}`}>
      {["naturalness","hinglish","energy"].map((k) => (
        <div key={k} className="rate-axis">
          <span className="mono dim">{k.toUpperCase()}</span>
          <div className="rate-stars">
            {[1,2,3,4,5].map((n) => (
              <button
                key={n}
                type="button"
                className={`rate-star ${scores[k] >= n ? "is-on" : ""}`}
                onClick={() => setScores((s) => ({ ...s, [k]: n }))}
                data-testid={`rate-${segmentId}-${k}-${n}`}
              >
                <Star size={12} fill={scores[k] >= n ? "#ffd700" : "none"} />
              </button>
            ))}
          </div>
        </div>
      ))}
      <button
        type="button"
        className="rate-submit"
        onClick={submit}
        disabled={submitting}
        data-testid={`rate-submit-${segmentId}`}
      >
        {submitting ? <Loader2 className="spin" size={12} /> : "SAVE"}
      </button>
    </div>
  );
}

export default function AdminRjQuality() {
  const [data, setData] = useState(null);
  const [dash, setDash] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filterProfile, setFilterProfile] = useState("all");
  const [refreshKey, setRefreshKey] = useState(0);

  const fetchAll = async () => {
    setLoading(true);
    try {
      const [recent, dashboard] = await Promise.all([
        axios.get(`${API}/admin/rj-quality/recent?limit=50` +
                  (filterProfile !== "all" ? `&profile=${filterProfile}` : "")),
        axios.get(`${API}/admin/rj-quality/dashboard`),
      ]);
      setData(recent.data);
      setDash(dashboard.data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not load dashboard");
    } finally { setLoading(false); }
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { fetchAll(); }, [filterProfile, refreshKey]);

  const flagWinning = async (segId) => {
    try {
      await axios.post(`${API}/admin/rj-quality/${segId}/winning?winning=true`);
      toast.success("Flagged as winning take");
      setRefreshKey((k) => k + 1);
    } catch (e) {
      toast.error("Flag failed");
    }
  };

  if (loading || !data) {
    return (
      <div className="rj-quality-shell">
        <div className="loading-block"><Loader2 className="spin" size={32} /></div>
      </div>
    );
  }

  const profileFilters = ["all", ...(dash?.personality_profiles?.map(p => p.slug) || [])];

  return (
    <div className="rj-quality-shell" data-testid="rj-quality-page">
      <Toaster theme="dark" position="bottom-right" richColors />

      <header className="rjq-head">
        <Link to="/admin" className="back-link mono" data-testid="rjq-back">
          <ArrowLeft size={14} /> BACK TO ADMIN
        </Link>
        <div className="rjq-title">
          <Volume2 size={20} />
          <span>RJ Quality Dashboard</span>
          <span className="mono dim">PHASE 3.7</span>
        </div>
      </header>

      {/* Hero stats */}
      <section className="rjq-hero" data-testid="rjq-hero">
        <div className="hero-tile">
          <BarChart3 size={20} />
          <div>
            <div className="big">{dash?.total_segments || 0}</div>
            <div className="mono dim">SEGMENTS TRACKED</div>
          </div>
        </div>
        <div className="hero-tile">
          <Crown size={20} />
          <div>
            <div className="big">{dash?.winning_takes || 0}</div>
            <div className="mono dim">WINNING TAKES</div>
          </div>
        </div>
        <div className="hero-tile">
          <AlertTriangle size={20} />
          <div>
            <div className="big">{dash?.common_issues_24h?.length || 0}</div>
            <div className="mono dim">ISSUE PATTERNS / 24H</div>
          </div>
        </div>
        <div className="hero-tile">
          <Award size={20} />
          <div>
            <div className="big">{dash?.top_rated_voices?.length || 0}</div>
            <div className="mono dim">RATED VOICES</div>
          </div>
        </div>
      </section>

      {/* Top issues + voices */}
      {(dash?.common_issues_24h?.length > 0 || dash?.top_rated_voices?.length > 0) && (
        <section className="rjq-twocol">
          {dash?.common_issues_24h?.length > 0 && (
            <div className="rjq-card" data-testid="common-issues">
              <h3>Common script issues (24h)</h3>
              <ul>
                {dash.common_issues_24h.map((i, n) => (
                  <li key={n}>
                    <span className="issue-count mono">×{i.count}</span>
                    <code>{i.phrase}</code>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {dash?.top_rated_voices?.length > 0 && (
            <div className="rjq-card" data-testid="top-voices">
              <h3>Top rated voices</h3>
              <ul>
                {dash.top_rated_voices.map((v, n) => (
                  <li key={n}>
                    <code className="mono">{v.voice_key}</code>
                    <span>nat <b>{v.avg_naturalness}</b> · hindi <b>{v.avg_hinglish}</b> · energy <b>{v.avg_energy}</b></span>
                    <span className="mono dim">({v.rating_count} ratings)</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}

      {/* Personality filter */}
      <section className="rjq-filters" data-testid="rjq-filters">
        <Filter size={12} />
        <span className="mono dim">PROFILE:</span>
        {profileFilters.map((p) => (
          <button
            key={p}
            type="button"
            className={`rjq-chip ${filterProfile === p ? "is-on" : ""}`}
            onClick={() => setFilterProfile(p)}
            data-testid={`filter-profile-${p}`}
            style={{ "--chip-color": PROFILE_COLOR[p] || "#888" }}
          >{p}</button>
        ))}
      </section>

      <section className="rjq-list" data-testid="rjq-list">
        <div className="rjq-list-head mono dim">
          {data.total} recent breaks · sorted newest first
        </div>
        {(data.items || []).map((qa) => {
          const profileColor = PROFILE_COLOR[qa.personality_profile_slug] || "#888";
          const segUrl = `${API}${qa.final_audio_url}`;
          const hasIssues = qa.banned_phrase_hits?.length > 0;
          return (
            <article
              className={`qa-row ${qa.is_winning_take ? "is-winning" : ""}`}
              key={qa.segment_id}
              data-testid={`qa-row-${qa.segment_id}`}
            >
              <header className="qa-row-head">
                <div className="qa-meta">
                  <span className="mono dim">{new Date(qa.created_at).toLocaleString()}</span>
                  <span className="profile-tag mono" style={{ background: profileColor }}>
                    {qa.personality_profile_slug}
                  </span>
                  <span className="mono dim">{qa.channel_slug}</span>
                  <span className="mono dim">{qa.voice_key} · {qa.format}</span>
                  <span className="mono dim">{qa.market}</span>
                  {qa.is_winning_take && (
                    <span className="winner-tag mono"><Crown size={11}/> WINNER</span>
                  )}
                </div>
                <div className="qa-actions">
                  {!qa.is_winning_take && (
                    <button
                      type="button"
                      className="qa-action mono"
                      onClick={() => flagWinning(qa.segment_id)}
                      data-testid={`flag-winning-${qa.segment_id}`}
                    >
                      <Crown size={11}/> WINNING
                    </button>
                  )}
                </div>
              </header>

              {hasIssues && (
                <div className="qa-issues" data-testid={`qa-issues-${qa.segment_id}`}>
                  <AlertTriangle size={11}/>
                  <span className="mono">BANNED PHRASES DETECTED:</span>
                  {qa.banned_phrase_hits.map((b, n) => (
                    <code key={n}>{b}</code>
                  ))}
                </div>
              )}

              <div className="qa-scripts">
                <div className="qa-script">
                  <div className="mono dim">STAGE 1 · DRAFT</div>
                  <p>{qa.initial_script || "—"}</p>
                </div>
                <div className="qa-script qa-script-final">
                  <div className="mono dim">STAGE 2 · NATURALNESS REWRITE</div>
                  <p>{qa.rewritten_script || "—"}</p>
                </div>
              </div>

              <audio
                controls
                preload="none"
                src={segUrl}
                className="qa-audio"
                data-testid={`qa-audio-${qa.segment_id}`}
              />

              <RatingControl
                segmentId={qa.segment_id}
                onRated={() => setRefreshKey((k) => k + 1)}
              />
            </article>
          );
        })}
      </section>
    </div>
  );
}
