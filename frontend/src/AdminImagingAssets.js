// AdminImagingAssets.js — Per-station asset management for Phase 3.8.
// Lists all imaging assets for a station, grouped by type. Lets admin
// preview audio, rate weight (rotation), toggle active, regenerate, edit script.
import { useEffect, useState, useCallback, useMemo } from "react";
import { useParams, Link } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import { Loader2, RefreshCcw, ChevronLeft, RotateCcw } from "lucide-react";
import "./AdminImaging.css";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
axios.defaults.withCredentials = true;

const TYPE_LABEL = {
  brand_id_short:  "Brand ID — Short",
  brand_id_long:   "Brand ID — Long",
  daypart_opener:  "Daypart Opener",
  top_of_hour:     "Top of Hour",
  sponsor_bumper:  "Sponsor Bumper",
  game_stinger:    "Game Stinger",
  winner_stinger:  "Winner Stinger",
  premium_id:      "Premium ID",
  legal_id:        "Legal ID",
  music_bed:       "Music Bed",
  sweeper_short:   "Sweeper",
};

function AssetRow({ a, stationSlug, onChange, onRegen }) {
  const [weight, setWeight] = useState(a.weight || 1.0);
  const [active, setActive] = useState(!!a.active);
  const [busy, setBusy] = useState(false);

  const status = a.generation_status || "pending";
  const audioUrl = status === "ready" ? `${process.env.REACT_APP_BACKEND_URL}${a.audio_url}` : null;

  const saveWeight = async (w) => {
    try {
      await axios.post(`${API}/admin/imaging/${stationSlug}/asset/${a.id}`, { weight: w });
    } catch (e) {
      toast.error("Save weight failed");
    }
  };
  const toggleActive = async () => {
    try {
      const nv = !active;
      await axios.post(`${API}/admin/imaging/${stationSlug}/asset/${a.id}`, { active: nv });
      setActive(nv);
      onChange?.();
    } catch (e) { toast.error("Toggle failed"); }
  };
  const regen = async () => {
    setBusy(true);
    try {
      const r = await axios.post(`${API}/admin/imaging/${stationSlug}/asset/${a.id}/regenerate`);
      toast.success(`Regenerated — ${r.data.asset.generation_status}`);
      onRegen?.();
    } catch (e) {
      toast.error("Regenerate failed");
    } finally { setBusy(false); }
  };

  return (
    <div className="asset-row" data-testid={`asset-row-${a.slug}`}>
      <div className="asset-row-head">
        <span className="asset-slug" data-testid={`asset-slug-${a.slug}`}>{a.slug}</span>
        <span className={`asset-status ${status}`} data-testid={`asset-status-${a.slug}`}>{status}</span>
      </div>

      <div className="asset-script">"{a.script}"</div>

      <div className="asset-meta-row">
        {a.voice_key && <span>VOICE<b>{a.voice_key}</b></span>}
        {a.daypart && <span>DAYPART<b>{a.daypart}</b></span>}
        {a.energy && <span>ENERGY<b>{a.energy}</b></span>}
        {a.duration_sec ? <span>DUR<b>{Number(a.duration_sec).toFixed(1)}s</b></span> : null}
        {a.loudness_lufs ? <span>LUFS<b>{Number(a.loudness_lufs).toFixed(1)}</b></span> : null}
      </div>

      {audioUrl ? (
        <audio
          controls
          src={audioUrl}
          preload="none"
          className="asset-audio"
          data-testid={`asset-audio-${a.slug}`}
        />
      ) : (
        <div style={{ fontSize: 11, color: "#6c6c78", fontStyle: "italic" }}>
          {status === "pending"
            ? "⏳ Awaiting generation — click Regenerate or use the bulk button on the dashboard."
            : status === "failed" ? "⚠️ Generation failed last time. Click Regenerate to retry."
            : "—"}
        </div>
      )}

      <div className="asset-actions">
        <input
          type="range" min="0" max="3" step="0.1"
          value={weight}
          onChange={(e) => { const w = Number(e.target.value); setWeight(w); }}
          onMouseUp={() => saveWeight(weight)}
          onTouchEnd={() => saveWeight(weight)}
          className="weight-slider"
          data-testid={`asset-weight-${a.slug}`}
        />
        <div style={{ width: 36, fontSize: 11, color: "#aaa" }}>{weight.toFixed(1)}x</div>
        <button
          type="button"
          className="asset-btn"
          onClick={toggleActive}
          data-testid={`asset-active-${a.slug}`}
        >
          {active ? "ACTIVE" : "MUTED"}
        </button>
        <button
          type="button"
          className="asset-btn primary"
          onClick={regen}
          disabled={busy}
          data-testid={`asset-regen-${a.slug}`}
        >
          {busy ? <Loader2 className="spin" size={12} /> : <RotateCcw size={12} />}
        </button>
      </div>
    </div>
  );
}

