/** Phase 42-C — Station owner dashboard.
 *
 *  Route: `/owner/dashboard`
 *
 *  Lists the claimed stations + lets the owner edit basic overrides
 *  (description, market city/country, bio, logo URL).  Stats shown
 *  are simple counts read from `/api/owner/dashboard`.
 */

import React, { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import {
  ArrowLeft, Radio as RadioIcon, Pencil, X, Check, Loader2,
  ShieldCheck, Building2, BarChart3, ExternalLink, MapPin,
  Heart, MousePointerClick, ThumbsUp,
  // Phase CLAIM.1b — media & description uploader icons.
  Upload, FileAudio, Image as ImageIcon, Trash2, Volume2,
} from "lucide-react";
import { API } from "@/AuthContext";
// Phase CLAIM.1b — design variant.
import { useDesignVariant } from "@/hooks/useDesignVariant";

function StatPill({ icon: Icon, label, value, testid }) {
  return (
    <div data-testid={testid}
         className="flex items-center gap-2 px-3 h-8 rounded-lg
                    bg-white/[0.04] border border-white/[0.08]
                    text-xs text-white/70">
      <Icon size={12} className="text-white/40" />
      <span className="font-mono text-white/90">{value ?? 0}</span>
      <span>{label}</span>
    </div>
  );
}

function EditOverridesModal({ station, onClose, onSaved }) {
  const o = station.owner_overrides || {};
  const [logoUrl, setLogoUrl] = useState(o.logo_url || "");
  const [description, setDescription] = useState(o.description || "");
  const [marketCity, setMarketCity] = useState(o.market_city || "");
  const [marketCountry, setMarketCountry] = useState(o.market_country || "");
  const [bio, setBio] = useState(o.bio || "");
  const [saving, setSaving] = useState(false);

  const onSave = async () => {
    setSaving(true);
    try {
      const r = await axios.patch(`${API}/owner/stations/${station.id}`, {
        logo_url: logoUrl, description, market_city: marketCity,
        market_country: marketCountry, bio,
      }, { withCredentials: true });
      onSaved(r.data?.owner_overrides || {});
      toast.success("Saved");
      onClose();
    } catch (e) {
      const code = e.response?.data?.detail?.code || "save_failed";
      toast.error(code);
    } finally { setSaving(false); }
  };

  return (
    <div data-testid="owner-edit-overrides-modal"
         className="fixed inset-0 z-50 bg-black/70 flex items-center
                    justify-center p-4 overflow-auto">
      <div className="bg-[#0a0a0c] border border-white/[0.10]
                      rounded-2xl w-full max-w-[560px] p-6 my-8">
        <div className="flex items-center justify-between mb-5">
          <div>
            <div className="text-xs uppercase tracking-widest text-white/40
                            font-mono mb-1">Edit overrides</div>
            <div className="font-semibold text-white truncate">{station.name}</div>
          </div>
          <button onClick={onClose}
                  data-testid="owner-edit-modal-close"
                  className="p-1.5 rounded hover:bg-white/[0.06]
                             text-white/60 hover:text-white">
            <X size={16} />
          </button>
        </div>
        <div className="space-y-4">
          <div>
            <label className="block text-xs text-white/60 mb-1">Logo URL</label>
            <input type="url" value={logoUrl}
                   onChange={(e) => setLogoUrl(e.target.value)}
                   data-testid="owner-edit-logo-url"
                   placeholder="https://yourstation.com/logo.png"
                   className="w-full px-3 h-10 rounded-lg bg-black/40
                              border border-white/[0.10] text-sm
                              placeholder:text-white/30
                              focus:border-cyan-400/50 focus:outline-none" />
          </div>
          <div>
            <label className="block text-xs text-white/60 mb-1">Description</label>
            <textarea value={description}
                      onChange={(e) => setDescription(e.target.value)}
                      data-testid="owner-edit-description"
                      placeholder="A short tagline shown on your station page."
                      rows={2}
                      className="w-full px-3 py-2 rounded-lg bg-black/40
                                 border border-white/[0.10] text-sm
                                 placeholder:text-white/30
                                 focus:border-cyan-400/50 focus:outline-none
                                 resize-y" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-white/60 mb-1">Market city</label>
              <input type="text" value={marketCity}
                     onChange={(e) => setMarketCity(e.target.value)}
                     data-testid="owner-edit-market-city"
                     placeholder="e.g. Dubai"
                     className="w-full px-3 h-10 rounded-lg bg-black/40
                                border border-white/[0.10] text-sm
                                placeholder:text-white/30
                                focus:border-cyan-400/50 focus:outline-none" />
            </div>
            <div>
              <label className="block text-xs text-white/60 mb-1">Market country</label>
              <input type="text" value={marketCountry}
                     onChange={(e) => setMarketCountry(e.target.value)}
                     data-testid="owner-edit-market-country"
                     placeholder="e.g. AE"
                     className="w-full px-3 h-10 rounded-lg bg-black/40
                                border border-white/[0.10] text-sm
                                placeholder:text-white/30
                                focus:border-cyan-400/50 focus:outline-none" />
            </div>
          </div>
          <div>
            <label className="block text-xs text-white/60 mb-1">Bio</label>
            <textarea value={bio}
                      onChange={(e) => setBio(e.target.value)}
                      data-testid="owner-edit-bio"
                      placeholder="Long-form station bio (max ~400 chars)."
                      rows={3}
                      className="w-full px-3 py-2 rounded-lg bg-black/40
                                 border border-white/[0.10] text-sm
                                 placeholder:text-white/30
                                 focus:border-cyan-400/50 focus:outline-none
                                 resize-y" />
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-6">
          <button onClick={onClose}
                  data-testid="owner-edit-cancel"
                  disabled={saving}
                  className="px-4 h-10 rounded-full bg-white/[0.06]
                             hover:bg-white/[0.10] border border-white/[0.10]
                             text-sm">
            Cancel
          </button>
          <button onClick={onSave}
                  data-testid="owner-edit-save"
                  disabled={saving}
                  className="inline-flex items-center gap-2 px-5 h-10
                             rounded-full bg-cyan-400 text-slate-900
                             text-sm font-semibold hover:bg-cyan-300
                             disabled:opacity-50">
            {saving && <Loader2 size={13} className="animate-spin" />}
            Save changes
          </button>
        </div>
      </div>
    </div>
  );
}

export default function OwnerDashboard() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);
  const [editing, setEditing] = useState(null); // station
  // Phase CLAIM.1b — media/description uploader for the selected station.
  const [mediaFor, setMediaFor] = useState(null);
  const variant = useDesignVariant();
  const light = variant === "radiolife";

  const load = useCallback(async () => {
    setLoading(true); setErr(null);
    try {
      const r = await axios.get(`${API}/owner/dashboard`,
                                { withCredentials: true });
      setData(r.data);
    } catch (e) {
      const code = e.response?.data?.detail?.code || e.response?.status;
      setErr(code);
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) {
    return (
      <div data-testid="owner-dashboard-loading"
           className="text-white max-w-[1100px] mx-auto px-5 py-16
                      flex items-center gap-3 text-white/60">
        <Loader2 size={16} className="animate-spin" />
        Loading your stations…
      </div>
    );
  }

  if (err) {
    return (
      <div data-testid="owner-dashboard-error"
           className="text-white max-w-[640px] mx-auto px-5 py-16">
        <h1 className="text-2xl font-bold mb-3">Unable to load dashboard</h1>
        <p className="text-sm text-white/60 mb-6">
          {err === 401 || err === "Not authenticated"
            ? "Please sign in to manage your stations."
            : `Something went wrong (${err}). Try again in a moment.`}
        </p>
        <Link to="/radio"
              className="text-xs text-cyan-300 hover:text-cyan-200">
          ← Back to Radio
        </Link>
      </div>
    );
  }

  const stations = data?.stations || [];
  const profile = data?.profile;

  return (
    <div data-testid="owner-dashboard-page"
         data-station-count={stations.length}
         data-variant={variant}
         className={"max-w-[1100px] mx-auto px-5 pt-6 pb-24 " +
                    (light ? "text-slate-900" : "text-white")}>
      <Link to="/radio"
            data-testid="owner-dashboard-back"
            className="inline-flex items-center gap-1 text-xs
                       text-white/50 hover:text-white mb-6">
        <ArrowLeft size={12} /> Back to Radio
      </Link>

      <div className="flex items-start justify-between mb-8 flex-wrap gap-4">
        <div>
          <div className="text-xs uppercase tracking-widest text-cyan-400/80
                          font-mono mb-1">Station owner dashboard</div>
          <h1 className="text-3xl sm:text-4xl font-bold tracking-tight">
            {profile?.organization_name || "Your stations"}
          </h1>
          {profile && (
            <div className="text-xs text-white/50 mt-2 flex flex-wrap gap-4">
              <span className="inline-flex items-center gap-1.5">
                <Building2 size={11} /> {profile.organization_name || "—"}
              </span>
              <span className="inline-flex items-center gap-1.5">
                <ShieldCheck size={11} className="text-emerald-300" />
                Verified owner
              </span>
              <span className="inline-flex items-center gap-1.5">
                Payout: <strong className="text-white/70 capitalize">
                  {(profile.payout_status || "not_setup").replace("_", " ")}
                </strong>
              </span>
            </div>
          )}
        </div>
        <div data-testid="owner-dashboard-station-count-chip"
             className="inline-flex items-center gap-2 px-3 h-9
                        rounded-full bg-cyan-400/15
                        border border-cyan-400/30 text-cyan-200 text-xs">
          <RadioIcon size={12} />
          {stations.length} claimed station{stations.length === 1 ? "" : "s"}
        </div>
      </div>

      {stations.length === 0 ? (
        <div data-testid="owner-dashboard-empty"
             className="rounded-2xl border border-white/[0.10]
                        bg-white/[0.03] p-10 text-center">
          <RadioIcon size={36} className="mx-auto mb-4 text-white/30" />
          <h2 className="text-lg font-semibold mb-2">No claimed stations yet</h2>
          <p className="text-sm text-white/60 mb-5 max-w-md mx-auto">
            Find your station in the Radio Browser catalog and click
            &quot;Claim this station&quot; to start the verification process.
          </p>
          <Link to="/radio/browse"
                data-testid="owner-dashboard-find-station-cta"
                className="inline-flex items-center gap-1.5 px-4 h-10
                           rounded-full bg-cyan-400 text-slate-900
                           text-sm font-semibold hover:bg-cyan-300">
            Browse stations →
          </Link>
        </div>
      ) : (
        <ul data-testid="owner-dashboard-stations"
            className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {stations.map((s) => {
            const o = s.owner_overrides || {};
            return (
              <li key={s.id}
                  data-testid={`owner-station-${s.id}`}
                  data-station-id={s.id}
                  className="rounded-2xl border border-white/[0.10]
                             bg-white/[0.03] p-5">
                <div className="flex items-start gap-4 mb-4">
                  <div className="w-14 h-14 rounded-lg bg-gradient-to-br
                                  from-slate-700 to-slate-900 flex items-center
                                  justify-center flex-shrink-0 overflow-hidden">
                    {(o.logo_url || s.favicon) && (
                      <img src={o.logo_url || s.favicon} alt=""
                           onError={(e) => { e.currentTarget.style.display = "none"; }}
                           className="w-full h-full object-cover" />
                    )}
                  </div>
                  <div className="flex-grow min-w-0">
                    <div className="font-semibold mb-1 truncate"
                         data-testid={`owner-station-name-${s.id}`}>
                      {s.name}
                    </div>
                    <div className="text-xs text-white/50 flex flex-wrap
                                    gap-x-3 gap-y-1 mb-1">
                      {(o.market_city || s.country) && (
                        <span className="inline-flex items-center gap-1">
                          <MapPin size={10} />
                          {o.market_city || s.country}
                          {o.market_country ? `, ${o.market_country}` : ""}
                        </span>
                      )}
                      {s.language && (
                        <span className="capitalize">{s.language}</span>
                      )}
                    </div>
                    {o.description && (
                      <div className="text-xs text-white/70 mt-1.5 line-clamp-2">
                        {o.description}
                      </div>
                    )}
                  </div>
                </div>
                <div className="flex flex-wrap gap-2 mb-4">
                  <StatPill icon={ThumbsUp} label="votes" value={s.votes}
                            testid={`owner-stat-votes-${s.id}`} />
                  <StatPill icon={MousePointerClick} label="clicks"
                            value={s.click_count}
                            testid={`owner-stat-clicks-${s.id}`} />
                  <StatPill icon={Heart} label="favorites"
                            value={s.favorites_count}
                            testid={`owner-stat-favorites-${s.id}`} />
                </div>
                <div className="flex flex-wrap gap-2">
                  <button onClick={() => setEditing(s)}
                                  data-testid={`owner-edit-btn-${s.id}`}
                                  className="inline-flex items-center gap-1.5 px-3 h-9
                                                        rounded-full bg-cyan-400 text-slate-900
                                                        text-xs font-semibold hover:bg-cyan-300">
                    <Pencil size={12} /> Edit profile
                  </button>
                  {/* Phase CLAIM.1b — media uploader trigger. */}
                  <button onClick={() => setMediaFor(s)}
                                  data-testid={`owner-media-btn-${s.id}`}
                                  className="inline-flex items-center gap-1.5 px-3 h-9
                                                        rounded-full bg-fuchsia-500 text-white
                                                        text-xs font-semibold hover:bg-fuchsia-400">
                    <Upload size={12} /> Media &amp; description
                  </button>
                  <Link to={`/radio/station/${s.id}`}
                        data-testid={`owner-view-btn-${s.id}`}
                        className="inline-flex items-center gap-1.5 px-3 h-9
                                   rounded-full bg-white/[0.06]
                                   hover:bg-white/[0.10]
                                   border border-white/[0.10] text-xs">
                    <BarChart3 size={12} /> View page
                  </Link>
                  {s.homepage && (
                    <a href={s.homepage} target="_blank" rel="noopener noreferrer"
                       data-testid={`owner-homepage-${s.id}`}
                       className="inline-flex items-center gap-1.5 px-3 h-9
                                  rounded-full bg-white/[0.06]
                                  hover:bg-white/[0.10]
                                  border border-white/[0.10] text-xs">
                      <ExternalLink size={11} /> Homepage
                    </a>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}

      {editing && (
        <EditOverridesModal
          station={editing}
          onClose={() => setEditing(null)}
          onSaved={(overrides) => {
            // Patch in-place.
            setData((d) => ({
              ...d,
              stations: d.stations.map((x) =>
                x.id === editing.id ? { ...x, owner_overrides: overrides } : x),
            }));
          }} />
      )}
      {/* Phase CLAIM.1b — media & description uploader modal. */}
      {mediaFor && (
        <MediaUploaderModal
          station={mediaFor}
          variant={variant}
          onClose={() => setMediaFor(null)}
          onSaved={() => { setMediaFor(null); load(); }} />
      )}
    </div>
  );
}


// Phase CLAIM.1b — description text / audio / banner uploader panel.
// Submits to `POST /api/stations/owner/{station_id}/edit-request` with
// multipart form data.  Description text is a plain JSON field; audio
// + banner are file uploads.
function MediaUploaderModal({ station, variant, onClose, onSaved }) {
  const light = variant === "radiolife";
  const [descText, setDescText] = useState(station.description_text || "");
  const [audioFile, setAudioFile] = useState(null);
  const [bannerFile, setBannerFile] = useState(null);
  const [audioPreview, setAudioPreview] = useState(
    station.description_audio_url || null);
  const [bannerPreview, setBannerPreview] = useState(
    station.banner_image_url || null);
  const [saving, setSaving] = useState(false);

  const audioUrl = audioFile ? URL.createObjectURL(audioFile) : audioPreview;
  const bannerUrl = bannerFile ? URL.createObjectURL(bannerFile) : bannerPreview;

  const onDescAudio = (e) => {
    const f = e.target.files && e.target.files[0];
    if (!f) return;
    if (f.size > 3 * 1024 * 1024) {
      toast.error("Audio exceeds 3 MB");
      return;
    }
    if (!/^audio\/(mpeg|mp3|wav|x-wav|webm)/i.test(f.type)) {
      toast.error("Please upload an MP3 or WAV file");
      return;
    }
    setAudioFile(f);
    setAudioPreview(null);
  };

  const onBanner = (e) => {
    const f = e.target.files && e.target.files[0];
    if (!f) return;
    if (f.size > 5 * 1024 * 1024) {
      toast.error("Banner exceeds 5 MB");
      return;
    }
    if (!/^image\/(png|jpe?g|webp)/i.test(f.type)) {
      toast.error("Please upload PNG / JPG / WEBP");
      return;
    }
    setBannerFile(f);
    setBannerPreview(null);
  };

  const submit = async () => {
    if (!descText.trim() && !audioFile && !bannerFile) {
      toast.error("Change at least one field before submitting.");
      return;
    }
    setSaving(true);
    try {
      const fd = new FormData();
      const proposed = {};
      if (descText.trim() && descText.trim() !== (station.description_text || "")) {
        proposed.description_text = descText.trim();
      }
      fd.append("proposed_changes", JSON.stringify(proposed));
      if (bannerFile) fd.append("banner_image", bannerFile);
      if (audioFile) fd.append("description_audio", audioFile);
      const r = await axios.post(
        `${API}/stations/owner/${station.id}/edit-request`,
        fd,
        { withCredentials: true,
          headers: { "Content-Type": "multipart/form-data" } });
      const auto = r.data?.edit_request?.edit_status === "approved";
      toast.success(auto
        ? "Changes published"
        : "Submitted for admin review");
      onSaved && onSaved();
    } catch (e) {
      const code = e.response?.data?.detail?.code || "save_failed";
      const msg  = e.response?.data?.detail?.message || code;
      toast.error(msg);
    } finally { setSaving(false); }
  };

  return (
    <div data-testid="owner-media-modal"
              className={"fixed inset-0 z-50 flex items-center justify-center p-4 overflow-auto " +
                                    (light ? "bg-slate-900/40 backdrop-blur-sm" : "bg-black/70")}>
      <div className={"w-full max-w-[640px] rounded-2xl p-6 my-8 " + (light
                  ? "bg-white border border-slate-200 shadow-2xl"
                  : "bg-[#0a0a0c] border border-white/[0.10]")}>
        <div className="flex items-center justify-between mb-5">
          <div>
            <div className={"text-xs uppercase tracking-widest font-mono mb-1 " +
                                            (light ? "text-fuchsia-600" : "text-cyan-300")}>
              Media &amp; description
            </div>
            <div className={"font-semibold truncate " +
                                          (light ? "text-slate-900" : "text-white")}>
              {station.name}
            </div>
          </div>
          <button onClick={onClose}
                          data-testid="owner-media-close"
                          className={"p-1.5 rounded " + (light
                            ? "text-slate-500 hover:bg-slate-100"
                            : "text-white/60 hover:bg-white/[0.06] hover:text-white")}>
            <X size={16} />
          </button>
        </div>

        {/* Description text */}
        <div className="mb-5">
          <label className={"block text-xs mb-1 " +
                                          (light ? "text-slate-600" : "text-white/60")}>
            Description (markdown supported, up to ~10 000 chars)
          </label>
          <textarea rows={5}
                                value={descText}
                                onChange={(e) => setDescText(e.target.value)}
                                data-testid="owner-dashboard-desc-text"
                                placeholder="Tell listeners about your station, format, DJs, region…"
                                className={"w-full px-3 py-2 rounded-lg text-sm resize-y " +
                                                      (light
                                                          ? "bg-slate-50 border border-slate-200 focus:border-fuchsia-500 focus:outline-none"
                                                          : "bg-black/40 border border-white/[0.10] focus:border-cyan-400/50 focus:outline-none")} />
        </div>

        {/* Description audio */}
        <div className="mb-5">
          <label className={"block text-xs mb-1 " +
                                          (light ? "text-slate-600" : "text-white/60")}>
            Description audio (MP3/WAV, ≤ 3 MB, ~30 sec intro)
          </label>
          <div className={"rounded-lg p-3 flex items-center gap-3 " +
                                        (light
                                            ? "bg-slate-50 border border-slate-200"
                                            : "bg-black/40 border border-white/[0.10]")}>
            <div className={"w-9 h-9 rounded flex items-center justify-center flex-shrink-0 " +
                                          (audioUrl
                                              ? (light ? "bg-emerald-100 text-emerald-700" : "bg-emerald-400/15 text-emerald-300")
                                              : (light ? "bg-slate-200 text-slate-500"     : "bg-white/[0.06] text-white/50"))}>
              <FileAudio size={16} />
            </div>
            <div className="flex-grow min-w-0">
              {audioUrl ? (
                <audio controls src={audioUrl}
                              data-testid="owner-dashboard-desc-audio-preview"
                              className="w-full h-8" />
              ) : (
                <span className={"text-sm " + (light ? "text-slate-500" : "text-white/50")}>
                  No audio uploaded
                </span>
              )}
            </div>
            {audioFile ? (
              <button onClick={() => setAudioFile(null)}
                              className={"p-1.5 rounded " +
                                                    (light ? "text-rose-600 hover:bg-rose-50"
                                                                      : "text-rose-300 hover:bg-white/[0.06]")}>
                <Trash2 size={13} />
              </button>
            ) : (
              <label className={"px-3 h-8 rounded-full text-xs font-semibold cursor-pointer " +
                                                        "inline-flex items-center gap-1 " +
                                                        (light
                                                            ? "bg-fuchsia-600 text-white hover:bg-fuchsia-500"
                                                            : "bg-cyan-400 text-slate-900 hover:bg-cyan-300")}>
                <Upload size={11} /> Upload
                <input type="file" hidden accept="audio/*"
                                data-testid="owner-dashboard-desc-audio-upload"
                                onChange={onDescAudio} />
              </label>
            )}
          </div>
        </div>

        {/* Banner image */}
        <div className="mb-5">
          <label className={"block text-xs mb-1 " +
                                          (light ? "text-slate-600" : "text-white/60")}>
            Banner image (PNG/JPG/WEBP, ≤ 5 MB, 16:9 recommended)
          </label>
          <div className={"rounded-lg p-3 " +
                                        (light
                                            ? "bg-slate-50 border border-slate-200"
                                            : "bg-black/40 border border-white/[0.10]")}>
            {bannerUrl && (
              <img src={bannerUrl} alt="banner preview"
                        data-testid="owner-dashboard-banner-preview"
                        className={"w-full max-h-40 object-cover rounded mb-3 " +
                                                (light ? "border border-slate-200" : "border border-white/[0.10]")} />
            )}
            <div className="flex items-center gap-3">
              <div className={"w-9 h-9 rounded flex items-center justify-center flex-shrink-0 " +
                                            (bannerUrl
                                                ? (light ? "bg-emerald-100 text-emerald-700" : "bg-emerald-400/15 text-emerald-300")
                                                : (light ? "bg-slate-200 text-slate-500"     : "bg-white/[0.06] text-white/50"))}>
                <ImageIcon size={16} />
              </div>
              <div className={"flex-grow text-sm " +
                                          (light ? "text-slate-600" : "text-white/60")}>
                {bannerFile
                  ? `${bannerFile.name} · ${(bannerFile.size / 1024).toFixed(0)} KB`
                  : bannerPreview ? "Current banner" : "No banner uploaded"}
              </div>
              {bannerFile ? (
                <button onClick={() => setBannerFile(null)}
                                className={"p-1.5 rounded " +
                                                      (light ? "text-rose-600 hover:bg-rose-50"
                                                                        : "text-rose-300 hover:bg-white/[0.06]")}>
                  <Trash2 size={13} />
                </button>
              ) : (
                <label className={"px-3 h-8 rounded-full text-xs font-semibold cursor-pointer " +
                                                          "inline-flex items-center gap-1 " +
                                                          (light
                                                              ? "bg-fuchsia-600 text-white hover:bg-fuchsia-500"
                                                              : "bg-cyan-400 text-slate-900 hover:bg-cyan-300")}>
                  <Upload size={11} /> Upload
                  <input type="file" hidden accept="image/png,image/jpeg,image/webp"
                                  data-testid="owner-dashboard-banner-upload"
                                  onChange={onBanner} />
                </label>
              )}
            </div>
          </div>
        </div>

        <div className={"px-3 py-2 rounded-lg text-xs mb-4 " +
                                      (light
                                          ? "bg-amber-50 text-amber-800 border border-amber-200"
                                          : "bg-amber-400/[0.06] text-amber-200 border border-amber-400/20")}>
          <Volume2 size={11} className="inline mr-1" />
          Changes go through admin review unless auto-publish is enabled
          on this station by RadioLife staff.
        </div>

        <div className="flex justify-end gap-2">
          <button onClick={onClose} disabled={saving}
                          data-testid="owner-media-cancel"
                          className={"px-4 h-10 rounded-full text-sm " +
                                                (light
                                                    ? "bg-slate-200 text-slate-800 hover:bg-slate-300"
                                                    : "bg-white/[0.06] hover:bg-white/[0.10] border border-white/[0.10]")}>
            Cancel
          </button>
          <button onClick={submit} disabled={saving}
                          data-testid="owner-media-submit"
                          className={"inline-flex items-center gap-2 px-5 h-10 rounded-full text-sm font-semibold disabled:opacity-50 " +
                                                (light
                                                    ? "bg-fuchsia-600 text-white hover:bg-fuchsia-500"
                                                    : "bg-cyan-400 text-slate-900 hover:bg-cyan-300")}>
            {saving && <Loader2 size={13} className="animate-spin" />}
            Submit for review
          </button>
        </div>
      </div>
    </div>
  );
}
