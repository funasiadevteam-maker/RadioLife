// Phase 13e — Apple SIWA return handler.
// Reads ?session_token=...&user_id=... from query string and finalises auth.
import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { Loader2 } from "lucide-react";
import { API, useAuth } from "./AuthContext";

export default function AppleAuthReturn() {
  const navigate = useNavigate();
  const { setUser } = useAuth();
  const handled = useRef(false);

  useEffect(() => {
    if (handled.current) return;
    handled.current = true;
    const q = new URLSearchParams(window.location.search);
    const session_token = q.get("session_token");
    const user_id = q.get("user_id");
    if (!session_token) {
      navigate("/login",
                  { replace: true,
                    state: { authError: "Apple sign-in did not return a session." }});
      return;
    }
    (async () => {
      try {
        // Persist the bearer token + fetch /me to refresh user context.
        localStorage.setItem("bigfm_session_token", session_token);
        axios.defaults.headers.common.Authorization =
            `Bearer ${session_token}`;
        const r = await axios.get(`${API}/auth/me`);
        setUser(r.data);
        window.history.replaceState(null, "",
            window.location.pathname);
        if (!r.data?.onboarding_complete) {
          navigate("/onboarding",
                      { replace: true, state: { user: r.data } });
        } else {
          navigate("/", { replace: true, state: { user: r.data } });
        }
      } catch (_e) {
        navigate("/login",
                    { replace: true,
                      state: { authError: "Apple sign-in failed." }});
      }
    })();
  }, [navigate, setUser]);

  return (
    <div className="auth-loading" data-testid="apple-auth-return-loading">
      <Loader2 className="spin" size={32} />
      <p className="mono">SIGNING YOU IN WITH APPLE…</p>
    </div>
  );
}
