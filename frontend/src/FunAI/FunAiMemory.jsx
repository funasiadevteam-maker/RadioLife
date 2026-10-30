/** FunAiMemory — Companion Memory controls (web).
 *  Opt-out toggle (ON by default) + per-category chips the listener can add to
 *  or delete: favourite genres, favourite stations, disliked genres, languages
 *  and interests. Fun AI honours these approved preferences in every voice
 *  session. Renders nothing for signed-out users (the memory API needs auth). */
import React, { useEffect, useMemo, useState } from "react";
import axios from "axios";
import { Brain, X, Plus, Trash2, ChevronDown, ChevronUp } from "lucide-react";
import { API } from "@/AuthContext";

const CATS = [
  { k: "genres", label: "Favourite genres", ph: "e.g. Bollywood" },
  { k: "stations", label: "Favourite stations", ph: "e.g. Big 106.2" },
  { k: "disliked", label: "Disliked genres", ph: "e.g. Heavy metal" },
  { k: "languages", label: "Languages", ph: "e.g. Hindi" },
  { k: "interests", label: "Interests", ph: "e.g. Cricket" },
];

const slug = (s) => String(s).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");

function AddRow({ kind, ph, accent, line, chipBg, fg, sub, onAdd, prefix }) {
  const [val, setVal] = useState("");
  const submit = () => { const v = val.trim(); if (!v) return; onAdd(kind, v); setVal(""); };
  return (
    <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
      <input data-testid={`${prefix}-input-${kind}`}
             value={val} onChange={(e) => setVal(e.target.value)}
             onKeyDown={(e) => { if (e.key === "Enter") submit(); }}
             placeholder={ph} maxLength={60}
             style={{ flex: 1, padding: "7px 10px", borderRadius: 8, fontSize: 12,
                      border: `1px solid ${line}`, background: chipBg, color: fg }} />
      <button data-testid={`${prefix}-add-${kind}`} onClick={submit} aria-label={`Add ${kind}`}
              style={{ display: "inline-flex", alignItems: "center", gap: 4, background: accent,
                       color: "#001018", border: "none", borderRadius: 8, padding: "7px 12px",
                       fontWeight: 800, fontSize: 12, cursor: "pointer" }}>
        <Plus size={13} /> Add
      </button>
    </div>
  );
}

