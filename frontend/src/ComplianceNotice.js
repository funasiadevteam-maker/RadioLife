// Phase 8c — Compliance notice shown on the game intro card BEFORE start.
// Shows terms excerpt, full T&C disclosure expandable, odds line, NPN line,
// and an age-gate dropdown when age_restriction > 0.
import { useState } from "react";
import { ChevronDown, ChevronUp, FileText, AlertCircle } from "lucide-react";

const AGE_OPTIONS = [
  { v: "", label: "Select age" },
  { v: "13-17", n: 17 },
  { v: "18-20", n: 20 },
  { v: "21-29", n: 29 },
  { v: "30-44", n: 44 },
  { v: "45-64", n: 64 },
  { v: "65+", n: 65 },
];


export default function ComplianceNotice({ compliance, prizes,
                                                        onConfirm, ageGateValue,
                                                        onAgeChange }) {
  const [open, setOpen] = useState(false);
  const ageReq = parseInt(compliance?.age_restriction || "0", 10);
  const odds = compliance?.odds_disclosure;
  const npn = compliance?.no_purchase_necessary_text;
  const terms = compliance?.terms_text;
  const fullTandc = compliance?.full_terms_url || null;

  if (!terms && !odds && !npn && !ageReq) return null;
  return (
    <div className="compliance-notice" data-testid="compliance-notice">
      <div className="compl-header" onClick={() => setOpen(!open)}>
        <FileText size={14} />
        <span>Rules & disclosures</span>
        {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
      </div>
      {open && (
        <div className="compl-body">
          {terms && (
            <p className="compl-line">
              <span className="mono dim">TERMS · </span>
              {terms.slice(0, 280)}
              {terms.length > 280 && <>…
                {fullTandc && <a href={fullTandc} target="_blank"
                                      rel="noreferrer"
                                      className="compl-link">read more</a>}
              </>}
            </p>
          )}
          {odds && (
            <p className="compl-line">
              <span className="mono dim">ODDS · </span>{odds}
            </p>
          )}
          {npn && (
            <p className="compl-line">
              <span className="mono dim">NPN · </span>{npn}
            </p>
          )}
          {ageReq > 0 && (
            <div className="compl-age-gate" data-testid="age-gate">
              <AlertCircle size={12} />
              <span>This campaign is restricted to {ageReq}+.</span>
              <select className="compl-age-select"
                         value={ageGateValue || ""}
                         onChange={(e) => onAgeChange && onAgeChange(e.target.value)}
                         data-testid="age-gate-select">
                {AGE_OPTIONS.map((o) => (
                  <option key={o.v} value={o.v}>{o.label || o.v}</option>
                ))}
              </select>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
