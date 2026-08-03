// ReactivationBanner.jsx — Phase 12b
// Slim banner shown at top of the player when the signed-in user's
// churn band is at_risk / dormant.  Dismissable; respects the
// `dismissable_until` payload + server-side dismiss endpoint.
import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { X, AlertCircle } from "lucide-react";
import { API, useAuth } from "@/AuthContext";

axios.defaults.withCredentials = true;

const COLOR_BY_TYPE = {
  dormant: "#ff4d4d",
  at_risk: "#fdb756",
};

export default function ReactivationBanner() {
  const { user } = useAuth();
  const [prompt, setPrompt] = useState(null);
  const [hidden, setHidden] = useState(false);

  const fetchPrompt = useCallback(async () => {
    if (!user) return;
    try {
      const r = await axios.get(`${API}/me/reactivation_prompt`);
      // 204 → axios resolves with empty body; ignore
      if (r.status === 200 && r.data) setPrompt(r.data);
    } catch (_e) { /* silent */ }
  }, [user]);

  useEffect(() => { fetchPrompt(); }, [fetchPrompt]);

  if (!user || !prompt || hidden) return null;
  const color = COLOR_BY_TYPE[prompt.prompt_type] || "#fdb756";

  const dismiss = async () => {
    setHidden(true);
    try {
      await axios.post(`${API}/me/reactivation_prompt/dismiss`);
    } catch (_e) {}
  };

  return (
    <div data-testid="reactivation-banner"
            style={{ position: "sticky", top: 0, zIndex: 30,
                        background: "#15151c",
                        borderBottom: `2px solid ${color}`,
                        padding: "10px 16px",
                        display: "flex", alignItems: "center",
                        gap: 12, fontSize: 13, color: "#e4e4ec",
                        boxShadow: "0 2px 12px rgba(0,0,0,0.6)" }}>
      <AlertCircle size={16} color={color} />
      <div style={{ flex: 1 }}>
        <strong style={{ color }}>{prompt.headline}</strong>
        <span style={{ color: "#aaaab0", marginLeft: 8 }}>{prompt.body}</span>
      </div>
      <a href={prompt.cta_href}
            data-testid="reactivation-cta"
            style={{ background: color, color: "#0a0a0f", padding: "6px 12px",
                        borderRadius: 999, fontWeight: 700, fontSize: 12,
                        textDecoration: "none" }}>
        {prompt.cta_label}
      </a>
      <button type="button" onClick={dismiss}
                   data-testid="reactivation-dismiss"
                   aria-label="Dismiss"
                   style={{ background: "transparent", border: "none",
                              color: "#888892", cursor: "pointer",
                              padding: 4 }}>
        <X size={16} />
      </button>
    </div>
  );
}
