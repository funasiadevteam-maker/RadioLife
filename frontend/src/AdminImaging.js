// AdminImaging.js — Phase 3.8 Sonic Branding & Stations dashboard.
// Admin-only. Lists FUUSIC + FunAsia DFW stations with branding + asset
// generation status + a "Regenerate" CTA per station.
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import { Loader2, RefreshCcw, ChevronRight, Radio, Music2 } from "lucide-react";
import "./AdminImaging.css";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
axios.defaults.withCredentials = true;

function BrandWordPill({ word }) {
  return <span className="brand-word">{word}</span>;
}

function StationCard({ st, onRegenerate, busy }) {
  const counts = st.asset_counts || {};
  const total = counts.total || 0;
  const ready = counts.ready || 0;
  const pct = total ? Math.round((ready / total) * 100) : 0;
  return (
    <div className="img-station-card" data-testid={`station-card-${st.station_slug}`}>
      <div className="img-station-head">
        <div className="img-station-flag">{st.market === "dfw" ? "🇺🇸" : "🇦🇪"}</div>
        <div className="img-station-title">
          <div className="img-station-name" data-testid={`station-name-${st.station_slug}`}>{st.station_name}</div>
          <div className="img-station-tag">{st.tagline}</div>
        </div>
        <Link
          to={`/admin/imaging/${st.station_slug}/assets`}
          className="img-station-cta"
          data-testid={`open-assets-${st.station_slug}`}
        >
          Manage <ChevronRight size={14} />
        </Link>
      </div>

      <div className="img-station-meta">
        <div><span className="meta-label">PRIMARY VOICE</span><span className="meta-val">{st.primary_voice_key}</span></div>
        <div><span className="meta-label">SECONDARY VOICE</span><span className="meta-val">{st.secondary_voice_key}</span></div>
        <div><span className="meta-label">STYLE</span><span className="meta-val">{st.imaging_style_preset}</span></div>
      </div>

      <div className="brand-words">
        {(st.brand_words || []).slice(0, 8).map((w) => <BrandWordPill key={w} word={w} />)}
      </div>

      <div className="img-station-progress">
        <div className="progress-row">
          <span className="progress-label">Imaging library generated</span>
          <span className="progress-value">{ready} / {total} ({pct}%)</span>
        </div>
        <div className="progress-bar">
          <div className="progress-bar-fill" style={{ width: `${pct}%` }} />
        </div>
        <div className="progress-tag-row">
          <span className="progress-tag" data-testid={`station-pending-${st.station_slug}`}>{counts.pending || 0} pending</span>
          <span className="progress-tag progress-tag-ready">{ready} ready</span>
          {counts.failed ? <span className="progress-tag progress-tag-failed">{counts.failed} failed</span> : null}
        </div>
      </div>

      <button
        type="button"
        className="img-regenerate-btn"
        onClick={() => onRegenerate(st.station_slug)}
        disabled={busy === st.station_slug}
        data-testid={`regenerate-${st.station_slug}`}
      >
        {busy === st.station_slug ? <Loader2 className="spin" size={14} /> : <RefreshCcw size={14} />}
        {busy === st.station_slug ? " Kicking off..." : " Regenerate library"}
      </button>
    </div>
  );
}

export default function AdminImaging() {
  const [stations, setStations] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(null);

  const fetchStations = async () => {
    try {
      const r = await axios.get(`${API}/admin/imaging/stations`);
      setStations(r.data.stations || []);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not load stations");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStations();
    const t = setInterval(fetchStations, 8000);  // poll generation progress
    return () => clearInterval(t);
  }, []);

  const regenerate = async (slug) => {
    setBusy(slug);
    try {
      await axios.post(`${API}/admin/imaging/${slug}/regenerate?limit=15`);
      toast.success(`Generation kicked off for ${slug}. Audio appears as it completes.`);
      setTimeout(fetchStations, 1500);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not start regeneration");
    } finally {
      setBusy(null);
    }
  };

  if (loading || !stations) {
    return (
      <div className="admin-img-wrap" data-testid="imaging-loading">
        <Loader2 className="spin" size={28} />
      </div>
    );
  }

  return (
    <div className="admin-img-wrap" data-testid="admin-imaging-page">
      <header className="admin-img-header">
        <div>
          <h1 data-testid="imaging-title"><Radio size={24} style={{ marginRight: 10, verticalAlign: "-4px" }} />Station Imaging Engine</h1>
          <p>Sonic branding, station IDs, daypart openers, music beds, and sweepers — produced and rotated automatically.</p>
        </div>
        <div className="admin-img-pills">
          <Link to="/admin/rj-quality" className="admin-pill"><Music2 size={12} /> RJ Quality</Link>
          <Link to="/audition" className="admin-pill">Audition</Link>
        </div>
      </header>

      <section className="img-stations-grid" data-testid="imaging-stations-grid">
        {stations.map((st) => (
          <StationCard key={st.station_slug} st={st} onRegenerate={regenerate} busy={busy} />
        ))}
      </section>

      <footer className="admin-img-footer">
        <p>Phase 3.8 — every asset is loudness-normalized to <strong>-14 LUFS</strong> with a <strong>-1 dBFS</strong> true-peak ceiling. Click "Regenerate" to start TTS + Sound Generation for the first batch. Larger batches can be queued from the per-station screen.</p>
      </footer>
    </div>
  );
}
