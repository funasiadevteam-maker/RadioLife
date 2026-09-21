// Sponsor Game Builder — stores configure a branded Wheel of Fortune or
// Scratch Card (logo + coupon prize pool + points). Writes to the shared
// `branded_games` model consumed by the 2.5D instant games.
import React, { useCallback, useEffect, useRef, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import {
  Aperture, Ticket, Plus, Trash2, Loader2, X, Upload, Play, Pause,
  Sparkles, Gift, Coins, Ban, ExternalLink, BarChart3, Users, Trophy, Eye,
} from "lucide-react";
import { useMerchant } from "./MerchantShell";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

const KIND_META = {
  points: { label: "Points", Icon: Coins, color: "#a855f7" },
  coupon: { label: "Coupon", Icon: Gift, color: "#ec4899" },
  none: { label: "Try again", Icon: Ban, color: "#475569" },
};

const DEFAULT_POOL = [
  { label: "50 pts", kind: "points", value: 50, weight: 24, color: "#a855f7" },
  { label: "100 pts", kind: "points", value: 100, weight: 20, color: "#ec4899" },
  { label: "Try again", kind: "none", value: 0, weight: 16, color: "#334155" },
  { label: "250 pts", kind: "points", value: 250, weight: 14, color: "#f59e0b" },
  { label: "500 pts", kind: "points", value: 500, weight: 10, color: "#22d3ee" },
  { label: "1000 pts", kind: "points", value: 1000, weight: 6, color: "#10b981" },
];

export default function MerchantSponsorGames() {
  const { merchant, light } = useMerchant();
  const mid = merchant?.merchant_id;
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null); // game object or {} for new
  const [analytics, setAnalytics] = useState(null); // game being analyzed

  const load = useCallback(async () => {
    if (!mid) return;
    setLoading(true);
    try {
      const { data } = await axios.get(`${API}/games/sponsor/${mid}/builder`,
        { withCredentials: true });
      setData(data);
    } catch (e) {
      toast.error(e?.response?.data?.detail?.code || "Couldn't load builder");
    } finally { setLoading(false); }
  }, [mid]);
  useEffect(() => { load(); }, [load]);

  const toggle = async (g) => {
    try {
      const { data: r } = await axios.post(
        `${API}/games/sponsor/${mid}/branded-games/${g.game_id}/toggle`,
        null, { withCredentials: true });
      toast.success(r.active ? "Game is live" : "Game paused");
      load();
    } catch (_) { toast.error("Couldn't update"); }
  };

  const bg = light
    ? "min-h-screen bg-gradient-to-b from-purple-50 via-white to-pink-50"
    : "min-h-screen bg-slate-950 text-slate-100";

  if (loading) return (
    <div className={`${bg} p-8`} data-testid="sponsor-games-loading">
      <Loader2 className="animate-spin mx-auto mt-24" size={30} />
    </div>);

  const games = data?.games || [];

  return (
    <div className={`${bg} p-4 sm:p-8`} data-testid="sponsor-games-page">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-start justify-between mb-6 gap-4 flex-wrap">
          <div>
            <div className={`text-[10px] font-black uppercase tracking-widest ${light ? "text-purple-600" : "text-cyan-400"}`}>
              Instant Games · Sponsor Builder
            </div>
            <h1 className={`text-3xl font-black tracking-tight ${light ? "text-slate-900" : "text-white"}`}>
              Sponsor a Game
            </h1>
            <p className={`text-sm mt-1 ${light ? "text-slate-600" : "text-slate-400"}`}>
              Build a branded 2.5D Wheel of Fortune or Scratch Card. Add your logo
              and mix your coupons with points as prizes.
            </p>
          </div>
          <button type="button" data-testid="sponsor-games-new-btn"
            onClick={() => setEditing({})}
            className="inline-flex items-center gap-2 h-11 rounded-full px-5 text-sm font-black text-white"
            style={{ background: "linear-gradient(135deg,#a855f7,#ec4899)" }}>
            <Plus size={16} /> New sponsor game
          </button>
        </div>

        {games.length === 0 ? (
          <div className={`rounded-3xl p-10 text-center ${light ? "bg-white border border-slate-100 shadow-sm" : "bg-slate-900 border border-slate-800"}`}
            data-testid="sponsor-games-empty">
            <Sparkles className="mx-auto mb-3" size={40} color={light ? "#a855f7" : "#00d4ff"} />
            <h3 className={`text-lg font-black ${light ? "text-slate-900" : "text-white"}`}>No sponsor games yet</h3>
            <p className={`text-sm mt-1 ${light ? "text-slate-600" : "text-slate-400"}`}>
              Launch a Wheel or Scratch Card to drive footfall — winners' coupons land straight in their wallet.
            </p>
          </div>
        ) : (
          <div className="grid sm:grid-cols-2 gap-3" data-testid="sponsor-games-list">
            {games.map((g) => (
              <GameCard key={g.game_id} g={g} light={light} onEdit={() => setEditing(g)} onToggle={() => toggle(g)} onAnalytics={() => setAnalytics(g)} />
            ))}
          </div>
        )}
      </div>

      {editing && (
        <BuilderModal light={light} mid={mid} data={data} initial={editing}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); load(); }} />
      )}
      {analytics && (
        <AnalyticsModal light={light} mid={mid} game={analytics} onClose={() => setAnalytics(null)} />
      )}
    </div>
  );
}

