// Phase 8b — Public game landing page. Anonymous-playable: no auth needed
// to view the landing card; if user is signed-in we deep-link to GamePlayer,
// otherwise we prompt them to sign in.
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import axios from "axios";
import { Loader2, Gift, ChevronRight, AlertTriangle } from "lucide-react";
import { useAuth, API } from "@/AuthContext";
import "./PlayAndWin.css";

export default function PublicLanding() {
  const { slug } = useParams();
  const { user, loading: authLoading } = useAuth();
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const r = await axios.get(`${API}/public/game/${slug}`);
        setData(r.data);
      } catch (e) {
        setErr(e?.response?.data?.detail || "Landing page not found");
      }
    })();
  }, [slug]);

  if (err) {
    return (
      <div className="public-landing-shell" data-testid="public-landing-error">
        <div className="public-landing-error">
          <AlertTriangle size={40} />
          <h1>That campaign is no longer active.</h1>
          <p>Head back to RadioLife to find more games to play.</p>
          <Link to="/" className="public-landing-cta">Go to RadioLife</Link>
        </div>
      </div>
    );
  }
  if (!data) {
    return <div className="paw-loading"><Loader2 size={28} className="spin" /></div>;
  }

  const brand = data.brand_colors_json?.primary || "#ff2d95";
  const qrUrl = `${API}/public/game/${slug}/qr.png`;

  return (
    <div className="public-landing-shell" data-testid="public-landing"
            data-slug={slug}
            style={{ "--brand": brand }}>
      <div className="public-landing-card" data-testid="public-landing-card">
        <div className="pl-sponsor-row">
          {data.sponsor_logo_url && (
            <img src={data.sponsor_logo_url} alt={data.sponsor_name}
                  className="pl-sponsor-logo" />
          )}
          <span className="mono dim">PRESENTED BY {data.sponsor_name?.toUpperCase()}</span>
        </div>
        <h1 data-testid="public-landing-title">{data.title}</h1>
        <p className="pl-desc">{data.description || "Play & win on RadioLife"}</p>
        <div className="pl-prizes" data-testid="public-landing-prizes">
          <div className="mono dim">PRIZES UP FOR GRABS</div>
          {(data.prizes || []).slice(0, 6).map((p, i) => (
            <div className="pl-prize-row" key={i}>
              <Gift size={14} />
              <span>{p.title}</span>
              {!p.in_stock && <span className="pl-out">SOLD OUT</span>}
            </div>
          ))}
        </div>
        <div className="pl-actions">
          {authLoading ? (
            <Loader2 className="spin" size={16} />
          ) : user ? (
            <Link to={`/play-and-win/${data.campaign_id}`}
                  className="public-landing-cta"
                  data-testid="public-landing-play-btn">
              Play now <ChevronRight size={16} />
            </Link>
          ) : (
            <Link to={`/login?redirect=${encodeURIComponent(`/play-and-win/${data.campaign_id}`)}`}
                  className="public-landing-cta"
                  data-testid="public-landing-signin-btn">
              Sign in to play <ChevronRight size={16} />
            </Link>
          )}
        </div>
        <div className="pl-qr-block">
          <img src={qrUrl} alt="QR to this game" className="pl-qr"
                data-testid="public-landing-qr" />
          <div className="mono dim">SCAN ON YOUR PHONE</div>
        </div>
      </div>
      <div className="pl-footer mono">
        bigfm.link/{slug} · no purchase necessary · odds vary by prize tier
      </div>
    </div>
  );
}