export default function FunAiMemory({ dark = true, accent = "#00b8d9",
                                      testIdPrefix = "fun-ai-memory" }) {
  const [mem, setMem] = useState(null);     // null = loading / unavailable (hidden)
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    axios.get(`${API}/fun-ai/memory`, { withCredentials: true })
      .then((r) => setMem(r.data || null))
      .catch(() => setMem(null));
  }, []);

  const pal = useMemo(() => dark ? {
    fg: "#f3f7ff", sub: "#b4c4de", line: "rgba(255,255,255,0.18)",
    chipBg: "rgba(255,255,255,0.08)", card: "rgba(8,12,22,0.62)",
  } : {
    fg: "#0b1220", sub: "#64748b", line: "rgba(0,0,0,0.12)",
    chipBg: "#f1f5f9", card: "#ffffff",
  }, [dark]);

  if (!mem) return null;

  const patch = (next) => setMem((m) => ({ ...m, ...next }));

  const toggle = async () => {
    const nextEnabled = !mem.enabled;
    patch({ enabled: nextEnabled });
    try {
      const r = await axios.put(`${API}/fun-ai/memory`, { enabled: nextEnabled },
                                { withCredentials: true });
      setMem(r.data);
    } catch { patch({ enabled: !nextEnabled }); }
  };

  const addItem = async (kind, value) => {
    try {
      const r = await axios.post(`${API}/fun-ai/memory`, { kind, value },
                                 { withCredentials: true });
      setMem(r.data);
    } catch { /* noop */ }
  };

  const removeItem = async (kind, value) => {
    try {
      const r = await axios.post(`${API}/fun-ai/memory/remove`, { kind, value },
                                 { withCredentials: true });
      setMem(r.data);
    } catch { /* noop */ }
  };

  const clearAll = async () => {
    setBusy(true);
    try {
      const r = await axios.post(`${API}/fun-ai/memory/clear`, {}, { withCredentials: true });
      setMem(r.data);
    } catch { /* noop */ } finally { setBusy(false); }
  };

  const total = CATS.reduce((n, c) => n + (mem[c.k]?.length || 0), 0);

  return (
    <div data-testid={`${testIdPrefix}-panel`}
         style={{ marginBottom: 14, background: pal.card, border: `1px solid ${pal.line}`,
                  borderRadius: 14, padding: 14 }}>
      {/* header row */}
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <div style={{ width: 32, height: 32, borderRadius: 9, display: "grid", placeItems: "center",
                      background: "rgba(0,184,217,0.12)", flexShrink: 0 }}>
          <Brain size={17} color={accent} />
        </div>
        <button data-testid={`${testIdPrefix}-expand`} onClick={() => setOpen((o) => !o)}
                style={{ flex: 1, textAlign: "left", background: "transparent", border: "none",
                         cursor: "pointer", color: pal.fg, padding: 0 }}>
          <div style={{ fontSize: 14, fontWeight: 800 }}>Companion Memory</div>
          <div style={{ fontSize: 11, color: pal.sub }}>
            {mem.enabled ? (total ? `${total} saved — Fun AI remembers these` : "On — add what Fun AI should remember")
                         : "Off — Fun AI won't use your saved preferences"}
          </div>
        </button>
        {/* on/off toggle */}
        <button data-testid={`${testIdPrefix}-toggle`} onClick={toggle} role="switch"
                aria-checked={mem.enabled}
                style={{ width: 44, height: 26, borderRadius: 999, border: "none", cursor: "pointer",
                         background: mem.enabled ? accent : (dark ? "#2a3444" : "#cbd5e1"),
                         position: "relative", transition: "background .15s", flexShrink: 0 }}>
          <span style={{ position: "absolute", top: 3, left: mem.enabled ? 21 : 3, width: 20, height: 20,
                         borderRadius: "50%", background: "#fff", transition: "left .15s" }} />
        </button>
        <button data-testid={`${testIdPrefix}-collapse-caret`} onClick={() => setOpen((o) => !o)}
                aria-label="Toggle details"
                style={{ background: "transparent", border: "none", cursor: "pointer",
                         color: pal.sub, display: "inline-flex", padding: 0 }}>
          {open ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
        </button>
      </div>

      {open && (
        <div data-testid={`${testIdPrefix}-body`} style={{ marginTop: 14,
             opacity: mem.enabled ? 1 : 0.55, pointerEvents: mem.enabled ? "auto" : "none" }}>
          {CATS.map((cat) => (
            <div key={cat.k} style={{ marginBottom: 14 }}>
              <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 1,
                            color: pal.sub, marginBottom: 6 }}>{cat.label}</div>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                {(mem[cat.k] || []).length === 0 && (
                  <span style={{ fontSize: 12, color: pal.sub, fontStyle: "italic" }}>Nothing saved yet</span>
                )}
                {(mem[cat.k] || []).map((v) => (
                  <span key={v} data-testid={`${testIdPrefix}-chip-${cat.k}-${slug(v)}`}
                        style={{ display: "inline-flex", alignItems: "center", gap: 6,
                                 background: pal.chipBg, border: `1px solid ${pal.line}`,
                                 borderRadius: 999, padding: "6px 10px", fontSize: 12, color: pal.fg }}>
                    {v}
                    <button data-testid={`${testIdPrefix}-remove-${cat.k}-${slug(v)}`}
                            onClick={() => removeItem(cat.k, v)} aria-label={`Remove ${v}`}
                            style={{ background: "transparent", border: "none", color: pal.sub,
                                     cursor: "pointer", padding: 0, display: "inline-flex" }}>
                      <X size={13} />
                    </button>
                  </span>
                ))}
              </div>
              <AddRow kind={cat.k} ph={cat.ph} accent={accent} line={pal.line} chipBg={pal.chipBg}
                      fg={pal.fg} sub={pal.sub} onAdd={addItem} prefix={testIdPrefix} />
            </div>
          ))}

          {total > 0 && (
            <button data-testid={`${testIdPrefix}-clear`} onClick={clearAll} disabled={busy}
                    style={{ display: "inline-flex", alignItems: "center", gap: 6, background: "transparent",
                             color: "#ef4444", border: "1px solid rgba(239,68,68,0.4)", borderRadius: 10,
                             padding: "8px 12px", fontWeight: 700, fontSize: 12,
                             cursor: busy ? "default" : "pointer", opacity: busy ? 0.6 : 1 }}>
              <Trash2 size={14} /> Clear everything Fun AI remembers
            </button>
          )}
        </div>
      )}
    </div>
  );
}