function GameCard({ g, light, onEdit, onToggle, onAnalytics }) {
  const isWheel = g.game_type === "wheel";
  const prizeCount = (g.segments || []).filter((s) => s.kind !== "none").length;
  const playUrl = `${typeof window !== "undefined" ? window.location.origin : ""}/games/${isWheel ? "spin" : "scratch"}?game_id=${g.game_id}`;
  return (
    <div className={`rounded-2xl p-4 ${light ? "bg-white border border-slate-100 shadow-sm" : "bg-slate-900 border border-slate-800"}`}
      data-testid={`sponsor-game-card-${g.game_id}`}>
      <div className="flex items-center gap-3">
        {g.logo_url
          ? <img src={g.logo_url} alt={g.sponsor_name} className="w-11 h-11 rounded-xl object-cover" />
          : <div className="w-11 h-11 rounded-xl grid place-items-center" style={{ background: "linear-gradient(135deg,#a855f7,#ec4899)" }}>
              {isWheel ? <Aperture size={20} className="text-white" /> : <Ticket size={20} className="text-white" />}
            </div>}
        <div className="min-w-0 flex-1">
          <div className={`text-sm font-black truncate ${light ? "text-slate-900" : "text-white"}`}>{g.sponsor_name}</div>
          <div className={`text-[11px] font-bold ${light ? "text-slate-500" : "text-slate-400"}`}>
            {isWheel ? "Wheel of Fortune" : "Scratch Card"} · {prizeCount} prize{prizeCount !== 1 ? "s" : ""} · {g.daily_spins}/day
          </div>
        </div>
        <span className={`text-[10px] font-black uppercase tracking-widest px-2 py-1 rounded-full ${g.active
          ? (light ? "bg-emerald-100 text-emerald-700" : "bg-emerald-500/15 text-emerald-300")
          : (light ? "bg-slate-100 text-slate-500" : "bg-slate-800 text-slate-500")}`}
          data-testid={`sponsor-game-status-${g.game_id}`}>
          {g.active ? "Live" : "Paused"}
        </span>
      </div>
      <div className="mt-3 flex items-center gap-2">
        <button type="button" onClick={onEdit} data-testid={`sponsor-game-edit-${g.game_id}`}
          className={`text-xs font-bold h-9 px-4 rounded-full ${light ? "bg-slate-100 text-slate-700 hover:bg-slate-200" : "bg-slate-800 text-slate-200 hover:bg-slate-700"}`}>
          Edit
        </button>
        <button type="button" onClick={onAnalytics} data-testid={`sponsor-game-analytics-${g.game_id}`}
          className={`inline-flex items-center gap-1.5 text-xs font-bold h-9 px-4 rounded-full ${light ? "bg-slate-100 text-slate-700 hover:bg-slate-200" : "bg-slate-800 text-slate-200 hover:bg-slate-700"}`}>
          <BarChart3 size={13} /> Analytics
        </button>
        <button type="button" onClick={onToggle} data-testid={`sponsor-game-toggle-${g.game_id}`}
          className={`inline-flex items-center gap-1.5 text-xs font-bold h-9 px-4 rounded-full ${light ? "bg-slate-100 text-slate-700 hover:bg-slate-200" : "bg-slate-800 text-slate-200 hover:bg-slate-700"}`}>
          {g.active ? <><Pause size={13} /> Pause</> : <><Play size={13} /> Resume</>}
        </button>
        <a href={playUrl} target="_blank" rel="noreferrer" data-testid={`sponsor-game-preview-${g.game_id}`}
          className="ml-auto inline-flex items-center gap-1 text-xs font-bold text-violet-500 hover:text-violet-400">
          Preview <ExternalLink size={12} />
        </a>
      </div>
    </div>
  );
}

