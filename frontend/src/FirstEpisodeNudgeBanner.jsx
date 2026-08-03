// Phase 36e Turn 3 — First-Episode Publish Nudge banner.
// Renders on the Creator dashboard when /nudge-status says qualifies=true.
// "Pause nudges" link flips the persistent setting; banner disappears.
import React, {useEffect, useState, useCallback} from "react";
import {Link} from "react-router-dom";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

export function FirstEpisodeNudgeBanner({creatorId}) {
  const [status, setStatus] = useState(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    if (!creatorId) return;
    try {
      const r = await axios.get(
        `${API}/podcasts/creators/${creatorId}/nudge-status`,
        {withCredentials: true});
      setStatus(r.data);
    } catch (_) { setStatus(null); }
  }, [creatorId]);

  useEffect(() => { refresh(); }, [refresh]);

  const pause = async () => {
    setBusy(true);
    try {
      await axios.post(
        `${API}/podcasts/creators/${creatorId}/nudge-status/pause`, {},
        {withCredentials: true});
      await refresh();
    } finally { setBusy(false); }
  };

  if (!status || !status.qualifies) return null;

  return (
    <div data-testid="first-episode-nudge-banner"
              style={{background: "linear-gradient(135deg,#1c1b35,#0d0c1f)",
                          border: "1px solid rgba(245,158,11,0.5)",
                          borderRadius: 12, padding: 16,
                          marginBottom: 16, color: "#fbf3da",
                          display: "flex", alignItems: "center", gap: 16}}>
      <div style={{flex: 1}}>
        <div style={{fontSize: 11, color: "#fbbf24", letterSpacing: 0.6,
                                  textTransform: "uppercase", marginBottom: 4}}>
          Get started
        </div>
        <div style={{fontSize: 14, lineHeight: 1.5}}>
          {status.banner_message ||
            "🎙️ Record your first episode to start building your audience"}
        </div>
      </div>
      <Link to="/creator/studio/new"
                  data-testid="nudge-banner-cta"
                  style={{padding: "9px 16px", borderRadius: 8,
                              background: "#f59e0b", color: "#0a0a0c",
                              textDecoration: "none", fontWeight: 700,
                              fontSize: 13, whiteSpace: "nowrap"}}>
        Record episode →
      </Link>
      <button data-testid="nudge-banner-pause"
                      onClick={pause} disabled={busy}
                      style={{padding: "6px 10px", borderRadius: 6,
                                    background: "transparent", color: "#9aa3af",
                                    border: "1px solid #2a2d35", fontSize: 11,
                                    cursor: busy ? "not-allowed" : "pointer"}}>
        {busy ? "Pausing…" : "Pause nudges"}
      </button>
    </div>);
}
