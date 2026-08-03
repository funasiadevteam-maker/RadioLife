// Phase 18b — AI Ad Creator wizard.
//   Form → 3-step progress → preview (audio + image + transcript + safety badge)
//   → save to creatives library.
import { useEffect, useState } from "react";
import axios from "axios";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Sparkles, Loader2, Check, AlertTriangle, RefreshCw, X } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const TONES = ["friendly", "energetic", "luxurious", "chill", "urgent"];

export default function AIAdCreator() {
  const navigate = useNavigate();
  const [advs, setAdvs] = useState([]);
  const [advId, setAdvId] = useState(localStorage.getItem("bigfm_active_advertiser") || "");
  const [voices, setVoices] = useState([]);
  const [form, setForm] = useState({
    business: "", description: "", tone: "friendly",
    audio_length_sec: 15, voice_id: "maya",
    brand_color: "#F59E0B", keywords: "",
    include_image: true,
  });
  const [stage, setStage] = useState(null);      // null | 'script' | 'voice' | 'image' | 'safety' | 'done' | 'error'
  const [preview, setPreview] = useState(null);
  const [saving, setSaving]   = useState(false);
  const [errMsg, setErrMsg]   = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const r = await axios.get(`${API}/advertiser/me`);
        const list = r.data?.items || [];
        setAdvs(list);
        const aid = advId || list[0]?.advertiser_id;
        if (aid) {
          setAdvId(aid);
          const v = await axios.get(`${API}/advertiser/${aid}/ai/voices`);
          setVoices(v.data?.items || []);
          // Default business name to advertiser.name
          const me = list.find((x) => x.advertiser_id === aid);
          if (me?.name) setForm((p) => ({ ...p, business: me.name }));
        }
      } catch {}
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const generate = async () => {
    if (!advId) { toast.error("No advertiser selected"); return; }
    if (!form.business?.trim() || !form.description?.trim()) {
      toast.error("Business name and description are required"); return;
    }
    setPreview(null); setErrMsg(null);
    // Cosmetic 3-step progress while the real call runs.
    setStage("script");
    const lapse = (s, ms) => new Promise((r) => setTimeout(() => { setStage(s); r(); }, ms));
    lapse("voice", 800).then(() => lapse("image", 1600));
    try {
      const body = {
        ...form,
        include_image: form.include_image,
        keywords: form.keywords
          ? form.keywords.split(",").map((x) => x.trim()).filter(Boolean).slice(0, 3)
          : null,
      };
      const r = await axios.post(`${API}/advertiser/${advId}/ai/generate`, body);
      setPreview(r.data);
      setStage("done");
      toast.success(`Ready · safety verdict: ${r.data.verdict}`);
    } catch (e) {
      setStage("error");
      setErrMsg(e?.response?.data?.detail || "Generation failed");
      toast.error(e?.response?.data?.detail || "Generation failed");
    }
  };

  const save = async () => {
    if (!preview) return;
    setSaving(true);
    try {
      const r = await axios.post(`${API}/advertiser/${advId}/ai/save`, {
        creative_id:        preview.creative_id,
        title:                  form.business + " · AI",
        script:                preview.script,
        audio_url:           preview.audio_url,
        audio_path:         preview.audio_path,
        duration_sec:      preview.duration_sec,
        image_url:           preview.image_url,
        brand_safety_check: preview.brand_safety_check,
        vast_xml:            preview.vast_xml,
        voice_id:             preview.voice_id,
        tone:                    preview.tone,
        audio_length_sec: preview.audio_length_sec,
        audio_source:      preview.audio_source,
      });
      toast.success(`Creative saved · ${r.data.status}`);
      navigate("/advertiser/creatives");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Save failed");
    } finally { setSaving(false); }
  };

  const verdict = preview?.brand_safety_check?.verdict;
  const badge =
    verdict === "approved" ? { c: "emerald", t: "Approved" }
    : verdict === "rejected" ? { c: "rose", t: "Rejected" }
    : { c: "amber", t: "Needs review" };

  return (
    <div className="min-h-screen bg-bg-base text-text-primary" data-testid="ai-creator">
      <header className="border-b border-white/[0.06] px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Sparkles size={20} className="text-amber-400" />
          <h1 className="font-display font-bold text-xl">AI Ad Creator</h1>
        </div>
        <button onClick={() => navigate("/advertiser/creatives")}
                    data-testid="ai-close" className="text-text-secondary text-sm">
          <X size={16} />
        </button>
      </header>

      <div className="max-w-5xl mx-auto p-6 grid md:grid-cols-2 gap-6">
        {/* ─── INPUT FORM ───────────────────────────────────── */}
        <section className="space-y-4" data-testid="ai-form">
          <Field label="Business name">
            <input className="bigfm-input" data-testid="ai-business"
                        value={form.business}
                        onChange={(e) => setForm({...form, business: e.target.value})} />
          </Field>
          <Field label="Offer / product (1 line)">
            <textarea rows={3} className="bigfm-input" data-testid="ai-description"
                              value={form.description}
                              placeholder="e.g. Free dessert with any lunch combo, weekdays 12-2pm"
                              onChange={(e) => setForm({...form, description: e.target.value})} />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Tone">
              <select className="bigfm-input" data-testid="ai-tone"
                          value={form.tone}
                          onChange={(e) => setForm({...form, tone: e.target.value})}>
                {TONES.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </Field>
            <Field label="Length">
              <select className="bigfm-input" data-testid="ai-length"
                          value={form.audio_length_sec}
                          onChange={(e) => setForm({...form, audio_length_sec: parseInt(e.target.value)})}>
                <option value={15}>15 seconds</option>
                <option value={30}>30 seconds</option>
              </select>
            </Field>
          </div>
          <Field label="Voice">
            <select className="bigfm-input" data-testid="ai-voice"
                        value={form.voice_id}
                        onChange={(e) => setForm({...form, voice_id: e.target.value})}>
              {voices.map((v) => (
                <option key={v.id} value={v.id}>{v.label} · {v.persona}</option>
              ))}
            </select>
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Brand color">
              <input type="color" className="bigfm-input h-12" data-testid="ai-color"
                          value={form.brand_color}
                          onChange={(e) => setForm({...form, brand_color: e.target.value})} />
            </Field>
            <Field label="Hard-include keywords (max 3, comma-sep)">
              <input className="bigfm-input" data-testid="ai-keywords"
                          value={form.keywords}
                          onChange={(e) => setForm({...form, keywords: e.target.value})} />
            </Field>
          </div>
          <label className="flex items-center gap-2 text-sm cursor-pointer">
            <input type="checkbox" data-testid="ai-skip-image"
                        checked={!form.include_image}
                        onChange={(e) => setForm({...form, include_image: !e.target.checked})} />
            Skip image generation (faster · cuts ~7s + reduces token spend)
          </label>
          <button onClick={generate} disabled={!!stage && stage !== "done" && stage !== "error"}
                      data-testid="ai-generate-btn"
                      className="w-full rounded-2xl py-3 font-display font-bold
                                          bg-amber-400 text-bg-base hover:bg-amber-300 disabled:opacity-50">
            {stage && stage !== "done" && stage !== "error"
              ? "Cooking your ad…" : "Generate ad"}
          </button>
        </section>

        {/* ─── PROGRESS + PREVIEW ──────────────────────────── */}
        <section className="space-y-4">
          {stage && stage !== "done" && stage !== "error" && (
            <div className="rounded-2xl p-5 border border-white/[0.08]" data-testid="ai-progress">
              <Step name="script" current={stage} label="✏️ Writing script" />
              <Step name="voice"  current={stage} label="🎙️ Recording voice" />
              <Step name="image" current={stage} label="🎨 Designing visual" />
            </div>
          )}

          {stage === "error" && (
            <div className="rounded-2xl p-5 border border-rose-400/40 text-rose-200 text-sm"
                    data-testid="ai-error">
              <AlertTriangle size={16} className="inline mr-2" />
              {errMsg}
            </div>
          )}

          {preview && stage === "done" && (
            <div className="space-y-4" data-testid="ai-preview">
              {preview.image_url ? (
                <img src={`${process.env.REACT_APP_BACKEND_URL}${preview.image_url}`}
                          data-testid="ai-image"
                          className="w-full aspect-square rounded-2xl object-cover" alt="ad" />
              ) : (
                <div className="w-full aspect-square rounded-2xl flex items-center
                                          justify-center text-center px-6"
                          style={{ background: form.brand_color || "#262626" }}
                          data-testid="ai-image-skipped">
                  <div>
                    <div className="text-xs uppercase tracking-widest opacity-80 mb-2">
                      Audio-only ad
                    </div>
                    <div className="font-display font-bold text-4xl text-white drop-shadow">
                      {form.business || "Your brand"}
                    </div>
                  </div>
                </div>
              )}
              <div className="rounded-2xl p-3 border border-white/[0.08]">
                <audio src={`${process.env.REACT_APP_BACKEND_URL}${preview.audio_url}`}
                            controls data-testid="ai-audio" className="w-full" />
                <div className="text-xs text-text-secondary mt-2 flex justify-between">
                  <span>Voice: {preview.voice_label} ({preview.audio_source})</span>
                  <span>{Math.round(preview.duration_sec)}s</span>
                </div>
              </div>
              <div className="rounded-2xl p-3 border border-white/[0.08]">
                <div className="text-xs text-text-secondary mb-1">Script · transcript</div>
                <p className="text-sm" data-testid="ai-transcript">{preview.script}</p>
              </div>
              <div className={`rounded-2xl p-3 border border-${badge.c}-400/40
                                          bg-${badge.c}-400/[0.06] text-sm`}
                      data-testid="ai-safety">
                <Check size={14} className="inline mr-1" /> Safety: <b>{badge.t}</b>
              </div>
              {(() => {
                const total = preview.total_latency_ms || 0;
                const seconds = (total / 1000).toFixed(1);
                const slow = total > 20000;
                return (
                  <div data-testid="ai-latency-chip"
                          className={`rounded-2xl p-3 border text-sm
                            ${slow ? "border-amber-400/40 bg-amber-400/[0.06] text-amber-200"
                                       : "border-white/[0.08] text-text-secondary"}`}>
                    Took <b className="text-white">{seconds}s</b>
                    {slow && (
                      <span>{" — generating audio + image is the slow part. "}
                        Try the <b>Skip image</b> toggle on your next generation to cut session
                        time in half.</span>
                    )}
                  </div>
                );
              })()}
              <div className="flex gap-2">
                <button onClick={generate} data-testid="ai-regenerate"
                            className="flex-1 rounded-2xl py-2 border border-white/[0.08]
                                              text-sm flex items-center justify-center gap-1
                                              hover:bg-white/[0.04]">
                  <RefreshCw size={14} /> Regenerate
                </button>
                <button onClick={save} disabled={saving} data-testid="ai-save"
                            className="flex-1 rounded-2xl py-2 bg-amber-400 text-bg-base
                                              font-display font-bold hover:bg-amber-300 disabled:opacity-50">
                  {saving ? <Loader2 size={14} className="animate-spin inline" /> : "Save as creative"}
                </button>
              </div>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

const Field = ({ label, children }) => (
  <div className="space-y-1">
    <div className="text-xs text-text-secondary uppercase tracking-wide">{label}</div>
    {children}
  </div>
);

const Step = ({ name, current, label }) => {
  const order = ["script", "voice", "image"];
  const idx   = order.indexOf(name);
  const cur   = order.indexOf(current);
  const active = idx === cur;
  const done   = idx < cur;
  return (
    <div className={`flex items-center gap-2 py-1 text-sm
                            ${done ? "text-emerald-300" : active ? "text-amber-300" : "text-text-secondary"}`}
            data-testid={`ai-step-${name}`}>
      {done ? <Check size={14} /> : active ? <Loader2 size={14} className="animate-spin" /> : <span className="w-3.5"/>}
      <span>{label}</span>
    </div>
  );
};
