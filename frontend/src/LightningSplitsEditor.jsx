// Phase 36d Turn 3 — Lightning splits editor (placeholder schema).
//
// Reusable editor used by both CreatorChannelSettings.jsx (channel default)
// and TranscriptEditor.jsx (per-episode override).
//
// NO real Lightning payment processing. The recipients list is written to
// the `podcast_lightning_splits` collection and emitted in the RSS feed
// via `<podcast:value>` so Podcasting 2.0 apps can stream sats directly.

import React, {useEffect, useMemo, useState} from "react";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

const EMPTY_RECIPIENT = () => ({
  name: "", type: "node", address: "", split_pct: 0, fee_pct: 0,
});

function totalSplit(recipients) {
  return recipients.reduce((s, r) => s + (Number(r.split_pct) || 0), 0);
}

/**
 * Props:
 *   testIdPrefix: "lightning" | "lightning-ep"  (UI namespace)
 *   loadUrl:     GET endpoint
 *   saveUrl:     PUT endpoint
 *   helperText:  string shown at the top
 *   readOnly:    when true, render values without inputs
 *   onChangeDirty: optional callback(recipientsCount) — used by parent
 *                                  to react to row count when needed.
 */
export function LightningSplitsEditor({
  testIdPrefix, loadUrl, saveUrl, helperText, readOnly,
}) {
  const [loaded, setLoaded] = useState(false);
  const [recipients, setRecipients] = useState([]);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    if (!loadUrl) { setLoaded(true); return; }
    axios.get(loadUrl, {withCredentials: true})
      .then((r) => {
        setRecipients((r.data?.recipients || []).map((x) => ({
          name: x.name || "", type: x.type || "node",
          address: x.address || "",
          split_pct: Number(x.split_pct) || 0,
          fee_pct: Number(x.fee_pct) || 0,
        })));
        setLoaded(true);
      })
      .catch((e) => { setErr(_msg(e)); setLoaded(true); });
  }, [loadUrl]);

  const total = useMemo(() => totalSplit(recipients), [recipients]);
  const validTotal = Math.abs(total - 100) <= 0.5;
  const totalColor = validTotal ? "#22c55e" : "#ef4444";

  const updateRow = (i, patch) =>
    setRecipients(recipients.map((r, idx) => idx === i ? {...r, ...patch} : r));
  const removeRow = (i) =>
    setRecipients(recipients.filter((_, idx) => idx !== i));
  const addRow = () =>
    setRecipients([...recipients, EMPTY_RECIPIENT()]);

  const save = async () => {
    if (!validTotal || !saveUrl) return;
    setSaving(true); setErr("");
    try {
      const r = await axios.put(saveUrl, {recipients},
                                                {withCredentials: true});
      setRecipients(r.data?.recipients || recipients);
    } catch (e) {
      setErr(_msg(e));
    } finally { setSaving(false); }
  };

  if (!loaded) return (
    <div data-testid={`${testIdPrefix}-loading`}
              style={{color: "#9aa3af"}}>Loading splits…</div>
  );

  return (
    <div data-testid={`${testIdPrefix}-editor`}>
      {helperText && (
        <p style={{fontSize: 12, color: "#9aa3af", marginBottom: 12,
                              lineHeight: 1.5}}>
          {helperText}
        </p>
      )}
      {err && (
        <div data-testid={`${testIdPrefix}-err`}
                  style={{color: "#ef4444", marginBottom: 8, fontSize: 12}}>
          {err}
        </div>
      )}
      <div style={{display: "grid",
                          gridTemplateColumns: "1.2fr 0.6fr 1.6fr 0.5fr 0.4fr 0.2fr",
                          gap: 6, fontSize: 10, color: "#6b7280",
                          textTransform: "uppercase", letterSpacing: 0.5,
                          marginBottom: 4, padding: "0 4px"}}>
        <div>Name</div><div>Type</div><div>Address</div>
        <div>Split %</div><div>Fee %</div><div></div>
      </div>
      {recipients.map((r, i) => (
        <div key={i} data-testid={`${testIdPrefix}-row-${i}`}
                  style={{display: "grid",
                              gridTemplateColumns: "1.2fr 0.6fr 1.6fr 0.5fr 0.4fr 0.2fr",
                              gap: 6, marginBottom: 6, alignItems: "center"}}>
          <input data-testid={`${testIdPrefix}-name-${i}`}
                      value={r.name} disabled={readOnly}
                      onChange={(e) => updateRow(i, {name: e.target.value})}
                      placeholder="Recipient name" style={inp()}/>
          <select data-testid={`${testIdPrefix}-type-${i}`}
                          value={r.type} disabled={readOnly}
                          onChange={(e) => updateRow(i, {type: e.target.value})}
                          style={inp()}>
            <option value="node">node</option>
            <option value="lnaddress">lnaddress</option>
          </select>
          <input data-testid={`${testIdPrefix}-address-${i}`}
                      value={r.address} disabled={readOnly}
                      onChange={(e) => updateRow(i, {address: e.target.value})}
                      placeholder={r.type === "node" ? "66-char node pubkey" : "user@domain.tld"}
                      style={{...inp(), fontFamily: "monospace", fontSize: 11}}/>
          <input data-testid={`${testIdPrefix}-split-${i}`} type="number"
                      min={0} max={100} step={0.5} disabled={readOnly}
                      value={r.split_pct}
                      onChange={(e) => updateRow(i, {split_pct: Number(e.target.value)})}
                      style={inp()}/>
          <input data-testid={`${testIdPrefix}-fee-${i}`} type="number"
                      min={0} max={10} step={0.1} disabled={readOnly}
                      value={r.fee_pct}
                      onChange={(e) => updateRow(i, {fee_pct: Number(e.target.value)})}
                      style={inp()}/>
          <button data-testid={`${testIdPrefix}-delete-${i}`}
                          disabled={readOnly}
                          onClick={() => removeRow(i)}
                          style={trash()}>×</button>
        </div>
      ))}
      {!readOnly && (
        <button data-testid={`${testIdPrefix}-add`} onClick={addRow}
                        style={btnSec(false)}>+ Add recipient</button>
      )}
      <div style={{display: "flex", alignItems: "center", gap: 8,
                          marginTop: 12}}>
        <span data-testid={`${testIdPrefix}-total-chip`}
                  style={{padding: "4px 10px", borderRadius: 999,
                              background: `${totalColor}22`, color: totalColor,
                              fontSize: 12, fontWeight: 700,
                              fontFamily: "monospace"}}>
          Total: {total.toFixed(1)}%
        </span>
        {!readOnly && saveUrl && (
          <button data-testid={`${testIdPrefix}-save`} onClick={save}
                          disabled={!validTotal || saving || recipients.length === 0}
                          style={btnPrimary(!validTotal || saving)}>
            {saving ? "Saving…" : "Save splits"}
          </button>
        )}
      </div>
    </div>
  );
}

function _msg(e) {
  return e?.response?.data?.detail || e?.message || String(e);
}

const inp = () => ({padding: "5px 8px", borderRadius: 5,
  background: "#0a0a14", color: "#fff",
  border: "1px solid rgba(255,255,255,0.1)", width: "100%",
  fontSize: 12});
const trash = () => ({padding: 0, width: 26, height: 26, borderRadius: 4,
  background: "transparent", color: "#ef4444",
  border: "1px solid rgba(239,68,68,0.4)", cursor: "pointer", fontSize: 16,
  lineHeight: 1});
const btnPrimary = (disabled) => ({padding: "6px 14px", borderRadius: 6,
  fontWeight: 700, cursor: disabled ? "not-allowed" : "pointer",
  background: disabled ? "#3f3f46" : "#f59e0b",
  color: disabled ? "#a1a1aa" : "#0a0a0c",
  border: "none", fontSize: 12});
const btnSec = (disabled) => ({padding: "6px 12px", borderRadius: 6,
  fontWeight: 600, cursor: disabled ? "not-allowed" : "pointer",
  background: "rgba(255,255,255,0.04)", color: "#e7e7ea",
  border: "1px solid rgba(255,255,255,0.1)", fontSize: 12,
  marginTop: 4});