function BuilderModal({ light, mid, data, initial, onClose, onSaved }) {
  const isEdit = !!initial.game_id;
  const [gameType, setGameType] = useState(initial.game_type || "wheel");
  const [sponsorName, setSponsorName] = useState(initial.sponsor_name || data?.business?.name || "");
  const [logoUrl, setLogoUrl] = useState(initial.logo_url || data?.business?.logo_url || "");
  const [dailySpins, setDailySpins] = useState(initial.daily_spins || data?.defaults?.daily_spins || 3);
  const [segments, setSegments] = useState(
    (initial.segments && initial.segments.length ? initial.segments : DEFAULT_POOL)
      .map((s) => ({ label: s.label, kind: s.kind || "points", value: s.value || 0, weight: s.weight || 1, color: s.color || "#a855f7", coupon_offer_id: s.coupon_offer_id || "" })));
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [preview, setPreview] = useState(false);
  const fileRef = useRef(null);
  const offers = data?.offers || [];

  const totalWeight = segments.reduce((s, x) => s + (Number(x.weight) || 0), 0);

  const update = (i, patch) => setSegments((arr) => arr.map((s, idx) => idx === i ? { ...s, ...patch } : s));
  const remove = (i) => setSegments((arr) => arr.filter((_, idx) => idx !== i));
  const add = () => setSegments((arr) => [...arr, { label: "50 pts", kind: "points", value: 50, weight: 8, color: "#a855f7", coupon_offer_id: "" }]);
  const loadPool = () => setSegments(DEFAULT_POOL.map((s) => ({ ...s, coupon_offer_id: "" })));

  const onPickKind = (i, kind) => {
    if (kind === "coupon") {
      const first = offers[0];
      update(i, { kind, coupon_offer_id: first?.offer_id || "", label: first?.title?.slice(0, 40) || "Coupon", color: "#ec4899" });
    } else if (kind === "none") {
      update(i, { kind, coupon_offer_id: "", label: "Try again", value: 0, color: "#334155" });
    } else {
      update(i, { kind, coupon_offer_id: "", label: "100 pts", value: 100, color: "#a855f7" });
    }
  };

  const onUpload = async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", f);
      const { data: r } = await axios.post(`${API}/games/sponsor/${mid}/game-logo`, fd,
        { withCredentials: true, headers: { "Content-Type": "multipart/form-data" } });
      setLogoUrl(r.logo_url);
      toast.success("Logo uploaded");
    } catch (err) {
      toast.error(err?.response?.data?.detail?.code || "Upload failed");
    } finally { setUploading(false); }
  };

  const save = async () => {
    if (!sponsorName.trim()) { toast.info("Give your game a sponsor name."); return; }
    if (segments.length === 0) { toast.info("Add at least one prize slice."); return; }
    if (totalWeight <= 0) { toast.info("Weights must add up to more than zero."); return; }
    for (const s of segments) {
      if (s.kind === "coupon" && !s.coupon_offer_id) { toast.info("Pick a coupon for each coupon slice."); return; }
    }
    setBusy(true);
    try {
      await axios.post(`${API}/games/sponsor/${mid}/branded-games`, {
        game_id: initial.game_id || undefined,
        game_type: gameType, sponsor_name: sponsorName.trim(),
        logo_url: logoUrl || undefined, daily_spins: Number(dailySpins) || 3,
        active: initial.active !== false,
        segments: segments.map((s) => ({
          label: s.label, kind: s.kind, value: Number(s.value) || 0,
          weight: Number(s.weight) || 1, color: s.color,
          coupon_offer_id: s.kind === "coupon" ? s.coupon_offer_id : undefined,
        })),
      }, { withCredentials: true });
      toast.success(isEdit ? "Game updated" : "Sponsor game created");
      onSaved();
    } catch (e) {
      toast.error(e?.response?.data?.detail?.code || e?.response?.data?.detail?.detail || "Couldn't save");
    } finally { setBusy(false); }
  };

  const input = light
    ? "w-full h-11 rounded-xl px-3 text-sm bg-slate-50 border border-slate-200 text-slate-900 outline-none focus:border-purple-500"
    : "w-full h-11 rounded-xl px-3 text-sm bg-slate-950 border border-slate-800 text-slate-100 outline-none focus:border-cyan-500";
  const smallInput = light
    ? "w-full h-9 rounded-lg px-2 text-xs bg-white border border-slate-300 text-slate-900 outline-none"
    : "w-full h-9 rounded-lg px-2 text-xs bg-slate-900 border border-slate-700 text-white outline-none";
  const lbl = `text-[10px] font-black uppercase tracking-widest mb-1 ${light ? "text-slate-500" : "text-slate-500"}`;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} data-testid="sponsor-builder-modal"
        className={`w-full max-w-lg rounded-3xl p-6 max-h-[95vh] overflow-y-auto ${light ? "bg-white" : "bg-slate-900 border border-slate-800"}`}>
        <div className="flex items-center justify-between mb-3">
          <h2 className={`text-xl font-black ${light ? "text-slate-900" : "text-white"}`}>
            {isEdit ? "Edit sponsor game" : "New sponsor game"}
          </h2>
          <button type="button" onClick={onClose} className={light ? "text-slate-500" : "text-slate-500"}><X size={20} /></button>
        </div>

        {/* Type */}
        <div className={lbl}>Game type</div>
        <div className="grid grid-cols-2 gap-2 mb-4">
          {[{ id: "wheel", label: "Wheel of Fortune", Icon: Aperture }, { id: "scratch", label: "Scratch Card", Icon: Ticket }].map((t) => (
            <button key={t.id} type="button" onClick={() => setGameType(t.id)} disabled={isEdit}
              data-testid={`sponsor-type-${t.id}`} data-active={gameType === t.id}
              className={`p-4 rounded-2xl text-left ${gameType === t.id
                ? (light ? "bg-purple-100 border-2 border-purple-500" : "bg-cyan-500/15 border-2 border-cyan-500")
                : (light ? "bg-slate-50 border-2 border-transparent" : "bg-slate-950 border-2 border-transparent")} ${isEdit ? "opacity-60" : ""}`}>
              <t.Icon size={22} color={gameType === t.id ? (light ? "#a855f7" : "#00d4ff") : (light ? "#94a3b8" : "#64748b")} />
              <div className={`mt-2 text-sm font-black ${light ? "text-slate-900" : "text-white"}`}>{t.label}</div>
            </button>
          ))}
        </div>

        {/* Sponsor name + logo */}
        <div className={lbl}>Sponsor name</div>
        <input value={sponsorName} onChange={(e) => setSponsorName(e.target.value)} data-testid="sponsor-name-input"
          placeholder="e.g. Karak House" className={`${input} mb-4`} />

        <div className={lbl}>Logo</div>
        <div className="flex items-center gap-3 mb-4">
          {logoUrl
            ? <img src={logoUrl} alt="logo" className="w-14 h-14 rounded-xl object-cover" data-testid="sponsor-logo-preview" />
            : <div className={`w-14 h-14 rounded-xl grid place-items-center ${light ? "bg-slate-100" : "bg-slate-800"}`}><Gift size={20} className="text-slate-400" /></div>}
          <div className="flex-1">
            <input value={logoUrl || ""} onChange={(e) => setLogoUrl(e.target.value)} data-testid="sponsor-logo-url"
              placeholder="Paste logo URL or upload" className={smallInput} />
            <button type="button" onClick={() => fileRef.current?.click()} disabled={uploading} data-testid="sponsor-logo-upload"
              className="mt-2 inline-flex items-center gap-1.5 text-xs font-bold text-violet-500 hover:text-violet-400">
              {uploading ? <Loader2 size={13} className="animate-spin" /> : <Upload size={13} />} Upload image
            </button>
            <input ref={fileRef} type="file" accept="image/*" hidden onChange={onUpload} />
          </div>
        </div>

        {/* Prize pool */}
        <div className="flex items-center justify-between mb-1">
          <div className={lbl}>Prize pool ({segments.length})</div>
          <button type="button" onClick={loadPool} data-testid="sponsor-load-pool"
            className="text-[11px] font-bold text-violet-500 hover:text-violet-400">Load points pool</button>
        </div>
        <div className="space-y-2 max-h-[300px] overflow-y-auto pr-1" data-testid="sponsor-segments">
          {segments.map((s, i) => {
            const meta = KIND_META[s.kind] || KIND_META.points;
            return (
              <div key={i} className={`rounded-xl p-3 ${light ? "bg-slate-50 border border-slate-200" : "bg-slate-950 border border-slate-800"}`}
                data-testid={`sponsor-segment-${i}`}>
                <div className="flex items-center gap-2 mb-2">
                  <span className="w-3 h-3 rounded-full shrink-0" style={{ background: s.color }} />
                  <select value={s.kind} onChange={(e) => onPickKind(i, e.target.value)} data-testid={`sponsor-segment-kind-${i}`}
                    className={`h-8 rounded-lg px-2 text-xs font-bold ${light ? "bg-white border border-slate-300" : "bg-slate-900 border border-slate-700 text-white"}`}>
                    {Object.entries(KIND_META).map(([k, m]) => <option key={k} value={k}>{m.label}</option>)}
                  </select>
                  <input value={s.label} onChange={(e) => update(i, { label: e.target.value.slice(0, 40) })} data-testid={`sponsor-segment-label-${i}`}
                    placeholder="Label" className={`flex-1 h-8 rounded-lg px-2 text-xs ${light ? "bg-white border border-slate-300" : "bg-slate-900 border border-slate-700 text-white"}`} />
                  <button type="button" onClick={() => remove(i)} data-testid={`sponsor-segment-remove-${i}`} className="text-rose-500 hover:text-rose-400"><Trash2 size={14} /></button>
                </div>
                <div className="grid grid-cols-3 gap-2">
                  {s.kind === "points" && (
                    <div>
                      <div className={lbl}>Points</div>
                      <input type="number" min={0} value={s.value} onChange={(e) => update(i, { value: Number(e.target.value) })}
                        data-testid={`sponsor-segment-points-${i}`} className={smallInput} />
                    </div>
                  )}
                  {s.kind === "coupon" && (
                    <div className="col-span-2">
                      <div className={lbl}>Coupon</div>
                      {offers.length === 0
                        ? <div className="text-[11px] text-amber-500">No offers yet — create one under Offers first.</div>
                        : <select value={s.coupon_offer_id} onChange={(e) => { const o = offers.find((x) => x.offer_id === e.target.value); update(i, { coupon_offer_id: e.target.value, label: (o?.title || "Coupon").slice(0, 40) }); }}
                            data-testid={`sponsor-segment-offer-${i}`} className={smallInput + " font-mono"}>
                            {offers.map((o) => <option key={o.offer_id} value={o.offer_id}>{o.title} ({o.status})</option>)}
                          </select>}
                    </div>
                  )}
                  <div>
                    <div className={lbl}>Weight</div>
                    <input type="number" min={0} value={s.weight} onChange={(e) => update(i, { weight: Number(e.target.value) })}
                      data-testid={`sponsor-segment-weight-${i}`} className={smallInput} />
                  </div>
                  <div>
                    <div className={lbl}>Color</div>
                    <input type="color" value={s.color} onChange={(e) => update(i, { color: e.target.value })}
                      className="w-full h-9 rounded-lg border-0 bg-transparent p-0" />
                  </div>
                </div>
              </div>
            );
          })}
        </div>
        <button type="button" onClick={add} data-testid="sponsor-segment-add"
          className={`mt-2 w-full h-10 rounded-xl border-2 border-dashed text-xs font-bold inline-flex items-center justify-center gap-1 ${light ? "border-purple-300 text-purple-700 hover:bg-purple-50" : "border-cyan-500/30 text-cyan-300 hover:bg-slate-800"}`}>
          <Plus size={14} /> Add slice
        </button>
        <div className={`mt-1 text-[10px] ${light ? "text-slate-500" : "text-slate-500"}`}>
          Weights sum to <b>{totalWeight}</b> — a higher weight means a slice is won more often.
        </div>

        {/* Daily plays */}
        <div className="mt-4">
          <div className={lbl}>Plays per player, per day</div>
          <input type="number" min={1} max={20} value={dailySpins} onChange={(e) => setDailySpins(e.target.value)}
            data-testid="sponsor-daily-spins" className={input} />
        </div>

        {/* Prize preview */}
        <button type="button" onClick={() => setPreview((v) => !v)} data-testid="sponsor-preview-toggle"
          className={`mt-4 w-full h-11 rounded-full inline-flex items-center justify-center gap-2 text-sm font-black ${light ? "bg-slate-100 text-slate-800 hover:bg-slate-200" : "bg-slate-800 text-slate-100 hover:bg-slate-700"}`}>
          <Eye size={16} /> {preview ? "Hide preview" : "Preview with my prizes"}
        </button>
        {preview && (
          <div className="mt-3" data-testid="sponsor-preview-panel">
            <GamePreview gameType={gameType} segments={segments} sponsorName={sponsorName} logoUrl={logoUrl} light={light} />
          </div>
        )}

        <button type="button" onClick={save} disabled={busy} data-testid="sponsor-save-btn"
          className="mt-5 w-full h-12 rounded-full font-black text-white disabled:opacity-50"
          style={{ background: "linear-gradient(135deg,#a855f7,#ec4899)" }}>
          {busy ? <Loader2 className="animate-spin mx-auto" /> : (isEdit ? "Save changes" : "Publish game")}
        </button>
      </div>
    </div>
  );
}

