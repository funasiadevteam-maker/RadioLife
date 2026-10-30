// Games → Appearance (admin). No-code control of the game-hub tiles shared by
// the web (PlayAndWin.js) and mobile (games.tsx) hubs. Backed by
// /api/admin/game-appearance/* — edit label/colour/icon/visibility, upload or
// AI-generate (Gemini) tile art, clear art, and reorder.
import React, { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { toast, Toaster } from "sonner";
import {
  ArrowLeft, Gamepad2, Upload, Sparkles, Trash2, Save, Loader2,
  ChevronUp, ChevronDown, Eye, EyeOff, X,
  Aperture, Gift, Music, Mic, HelpCircle, Dice5, Cherry, LayoutGrid,
  Type, Box, Layers, Trophy, Star, Rocket, Flame,
} from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
const BACKEND = process.env.REACT_APP_BACKEND_URL || "";

const COLORS = {
  bg: "#0a0a0c",
  surface: "rgba(255,255,255,0.02)",
  border: "rgba(255,255,255,0.08)",
  text: "#e7e7ea",
  muted: "#9aa3af",
  amber: "#f59e0b",
  green: "#22c55e",
  red: "#ef4444",
  inputBg: "#111114",
};

// Concept icon (backend CONCEPT_ICONS) → lucide component.
const ICON_MAP = {
  wheel: Aperture, gift: Gift, music: Music, mic: Mic, question: HelpCircle,
  dice: Dice5, slot: Cherry, grid: LayoutGrid, text: Type, cube: Box,
  cards: Layers, trophy: Trophy, star: Star, sparkles: Sparkles,
  rocket: Rocket, flame: Flame,
};

function resolveImg(url) {
  if (!url) return null;
  return url.startsWith("http") ? url : `${BACKEND}${url}`;
}

function GameCard({ game, icons, index, total, onSaved, onReorder }) {
  const [label, setLabel] = useState(game.label || "");
  const [color, setColor] = useState(game.color || "#a855f7");
  const [icon, setIcon] = useState(game.icon || "wheel");
  const [hidden, setHidden] = useState(!!game.hidden);
  const [imageUrl, setImageUrl] = useState(game.image_url || null);
  const [saving, setSaving] = useState(false);
  const [busy, setBusy] = useState(false);       // upload/generate/clear
  const [showGen, setShowGen] = useState(false);
  const [prompt, setPrompt] = useState("");
  const fileRef = useRef(null);

  const dirty =
    label !== (game.label || "") ||
    color !== (game.color || "#a855f7") ||
    icon !== (game.icon || "wheel") ||
    hidden !== !!game.hidden;

  const save = async () => {
    setSaving(true);
    try {
      const r = await axios.put(`${API}/admin/game-appearance/${game.key}`,
        { label, color, icon, hidden }, { withCredentials: true });
      toast.success(`Saved “${r.data.game.label}”`);
      onSaved();
    } catch (_e) {
      toast.error("Could not save changes");
    } finally { setSaving(false); }
  };

  const onPickFile = async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    if (f.size > 6 * 1024 * 1024) { toast.error("Image too large (max 6MB)"); return; }
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", f);
      const r = await axios.post(`${API}/admin/game-appearance/${game.key}/image`,
        fd, { withCredentials: true });
      setImageUrl(r.data.image_url);
      toast.success("Artwork uploaded");
      onSaved();
    } catch (_e) {
      toast.error("Upload failed");
    } finally { setBusy(false); if (fileRef.current) fileRef.current.value = ""; }
  };

  const generate = async () => {
    const p = prompt.trim();
    if (p.length < 3) { toast.error("Describe the art (min 3 chars)"); return; }
    setBusy(true);
    try {
      const r = await axios.post(`${API}/admin/game-appearance/${game.key}/generate`,
        { prompt: p }, { withCredentials: true });
      setImageUrl(r.data.image_url);
      setShowGen(false); setPrompt("");
      toast.success("AI artwork generated");
      onSaved();
    } catch (e) {
      const st = e?.response?.data?.detail?.status;
      toast.error(st === "image_gen_unconfigured"
        ? "Image generation is not configured"
        : "Generation failed — try a different prompt");
    } finally { setBusy(false); }
  };

  const autoGenerate = () => {
    setPrompt(`Fun, vibrant tile art representing the “${game.label}” game.`);
    setShowGen(true);
  };

  const clearImg = async () => {
    setBusy(true);
    try {
      await axios.delete(`${API}/admin/game-appearance/${game.key}/image`,
        { withCredentials: true });
      setImageUrl(null);
      toast.success("Artwork cleared");
      onSaved();
    } catch (_e) {
      toast.error("Could not clear artwork");
    } finally { setBusy(false); }
  };

  const Ic = ICON_MAP[icon] || Gamepad2;
  const preview = resolveImg(imageUrl);

  return (
    <div data-testid={`gameart-card-${game.key}`}
      style={{ display: "flex", flexDirection: "column", gap: 14,
        background: COLORS.surface, border: `1px solid ${COLORS.border}`,
        borderRadius: 16, padding: 16, opacity: hidden ? 0.72 : 1 }}>
      <div style={{ display: "flex", gap: 16 }}>
        {/* Art preview */}
        <div style={{ position: "relative", width: 92, height: 92, flexShrink: 0,
          borderRadius: 14, overflow: "hidden", background: color,
          display: "grid", placeItems: "center",
          border: `1px solid ${COLORS.border}` }}>
          {preview
            ? <img src={preview} alt={label} data-testid={`gameart-preview-${game.key}`}
                style={{ width: "100%", height: "100%", objectFit: "cover" }} />
            : <Ic size={34} color="#fff" />}
        </div>

        {/* Fields */}
        <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 10 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 10, fontWeight: 800, letterSpacing: 1,
              textTransform: "uppercase", color: COLORS.muted,
              background: "rgba(255,255,255,0.05)", padding: "2px 8px", borderRadius: 999 }}>
              {game.kind}
            </span>
            <span style={{ fontSize: 11, color: COLORS.muted, fontFamily: "monospace" }}>{game.key}</span>
            <div style={{ flex: 1 }} />
            <div style={{ display: "flex", gap: 4 }}>
              <button type="button" onClick={() => onReorder(index, -1)} disabled={index === 0}
                data-testid={`gameart-up-${game.key}`} title="Move up"
                style={iconBtn(index === 0)}><ChevronUp size={15} /></button>
              <button type="button" onClick={() => onReorder(index, 1)} disabled={index === total - 1}
                data-testid={`gameart-down-${game.key}`} title="Move down"
                style={iconBtn(index === total - 1)}><ChevronDown size={15} /></button>
            </div>
          </div>

          <input value={label} onChange={(e) => setLabel(e.target.value)} maxLength={60}
            data-testid={`gameart-label-${game.key}`} placeholder="Tile label"
            style={inputStyle} />

          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
            <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <input type="color" value={color} onChange={(e) => setColor(e.target.value)}
                data-testid={`gameart-color-${game.key}`}
                style={{ width: 34, height: 30, border: "none", background: "none", cursor: "pointer", padding: 0 }} />
              <span style={{ fontSize: 12, color: COLORS.muted, fontFamily: "monospace" }}>{color}</span>
            </label>

            <select value={icon} onChange={(e) => setIcon(e.target.value)}
              data-testid={`gameart-icon-${game.key}`}
              style={{ ...inputStyle, width: "auto", paddingRight: 24, cursor: "pointer" }}>
              {icons.map((ic) => <option key={ic} value={ic}>{ic}</option>)}
            </select>

            <button type="button" onClick={() => setHidden((h) => !h)}
              data-testid={`gameart-hidden-${game.key}`}
              style={{ display: "inline-flex", alignItems: "center", gap: 6,
                padding: "6px 12px", borderRadius: 999, cursor: "pointer",
                border: `1px solid ${hidden ? COLORS.red : COLORS.border}`,
                background: hidden ? "rgba(239,68,68,0.12)" : "rgba(34,197,94,0.1)",
                color: hidden ? "#fda4af" : "#4ade80", fontSize: 12, fontWeight: 700 }}>
              {hidden ? <><EyeOff size={13} /> Hidden</> : <><Eye size={13} /> Visible</>}
            </button>
          </div>
        </div>
      </div>

      {/* Actions */}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <input ref={fileRef} type="file" accept="image/*" onChange={onPickFile}
          data-testid={`gameart-file-${game.key}`} style={{ display: "none" }} />
        <button type="button" onClick={() => fileRef.current?.click()} disabled={busy}
          data-testid={`gameart-upload-${game.key}`} style={actionBtn()}>
          <Upload size={13} /> Upload
        </button>
        <button type="button" onClick={autoGenerate} disabled={busy}
          data-testid={`gameart-generate-${game.key}`}
          style={actionBtn("linear-gradient(135deg,#a855f7,#ec4899)", "#fff", "transparent")}>
          {busy ? <Loader2 size={13} className="spin" /> : <Sparkles size={13} />} AI Art
        </button>
        {imageUrl && (
          <button type="button" onClick={clearImg} disabled={busy}
            data-testid={`gameart-clear-${game.key}`}
            style={actionBtn("rgba(239,68,68,0.12)", "#fda4af", COLORS.red)}>
            <Trash2 size={13} /> Clear
          </button>
        )}
        <div style={{ flex: 1 }} />
        <button type="button" onClick={save} disabled={!dirty || saving}
          data-testid={`gameart-save-${game.key}`}
          style={actionBtn(dirty ? COLORS.amber : "rgba(255,255,255,0.05)",
            dirty ? "#1a1a1a" : COLORS.muted, "transparent")}>
          {saving ? <Loader2 size={13} className="spin" /> : <Save size={13} />} Save
        </button>
      </div>

      {/* AI prompt row */}
      {showGen && (
        <div data-testid={`gameart-genrow-${game.key}`}
          style={{ display: "flex", gap: 8, alignItems: "center",
            background: COLORS.inputBg, border: `1px solid ${COLORS.border}`,
            borderRadius: 12, padding: 10 }}>
          <Sparkles size={15} color="#c084fc" />
          <input value={prompt} onChange={(e) => setPrompt(e.target.value)} autoFocus
            data-testid={`gameart-prompt-${game.key}`} maxLength={400}
            placeholder="Describe the artwork (e.g. neon spinning wheel, confetti)"
            onKeyDown={(e) => { if (e.key === "Enter") generate(); }}
            style={{ ...inputStyle, flex: 1 }} />
          <button type="button" onClick={generate} disabled={busy}
            data-testid={`gameart-gen-submit-${game.key}`}
            style={actionBtn("linear-gradient(135deg,#a855f7,#ec4899)", "#fff", "transparent")}>
            {busy ? <Loader2 size={13} className="spin" /> : "Generate"}
          </button>
          <button type="button" onClick={() => setShowGen(false)} style={iconBtn(false)}>
            <X size={15} />
          </button>
        </div>
      )}
    </div>
  );
}

