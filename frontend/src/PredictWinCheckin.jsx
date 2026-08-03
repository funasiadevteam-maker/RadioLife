/** Sub-Phase E3 — Predict & Win check-in landing page.
 *
 * Route: `/predict-win/checkin?campaign={id}&token={token}`
 *
 * The TV's QR encodes this URL.  When a listener scans it on their
 * phone we:
 *   1. Require auth — if not logged in, stash the deep-link payload in
 *        localStorage and bounce to `/login?next=/predict-win/checkin?…`.
 *   2. POST /api/predict-win/checkin to redeem the token.  Backend
 *        returns `venue_checkin_id`.
 *   3. Forward to `/predict-win` with the campaign + checkin id encoded
 *        in the URL hash so the Active tab can auto-open the Enter modal.
 */
/* eslint-disable react-hooks/set-state-in-effect, react-hooks/purity */
import React, { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import axios from "axios";
import { Loader2, CheckCircle2, AlertCircle, QrCode } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
axios.defaults.withCredentials = true;

const PENDING_KEY = "bigfm.predict_win.pending_checkin";

export default function PredictWinCheckin() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [phase, setPhase] = useState("redeeming");   // redeeming|success|error|auth_required
  const [err, setErr]      = useState(null);
  const [result, setResult] = useState(null);

  useEffect(() => {
    const campaign = params.get("campaign");
    const token      = params.get("token");
    if (!campaign || !token) {
      setPhase("error");
      setErr("Missing campaign or token. Re-scan the venue QR.");
      return;
    }
    (async () => {
      try {
        // Auth check first.  /api/auth/me returns 200 if logged in.
        await axios.get(`${API}/auth/me`);
      } catch (_) {
        // Not logged in — stash the payload and route to login.
        try {
          localStorage.setItem(PENDING_KEY,
            JSON.stringify({ campaign, token, at: Date.now() }));
        } catch (_e) { /* private mode */ }
        const next = encodeURIComponent(
          `/predict-win/checkin?campaign=${campaign}&token=${token}`);
        setPhase("auth_required");
        setTimeout(() => navigate(`/login?next=${next}`), 1200);
        return;
      }
      try {
        const r = await axios.post(`${API}/predict-win/checkin`,
          { campaign_id: campaign, token });
        setResult(r.data); setPhase("success");
        // Forward to /predict-win with the checkin baked into the hash
        // so the Active card auto-opens the Enter modal pre-loaded
        // with the venue_checkin_id.
        const hash =
          `#checkin=${r.data.venue_checkin_id}` +
          `&campaign=${campaign}`;
        setTimeout(() => navigate(`/predict-win${hash}`), 1100);
      } catch (e) {
        setPhase("error");
        const d = e.response?.data?.detail;
        setErr(d?.message || d?.code || e.message || "Check-in failed.");
      }
    })();
  }, [params, navigate]);

  return (
    <div data-testid="predict-win-checkin-page"
            data-phase={phase}
            style={{ minHeight: "100vh", display: "grid",
                        placeItems: "center", color: "#fff",
                        background: "linear-gradient(135deg, #00d9ff1f, #05080d 60%)",
                        fontFamily: "Inter, system-ui", padding: 40 }}>
      <div style={{ textAlign: "center", maxWidth: 480 }}>
        <div style={{ marginBottom: 22 }}>
          {phase === "redeeming" && <Loader2 size={56} className="spin"
                                                                    color="#00d9ff" />}
          {phase === "success"      && <CheckCircle2 size={56} color="#22c55e"/>}
          {phase === "auth_required" && <QrCode size={56} color="#fbbf24"/>}
          {phase === "error"          && <AlertCircle size={56} color="#f87171"/>}
        </div>
        <h1 style={{ fontSize: 28, fontWeight: 800, marginBottom: 10 }}
              data-testid="checkin-status-title">
          {phase === "redeeming"      && "Checking you in…"}
          {phase === "success"          && "You're in!"}
          {phase === "auth_required" && "Sign in to continue"}
          {phase === "error"              && "Couldn't check you in"}
        </h1>
        <div style={{ color: "#9aa3af", lineHeight: 1.5,
                                fontSize: 15, marginBottom: 18 }}>
          {phase === "redeeming"      && "Confirming the venue QR token…"}
          {phase === "success" && (
            <>Your venue check-in is valid for 30 minutes. Locking in your
            pick now…</>)}
          {phase === "auth_required" && (
            <>We'll bring you back to this campaign right after you log in.</>)}
          {phase === "error" && (err || "Tap retry from the venue's TV.")}
        </div>
        {phase === "error" && (
          <button onClick={() => window.location.reload()}
                          data-testid="checkin-retry-btn"
                          style={{ background: "#00d9ff", color: "#062533",
                                      fontWeight: 700, padding: "10px 22px",
                                      borderRadius: 999, border: "none",
                                      cursor: "pointer" }}>Retry</button>)}
        {result && (
          <div data-testid="checkin-success-meta"
                  style={{ marginTop: 10, fontFamily: "monospace",
                              color: "#475569", fontSize: 11 }}>
            checkin_id: {result.venue_checkin_id}
          </div>)}
      </div>
      <style>{`
        @keyframes spin360 { from { transform: rotate(0deg); }
                                          to     { transform: rotate(360deg); } }
        .spin { animation: spin360 1s linear infinite; }
      `}</style>
    </div>);
}
