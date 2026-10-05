// Quota-guard banner — shows admins when the AI DJ has degraded to
// music-only (e.g. the LLM provider is out of credits). Polls the backend
// rj-health signal every 60s and renders only when degraded.
import { useEffect, useState } from "react";
import axios from "axios";
import { AlertTriangle } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

export default function RjHealthBanner() {
  const [h, setH] = useState(null);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const { data } = await axios.get(`${API}/admin/radio/rj-health`,
          { withCredentials: true });
        if (alive) setH(data);
      } catch (_) { /* non-admins / transient — stay silent */ }
    };
    load();
    const t = setInterval(load, 60_000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  if (!h?.degraded) return null;

  return (
    <div
      data-testid="rj-health-banner"
      className="mb-4 rounded-2xl bg-red-500/15 border border-red-500/40 p-4
                 flex items-start gap-3 text-sm"
    >
      <AlertTriangle className="w-5 h-5 text-red-400 shrink-0 mt-0.5" />
      <div className="min-w-0">
        <div className="font-bold text-red-300">AI DJ paused — music only</div>
        <div className="mt-0.5 text-red-200/90">
          {h.message
            || "Voiceovers are being skipped. Add LLM credits to restore the AI DJ."}
        </div>
        {h.last_error && (
          <div className="mt-1 text-xs text-red-300/60 truncate" title={h.last_error}>
            Last error: {h.last_error}
          </div>
        )}
      </div>
    </div>
  );
}
