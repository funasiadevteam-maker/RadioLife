// Admin → Fun AI → Interactive News Sponsor.
// Lets an admin enter their OWN approved sponsor copy and toggle it on. The
// anchor opens with a disclosed acknowledgement; nothing shows until enabled.
// Paid advertising vs underwriting language is the admin's responsibility.
import React, { useEffect, useState } from "react";
import axios from "axios";
import { Megaphone, Save, Loader2, Check, BarChart3, Eye, Users, DollarSign } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

const fmtUsd = (cents) => `$${((Number(cents) || 0) / 100).toFixed(2)}`;

export default function AdminFunAiNews() {
  const [s, setS] = useState({ enabled: false, sponsor_name: "", opening_line: "", closing_line: "" });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [report, setReport] = useState(null);
  const [reportDays, setReportDays] = useState(30);
  const [loadingReport, setLoadingReport] = useState(true);

  useEffect(() => {
    axios.get(`${API}/admin/fun-ai/news-sponsor`, { withCredentials: true })
      .then((r) => setS({ ...s, ...(r.data?.sponsor || {}) }))
      .catch(() => {})
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    setLoadingReport(true);
    axios.get(`${API}/admin/fun-ai/break-report`, { params: { days: reportDays }, withCredentials: true })
      .then((r) => setReport(r.data || null))
      .catch(() => setReport(null))
      .finally(() => setLoadingReport(false));
  }, [reportDays]);

  const save = async () => {
    setSaving(true); setSaved(false);
    try {
      const r = await axios.put(`${API}/admin/fun-ai/news-sponsor`, s, { withCredentials: true });
      setS({ ...s, ...(r.data?.sponsor || {}) });
      setSaved(true); setTimeout(() => setSaved(false), 2500);
    } catch (_e) { /* noop */ } finally { setSaving(false); }
  };

  const defaultOpening = s.sponsor_name
    ? `FUUSIC Interactive News is sponsored by ${s.sponsor_name}.`
    : "FUUSIC Interactive News is sponsored by …";

  const field = { width: "100%", background: "#0b1220", color: "#e7eefc",
                  border: "1px solid #2a3550", borderRadius: 10, padding: "11px 13px",
                  fontSize: 14, outline: "none", boxSizing: "border-box" };
  const label = { display: "block", fontSize: 12, textTransform: "uppercase",
                  letterSpacing: 1, color: "#8aa3c7", margin: "0 0 7px" };

  return (
    <div data-testid="admin-fun-ai-news-page"
         style={{ minHeight: "100vh", background: "#070b16", color: "#e7eefc", padding: "28px 24px" }}>
      <div style={{ maxWidth: 680, margin: "0 auto" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 6 }}>
          <Megaphone size={22} color="#00d9ff" />
          <h1 style={{ fontSize: 22, fontWeight: 800, margin: 0 }}>Fun AI — News Sponsor</h1>
        </div>
        <p style={{ color: "#8aa3c7", fontSize: 13, marginBottom: 22 }}>
          Enter your own approved sponsor copy. When enabled, the AI anchor opens the news
          program with a clearly-disclosed acknowledgement. Keep paid advertising distinct from
          editorial — the anchor never presents sponsor claims as independent journalism.
        </p>

        {loading ? (
          <Loader2 className="spin" size={22} />
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 18,
                        background: "#0d1322", border: "1px solid #1d2740",
                        borderRadius: 16, padding: 22 }}>
            <label style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer" }}>
              <input type="checkbox" data-testid="sponsor-enabled" checked={!!s.enabled}
                     onChange={(e) => setS({ ...s, enabled: e.target.checked })}
                     style={{ width: 18, height: 18 }} />
              <span style={{ fontWeight: 700 }}>Sponsorship enabled</span>
              <span style={{ color: "#8aa3c7", fontSize: 12 }}>
                {s.enabled ? "Showing on Interactive News" : "Hidden until enabled"}
              </span>
            </label>

            <div>
              <label style={label}>Sponsor name</label>
              <input data-testid="sponsor-name" value={s.sponsor_name} style={field}
                     placeholder="e.g. ABC Insurance"
                     onChange={(e) => setS({ ...s, sponsor_name: e.target.value })} />
            </div>

            <div>
              <label style={label}>Opening acknowledgement</label>
              <textarea data-testid="sponsor-opening" value={s.opening_line} style={{ ...field, minHeight: 72, resize: "vertical" }}
                        placeholder={defaultOpening}
                        onChange={(e) => setS({ ...s, opening_line: e.target.value })} />
            </div>

            <div>
              <label style={label}>Closing sign-off (optional)</label>
              <textarea data-testid="sponsor-closing" value={s.closing_line} style={{ ...field, minHeight: 60, resize: "vertical" }}
                        placeholder="Thanks for listening — this program was sponsored by …"
                        onChange={(e) => setS({ ...s, closing_line: e.target.value })} />
            </div>

            {/* Live preview of the disclosed acknowledgement */}
            <div style={{ background: "rgba(0,217,255,0.06)", border: "1px dashed rgba(0,217,255,0.3)",
                          borderRadius: 10, padding: 14 }}>
              <div style={{ fontSize: 10, letterSpacing: 1, color: "#8aa3c7", fontWeight: 800, marginBottom: 6 }}>
                SPONSORED — PREVIEW
              </div>
              <div data-testid="sponsor-preview" style={{ fontSize: 14, color: "#cfe0ff" }}>
                {s.opening_line || defaultOpening}
              </div>
            </div>

            <button data-testid="sponsor-save" onClick={save} disabled={saving}
                    style={{ display: "inline-flex", alignItems: "center", justifyContent: "center",
                             gap: 8, background: "#00b8d9", color: "#001018", border: "none",
                             borderRadius: 10, padding: "12px 18px", fontWeight: 800, fontSize: 14,
                             cursor: saving ? "default" : "pointer", opacity: saving ? 0.7 : 1 }}>
              {saving ? <Loader2 className="spin" size={16} /> : saved ? <Check size={16} /> : <Save size={16} />}
              {saved ? "Saved" : "Save sponsor"}
            </button>
          </div>
        )}

        {/* ── Break Ad Report ───────────────────────────────────────── */}
        <div data-testid="break-report" style={{ marginTop: 26 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
            <BarChart3 size={20} color="#00d9ff" />
            <h2 style={{ fontSize: 18, fontWeight: 800, margin: 0 }}>Break Ad Report</h2>
            <div style={{ marginLeft: "auto", display: "flex", gap: 6 }}>
              {[7, 30, 90].map((d) => (
                <button key={d} data-testid={`break-report-days-${d}`} onClick={() => setReportDays(d)}
                        style={{ padding: "5px 11px", borderRadius: 999, fontSize: 12, fontWeight: 700,
                                 cursor: "pointer", border: `1px solid ${reportDays === d ? "#00b8d9" : "#2a3550"}`,
                                 background: reportDays === d ? "#00b8d9" : "transparent",
                                 color: reportDays === d ? "#001018" : "#8aa3c7" }}>
                  {d}d
                </button>
              ))}
            </div>
          </div>
          <p style={{ color: "#8aa3c7", fontSize: 13, margin: "0 0 16px" }}>
            Impressions logged across the Interactive News sponsor breaks, with paid-spot spend
            drawn from the live ad-stack reads injected mid-program.
          </p>

          {loadingReport ? (
            <Loader2 className="spin" size={22} />
          ) : !report ? (
            <div style={{ color: "#8aa3c7", fontSize: 13 }}>No report data available.</div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              {/* stat cards */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 12 }}>
                {[
                  { k: "impressions", icon: <Eye size={16} />, label: "Impressions", testid: "break-report-impressions", val: report.totals.impressions },
                  { k: "unique", icon: <Users size={16} />, label: "Unique listeners", testid: "break-report-unique", val: report.totals.unique_listeners },
                  { k: "spend", icon: <DollarSign size={16} />, label: "Paid spend", testid: "break-report-spend", val: fmtUsd(report.totals.spend_cents) },
                ].map((c) => (
                  <div key={c.k} data-testid={c.testid}
                       style={{ background: "#0d1322", border: "1px solid #1d2740",
                                borderRadius: 14, padding: 16 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 6, color: "#8aa3c7",
                                  fontSize: 11, textTransform: "uppercase", letterSpacing: 1, marginBottom: 8 }}>
                      {c.icon} {c.label}
                    </div>
                    <div style={{ fontSize: 26, fontWeight: 800, color: "#e7eefc" }}>{c.val}</div>
                  </div>
                ))}
              </div>

              {/* placement breakdown */}
              <div style={{ background: "#0d1322", border: "1px solid #1d2740", borderRadius: 14, padding: 18 }}>
                <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 1,
                              color: "#8aa3c7", fontWeight: 800, marginBottom: 12 }}>By placement</div>
                {report.by_placement.length === 0 ? (
                  <div style={{ color: "#8aa3c7", fontSize: 13 }}>No break impressions in this window yet.</div>
                ) : report.by_placement.map((p) => {
                  const max = Math.max(1, ...report.by_placement.map((x) => x.impressions));
                  return (
                    <div key={p.placement} data-testid={`break-report-placement-${p.placement}`}
                         style={{ marginBottom: 10 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13,
                                    marginBottom: 4 }}>
                        <span style={{ textTransform: "capitalize" }}>{p.placement}</span>
                        <span style={{ fontWeight: 700 }}>{p.impressions}</span>
                      </div>
                      <div style={{ height: 8, borderRadius: 999, background: "#0b1220" }}>
                        <div style={{ height: "100%", borderRadius: 999, background: "#00b8d9",
                                      width: `${(p.impressions / max) * 100}%` }} />
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* paid spots */}
              <div style={{ background: "#0d1322", border: "1px solid #1d2740", borderRadius: 14, padding: 18 }}>
                <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 1,
                              color: "#8aa3c7", fontWeight: 800, marginBottom: 12 }}>
                  Paid spots ({report.totals.paid_impressions} impressions)
                </div>
                {report.paid_spots.length === 0 ? (
                  <div style={{ color: "#8aa3c7", fontSize: 13 }}>
                    No paid ad-stack reads have run in the news breaks yet. Program sponsorship
                    (opening/closing acknowledgements) is free underwriting and carries no spend.
                  </div>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {report.paid_spots.map((sp) => (
                      <div key={sp.sponsored_read_id} data-testid={`break-report-spot-${sp.sponsored_read_id}`}
                           style={{ display: "flex", alignItems: "center", gap: 12,
                                    padding: "10px 12px", borderRadius: 10, background: "#0b1220",
                                    border: "1px solid #1d2740" }}>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ fontWeight: 700, fontSize: 14, overflow: "hidden",
                                        textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            {sp.advertiser || sp.persona_name || sp.sponsored_read_id}
                          </div>
                          <div style={{ fontSize: 11, color: "#8aa3c7" }}>
                            {sp.plays} plays · {fmtUsd(sp.cost_per_play_cents)}/play · {sp.status}
                          </div>
                        </div>
                        <div style={{ textAlign: "right" }}>
                          <div style={{ fontWeight: 800, fontSize: 15, color: "#00d9ff" }}>{fmtUsd(sp.spend_cents)}</div>
                          <div style={{ fontSize: 11, color: "#8aa3c7" }}>{fmtUsd(sp.remaining_budget_cents)} left</div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
      <style>{`.spin{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}`}</style>
    </div>
  );
}
