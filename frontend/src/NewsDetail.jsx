/** Phase 40 — /news/:news_id detail page. */
import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import axios from "axios";
import { ArrowLeft, ExternalLink, Mic } from "lucide-react";
import { API } from "@/AuthContext";
import SafeImage from "@/components/SafeImage";

export default function NewsDetail() {
  const { news_id }     = useParams();
  const [a, setA]       = useState(null);
  const [err, setErr]   = useState(null);

  useEffect(() => {
    let cancel = false;
    (async () => {
      try {
        const r = await axios.get(
          `${API}/news/article/${encodeURIComponent(news_id)}`,
          { withCredentials: true });
        if (!cancel) setA(r.data);
      } catch (e) {
        if (!cancel) setErr(e.response?.data?.detail?.code || "error");
      }
    })();
    return () => { cancel = true; };
  }, [news_id]);

  return (
    <div data-testid="news-detail-page"
         style={{ maxWidth: 780, margin: "0 auto", padding: "24px 20px" }}>
      <Link to="/news" data-testid="news-back"
            style={{ display: "inline-flex", alignItems: "center", gap: 6,
                     color: "#9aa3af", textDecoration: "none", fontSize: 13,
                     marginBottom: 18 }}>
        <ArrowLeft size={14} /> Back to news
      </Link>
      {err ? (
        <div data-testid="news-detail-error"
             style={{ color: "#f59e0b", padding: 24 }}>
          Article not found.
        </div>
      ) : !a ? (
        <div data-testid="news-detail-loading"
             style={{ color: "#9aa3af", padding: 24 }}>
          Loading…
        </div>
      ) : (
        <article>
          {a.image_url && (
            <SafeImage src={a.image_url} alt=""
                                fallbackKind="generic"
                                fallbackText={a.title || ""}
                                style={{ width: "100%", maxHeight: 360,
                                                    minHeight: 240,
                                                    objectFit: "cover", borderRadius: 12,
                                                    marginBottom: 18 }} />
          )}
          <h1 data-testid="news-detail-title"
              style={{ color: "#fff", fontSize: 26, fontWeight: 700,
                       lineHeight: 1.3, margin: "0 0 12px" }}>
            {a.title}
          </h1>
          <div style={{ display: "flex", gap: 12, color: "#9aa3af",
                        fontSize: 12, fontFamily: "monospace",
                        marginBottom: 18 }}>
            <span>{a.source_name || a.source_id}</span>
            <span>·</span>
            <span>{a.pubDate}</span>
          </div>
          {a.description && (
            <p data-testid="news-detail-desc"
               style={{ color: "#cbd5e1", fontSize: 16, lineHeight: 1.7,
                        marginBottom: 20 }}>
              {a.description}
            </p>
          )}
          {a.summary_script && (
            <div data-testid="news-detail-summary"
                 style={{ background: "#1f2937", padding: 16,
                          borderRadius: 12, marginBottom: 18,
                          borderLeft: "3px solid #00d9ff" }}>
              <div style={{ fontSize: 11, color: "#00d9ff", fontFamily: "monospace",
                            marginBottom: 6, letterSpacing: 1 }}>
                AI RADIO SUMMARY
              </div>
              <p style={{ color: "#cbd5e1", fontSize: 14, lineHeight: 1.6,
                          margin: 0 }}>
                {a.summary_script}
              </p>
            </div>
          )}
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            {a.link && (
              <a href={a.link} target="_blank" rel="noopener noreferrer"
                 data-testid="news-detail-source-link"
                 style={{ display: "inline-flex", alignItems: "center", gap: 6,
                          background: "rgba(255,255,255,0.05)", color: "#fff",
                          padding: "8px 14px", borderRadius: 8,
                          textDecoration: "none", fontSize: 13,
                          border: "1px solid rgba(255,255,255,0.1)" }}>
                Read original <ExternalLink size={13} />
              </a>
            )}
            {a.tts_audio_url && (
              <a href={a.tts_audio_url} target="_blank" rel="noopener noreferrer"
                 data-testid="news-detail-listen"
                 style={{ display: "inline-flex", alignItems: "center", gap: 6,
                          background: "#00d9ff", color: "#0b0b0b",
                          padding: "8px 14px", borderRadius: 8,
                          textDecoration: "none", fontSize: 13,
                          fontWeight: 600 }}>
                <Mic size={13} /> Listen
              </a>
            )}
          </div>
        </article>
      )}
    </div>
  );
}
