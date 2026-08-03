// Phase 36e Turn 1 — Listener "Your subscriptions" page (Profile tab).
import React, {useCallback, useEffect, useState} from "react";
import axios from "axios";
const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

export function ListenerSubscriptions() {
  const [subs, setSubs] = useState([]);
  const [busyId, setBusyId] = useState(null);
  const [err, setErr] = useState("");

  const refresh = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/listener/subscriptions`,
                                                {withCredentials: true});
      setSubs(r.data || []);
    } catch (e) { setErr(e?.message || "load failed"); }
  }, []);
  useEffect(() => { refresh(); }, [refresh]);

  const cancel = async (id) => {
    setBusyId(id);
    try {
      await axios.post(`${API}/listener/subscriptions/${id}/cancel`, {},
                                      {withCredentials: true});
      await refresh();
    } catch (e) { setErr(e?.response?.data?.detail || e?.message); }
    finally { setBusyId(null); }
  };
  const resume = async (id) => {
    setBusyId(id);
    try {
      await axios.post(`${API}/listener/subscriptions/${id}/resume`, {},
                                      {withCredentials: true});
      await refresh();
    } catch (e) { setErr(e?.response?.data?.detail || e?.message); }
    finally { setBusyId(null); }
  };

  return (
    <div data-testid="listener-subs-page" style={{padding: 24}}>
      <h1 style={{fontSize: 22, fontWeight: 800, marginBottom: 16}}>
        Your subscriptions
      </h1>
      {err && <div style={{color: "#fca5a5", marginBottom: 12,
                                                fontSize: 12}}>{err}</div>}
      {subs.length === 0 && (
        <div data-testid="no-subs" style={{color: "#94a3b8"}}>
          No active subscriptions yet.
        </div>
      )}
      <div style={{display: "grid", gap: 10}}>
        {subs.map(s => (
          <div key={s.id} data-testid={`listener-sub-row-${s.id}`}
                    style={{background: "#13131a", padding: 14, borderRadius: 10,
                                border: "1px solid rgba(255,255,255,0.06)",
                                display: "flex", justifyContent: "space-between",
                                alignItems: "center", gap: 12}}>
            <div>
              <div style={{fontWeight: 700, color: "#fff"}}>
                Channel {s.channel_id}
              </div>
              <div style={{fontSize: 12, color: "#94a3b8"}}>
                Status: <b style={{color: "#fbbf24"}}>{s.status}</b>
                {s.cancel_at_period_end && " · cancels at period end"}
              </div>
            </div>
            <div>
              {s.cancel_at_period_end ? (
                <button data-testid={`listener-sub-resume-${s.id}`}
                                onClick={() => resume(s.id)}
                                disabled={busyId === s.id}
                                style={btn(busyId === s.id, "#22c55e")}>
                  Resume
                </button>
              ) : (
                <button data-testid={`listener-sub-cancel-${s.id}`}
                                onClick={() => cancel(s.id)}
                                disabled={busyId === s.id}
                                style={btn(busyId === s.id, "#ef4444")}>
                  Cancel
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

const btn = (busy, color) => ({padding: "6px 14px", borderRadius: 6,
  border: `1px solid ${color}`, background: "transparent", color,
  fontWeight: 700, fontSize: 12,
  cursor: busy ? "not-allowed" : "pointer", opacity: busy ? 0.5 : 1});
