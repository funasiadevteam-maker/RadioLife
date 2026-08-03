/** Phase D — Admin RJ Personas management page.
 *
 *  Route: /admin/rj-personas  (admin-only, Legacy dark theme).
 *  Provides:
 *    - List of personas with quick actions
 *    - Create/Edit modal
 *    - Preview panel (LLM script + ElevenLabs audio, plays inline)
 *
 *  Station assignment lives on the existing flagship stations detail
 *  page — this page does NOT duplicate that flow, just links out.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import { Loader2, Mic, Plus, Edit3, Trash2, Play, X,
                  RadioTower, Sparkles, Copy, AlertTriangle,
                  CheckCircle2 } from "lucide-react";
import { API } from "@/AuthContext";
import AdminPageHeader from "@/components/AdminPageHeader";

const PERSONALITIES = ["energetic", "chill", "news", "party",
                                              "devotional", "custom"];
const VOICE_PROVIDERS = ["elevenlabs", "openai_tts"];
const STATUSES = ["draft", "active", "archived"];

const CONTEXT_PRESETS = [
  { id: "morning",  label: "Morning commute",
      context: { time_of_day: "morning", city: "Dubai",
                          weather_hint: "sunny 26 C", next_track_mood: "upbeat" } },
  { id: "lunch",      label: "Lunch break",
      context: { time_of_day: "lunch", city: "Dubai",
                          next_track_mood: "chill" } },
  { id: "rain",        label: "Rainy day",
      context: { time_of_day: "afternoon", city: "Dubai",
                          weather_hint: "rain 22 C", next_track_mood: "mellow" } },
  { id: "friday",    label: "Friday night",
      context: { time_of_day: "evening", city: "Dubai",
                          next_track_mood: "party" } },
  { id: "traffic",  label: "Rush-hour traffic",
      context: { time_of_day: "evening", city: "Dubai",
                          weather_hint: "hot 34 C", next_track_mood: "calming" } },
];

const empty_form = {
  name: "", tagline: "", description: "",
  voice_id: "", voice_provider: "elevenlabs",
  language: "en", personality: "energetic",
  persona_prompt: "",
  sample_audio_url: "", cover_image_url: "",
  status: "draft", is_default: false,
};

export default function AdminRJPersonas() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [health, setHealth] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(empty_form);
  const [editingId, setEditingId] = useState(null);
  const [saving, setSaving] = useState(false);
  const [previewFor, setPreviewFor] = useState(null);
  const [previewCtx, setPreviewCtx] = useState(CONTEXT_PRESETS[0].id);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [previewResult, setPreviewResult] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [r, h] = await Promise.all([
        axios.get(`${API}/admin/rj/personas?include_archived=true`,
          { withCredentials: true }),
        axios.get(`${API}/admin/rj/health`,
          { withCredentials: true }).catch(() => ({ data: null })),
      ]);
      setRows(r.data?.items || []);
      setHealth(h.data);
    } catch (e) {
      toast.error(e?.response?.data?.detail?.code || "Load failed");
    } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const openCreate = () => {
    setEditingId(null);
    setForm(empty_form);
    setShowForm(true);
  };
  const openEdit = async (p) => {
    // Fetch admin detail so persona_prompt is populated.
    try {
      const r = await axios.get(`${API}/admin/rj/personas/${p.id}`,
        { withCredentials: true });
      const d = r.data.persona;
      setForm({
        name: d.name || "", tagline: d.tagline || "",
        description: d.description || "",
        voice_id: d.voice_id || "",
        voice_provider: d.voice_provider || "elevenlabs",
        language: d.language || "en",
        personality: d.personality || "energetic",
        persona_prompt: d.persona_prompt || "",
        sample_audio_url: d.sample_audio_url || "",
        cover_image_url: d.cover_image_url || "",
        status: d.status || "draft",
        is_default: !!d.is_default,
      });
      setEditingId(p.id);
      setShowForm(true);
    } catch (e) {
      toast.error("Could not load persona");
    }
  };
  const save = async () => {
    if (!form.name.trim() || !form.voice_id.trim()) {
      toast.error("Name and voice_id are required");
      return;
    }
    setSaving(true);
    try {
      if (editingId) {
        await axios.patch(`${API}/admin/rj/personas/${editingId}`, form,
          { withCredentials: true });
        toast.success("Saved");
      } else {
        await axios.post(`${API}/admin/rj/personas`, form,
          { withCredentials: true });
        toast.success("Persona created");
      }
      setShowForm(false);
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail?.code || "Save failed");
    } finally { setSaving(false); }
  };
  const softDelete = async (p) => {
    if (!confirm(`Archive persona "${p.name}"?`)) return;
    try {
      await axios.delete(`${API}/admin/rj/personas/${p.id}`,
        { withCredentials: true });
      toast.success("Archived");
      await load();
    } catch (e) {
      toast.error("Archive failed");
    }
  };
  const openPreview = (p) => {
    setPreviewFor(p);
    setPreviewCtx(CONTEXT_PRESETS[0].id);
    setPreviewResult(null);
  };
  const runPreview = async () => {
    if (!previewFor) return;
    setPreviewBusy(true);
    setPreviewResult(null);
    const ctx = (CONTEXT_PRESETS.find(
      (x) => x.id === previewCtx) || CONTEXT_PRESETS[0]).context;
    try {
      const r = await axios.post(
        `${API}/admin/rj/personas/${previewFor.id}/preview`,
        { context: ctx }, { withCredentials: true });
      setPreviewResult(r.data);
    } catch (e) {
      const code = e?.response?.data?.detail?.code
                            || e?.response?.data?.detail?.message
                            || "Preview failed";
      const status = e?.response?.status;
      if (status === 503) {
        toast.error("ElevenLabs not configured (503).");
      } else {
        toast.error(String(code));
      }
    } finally { setPreviewBusy(false); }
  };

  const statusColor = (s) =>
    s === "active"      ? "text-emerald-400 border-emerald-500/30 bg-emerald-500/10"
    : s === "draft"    ? "text-amber-400 border-amber-500/30 bg-amber-500/10"
    :                              "text-slate-400 border-slate-500/30 bg-slate-500/10";

  return (
    <div className="min-h-screen bg-slate-950 text-white p-6 pb-24
                                  admin-content-inset"
              data-testid="admin-rj-personas-page">
      <div className="max-w-6xl mx-auto">
        <AdminPageHeader
          title="AI RJ Personas"
          subtitle="Voice-branded RJs for station preview + assignment."
          Icon={Mic}
          tint="text-violet-500"
          pinLabel="RJ Personas"
          breadcrumbs={[{ label: "Content" },
                                          { label: "RJ Personas" }]}
          actions={
            <button
              type="button" onClick={openCreate}
              data-testid="rj-personas-new-btn"
              className="inline-flex items-center gap-1.5 px-3 h-8 rounded-full
                                          bg-violet-500 text-white text-xs font-semibold
                                          hover:bg-violet-400">
              <Plus size={12} /> New Persona
            </button>
          } />

        {/* Health banner */}
        {health && (
          <div className="mt-4 flex flex-wrap gap-2 text-[11px] font-mono"
                      data-testid="rj-personas-health">
            <span className={`px-2 h-6 inline-flex items-center gap-1
                              rounded border ${health.elevenlabs_configured
                                ? "border-emerald-500/40 text-emerald-300"
                                : "border-red-500/40 text-red-300"}`}
                      data-testid="rj-personas-el-status">
              {health.elevenlabs_configured ? <CheckCircle2 size={11} /> : <AlertTriangle size={11} />}
              ElevenLabs {health.elevenlabs_configured ? "OK" : "MISSING"}
            </span>
            <span className={`px-2 h-6 inline-flex items-center gap-1
                              rounded border ${health.emergent_llm_configured
                                ? "border-emerald-500/40 text-emerald-300"
                                : "border-red-500/40 text-red-300"}`}
                      data-testid="rj-personas-llm-status">
              {health.emergent_llm_configured ? <CheckCircle2 size={11} /> : <AlertTriangle size={11} />}
              Emergent LLM {health.emergent_llm_configured ? "OK" : "MISSING"}
            </span>
          </div>
        )}

        {/* Table */}
        <div className="mt-6 border border-white/10 rounded-2xl
                                        bg-white/[0.02] overflow-hidden">
          {loading ? (
            <div className="p-10 flex justify-center">
              <Loader2 className="w-6 h-6 animate-spin text-violet-400" />
            </div>
          ) : rows.length === 0 ? (
            <div className="p-10 text-center text-white/60"
                        data-testid="rj-personas-empty">
              <Mic size={40} className="text-violet-400 mx-auto mb-3" />
              <div className="text-sm mb-2">No personas yet.</div>
              <button type="button" onClick={openCreate}
                          className="text-violet-400 underline text-sm">
                Create your first persona
              </button>
            </div>
          ) : (
            <table className="w-full text-sm"
                        data-testid="rj-personas-table">
              <thead>
                <tr className="text-[10px] uppercase tracking-widest
                                              text-white/40 font-mono
                                              border-b border-white/[0.06]">
                  <th className="text-left py-3 px-4">Name</th>
                  <th className="text-left py-3 px-4">Provider</th>
                  <th className="text-left py-3 px-4">Voice ID</th>
                  <th className="text-left py-3 px-4">Personality</th>
                  <th className="text-left py-3 px-4">Lang</th>
                  <th className="text-left py-3 px-4">Status</th>
                  <th className="text-right py-3 px-4">Actions</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((p) => (
                  <tr key={p.id}
                          data-testid={`rj-persona-row-${p.id}`}
                          className="border-b border-white/[0.04]
                                                    hover:bg-white/[0.02]">
                    <td className="py-3 px-4">
                      <div className="flex items-center gap-2">
                        {p.cover_image_url ? (
                          <img src={p.cover_image_url}
                                      alt=""
                                      className="w-8 h-8 rounded-full object-cover" />
                        ) : (
                          <div className="w-8 h-8 rounded-full bg-violet-500/20
                                                          text-violet-300 grid place-items-center
                                                          text-xs font-bold">
                            {(p.name || "?")[0]}
                          </div>
                        )}
                        <div>
                          <div className="font-semibold"
                                      data-testid={`rj-persona-name-${p.id}`}>
                            {p.name}
                            {p.is_default && (
                              <span className="ml-1 text-[9px]
                                                                        text-amber-400 font-mono
                                                                        uppercase tracking-widest">
                                default
                              </span>
                            )}
                          </div>
                          {p.tagline && (
                            <div className="text-[11px] text-white/50 truncate max-w-[240px]">
                              {p.tagline}
                            </div>
                          )}
                        </div>
                      </div>
                    </td>
                    <td className="py-3 px-4 font-mono text-[11px]">
                      {p.voice_provider}
                    </td>
                    <td className="py-3 px-4 font-mono text-[11px] text-white/60"
                            data-testid={`rj-persona-voice-${p.id}`}>
                      {(p.voice_id || "").slice(0, 22)}
                    </td>
                    <td className="py-3 px-4">{p.personality}</td>
                    <td className="py-3 px-4 font-mono text-[11px] text-white/50">
                      {p.language}
                    </td>
                    <td className="py-3 px-4">
                      <span className={`px-2 py-0.5 text-[10px] font-mono
                                          uppercase tracking-widest border rounded
                                          ${statusColor(p.status)}`}
                                  data-testid={`rj-persona-status-${p.id}`}>
                        {p.status}
                      </span>
                    </td>
                    <td className="py-3 px-4">
                      <div className="flex items-center gap-1.5 justify-end">
                        <button type="button" onClick={() => openPreview(p)}
                                    data-testid={`rj-persona-preview-${p.id}`}
                                    className="p-1.5 rounded hover:bg-violet-500/20
                                                              text-violet-300"
                                    title="Preview">
                          <Play size={13} />
                        </button>
                        <button type="button" onClick={() => openEdit(p)}
                                    data-testid={`rj-persona-edit-${p.id}`}
                                    className="p-1.5 rounded hover:bg-white/10
                                                              text-white/70"
                                    title="Edit">
                          <Edit3 size={13} />
                        </button>
                        {p.status !== "archived" && (
                          <button type="button" onClick={() => softDelete(p)}
                                      data-testid={`rj-persona-delete-${p.id}`}
                                      className="p-1.5 rounded hover:bg-red-500/20
                                                                text-red-300"
                                      title="Archive">
                            <Trash2 size={13} />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="mt-6 text-[11px] text-white/40 flex items-center
                                        gap-1">
          <RadioTower size={12} className="text-violet-400" />
          Assign personas to stations from{" "}
          <Link to="/admin/flagship-stations"
                      className="text-violet-400 underline">
            Flagship Stations
          </Link>.
        </div>
      </div>

      {/* Create/Edit modal */}
      {showForm && (
        <PersonaFormModal
          form={form} setForm={setForm}
          onClose={() => setShowForm(false)}
          onSave={save} saving={saving}
          isEdit={!!editingId} />
      )}

      {/* Preview modal */}
      {previewFor && (
        <PreviewModal
          persona={previewFor}
          ctxId={previewCtx} setCtxId={setPreviewCtx}
          onClose={() => setPreviewFor(null)}
          onRun={runPreview} busy={previewBusy}
          result={previewResult} />
      )}
    </div>
  );
}


function PersonaFormModal({ form, setForm, onClose, onSave, saving,
                                                            isEdit }) {
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center
                                  bg-black/70 backdrop-blur p-4"
              data-testid="rj-personas-form-modal">
      <div className="max-w-2xl w-full bg-slate-900 border border-white/10
                                      rounded-2xl overflow-hidden max-h-[92vh]
                                      flex flex-col">
        <div className="p-4 flex items-center justify-between border-b
                                        border-white/10">
          <h2 className="text-lg font-bold flex items-center gap-2">
            <Sparkles size={16} className="text-violet-400" />
            {isEdit ? "Edit persona" : "New persona"}
          </h2>
          <button type="button" onClick={onClose}
                      data-testid="rj-personas-form-close"
                      className="p-1.5 hover:bg-white/10 rounded">
            <X size={16} />
          </button>
        </div>
        <div className="p-4 overflow-y-auto space-y-3 flex-1">
          <label className="block">
            <span className="text-[10px] uppercase tracking-widest
                                            font-mono text-white/50">Name *</span>
            <input value={form.name}
                        onChange={(e) => set("name", e.target.value)}
                        data-testid="rj-personas-form-name"
                        className="w-full mt-1 h-10 px-3 bg-black/40
                                                  border border-white/10 rounded-lg text-sm" />
          </label>
          <label className="block">
            <span className="text-[10px] uppercase tracking-widest
                                            font-mono text-white/50">Tagline</span>
            <input value={form.tagline}
                        onChange={(e) => set("tagline", e.target.value)}
                        placeholder="Short one-liner for the chip"
                        data-testid="rj-personas-form-tagline"
                        className="w-full mt-1 h-10 px-3 bg-black/40
                                                  border border-white/10 rounded-lg text-sm" />
          </label>
          <label className="block">
            <span className="text-[10px] uppercase tracking-widest
                                            font-mono text-white/50">Description</span>
            <textarea value={form.description} rows={2}
                                  onChange={(e) => set("description", e.target.value)}
                                  data-testid="rj-personas-form-description"
                                  className="w-full mt-1 p-3 bg-black/40
                                                          border border-white/10 rounded-lg text-sm
                                                          font-sans" />
          </label>
          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="text-[10px] uppercase tracking-widest
                                              font-mono text-white/50">Voice provider</span>
              <select value={form.voice_provider}
                            onChange={(e) => set("voice_provider", e.target.value)}
                            data-testid="rj-personas-form-provider"
                            className="w-full mt-1 h-10 px-3 bg-black/40
                                                      border border-white/10 rounded-lg text-sm">
                {VOICE_PROVIDERS.map((v) =>
                  <option key={v} value={v}>{v}</option>)}
              </select>
            </label>
            <label className="block">
              <span className="text-[10px] uppercase tracking-widest
                                              font-mono text-white/50">Voice ID *</span>
              <input value={form.voice_id}
                          onChange={(e) => set("voice_id", e.target.value)}
                          placeholder="e.g. 21m00Tcm4TlvDq8ikWAM"
                          data-testid="rj-personas-form-voice-id"
                          className="w-full mt-1 h-10 px-3 bg-black/40
                                                    border border-white/10 rounded-lg text-sm
                                                    font-mono" />
            </label>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <label className="block">
              <span className="text-[10px] uppercase tracking-widest
                                              font-mono text-white/50">Language</span>
              <input value={form.language}
                          onChange={(e) => set("language", e.target.value)}
                          data-testid="rj-personas-form-language"
                          className="w-full mt-1 h-10 px-3 bg-black/40
                                                    border border-white/10 rounded-lg text-sm
                                                    font-mono" />
            </label>
            <label className="block">
              <span className="text-[10px] uppercase tracking-widest
                                              font-mono text-white/50">Personality</span>
              <select value={form.personality}
                            onChange={(e) => set("personality", e.target.value)}
                            data-testid="rj-personas-form-personality"
                            className="w-full mt-1 h-10 px-3 bg-black/40
                                                      border border-white/10 rounded-lg text-sm">
                {PERSONALITIES.map((v) =>
                  <option key={v} value={v}>{v}</option>)}
              </select>
            </label>
            <label className="block">
              <span className="text-[10px] uppercase tracking-widest
                                              font-mono text-white/50">Status</span>
              <select value={form.status}
                            onChange={(e) => set("status", e.target.value)}
                            data-testid="rj-personas-form-status"
                            className="w-full mt-1 h-10 px-3 bg-black/40
                                                      border border-white/10 rounded-lg text-sm">
                {STATUSES.map((v) =>
                  <option key={v} value={v}>{v}</option>)}
              </select>
            </label>
          </div>
          <label className="block">
            <span className="text-[10px] uppercase tracking-widest
                                            font-mono text-white/50">
              Persona prompt (LLM system message)
            </span>
            <textarea value={form.persona_prompt} rows={6}
                                  onChange={(e) => set("persona_prompt", e.target.value)}
                                  placeholder="You are ..."
                                  data-testid="rj-personas-form-prompt"
                                  className="w-full mt-1 p-3 bg-black/40
                                                          border border-white/10 rounded-lg text-sm
                                                          font-mono" />
          </label>
          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="text-[10px] uppercase tracking-widest
                                              font-mono text-white/50">Sample audio URL</span>
              <input value={form.sample_audio_url}
                          onChange={(e) => set("sample_audio_url", e.target.value)}
                          data-testid="rj-personas-form-sample-audio"
                          className="w-full mt-1 h-10 px-3 bg-black/40
                                                    border border-white/10 rounded-lg text-sm
                                                    font-mono" />
            </label>
            <label className="block">
              <span className="text-[10px] uppercase tracking-widest
                                              font-mono text-white/50">Cover image URL</span>
              <input value={form.cover_image_url}
                          onChange={(e) => set("cover_image_url", e.target.value)}
                          data-testid="rj-personas-form-cover"
                          className="w-full mt-1 h-10 px-3 bg-black/40
                                                    border border-white/10 rounded-lg text-sm
                                                    font-mono" />
            </label>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={form.is_default}
                        onChange={(e) => set("is_default", e.target.checked)}
                        data-testid="rj-personas-form-default" />
            Make this the default persona (unflags any other default)
          </label>
        </div>
        <div className="p-4 border-t border-white/10 flex justify-end
                                        gap-2">
          <button type="button" onClick={onClose}
                      className="px-4 h-10 rounded-full border border-white/10
                                                text-white/80 text-sm">
            Cancel
          </button>
          <button type="button" onClick={onSave} disabled={saving}
                      data-testid="rj-personas-form-save"
                      className="px-4 h-10 rounded-full bg-violet-500
                                                text-white text-sm font-semibold
                                                disabled:opacity-50">
            {saving ? "Saving…" : (isEdit ? "Save" : "Create")}
          </button>
        </div>
      </div>
    </div>
  );
}


function PreviewModal({ persona, ctxId, setCtxId, onClose, onRun,
                                                busy, result }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center
                                  bg-black/70 backdrop-blur p-4"
              data-testid="rj-personas-preview-modal">
      <div className="max-w-xl w-full bg-slate-900 border border-white/10
                                      rounded-2xl overflow-hidden">
        <div className="p-4 flex items-center justify-between border-b
                                        border-white/10">
          <h2 className="text-lg font-bold flex items-center gap-2">
            <Play size={14} className="text-violet-400" />
            Preview — {persona.name}
          </h2>
          <button type="button" onClick={onClose}
                      data-testid="rj-personas-preview-close"
                      className="p-1.5 hover:bg-white/10 rounded">
            <X size={16} />
          </button>
        </div>
        <div className="p-4 space-y-3">
          <label className="block">
            <span className="text-[10px] uppercase tracking-widest
                                            font-mono text-white/50">Context preset</span>
            <select value={ctxId} onChange={(e) => setCtxId(e.target.value)}
                          data-testid="rj-personas-preview-ctx"
                          className="w-full mt-1 h-10 px-3 bg-black/40
                                                    border border-white/10 rounded-lg text-sm">
              {CONTEXT_PRESETS.map((p) =>
                <option key={p.id} value={p.id}>{p.label}</option>)}
            </select>
          </label>
          <button type="button" onClick={onRun} disabled={busy}
                      data-testid="rj-personas-preview-run"
                      className="w-full h-11 rounded-full bg-violet-500
                                                text-white text-sm font-semibold
                                                disabled:opacity-50 inline-flex
                                                items-center justify-center gap-2">
            {busy
              ? <><Loader2 size={14} className="animate-spin" /> Generating…</>
              : <><Sparkles size={14} /> Generate segment</>}
          </button>
          {result && (
            <div className="space-y-3">
              <div className="rounded-lg bg-black/40 p-3 border border-white/10">
                <div className="text-[10px] uppercase tracking-widest
                                                font-mono text-white/50 mb-1
                                                flex items-center justify-between">
                  Script
                  <button type="button"
                          onClick={() => { navigator.clipboard.writeText(
                                                                            result.script_text || "");
                                                        toast.success("Copied"); }}
                          className="p-1 rounded hover:bg-white/10">
                    <Copy size={11} />
                  </button>
                </div>
                <p className="text-sm text-white/90 leading-relaxed"
                      data-testid="rj-personas-preview-script">
                  {result.script_text}
                </p>
              </div>
              <div className="rounded-lg bg-black/40 p-3 border border-white/10"
                          data-testid="rj-personas-preview-audio-wrap">
                <div className="text-[10px] uppercase tracking-widest
                                                font-mono text-white/50 mb-2">
                  Audio · {result.duration_seconds
                    ? `${result.duration_seconds.toFixed(1)} s` : "?"}
                </div>
                <audio controls className="w-full"
                              src={result.audio_url}
                              data-testid="rj-personas-preview-audio" />
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
