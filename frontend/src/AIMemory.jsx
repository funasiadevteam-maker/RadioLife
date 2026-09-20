/** Phase 39 Session 7 — /me/ai-memory page. */
import React, { useEffect, useState } from "react";
import axios from "axios";
import { Brain, Eye } from "lucide-react";

const API = process.env.REACT_APP_BACKEND_URL || "";

export default function AIMemory() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const r = await axios.get(`${API}/personas/memory_summary`,
                                  { withCredentials: true });
        setData(r.data);
      } catch (e) { /* silent */ }
      setLoading(false);
    })();
  }, []);

  return (
    <div data-testid="ai-memory-page"
         style={{ maxWidth: 760, margin: "0 auto", padding: 24 }}>
      <div data-testid="ai-memory-watermark"
           style={{ background: "rgba(245,158,11,0.1)", border: "1px dashed #f59e0b",
                    padding: "8px 14px", borderRadius: 6, color: "#f59e0b",
                    fontSize: 12, textAlign: "center", letterSpacing: 1,
                    fontWeight: 700, marginBottom: 18 }}>
        DRAFT — pending legal sign-off
      </div>
      <h1 style={{ color: "#fff", fontSize: 22, fontWeight: 700, margin: "0 0 14px",
                   display: "flex", alignItems: "center", gap: 8 }}>
        <Brain size={20} color="#8b5cf6" /> What FUUSIC has learned about you
      </h1>
      {loading ? (
        <div style={{ color: "#9aa3af", padding: 24 }}>Loading…</div>
      ) : !data ? (
        <div style={{ color: "#9aa3af", padding: 24 }}>No summary yet.</div>
      ) : (
        <>
          <p data-testid="ai-memory-summary"
             style={{ background: "#1f2937", color: "#cbd5e1", padding: 18,
                      borderRadius: 12, lineHeight: 1.6, fontSize: 15 }}>
            {data.summary_text}
          </p>
          <div style={{ display: "flex", gap: 12, marginTop: 14, color: "#9aa3af",
                        fontSize: 12 }}>
            <span data-testid="ai-memory-places">
              Places: {data.frequent_places_count}
            </span>
            <span data-testid="ai-memory-patterns">
              Patterns: {data.route_patterns_count}
            </span>
            {data.cached && (
              <span data-testid="ai-memory-cached" style={{ color: "#10b981" }}>
                cached
              </span>
            )}
          </div>
          <a href="/privacy" data-testid="ai-memory-forget-cta"
             style={{ display: "inline-flex", alignItems: "center", gap: 6,
                      marginTop: 18, color: "#ef4444",
                      border: "1px solid #ef4444", padding: "8px 14px",
                      borderRadius: 6, textDecoration: "none",
                      fontSize: 13, fontWeight: 600 }}>
            <Eye size={14} /> Forget some of this →
          </a>
        </>
      )}
    </div>
  );
}