export default function AdminImagingAssets() {
  const { station } = useParams();
  const [items, setItems] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filterType, setFilterType] = useState("all");
  const [regenBusy, setRegenBusy] = useState(false);

  const fetchAssets = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/admin/imaging/${station}/assets`);
      setItems(r.data.items || []);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not load assets");
    } finally { setLoading(false); }
  }, [station]);

  useEffect(() => {
    fetchAssets();
    const t = setInterval(fetchAssets, 6000); // poll for generation progress
    return () => clearInterval(t);
  }, [fetchAssets]);

  const types = useMemo(() => {
    if (!items) return [];
    const tmap = {};
    items.forEach((i) => { tmap[i.asset_type] = (tmap[i.asset_type] || 0) + 1; });
    return Object.entries(tmap).sort();
  }, [items]);

  const visible = useMemo(() => {
    if (!items) return [];
    if (filterType === "all") return items;
    return items.filter((i) => i.asset_type === filterType);
  }, [items, filterType]);

  const regenAll = async () => {
    setRegenBusy(true);
    try {
      await axios.post(`${API}/admin/imaging/${station}/regenerate?limit=30`);
      toast.success("Bulk generation kicked off — assets will appear as they complete.");
    } catch (e) {
      toast.error("Bulk regen failed");
    } finally { setRegenBusy(false); }
  };

  if (loading || !items) {
    return <div className="admin-img-wrap" data-testid="assets-loading"><Loader2 className="spin" size={28} /></div>;
  }

  const totalReady = items.filter((i) => i.generation_status === "ready").length;

  return (
    <div className="admin-img-wrap" data-testid="admin-imaging-assets-page">
      <header className="admin-img-header">
        <div>
          <h1>
            <Link to="/admin/imaging" style={{ color: "#888892", marginRight: 10 }}><ChevronLeft size={20} style={{ verticalAlign: "-4px" }}/></Link>
            {station} — Imaging Assets
          </h1>
          <p>{items.length} assets configured · {totalReady} ready · per-asset audio + rotation weight + script editor.</p>
        </div>
        <div className="admin-img-pills">
          <button
            type="button"
            className="img-regenerate-btn"
            onClick={regenAll}
            disabled={regenBusy}
            data-testid="bulk-regen-btn"
          >
            {regenBusy ? <Loader2 className="spin" size={14} /> : <RefreshCcw size={14} />}
            {regenBusy ? " Kicking..." : " Bulk regenerate (30)"}
          </button>
        </div>
      </header>

      <div className="assets-toolbar" data-testid="asset-type-toolbar">
        <button
          type="button"
          className={`asset-type-chip ${filterType === "all" ? "on" : ""}`}
          onClick={() => setFilterType("all")}
          data-testid="filter-all"
        >
          ALL · {items.length}
        </button>
        {types.map(([t, n]) => (
          <button
            key={t}
            type="button"
            className={`asset-type-chip ${filterType === t ? "on" : ""}`}
            onClick={() => setFilterType(t)}
            data-testid={`filter-${t}`}
          >
            {(TYPE_LABEL[t] || t)} · {n}
          </button>
        ))}
      </div>

      <div className="assets-grid">
        {visible.map((a) => (
          <AssetRow key={a.id} a={a} stationSlug={station} onChange={fetchAssets} onRegen={fetchAssets} />
        ))}
      </div>
    </div>
  );
}
