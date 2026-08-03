/** Sub-Phase E5 — Import-from-Predexon modal.
 *
 *  Wired into `Admin/PredictWinCampaigns.jsx` alongside the existing
 *  "New campaign" button.  Lists open Predexon prediction markets and
 *  lets the admin one-click import any of them as a draft campaign.
 */

import React, { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import {
  X, Search, RefreshCw, Loader2, Check, ExternalLink,
  AlertTriangle, Database,
} from "lucide-react";

const API = process.env.REACT_APP_BACKEND_URL;
const E5 = `${API}/api/admin/prediction`;

export default function ImportPredexonModal({ open, onClose, onImported }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [category, setCategory] = useState("");
  const [limit] = useState(20);
  const [importingId, setImportingId] = useState(null);
  const [health, setHealth] = useState(null);

  const fetchMarkets = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const params = new URLSearchParams({ limit: String(limit) });
      if (category.trim()) params.set("category", category.trim());
      const r = await axios.get(
        `${E5}/external-markets?${params.toString()}`,
        { withCredentials: true });
      setItems(r.data?.items || []);
    } catch (e) {
      setError(e.response?.data?.detail?.code
              || e.response?.data?.detail?.error
              || "Predexon unreachable");
    } finally { setLoading(false); }
  }, [category, limit]);

  const fetchHealth = useCallback(async () => {
    try {
      const r = await axios.get(`${E5}/predexon/health`,
                                                            { withCredentials: true });
      setHealth(r.data);
    } catch { setHealth({ ok: false }); }
  }, []);

  useEffect(() => {
    if (!open) return;
    fetchHealth();
    fetchMarkets();
  }, [open, fetchHealth, fetchMarkets]);

  const importOne = async (mkt) => {
    setImportingId(mkt.external_market_id);
    try {
      const r = await axios.post(`${E5}/import-market`,
        { external_market_id: mkt.external_market_id },
        { withCredentials: true });
      toast.success(`Imported ${mkt.title.slice(0, 40)}`);
      // Patch the local row so the chip flips to "imported".
      setItems((arr) => arr.map((it) =>
        it.external_market_id === mkt.external_market_id
          ? { ...it, already_imported_as_campaign_id: r.data.campaign_id }
          : it));
      if (onImported) onImported(r.data);
    } catch (e) {
      const code = e.response?.data?.detail?.code;
      if (code === "already_imported") {
        toast.error("This market is already imported.");
      } else {
        toast.error(`Import failed: ${code || "unknown_error"}`);
      }
    } finally { setImportingId(null); }
  };

  if (!open) return null;

  return (
    <div data-testid="import-predexon-backdrop"
         onClick={onClose}
         style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)",
                          zIndex: 60, display: "flex", alignItems: "flex-start",
                          justifyContent: "center", overflow: "auto",
                          padding: 24 }}>
      <div data-testid="import-predexon-modal"
           onClick={(e) => e.stopPropagation()}
           style={{ background: "#0a0a0c", border: "1px solid rgba(255,255,255,0.10)",
                            borderRadius: 16, width: "100%", maxWidth: 900,
                            marginTop: 32, padding: 24, color: "#e7e7ea" }}>

        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between",
                              alignItems: "flex-start", marginBottom: 16 }}>
          <div>
            <div style={{ fontSize: 11, color: "#22d3ee", fontFamily: "monospace",
                                  textTransform: "uppercase", letterSpacing: 1,
                                  marginBottom: 4 }}>
              <Database size={11} style={{ display: "inline", marginRight: 4 }} />
              Predexon data provider · v2/polymarket
            </div>
            <h2 style={{ fontSize: 22, margin: "4px 0", fontWeight: 700 }}>
              Import market from Predexon
            </h2>
            <p style={{ fontSize: 12, color: "#9aa3af", maxWidth: 580 }}>
              Pick an open market.  We'll pre-populate a draft campaign
              with the question + outcomes (locked, so option labels
              stay aligned for auto-resolution).  Add a prize, attach a
              compliance row, then submit for approval.
            </p>
          </div>
          <button onClick={onClose}
                          data-testid="import-predexon-close"
                          style={{ background: "transparent", border: "none",
                                          color: "#9aa3af", cursor: "pointer",
                                          padding: 6 }}>
            <X size={18} />
          </button>
        </div>

        {/* Health pill */}
        {health && (
          <div data-testid="import-predexon-health"
               data-ok={health.ok}
               style={{ display: "inline-flex", alignItems: "center", gap: 6,
                                padding: "4px 10px", borderRadius: 999, fontSize: 11,
                                fontFamily: "monospace", marginBottom: 14,
                                background: health.ok ? "rgba(34,197,94,0.10)"
                                                                : "rgba(239,68,68,0.10)",
                                border: `1px solid ${health.ok ? "rgba(34,197,94,0.3)"
                                                                                : "rgba(239,68,68,0.3)"}`,
                                color: health.ok ? "#86efac" : "#fca5a5" }}>
            {health.ok ? <Check size={11} /> : <AlertTriangle size={11} />}
            {health.ok
              ? `Predexon OK · key_loaded · ${health.response_time_ms}ms`
              : "Predexon unreachable"}
          </div>
        )}

        {/* Filter bar */}
        <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
          <div style={{ position: "relative", flex: 1 }}>
            <Search size={13} style={{ position: "absolute", left: 10, top: 12,
                                                              color: "#6b7280" }} />
            <input
              type="text"
              value={category}
              placeholder="Filter by category (e.g. politics, sports, crypto…)"
              onChange={(e) => setCategory(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") fetchMarkets();
              }}
              data-testid="import-predexon-category"
              style={{ width: "100%", padding: "8px 12px 8px 32px",
                              background: "rgba(0,0,0,0.4)", color: "#e7e7ea",
                              border: "1px solid rgba(255,255,255,0.10)",
                              borderRadius: 8, fontSize: 13 }} />
          </div>
          <button onClick={fetchMarkets}
                          data-testid="import-predexon-refresh"
                          disabled={loading}
                          style={{ padding: "6px 14px", borderRadius: 999,
                                          background: "rgba(255,255,255,0.06)",
                                          border: "1px solid rgba(255,255,255,0.10)",
                                          color: "#e7e7ea", fontSize: 12,
                                          cursor: "pointer", display: "inline-flex",
                                          alignItems: "center", gap: 6 }}>
            {loading ? <Loader2 size={12} style={{ animation: "spin 1s linear infinite" }} />
                                  : <RefreshCw size={12} />}
            Refresh
          </button>
        </div>

        {/* Table */}
        {error && (
          <div data-testid="import-predexon-error"
               style={{ padding: 14, borderRadius: 10,
                                background: "rgba(239,68,68,0.06)",
                                border: "1px solid rgba(239,68,68,0.3)",
                                color: "#fca5a5", fontSize: 12, marginBottom: 12 }}>
            <AlertTriangle size={12} style={{ display: "inline", marginRight: 6 }} />
            {error}
          </div>
        )}

        {loading && items.length === 0 ? (
          <div data-testid="import-predexon-loading"
               style={{ padding: 40, textAlign: "center",
                              color: "#9aa3af", fontSize: 13 }}>
            <Loader2 size={16} style={{ animation: "spin 1s linear infinite" }} />
            Loading Predexon markets…
          </div>
        ) : items.length === 0 ? (
          <div data-testid="import-predexon-empty"
               style={{ padding: 40, textAlign: "center", color: "#9aa3af",
                              fontSize: 13 }}>
            No markets found {category ? `for "${category}"` : ""}.
          </div>
        ) : (
          <ul data-testid="import-predexon-list"
              style={{ listStyle: "none", margin: 0, padding: 0,
                              maxHeight: 460, overflow: "auto" }}>
            {items.map((m) => {
              const isImported = !!m.already_imported_as_campaign_id;
              const isImporting = importingId === m.external_market_id;
              return (
                <li key={m.external_market_id}
                    data-testid={`import-predexon-row-${m.external_market_id}`}
                    style={{ padding: 14, borderRadius: 10,
                                    background: "rgba(255,255,255,0.03)",
                                    border: "1px solid rgba(255,255,255,0.08)",
                                    marginBottom: 8 }}>
                  <div style={{ display: "flex", justifyContent: "space-between",
                                          gap: 12, alignItems: "flex-start" }}>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 6,
                                              marginBottom: 6 }}>
                        <span style={{ padding: "2px 8px", borderRadius: 999,
                                                background: "rgba(255,255,255,0.06)",
                                                border: "1px solid rgba(255,255,255,0.10)",
                                                fontSize: 10, fontFamily: "monospace",
                                                color: "#9aa3af" }}>
                          ID {m.external_market_id}
                        </span>
                        {m.category && (
                          <span style={{ padding: "2px 8px", borderRadius: 999,
                                                  background: "rgba(34,211,238,0.10)",
                                                  border: "1px solid rgba(34,211,238,0.3)",
                                                  fontSize: 10, color: "#67e8f9" }}>
                            {m.category}
                          </span>
                        )}
                        <span style={{ padding: "2px 8px", borderRadius: 999,
                                                background: "rgba(255,255,255,0.04)",
                                                border: "1px solid rgba(255,255,255,0.08)",
                                                fontSize: 10, color: "#9aa3af" }}>
                          {m.outcomes_count} outcomes
                        </span>
                        {isImported && (
                          <span data-testid={`import-predexon-already-${m.external_market_id}`}
                                style={{ padding: "2px 8px", borderRadius: 999,
                                                background: "rgba(34,197,94,0.10)",
                                                border: "1px solid rgba(34,197,94,0.3)",
                                                fontSize: 10, color: "#86efac",
                                                display: "inline-flex", alignItems: "center",
                                                gap: 4 }}>
                            <Check size={10} /> Already imported
                          </span>
                        )}
                      </div>
                      <div style={{ fontSize: 14, fontWeight: 600,
                                              color: "#e7e7ea", marginBottom: 4 }}
                           data-testid={`import-predexon-title-${m.external_market_id}`}>
                        {m.title}
                      </div>
                      <div style={{ fontSize: 11, color: "#9aa3af",
                                              display: "flex", flexWrap: "wrap", gap: 8 }}>
                        <span>Outcomes:</span>
                        {(m.outcomes || []).slice(0, 4).map((o, i) => (
                          <span key={i} style={{ color: "#d1d5db" }}>
                            {o.label}
                          </span>
                        ))}
                      </div>
                      {m.market_url && (
                        <a href={m.market_url} target="_blank"
                           rel="noopener noreferrer"
                           data-testid={`import-predexon-link-${m.external_market_id}`}
                           style={{ fontSize: 11, color: "#67e8f9",
                                          display: "inline-flex", alignItems: "center",
                                          gap: 4, marginTop: 6 }}>
                          <ExternalLink size={10} /> source
                        </a>
                      )}
                    </div>
                    <button
                      onClick={() => importOne(m)}
                      disabled={isImported || isImporting}
                      data-testid={`import-predexon-import-${m.external_market_id}`}
                      style={{ padding: "6px 14px", borderRadius: 999,
                                      background: isImported
                                                          ? "rgba(255,255,255,0.04)"
                                                          : "#22d3ee",
                                      color: isImported ? "#9aa3af" : "#0a0a0c",
                                      border: "none", fontSize: 12,
                                      fontWeight: 600,
                                      cursor: isImported ? "default" : "pointer",
                                      opacity: isImporting ? 0.5 : 1,
                                      display: "inline-flex", alignItems: "center",
                                      gap: 6, flexShrink: 0 }}>
                      {isImporting && (
                        <Loader2 size={12} style={{ animation: "spin 1s linear infinite" }} />
                      )}
                      {isImported ? "Imported" : "Import"}
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}

        <div style={{ marginTop: 16, fontSize: 11, color: "#6b7280",
                              borderTop: "1px solid rgba(255,255,255,0.06)",
                              paddingTop: 12 }}>
          Showing {items.length} markets · Imports become DRAFT campaigns
          you must still attach a prize + compliance to before submitting
          for approval.
        </div>
      </div>
    </div>
  );
}
