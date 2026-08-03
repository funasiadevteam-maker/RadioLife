/** Phase 39 Session 7 — Advertiser Geo-Anchored Insights dashboard. */
import React, { useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";

const API = process.env.REACT_APP_BACKEND_URL || "";

export default function GeoInsights() {
  const [category, setCategory]       = useState("cafe");
  const [bucket, setBucket]             = useState("morning");
  const [agg, setAgg]                       = useState(null);
  const [aggError, setAggError]      = useState(null);
  const [campaigns, setCampaigns] = useState([]);
  const [name, setName]                 = useState("");
  const [creative, setCreative]      = useState("https://example.com/creative.mp3");
  const [busy, setBusy]                  = useState(false);

  const loadCampaigns = async () => {
    try {
      const r = await axios.get(`${API}/advertiser/campaigns/geo_anchored`,
                                { withCredentials: true });
      setCampaigns(r.data.campaigns || []);
    } catch (e) { /* silent */ }
  };
  useEffect(() => { loadCampaigns(); }, []);

  const runAggregate = async () => {
    setAgg(null); setAggError(null); setBusy(true);
    try {
      const r = await axios.get(`${API}/advertiser/audience/aggregate`,
        { params: { category, time_bucket: bucket },
          withCredentials: true });
      setAgg(r.data);
    } catch (e) {
      setAggError(e.response?.data?.detail || { code: "error" });
    }
    setBusy(false);
  };

  const createCampaign = async () => {
    if (!name.trim()) { toast.error("Name required"); return; }
    try {
      await axios.post(`${API}/advertiser/campaigns/geo_anchored`, {
        name, target_category: category,
        target_time_bucket: bucket,
        creative_audio_url: creative, budget_aed: 100,
      }, { withCredentials: true });
      toast.success("Campaign created");
      setName(""); loadCampaigns();
    } catch (e) {
      const d = e.response?.data?.detail;
      toast.error(d?.message || "Campaign creation failed");
    }
  };

  return (
    <div data-testid="geo-insights-page"
         style={{ maxWidth: 980, margin: "0 auto", padding: 24 }}>
      <div data-testid="geo-insights-watermark"
           style={{ background: "rgba(245,158,11,0.1)", border: "1px dashed #f59e0b",
                    padding: "8px 14px", borderRadius: 6, color: "#f59e0b",
                    fontSize: 12, textAlign: "center", letterSpacing: 1,
                    fontWeight: 700, marginBottom: 18 }}>
        DRAFT — pending legal sign-off
      </div>
      <h1 style={{ color: "#fff", fontSize: 22, fontWeight: 700, margin: "0 0 14px" }}>
        Geo-Anchored Audience Insights
      </h1>

      <section style={{ background: "#1f2937", padding: 16, borderRadius: 12,
                        marginBottom: 18 }}>
        <h3 style={{ color: "#fff", fontSize: 14, margin: "0 0 10px" }}>
          Audience Explorer
        </h3>
        <div style={{ display: "flex", gap: 8, marginBottom: 10, flexWrap: "wrap" }}>
          <select data-testid="geo-cat-select" value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  style={selStyle}>
            {["cafe","restaurant","bar","club","gym","mall","gas_station",
              "salon","dessert","grocery","theater","fast_food"].map(c => (
              <option key={c} value={c}>{c}</option>))}
          </select>
          <select data-testid="geo-bucket-select" value={bucket}
                  onChange={(e) => setBucket(e.target.value)} style={selStyle}>
            {["morning","lunch","evening","night"].map(b => (
              <option key={b} value={b}>{b}</option>))}
          </select>
          <button data-testid="geo-run-agg" onClick={runAggregate}
                  disabled={busy} style={btnStyle("#3b82f6")}>
            {busy ? "Running…" : "Estimate audience"}
          </button>
        </div>
        {agg && (
          <div data-testid="geo-agg-result" style={{ color: "#cbd5e1", fontSize: 13 }}>
            <div>Segment size: <b data-testid="geo-segment-size">{agg.segment_size}</b></div>
            <div>Top categories: {(agg.top_categories || [])
              .map(c => `${c.category} (${c.visit_count})`).join(", ") || "—"}</div>
            <div>Typical time buckets: {(agg.typical_time_buckets || [])
              .map(b => `${b.bucket} (${b.visit_count})`).join(", ") || "—"}</div>
          </div>
        )}
        {aggError && (
          <div data-testid="geo-agg-error" style={{ color: "#f59e0b", fontSize: 13 }}>
            {aggError.code === "segment_too_small"
              ? `Segment < ${aggError.min_required} users — broaden filters.`
              : "Aggregate query failed."}
          </div>
        )}
      </section>

      <section style={{ background: "#1f2937", padding: 16, borderRadius: 12,
                        marginBottom: 18 }}>
        <h3 style={{ color: "#fff", fontSize: 14, margin: "0 0 10px" }}>
          Create Geo-Anchored Campaign
        </h3>
        <input data-testid="geo-camp-name" placeholder="Campaign name"
               value={name} onChange={(e) => setName(e.target.value)}
               style={{ ...inputStyle, marginBottom: 8 }} />
        <input data-testid="geo-camp-creative" placeholder="Creative audio URL"
               value={creative} onChange={(e) => setCreative(e.target.value)}
               style={{ ...inputStyle, marginBottom: 8 }} />
        <button data-testid="geo-camp-create" onClick={createCampaign}
                style={btnStyle("#10b981")}>
          Create campaign
        </button>
      </section>

      <section style={{ background: "#1f2937", padding: 16, borderRadius: 12 }}>
        <h3 style={{ color: "#fff", fontSize: 14, margin: "0 0 10px" }}>
          Performance ({campaigns.length})
        </h3>
        {campaigns.length === 0 ? (
          <div data-testid="geo-no-campaigns"
               style={{ color: "#9aa3af", fontSize: 12 }}>
            No campaigns yet.
          </div>
        ) : (
          <table data-testid="geo-perf-table"
                 style={{ width: "100%", color: "#cbd5e1", fontSize: 12 }}>
            <thead>
              <tr style={{ textAlign: "left", color: "#9aa3af" }}>
                <th>Name</th><th>Target</th><th>Impressions</th>
                <th>Completion</th><th>Est. segment</th>
              </tr>
            </thead>
            <tbody>
              {campaigns.map(c => (
                <tr key={c.campaign_id} data-testid={`geo-camp-row-${c.campaign_id}`}>
                  <td>{c.name}</td>
                  <td>{c.target_category} · {c.target_time_bucket}</td>
                  <td>{c.delivered_impressions || 0}</td>
                  <td>{c.completed_impressions || 0}</td>
                  <td>{c.estimated_segment_size}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}

const selStyle  = { background: "#0b0b0b", color: "#fff",
                    border: "1px solid #2a2f3a", borderRadius: 6,
                    padding: "8px 10px", minWidth: 140 };
const inputStyle = { width: "100%", background: "#0b0b0b", color: "#fff",
                     border: "1px solid #2a2f3a", borderRadius: 6,
                     padding: "8px 10px" };
const btnStyle = (color) => ({
  background: color, color: "#0b0b0b", border: "none",
  padding: "8px 14px", borderRadius: 6, fontWeight: 600, cursor: "pointer",
});