const inputStyle = {
  background: COLORS.inputBg, border: `1px solid ${COLORS.border}`,
  borderRadius: 10, color: COLORS.text, fontSize: 13, padding: "8px 11px",
  width: "100%", outline: "none",
};

function iconBtn(disabled) {
  return {
    display: "grid", placeItems: "center", width: 28, height: 28, borderRadius: 8,
    border: `1px solid ${COLORS.border}`, background: "rgba(255,255,255,0.03)",
    color: disabled ? "#444" : COLORS.muted, cursor: disabled ? "default" : "pointer",
  };
}

function actionBtn(bg = "rgba(255,255,255,0.05)", fg = COLORS.text, border = COLORS.border) {
  return {
    display: "inline-flex", alignItems: "center", gap: 6, padding: "8px 14px",
    borderRadius: 10, fontSize: 12.5, fontWeight: 700, cursor: "pointer",
    background: bg, color: fg,
    border: `1px solid ${border === "transparent" ? "transparent" : border}`,
  };
}

export default function AdminGamesAppearance() {
  const [games, setGames] = useState([]);
  const [icons, setIcons] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/admin/game-appearance`, { withCredentials: true });
      setGames(r.data.games || []);
      setIcons(r.data.icons || []);
    } catch (_e) {
      toast.error("Failed to load game art");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const reorder = async (index, dir) => {
    const next = [...games];
    const target = index + dir;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target], next[index]];
    setGames(next);  // optimistic
    try {
      await axios.post(`${API}/admin/game-appearance/reorder`,
        { keys: next.map((g) => g.key) }, { withCredentials: true });
    } catch (_e) {
      toast.error("Reorder failed");
      load();
    }
  };

  return (
    <div style={{ minHeight: "100vh", background: COLORS.bg, color: COLORS.text }}
      data-testid="admin-games-appearance-page">
      <Toaster theme="dark" position="bottom-right" richColors />
      <div style={{ maxWidth: 860, margin: "0 auto", padding: "24px 20px 60px" }}>
        <Link to="/admin" data-testid="gameart-back"
          style={{ display: "inline-flex", alignItems: "center", gap: 6,
            fontSize: 12, color: COLORS.muted, textDecoration: "none", marginBottom: 18 }}>
          <ArrowLeft size={14} /> Admin Home
        </Link>

        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 6 }}>
          <span style={{ width: 42, height: 42, borderRadius: 12, display: "grid",
            placeItems: "center", background: "rgba(168,85,247,0.15)", color: "#c084fc" }}>
            <Gamepad2 size={22} />
          </span>
          <div>
            <h1 style={{ fontSize: 24, fontWeight: 900, margin: 0 }}>Game Art</h1>
            <p style={{ fontSize: 13, color: COLORS.muted, margin: "2px 0 0" }}>
              Swap tile art, labels, colours & visibility for the web and mobile game hubs — no code.
            </p>
          </div>
        </div>

        {loading ? (
          <div style={{ display: "grid", placeItems: "center", padding: 80 }}>
            <Loader2 size={28} className="spin" color={COLORS.amber} />
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 14, marginTop: 20 }}
            data-testid="gameart-list">
            {games.map((g, i) => (
              <GameCard key={g.key} game={g} icons={icons} index={i} total={games.length}
                onSaved={load} onReorder={reorder} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
