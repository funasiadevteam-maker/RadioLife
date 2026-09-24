// Advertiser Self-Serve — a store owner uploads a banner creative, picks
// rail/inline slots + a click destination, and publishes it live (instant
// house inventory), submits for review, or promotes (paid). Also shows each
// live banner's impressions / clicks / CTR.
import React, { useCallback, useEffect, useRef, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import {
  Megaphone, Upload, Loader2, Eye, MousePointerClick, Play, Pause,
  ExternalLink, Check, Rocket, ShieldCheck, CreditCard,
} from "lucide-react";
import { useMerchant } from "./MerchantShell";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
const BACKEND = process.env.REACT_APP_BACKEND_URL || "";

const MODES = [
  { key: "instant", label: "Go live now", sub: "Publishes immediately — free house inventory", Icon: Rocket },
  { key: "review", label: "Submit for review", sub: "An admin approves before it shows", Icon: ShieldCheck },
  { key: "paid", label: "Promote (paid)", sub: "Checkout, then admin approval", Icon: CreditCard },
];

const STATUS_STYLE = {
  active: { bg: "bg-emerald-500/15", text: "text-emerald-400", label: "LIVE" },
  paused: { bg: "bg-amber-500/15", text: "text-amber-400", label: "PAUSED" },
  pending: { bg: "bg-sky-500/15", text: "text-sky-400", label: "IN REVIEW" },
  pending_payment: { bg: "bg-fuchsia-500/15", text: "text-fuchsia-400", label: "AWAITING PAYMENT" },
  rejected: { bg: "bg-rose-500/15", text: "text-rose-400", label: "REJECTED" },
  completed: { bg: "bg-slate-500/15", text: "text-slate-400", label: "ENDED" },
};

const absUrl = (u) => (u && u.startsWith("/") ? `${BACKEND}${u}` : u);

export default function MerchantAdvertise() {
  const { merchant, light } = useMerchant();
  const mid = merchant?.merchant_id;
  const [slots, setSlots] = useState([]);
  const [mine, setMine] = useState([]);
  const [loading, setLoading] = useState(true);
  const [creativeUrl, setCreativeUrl] = useState("");
  const [uploading, setUploading] = useState(false);
  const [clickUrl, setClickUrl] = useState("");
  const [picked, setPicked] = useState([]);
  const [mode, setMode] = useState("instant");
  const [publishing, setPublishing] = useState(false);
  const fileRef = useRef(null);

  const load = useCallback(async () => {
    if (!mid) return;
    setLoading(true);
    try {
      const [s, m] = await Promise.all([
        axios.get(`${API}/ads/portal/banner/slots`, { withCredentials: true }),
        axios.get(`${API}/ads/portal/banner/mine`,
          { params: { merchant_id: mid }, withCredentials: true }),
      ]);
      setSlots(s.data.slots || []);
      setMine(m.data.items || []);
    } catch (e) {
      toast.error("Couldn't load your banners");
    } finally { setLoading(false); }
  }, [mid]);
  useEffect(() => { load(); }, [load]);

  const onFile = async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    if (!["image/png", "image/jpeg", "image/webp"].includes(f.type)) {
      toast.error("PNG, JPG or WEBP only"); return;
    }
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("merchant_id", mid);
      fd.append("file", f);
      const r = await axios.post(`${API}/ads/portal/banner/upload-creative`, fd,
        { withCredentials: true, headers: { "Content-Type": "multipart/form-data" } });
      setCreativeUrl(r.data.creative_image_url);
      toast.success("Creative uploaded");
    } catch (e) {
      const d = e?.response?.data?.detail;
      toast.error((d && (d.message || d.code)) || "Upload failed");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const togglePick = (sk) =>
    setPicked((p) => (p.includes(sk) ? p.filter((x) => x !== sk) : [...p, sk]));

  const publish = async () => {
    if (!creativeUrl) { toast.warning("Upload a banner image first"); return; }
    if (!picked.length) { toast.warning("Pick at least one slot"); return; }
    setPublishing(true);
    try {
      const r = await axios.post(`${API}/ads/portal/banner/publish`, {
        merchant_id: mid, creative_image_url: creativeUrl,
        click_url: clickUrl, slot_keys: picked, publish_mode: mode,
      }, { withCredentials: true });
      if (mode === "paid" && r.data.campaign_id) {
        const co = await axios.post(
          `${API}/ads/advertiser/banner-campaigns/${r.data.campaign_id}/checkout`,
          {}, { withCredentials: true });
        if (co.data.checkout_url) { window.location.href = absUrl(co.data.checkout_url); return; }
      }
      toast.success(r.data.live ? "Your banner is live! 🎉" : "Submitted — pending approval");
      setCreativeUrl(""); setClickUrl(""); setPicked([]); setMode("instant");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail?.code || "Couldn't publish");
    } finally { setPublishing(false); }
  };

  const toggle = async (c) => {
    try {
      const r = await axios.post(`${API}/ads/portal/banner/${c.campaign_id}/toggle`,
        {}, { withCredentials: true });
      toast.success(r.data.status === "active" ? "Banner is live" : "Banner paused");
      load();
    } catch { toast.error("Couldn't update"); }
  };

  const bg = light
    ? "min-h-screen bg-gradient-to-b from-purple-50 via-white to-pink-50"
    : "min-h-screen bg-slate-950 text-slate-100";
  const card = light ? "bg-white border-slate-200" : "bg-slate-900/70 border-slate-800";
  const muted = light ? "text-slate-600" : "text-slate-400";

  if (loading) return (
    <div className={`${bg} p-8`} data-testid="advertise-loading">
      <Loader2 className="animate-spin mx-auto mt-24" size={30} />
    </div>);

  return (
    <div className={`${bg} p-4 sm:p-8`} data-testid="advertise-page">
      <div className="max-w-4xl mx-auto">
        <div className="mb-6">
          <div className={`text-[10px] font-black uppercase tracking-widest ${light ? "text-purple-600" : "text-cyan-400"}`}>
            Advertising · Self-Serve
          </div>
          <h1 className={`text-3xl font-black tracking-tight flex items-center gap-2 ${light ? "text-slate-900" : "text-white"}`}>
            <Megaphone size={26} /> Promote your business
          </h1>
          <p className={`text-sm mt-1 ${muted}`}>
            Upload a banner, pick where it shows, and go live across the app in seconds.
          </p>
        </div>

        {/* Builder */}
        <div className={`rounded-2xl border p-5 ${card}`}>
          {/* Creative */}
          <label className={`text-xs font-black uppercase tracking-wide ${muted}`}>Banner image</label>
          <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp"
                    onChange={onFile} className="hidden" data-testid="advertise-file-input" />
          <div className="mt-2 flex items-center gap-4 flex-wrap">
            <button type="button" onClick={() => fileRef.current?.click()} disabled={uploading}
                        data-testid="advertise-upload-btn"
                        className="inline-flex items-center gap-2 h-11 rounded-full px-5 text-sm font-black text-white bg-gradient-to-r from-amber-500 to-pink-500 disabled:opacity-50">
              {uploading ? <Loader2 size={16} className="animate-spin" /> : <Upload size={16} />}
              {uploading ? "Uploading…" : (creativeUrl ? "Replace image" : "Upload image")}
            </button>
            <span className={`text-xs ${muted}`}>PNG / JPG / WEBP · up to 4 MB · ~300×250</span>
          </div>
          {creativeUrl && (
            <div className="mt-3" data-testid="advertise-creative-preview">
              <img src={absUrl(creativeUrl)} alt="preview"
                      className="rounded-xl border border-slate-700 max-w-[300px] w-full" />
            </div>
          )}

          {/* Click URL */}
          <div className="mt-5">
            <label className={`text-xs font-black uppercase tracking-wide ${muted}`}>Click destination (optional)</label>
            <input value={clickUrl} onChange={(e) => setClickUrl(e.target.value)}
                      placeholder="Defaults to your business page"
                      data-testid="advertise-click-url"
                      className={`mt-2 w-full h-11 rounded-xl px-3 text-sm border ${light ? "bg-white border-slate-300 text-slate-900" : "bg-slate-950 border-slate-700 text-slate-100"}`} />
          </div>

          {/* Slots */}
          <div className="mt-5">
            <label className={`text-xs font-black uppercase tracking-wide ${muted}`}>Where should it show?</label>
            <div className="mt-2 flex flex-wrap gap-2">
              {slots.map((s) => {
                const on = picked.includes(s.slot_key);
                return (
                  <button key={s.slot_key} type="button" onClick={() => togglePick(s.slot_key)}
                              data-testid={`advertise-slot-${s.slot_key}`}
                              className={`inline-flex items-center gap-1.5 h-9 rounded-full px-3 text-xs font-bold border transition ${on
                                ? "bg-cyan-500/20 border-cyan-400 text-cyan-300"
                                : (light ? "bg-white border-slate-300 text-slate-600" : "bg-slate-950 border-slate-700 text-slate-300")}`}>
                    {on && <Check size={13} />}{s.label} <span className="opacity-50">{s.size}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Publish mode */}
          <div className="mt-5">
            <label className={`text-xs font-black uppercase tracking-wide ${muted}`}>Publish</label>
            <div className="mt-2 grid sm:grid-cols-3 gap-2">
              {MODES.map((m) => {
                const on = mode === m.key;
                return (
                  <button key={m.key} type="button" onClick={() => setMode(m.key)}
                              data-testid={`advertise-mode-${m.key}`}
                              className={`text-left rounded-xl p-3 border transition ${on
                                ? "border-cyan-400 bg-cyan-500/10"
                                : (light ? "border-slate-200 bg-white" : "border-slate-800 bg-slate-950")}`}>
                    <div className={`flex items-center gap-1.5 text-sm font-black ${on ? "text-cyan-300" : (light ? "text-slate-900" : "text-slate-100")}`}>
                      <m.Icon size={15} />{m.label}
                    </div>
                    <div className={`text-[11px] mt-1 ${muted}`}>{m.sub}</div>
                  </button>
                );
              })}
            </div>
          </div>

          <button type="button" onClick={publish} disabled={publishing}
                      data-testid="advertise-publish-btn"
                      className="mt-6 inline-flex items-center gap-2 h-12 rounded-full px-6 text-sm font-black text-white bg-gradient-to-r from-cyan-500 to-emerald-500 disabled:opacity-50">
            {publishing ? <Loader2 size={16} className="animate-spin" /> : <Rocket size={16} />}
            {mode === "instant" ? "Publish & go live" : mode === "review" ? "Submit for review" : "Continue to payment"}
          </button>
        </div>

        {/* My banners + performance */}
        <div className="mt-8">
          <h2 className={`text-lg font-black ${light ? "text-slate-900" : "text-white"}`}>Your banners</h2>
          {mine.length === 0 ? (
            <div className={`mt-3 rounded-2xl border border-dashed p-8 text-center ${muted} ${card}`}
                    data-testid="advertise-empty">
              No banners yet — upload one above to reach shoppers across the app.
            </div>
          ) : (
            <div className="mt-3 space-y-3" data-testid="advertise-my-list">
              {mine.map((c) => {
                const st = STATUS_STYLE[c.status] || STATUS_STYLE.completed;
                return (
                  <div key={c.campaign_id} data-testid={`advertise-row-${c.campaign_id}`}
                          className={`rounded-2xl border p-3 flex items-center gap-4 flex-wrap ${card}`}>
                    <img src={absUrl(c.creative_image_url)} alt=""
                            className="w-20 h-16 object-cover rounded-lg border border-slate-700 flex-shrink-0" />
                    <div className="flex-1 min-w-[140px]">
                      <div className="flex items-center gap-2">
                        <span className={`text-[10px] font-black px-2 py-0.5 rounded-full ${st.bg} ${st.text}`}>{st.label}</span>
                        <span className={`text-xs ${muted}`}>{(c.slot_keys || []).length} slot(s)</span>
                      </div>
                      <a href={absUrl(c.click_url)} target="_blank" rel="noreferrer"
                          className="text-xs text-cyan-400 inline-flex items-center gap-1 mt-1 truncate max-w-[220px]">
                        {c.click_url} <ExternalLink size={11} />
                      </a>
                    </div>
                    <div className="flex items-center gap-4">
                      <Stat Icon={Eye} label="Impr." value={c.impressions} testid={`advertise-impr-${c.campaign_id}`} muted={muted} />
                      <Stat Icon={MousePointerClick} label="Clicks" value={c.clicks} testid={`advertise-clicks-${c.campaign_id}`} muted={muted} />
                      <Stat Icon={null} label="CTR" value={`${((c.ctr || 0) * 100).toFixed(2)}%`} testid={`advertise-ctr-${c.campaign_id}`} muted={muted} />
                    </div>
                    {(c.status === "active" || c.status === "paused") && (
                      <button type="button" onClick={() => toggle(c)}
                                  data-testid={`advertise-toggle-${c.campaign_id}`}
                                  className={`inline-flex items-center gap-1.5 h-9 rounded-full px-3 text-xs font-bold border ${c.status === "active"
                                    ? "border-amber-400 text-amber-300" : "border-emerald-400 text-emerald-300"}`}>
                        {c.status === "active" ? <><Pause size={13} />Pause</> : <><Play size={13} />Resume</>}
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Stat({ Icon, label, value, testid, muted }) {
  return (
    <div className="text-center min-w-[54px]" data-testid={testid}>
      <div className="text-base font-black flex items-center justify-center gap-1">
        {Icon && <Icon size={13} className="opacity-60" />}{value}
      </div>
      <div className={`text-[10px] uppercase tracking-wide ${muted}`}>{label}</div>
    </div>
  );
}
