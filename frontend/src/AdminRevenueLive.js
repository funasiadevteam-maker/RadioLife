// AdminRevenueLive.js — Phase 4 live revenue meter
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { Loader2, DollarSign, TrendingUp, Radio, Users } from "lucide-react";
import "./AdminImaging.css";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
axios.defaults.withCredentials = true;

function StatTile({ label, value, sub, accent = "#ff2d95", testid }) {
  return (
    <div className="img-station-card" style={{ padding: 18, gap: 8 }} data-testid={testid}>
      <div className="meta-label" style={{ fontSize: 10 }}>{label}</div>
      <div style={{ fontSize: 30, fontWeight: 800, color: accent, lineHeight: 1.0 }}>{value}</div>
      {sub && <div className="asset-slug" style={{ fontSize: 11, color: "#888892" }}>{sub}</div>}
    </div>
  );
}

export default function AdminRevenueLive() {
  const [data, setData] = useState(null);
  const [minutes, setMinutes] = useState(60);
  const [loading, setLoading] = useState(true);

  const fetchData = async () => {
    try {
      const r = await axios.get(`${API}/admin/ads/revenue/live?minutes=${minutes}`);
      setData(r.data);
    } catch (e) {} finally { setLoading(false); }
  };

  useEffect(() => {
    fetchData();
    const t = setInterval(fetchData, 5000);
    return () => clearInterval(t);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [minutes]);

  if (loading || !data) return <div className="admin-img-wrap"><Loader2 className="spin" size={28} /></div>;

  return (
    <div className="admin-img-wrap" data-testid="admin-revenue-live">
      <header className="admin-img-header">
        <div>
          <h1><DollarSign size={24} style={{ verticalAlign: "-4px", marginRight: 8 }} />Revenue · Live</h1>
          <p>Live revenue meter across direct-sold campaigns + paid imaging slots. Refresh every 5s.</p>
        </div>
        <div className="admin-img-pills">
          {[15, 60, 360, 1440].map((m) => (
            <button key={m} type="button"
              className={`asset-type-chip ${minutes === m ? "on" : ""}`}
              onClick={() => setMinutes(m)} data-testid={`rev-window-${m}`}>
              {m < 60 ? `${m}m` : m < 1440 ? `${m / 60}h` : `${m / 1440}d`}
            </button>
          ))}
        </div>
      </header>

      <section className="img-stations-grid" data-testid="revenue-tiles">
        <StatTile testid="tile-total-revenue" label="TOTAL REVENUE"
          value={`$${data.total_revenue_usd?.toFixed(2)}`}
          sub={`${data.total_impressions} impressions`}
          accent="#4ade80" />
        <StatTile testid="tile-imaging-revenue" label="IMAGING SLOT REV"
          value={`$${((data.imaging_revenue_cents || 0) / 100).toFixed(2)}`}
          sub="Sponsor bumper + paid imaging" accent="#fdb756" />
        <StatTile testid="tile-free-users" label="FREE LISTENERS"
          value={data.free_users}
          sub={`Premium: ${data.premium_users}`} accent="#7BD3F7" />
        <StatTile testid="tile-eCPM" label="eCPM"
          value={data.total_impressions ? `$${((data.total_revenue_cents / data.total_impressions) * 10).toFixed(2)}` : "—"}
          sub="per 1000 impressions" accent="#ff8a3d" />
      </section>

      <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))", gap: 18, marginTop: 18 }}>
        <div className="img-station-card" data-testid="by-market">
          <div className="meta-label"><Radio size={11} /> BY MARKET</div>
          {data.by_market.map((r) => (
            <div key={r.market} className="asset-meta-row" style={{ justifyContent: "space-between", padding: "8px 0", borderBottom: "1px solid #25252f" }}>
              <span style={{ fontSize: 13, color: "#fff" }}>{r.market === "dfw" ? "🇺🇸 DFW" : "🇦🇪 Dubai"}</span>
              <span style={{ color: "#aaa" }}>{r.impressions} imps · <b style={{ color: "#4ade80" }}>${(r.revenue_cents / 100).toFixed(2)}</b></span>
            </div>
          ))}
        </div>
        <div className="img-station-card" data-testid="by-channel">
          <div className="meta-label">TOP CHANNELS</div>
          {data.by_channel.slice(0, 8).map((r) => (
            <div key={r.channel} className="asset-meta-row" style={{ justifyContent: "space-between", padding: "6px 0", borderBottom: "1px solid #1f1f29" }}>
              <span style={{ fontSize: 12, color: "#ddd" }}>{r.channel}</span>
              <span style={{ color: "#aaa", fontSize: 11 }}>{r.impressions} · <b style={{ color: "#4ade80" }}>${(r.revenue_cents / 100).toFixed(2)}</b></span>
            </div>
          ))}
        </div>
        <div className="img-station-card" data-testid="by-campaign">
          <div className="meta-label"><TrendingUp size={11} /> TOP CAMPAIGNS</div>
          {data.by_campaign.slice(0, 10).map((r) => (
            <div key={r.campaign_id} className="asset-meta-row" style={{ justifyContent: "space-between", padding: "6px 0", borderBottom: "1px solid #1f1f29" }}>
              <span style={{ fontSize: 12, color: "#ddd" }}>{r.campaign_name}</span>
              <span style={{ color: "#aaa", fontSize: 11 }}>{r.impressions} · <b style={{ color: "#4ade80" }}>${(r.revenue_cents / 100).toFixed(2)}</b></span>
            </div>
          ))}
        </div>
        <div className="img-station-card" data-testid="imaging-by-type">
          <div className="meta-label">IMAGING SLOT BREAKDOWN</div>
          {data.imaging_by_type.map((r) => (
            <div key={r.item_type} className="asset-meta-row" style={{ justifyContent: "space-between", padding: "6px 0", borderBottom: "1px solid #1f1f29" }}>
              <span style={{ fontSize: 12, color: "#ddd" }}>{r.item_type}</span>
              <span style={{ color: "#aaa", fontSize: 11 }}>{r.count} · <b style={{ color: "#4ade80" }}>${(r.revenue_cents / 100).toFixed(2)}</b></span>
            </div>
          ))}
        </div>
      </section>

      <footer className="admin-img-footer" style={{ marginTop: 24 }}>
        Direct-sold inventory + imaging slot revenue. Programmatic backfill via /api/openrtb/bid ships in Phase 4.5.
      </footer>
    </div>
  );
}