// ─── Prize Preview (client-only, uses the current draft segments) ───
function polar(cx, cy, r, degFromTop) {
  const t = ((degFromTop - 90) * Math.PI) / 180;
  return [cx + r * Math.cos(t), cy + r * Math.sin(t)];
}
function slicePath(cx, cy, R, i, seg) {
  const a0 = i * seg, a1 = (i + 1) * seg;
  const [x0, y0] = polar(cx, cy, R, a0);
  const [x1, y1] = polar(cx, cy, R, a1);
  const large = seg > 180 ? 1 : 0;
  return `M ${cx} ${cy} L ${x0.toFixed(2)} ${y0.toFixed(2)} A ${R} ${R} 0 ${large} 1 ${x1.toFixed(2)} ${y1.toFixed(2)} Z`;
}

function GamePreview({ gameType, segments, sponsorName, logoUrl, light }) {
  const [rotation, setRotation] = useState(0);
  const [spinning, setSpinning] = useState(false);
  const segs = (segments || []).filter((s) => (Number(s.weight) || 0) > 0);
  const spin = () => {
    if (spinning || segs.length === 0) return;
    setSpinning(true);
    const turns = 4 + Math.random() * 2;
    const target = rotation + turns * 360 + Math.random() * 360;
    setRotation(target);
    setTimeout(() => setSpinning(false), 3600);
  };
  const wrap = light ? "bg-slate-50 border border-slate-200" : "bg-slate-950 border border-slate-800";

  if (gameType === "scratch") {
    const tiles = segs.slice(0, 3);
    while (tiles.length < 3) tiles.push({ label: "?", color: "#334155" });
    return (
      <div className={`rounded-2xl p-4 ${wrap}`} data-testid="sponsor-preview-scratch">
        <PreviewHeader sponsorName={sponsorName} logoUrl={logoUrl} light={light} type="Scratch card" />
        <div className="grid grid-cols-3 gap-3 mt-3">
          {tiles.map((t, i) => (
            <div key={i} className="aspect-square rounded-2xl grid place-items-center text-center px-1"
              style={{ background: t.color || "#1c1830" }}>
              <span className="text-xs font-black text-white leading-tight">{t.label}</span>
            </div>
          ))}
        </div>
        <div className={`mt-2 text-center text-[11px] ${light ? "text-slate-500" : "text-slate-500"}`}>Match 3 to win</div>
      </div>
    );
  }

  const N = segs.length || 1;
  const seg = 360 / N;
  const cx = 130, cy = 130, R = 122;
  return (
    <div className={`rounded-2xl p-4 ${wrap}`} data-testid="sponsor-preview-wheel">
      <PreviewHeader sponsorName={sponsorName} logoUrl={logoUrl} light={light} type="Wheel of Fortune" />
      <div className="relative mx-auto mt-3" style={{ width: 260, height: 260 }}>
        <div style={{ position: "absolute", top: -2, left: "50%", transform: "translateX(-50%)", zIndex: 2,
          width: 0, height: 0, borderLeft: "10px solid transparent", borderRight: "10px solid transparent",
          borderTop: `18px solid ${light ? "#0f172a" : "#fff"}` }} />
        <svg viewBox="0 0 260 260" width={260} height={260}
          style={{ transform: `rotate(${rotation}deg)`, transition: spinning ? "transform 3.5s cubic-bezier(0.17,0.67,0.12,0.99)" : "none" }}>
          {segs.map((s, i) => {
            const [lx, ly] = polar(cx, cy, R * 0.66, i * seg + seg / 2);
            return (
              <g key={i}>
                <path d={slicePath(cx, cy, R, i, seg)} fill={s.color || "#334155"} stroke="rgba(0,0,0,0.25)" strokeWidth="1" />
                <text x={lx} y={ly} fill="#fff" fontSize="9" fontWeight="800" textAnchor="middle"
                  transform={`rotate(${i * seg + seg / 2} ${lx} ${ly})`}>{(s.label || "").slice(0, 12)}</text>
              </g>
            );
          })}
          <circle cx={cx} cy={cy} r="16" fill={light ? "#0f172a" : "#fff"} />
        </svg>
      </div>
      <button type="button" onClick={spin} disabled={spinning} data-testid="sponsor-preview-spin"
        className="mt-3 w-full h-11 rounded-full font-black text-white disabled:opacity-60"
        style={{ background: "linear-gradient(135deg,#a855f7,#ec4899)" }}>
        {spinning ? "Spinning…" : "Test spin"}
      </button>
      <div className={`mt-1 text-center text-[11px] ${light ? "text-slate-500" : "text-slate-500"}`}>Preview only — no prizes are awarded</div>
    </div>
  );
}

