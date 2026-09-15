// Admin — Public Landing Analytics. Aggregated CTA clicks + section views +
// station previews captured from the New Look V2 public landing.
import { useEffect, useState } from "react";
import axios from "axios";
import { API } from "@/AuthContext";
import { Loader2, MousePointerClick, Eye, Radio } from "lucide-react";

export default function AdminLandingAnalytics() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);

  async function load() {
    setData(null); setErr(null);
    try {
      const { data } = await axios.get(`${API}/shell/landing-analytics`, { withCredentials: true });
      setData(data);
    } catch (e) { setErr(e?.response?.data?.detail?.code || e.message || "Failed to load"); }
  }
  useEffect(() => { load(); }, []);

  const maxCta = data ? Math.max(1, ...data.ctas.map((c) => c.count)) : 1;
  const maxSec = data ? Math.max(1, ...data.sections.map((c) => c.count)) : 1;

  return (
    <div style={{ minHeight: "100vh", background: "#0b0f1a", color: "#e8ecf5" }} data-testid="admin-landing-analytics-page">
      <div style={{ maxWidth: 960, margin: "0 auto", padding: "28px 20px 80px" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
          <div>
            <div style={{ fontSize: 11, letterSpacing: 2, textTransform: "uppercase", color: "#8b5cf6", fontFamily: "monospace" }}>New Look V2</div>
            <h1 style={{ fontSize: 26, fontWeight: 900, margin: "2px 0 0" }}>Public Landing Analytics</h1>
            <p style={{ color: "#8b93a7", fontSize: 14, margin: "4px 0 0" }}>What anonymous visitors click and view — use it to tune the page.</p>
          </div>
          <button onClick={load} data-testid="admin-landing-refresh"
            style={{ background: "#1c2540", color: "#c9d2ea", border: "1px solid #2a3556", borderRadius: 999, padding: "8px 16px", fontWeight: 700, fontSize: 13, cursor: "pointer" }}>
            Refresh
          </button>
        </div>

        {err && <div style={{ marginTop: 20, background: "rgba(239,68,68,0.12)", border: "1px solid rgba(239,68,68,0.4)", color: "#fca5a5", borderRadius: 10, padding: "10px 14px" }}>{err}</div>}
        {!data && !err && <div style={{ marginTop: 40, display: "flex", justifyContent: "center" }}><Loader2 className="animate-spin" /></div>}

        {data && (
          <>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px,1fr))", gap: 12, marginTop: 22 }}>
              <Stat icon={<MousePointerClick size={18} />} label="Total events" value={data.total_events} />
              <Stat icon={<Radio size={18} />} label="Station previews" value={data.preview_plays} />
              <Stat icon={<MousePointerClick size={18} />} label="CTA types" value={data.ctas.length} />
              <Stat icon={<Eye size={18} />} label="Sections viewed" value={data.sections.length} />
            </div>

            <Panel title="Top CTAs clicked" icon={<MousePointerClick size={16} />} testid="admin-landing-ctas">
              {data.ctas.length === 0 ? <Empty /> : data.ctas.map((c) => (
                <Bar key={c.key} label={c.key} count={c.count} sessions={c.sessions} pct={(c.count / maxCta) * 100} color="#8b5cf6" />
              ))}
            </Panel>

            <Panel title="Most-viewed sections" icon={<Eye size={16} />} testid="admin-landing-sections">
              {data.sections.length === 0 ? <Empty /> : data.sections.map((c) => (
                <Bar key={c.key} label={c.key.replace(/^public-/, "").replace(/-header$/, "")} count={c.count} sessions={c.sessions} pct={(c.count / maxSec) * 100} color="#ec4899" />
              ))}
            </Panel>
          </>
        )}
      </div>
    </div>
  );
}

function Stat({ icon, label, value }) {
  return (
    <div style={{ background: "#131a2e", border: "1px solid #232d4d", borderRadius: 14, padding: 16 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, color: "#8b93a7" }}>{icon}<span style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 1 }}>{label}</span></div>
      <div style={{ fontSize: 28, fontWeight: 900, marginTop: 6 }}>{Number(value || 0).toLocaleString()}</div>
    </div>
  );
}

function Panel({ title, icon, testid, children }) {
  return (
    <div style={{ background: "#131a2e", border: "1px solid #232d4d", borderRadius: 16, padding: 18, marginTop: 18 }} data-testid={testid}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, fontWeight: 800, marginBottom: 12 }}>{icon}{title}</div>
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>{children}</div>
    </div>
  );
}

function Bar({ label, count, sessions, pct, color }) {
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, marginBottom: 4 }}>
        <span style={{ fontWeight: 700 }}>{label}</span>
        <span style={{ color: "#8b93a7", fontFamily: "monospace", fontSize: 12 }}>{count} · {sessions} sessions</span>
      </div>
      <div style={{ height: 8, borderRadius: 999, background: "#1c2540", overflow: "hidden" }}>
        <div style={{ height: "100%", width: `${Math.max(4, pct)}%`, background: color, borderRadius: 999 }} />
      </div>
    </div>
  );
}

function Empty() {
  return <div style={{ color: "#6b7392", fontSize: 13, padding: "8px 0" }}>No data yet — engagement will appear here as visitors use the public landing.</div>;
}
