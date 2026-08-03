// AuthCallback — runs only when the URL has a #session_id=... fragment.
// Exchanges it for our HttpOnly cookie via /api/auth/google/session, then
// navigates the user into the app (onboarding if first time, / otherwise).
//
// REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH

import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { Loader2 } from "lucide-react";
import { API, useAuth } from "./AuthContext";

export default function AuthCallback() {
  const navigate = useNavigate();
  const { setUser } = useAuth();
  const hasProcessed = useRef(false);

  useEffect(() => {
    if (hasProcessed.current) return;
    hasProcessed.current = true;
    const hash = window.location.hash || "";
    const m = hash.match(/session_id=([^&]+)/);
    if (!m) { navigate("/login", { replace: true }); return; }
    const session_id = decodeURIComponent(m[1]);
    (async () => {
      try {
        const r = await axios.post(`${API}/auth/google/session`, { session_id });
        setUser(r.data);
        // Wipe the fragment from the URL bar before navigating.
        window.history.replaceState(null, "", window.location.pathname + window.location.search);
        if (!r.data.onboarding_complete) {
          navigate("/onboarding", { replace: true, state: { user: r.data } });
        } else {
          navigate("/", { replace: true, state: { user: r.data } });
        }
      } catch (_e) {
        navigate("/login", { replace: true, state: { authError: "Google sign-in failed" } });
      }
    })();
  }, [navigate, setUser]);

  return (
    <div className="auth-loading" data-testid="auth-callback-loading">
      <Loader2 className="spin" size={32} />
      <p className="mono">SIGNING YOU IN…</p>
    </div>
  );
}
