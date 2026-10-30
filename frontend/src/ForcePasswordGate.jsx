// Blocking gate shown when an admin has required the user to set a new
// password. Mounts globally; renders only when user.must_change_password.
import { useState } from "react";
import axios from "axios";
import { useAuth, API } from "@/AuthContext";

export default function ForcePasswordGate() {
  const { user, refresh } = useAuth();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  if (!user?.must_change_password) return null;

  const pwOk = next.length >= 8 && /\d/.test(next) && /[A-Za-z]/.test(next);
  const matchOk = next === confirm;
  const disabled = submitting || !current || !pwOk || !matchOk;

  const submit = async (e) => {
    e?.preventDefault?.();
    if (disabled) return;
    setSubmitting(true); setError("");
    try {
      await axios.post(`${API}/auth/change-password`,
        { current_password: current, new_password: next },
        { withCredentials: true });
      await refresh();   // clears the flag → gate unmounts
    } catch (err) {
      const d = err?.response?.data?.detail || err?.response?.data;
      setError(typeof d === "string" ? d
                    : (d?.message || d?.status || "Could not update password."));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div data-testid="force-pw-gate"
            style={{position: "fixed", inset: 0, zIndex: 100000,
                        background: "rgba(7,7,11,0.92)", backdropFilter: "blur(6px)",
                        display: "grid", placeItems: "center", padding: 20}}>
      <form onSubmit={submit}
                style={{width: "100%", maxWidth: 420, background: "#111114",
                            border: "1px solid rgba(255,255,255,0.08)",
                            borderRadius: 16, padding: 24,
                            boxShadow: "0 20px 60px rgba(0,0,0,0.5)"}}>
        <h2 style={{margin: "0 0 6px", fontSize: 20, fontWeight: 800,
                            color: "#e7e7ea"}}>Set a new password</h2>
        <p style={{margin: "0 0 18px", fontSize: 13, color: "#9aa3af"}}>
          An administrator requires you to choose a new password before
          continuing.
        </p>
        <Field label="Current password" value={current} onChange={setCurrent}
                    testid="force-pw-current" />
        <Field label="New password (min 8, letter + digit)" value={next}
                    onChange={setNext} testid="force-pw-new" />
        <Field label="Confirm new password" value={confirm} onChange={setConfirm}
                    testid="force-pw-confirm" />
        {confirm.length > 0 && !matchOk && (
          <div style={{fontSize: 12, color: "#fda4af", marginTop: -6,
                              marginBottom: 10}}>Passwords don't match.</div>
        )}
        {error && (
          <div data-testid="force-pw-error"
                  style={{fontSize: 13, color: "#fda4af", marginBottom: 12}}>
            {String(error)}
          </div>
        )}
        <button type="submit" data-testid="force-pw-submit" disabled={disabled}
                      style={{width: "100%", padding: "12px 0", borderRadius: 10,
                                  border: 0, fontWeight: 800, fontSize: 14,
                                  cursor: disabled ? "not-allowed" : "pointer",
                                  opacity: disabled ? 0.5 : 1,
                                  background: "#f59e0b", color: "#0a0a0c"}}>
          {submitting ? "Saving…" : "Save & continue"}
        </button>
      </form>
    </div>
  );
}

function Field({ label, value, onChange, testid }) {
  return (
    <label style={{display: "block", marginBottom: 12}}>
      <span style={{display: "block", fontSize: 12, color: "#9aa3af",
                            marginBottom: 6}}>{label}</span>
      <input type="password" value={value}
                  onChange={(e) => onChange(e.target.value)} data-testid={testid}
                  style={{width: "100%", padding: "10px 12px", borderRadius: 10,
                              background: "#0a0a0c", color: "#e7e7ea",
                              border: "1px solid rgba(255,255,255,0.1)",
                              fontSize: 14, outline: "none"}} />
    </label>
  );
}