function PreviewHeader({ sponsorName, logoUrl, light, type }) {
  return (
    <div className="flex items-center gap-2 justify-center">
      {logoUrl
        ? <img src={logoUrl} alt={sponsorName} className="w-7 h-7 rounded-full object-cover" />
        : <Gift size={16} className={light ? "text-slate-500" : "text-slate-400"} />}
      <div className={`text-xs font-black ${light ? "text-slate-700" : "text-slate-300"}`}>
        {sponsorName || "Sponsor"} · {type}
      </div>
    </div>
  );
}

// ─── Analytics modal ───
function AnalyticsModal({ light, mid, game, onClose }) {
  const [d, setD] = useState(null);
  const [err, setErr] = useState(false);
  useEffect(() => {
    axios.get(`${API}/games/sponsor/${mid}/branded-games/${game.game_id}/analytics`, { withCredentials: true })
      .then((r) => setD(r.data)).catch(() => setErr(true));
  }, [mid, game.game_id]);
  const stat = (label, value, Icon) => (
    <div className={`rounded-xl p-3 ${light ? "bg-slate-50 border border-slate-100" : "bg-slate-950 border border-slate-800"}`}>
      <div className={`text-[10px] font-black uppercase tracking-widest inline-flex items-center gap-1 ${light ? "text-slate-500" : "text-slate-500"}`}>
        {Icon ? <Icon size={11} /> : null} {label}
      </div>
      <div className={`text-2xl font-black tabular-nums mt-0.5 ${light ? "text-slate-900" : "text-white"}`}>{value ?? 0}</div>
    </div>
  );
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} data-testid="sponsor-analytics-modal"
        className={`w-full max-w-lg rounded-3xl p-6 max-h-[92vh] overflow-y-auto ${light ? "bg-white" : "bg-slate-900 border border-slate-800"}`}>
        <div className="flex items-center justify-between mb-1">
          <h2 className={`text-xl font-black ${light ? "text-slate-900" : "text-white"}`}>Analytics</h2>
          <button type="button" onClick={onClose} className={light ? "text-slate-500" : "text-slate-500"}><X size={20} /></button>
        </div>
        <div className={`text-sm mb-4 ${light ? "text-slate-600" : "text-slate-400"}`}>
          {game.sponsor_name} · {game.game_type === "wheel" ? "Wheel of Fortune" : "Scratch Card"}
        </div>
        {err ? (
          <div className="text-sm text-rose-400">Couldn't load analytics.</div>
        ) : !d ? (
          <div className="py-10 text-center"><Loader2 className="animate-spin mx-auto" /></div>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-3" data-testid="sponsor-analytics-stats">
              {stat("Plays", d.plays, Play)}
              {stat("Wins", d.wins, Trophy)}
              {stat("Unique players", d.unique_players, Users)}
              {stat("Win rate", `${Math.round((d.win_rate || 0) * 100)}%`, BarChart3)}
              {stat("Points awarded", (d.points_awarded || 0).toLocaleString(), Coins)}
              {stat("Coupons won", d.coupons_won, Gift)}
              {stat("Coupons redeemed", d.coupons_redeemed, Ticket)}
            </div>
            <h3 className={`mt-6 mb-2 text-sm font-black ${light ? "text-slate-900" : "text-white"}`}>Prize distribution</h3>
            <div className="space-y-1" data-testid="sponsor-analytics-distribution">
              {(d.prize_distribution || []).length === 0 ? (
                <div className={`text-xs italic ${light ? "text-slate-500" : "text-slate-500"}`}>No plays yet.</div>
              ) : d.prize_distribution.map((p) => (
                <div key={p.label} className={`flex justify-between text-xs p-2 rounded-lg ${light ? "bg-slate-50" : "bg-slate-950"}`}>
                  <span className={light ? "text-slate-800" : "text-slate-200"}>{p.label}</span>
                  <span className={`font-black ${light ? "text-slate-900" : "text-white"}`}>{p.count}</span>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
