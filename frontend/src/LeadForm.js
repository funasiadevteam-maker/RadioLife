// Phase 8c — Listener-facing lead form. Renders the campaign's lead_form
// schema and posts to /api/games_v2/campaigns/{id}/submit_lead before play.
import { useEffect, useState } from "react";
import axios from "axios";
import { Loader2, ChevronRight } from "lucide-react";
import { API } from "@/AuthContext";

export default function LeadForm({ campaignId, onSubmitted }) {
  const [form, setForm] = useState(null);
  const [values, setValues] = useState({});
  const [consent, setConsent] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState(null);

  useEffect(() => {
    axios.get(`${API}/games_v2/campaigns/${campaignId}/lead_form`)
        .then((r) => setForm(r.data?.lead_form))
        .catch(() => setForm(null));
  }, [campaignId]);

  if (!form) return null;
  const fields = form.fields_json || [];

  const submit = async (e) => {
    e?.preventDefault();
    setSubmitting(true);
    setErr(null);
    try {
      const r = await axios.post(
        `${API}/games_v2/campaigns/${campaignId}/submit_lead`,
        {form_data: values, consent_accepted: consent});
      onSubmitted && onSubmitted(r.data.lead_id);
    } catch (e) {
      setErr(e?.response?.data?.detail || "Submission failed");
    } finally {
      setSubmitting(false);
    }
  };

  const setVal = (name, val) =>
    setValues((s) => ({...s, [name]: val}));

  return (
    <form className="lead-form" onSubmit={submit}
              data-testid="lead-form" data-campaign-id={campaignId}>
      <div className="lead-form-eyebrow mono">ENTER TO PLAY</div>
      <h3 className="lead-form-title">A quick info before you start</h3>
      {fields.map((f) => (
        <label key={f.name} className="lead-field"
                  data-testid={`lead-field-${f.name}`}>
          <span className="lead-field-label">
            {f.label}{f.required && <span className="lead-req">*</span>}
          </span>
          {f.type === "select" ? (
            <select value={values[f.name] || ""}
                       onChange={(e) => setVal(f.name, e.target.value)}
                       required={f.required}
                       className="lead-input">
              <option value="">— select —</option>
              {(f.options || []).map((o) => (
                <option key={o} value={o}>{o}</option>
              ))}
            </select>
          ) : f.type === "checkbox" ? (
            <input type="checkbox"
                      checked={!!values[f.name]}
                      onChange={(e) => setVal(f.name, e.target.checked)}
                      data-testid={`lead-field-${f.name}-input`} />
          ) : (
            <input
                type={f.type === "email" ? "email"
                       : f.type === "phone" ? "tel" : "text"}
                value={values[f.name] || ""}
                onChange={(e) => setVal(f.name, e.target.value)}
                required={f.required}
                className="lead-input"
                placeholder={f.label}
                data-testid={`lead-field-${f.name}-input`} />
          )}
        </label>
      ))}
      {form.consent_text && (
        <label className="lead-consent" data-testid="lead-consent-row">
          <input type="checkbox" checked={consent}
                    onChange={(e) => setConsent(e.target.checked)}
                    data-testid="lead-consent-checkbox" />
          <span>{form.consent_text}</span>
        </label>
      )}
      {err && <div className="lead-error" data-testid="lead-error">{err}</div>}
      <button type="submit" className="lead-submit"
                  disabled={submitting || (form.consent_required && !consent)}
                  data-testid="lead-submit-btn">
        {submitting
          ? <><Loader2 size={14} className="spin" /> Submitting…</>
          : <>{form.submit_button_label || "Start playing"} <ChevronRight size={14} /></>}
      </button>
    </form>
  );
}
