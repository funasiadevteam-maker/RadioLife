// Phase MER.1 — Merchant Profile page (business info + locations + edit).
// Reuses SC.2 endpoints: PUT /api/merchant/{id}/profile,
//    POST/DELETE /api/merchant/{id}/locations, POST /api/merchant/{id}/logo.
import { useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { MapPin, Edit3, Trash2, Plus, Store, Phone, Globe, Loader2,
                  Upload, Check, X, Clock } from "lucide-react";
import { useMerchant } from "@/pages/merchant/MerchantShell";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;


export default function MerchantProfile() {
  const { merchant, light, refresh } = useMerchant();
  const [profile, setProfile] = useState(null);
  const [editing, setEditing] = useState(false);
  const [uploading, setUploading] = useState(false);

  const load = async () => {
    try {
      const { data } = await axios.get(
        `${API}/merchant/${merchant.merchant_id}`,
        { withCredentials: true });
      setProfile(data);
    } catch (e) {
      toast.error(`Load: ${e?.response?.data?.detail || e.message}`);
    }
  };
  useEffect(() => { if (merchant) load(); }, [merchant]);

  const uploadLogo = async (file) => {
    if (!file) return;
    setUploading(true);
    try {
      const form = new FormData();
      form.append("file", file);
      await axios.post(
        `${API}/merchant/${merchant.merchant_id}/logo`,
        form, { withCredentials: true,
                        headers: { "Content-Type": "multipart/form-data" } });
      toast.success("Logo updated");
      await load(); await refresh();
    } catch (e) {
      toast.error(`Logo: ${e?.response?.data?.detail || e.message}`);
    } finally { setUploading(false); }
  };

  const removeLocation = async (locId) => {
    if (!window.confirm("Remove this location?")) return;
    try {
      await axios.delete(
        `${API}/merchant/${merchant.merchant_id}/locations/${locId}`,
        { withCredentials: true });
      toast.success("Location removed");
      load();
    } catch (e) {
      toast.error(`Remove: ${e?.response?.data?.detail || e.message}`);
    }
  };

  if (!profile) {
    return (
      <div className="p-8 max-w-4xl mx-auto" data-testid="merchant-profile-loading">
        <Loader2 className="animate-spin" size={16}/>
      </div>
    );
  }

  const backendBase = (process.env.REACT_APP_BACKEND_URL || "").replace(/\/$/, "");
  const logoUrl = profile.logo_url?.startsWith("http")
    ? profile.logo_url : (profile.logo_url ? backendBase + profile.logo_url : null);

  return (
    <div className="p-6 lg:p-10 max-w-4xl mx-auto space-y-5"
              data-testid="merchant-profile-page">
      <div className="flex items-center gap-3 flex-wrap">
        <h1 className={`text-3xl font-black tracking-tight ${
          light ? "text-slate-900" : "text-white"
        }`}>Profile & Locations</h1>
        <button onClick={() => setEditing(true)}
                      data-testid="merchant-profile-edit-btn"
                      className={`ml-auto inline-flex items-center gap-1.5 h-10 px-4 rounded-full font-bold text-sm ${
                        light ? "bg-purple-100 text-purple-700 hover:bg-purple-200"
                                : "bg-cyan-500/15 text-cyan-300 hover:bg-cyan-500/25"
                      }`}>
          <Edit3 size={14}/> Edit
        </button>
      </div>

      {/* Business info */}
      <div className={`rounded-2xl p-6 ${
        light ? "bg-white border border-slate-100 shadow-sm"
                : "bg-slate-900 border border-slate-800"
      }`} data-testid="merchant-profile-info-card">
        <div className="flex items-start gap-5 flex-wrap">
          {logoUrl ? (
            <img src={logoUrl} alt="" className="w-24 h-24 rounded-2xl object-cover shrink-0"
                        data-testid="merchant-profile-logo"/>
          ) : (
            <div className={`w-24 h-24 rounded-2xl flex items-center justify-center shrink-0 ${
              light ? "bg-purple-50 text-purple-600"
                      : "bg-cyan-500/10 text-cyan-400"
            }`}><Store size={30}/></div>
          )}
          <label className={`shrink-0 h-9 px-3 rounded-full inline-flex items-center gap-1.5 text-xs font-bold cursor-pointer ${
            light ? "bg-slate-100 text-slate-700 hover:bg-slate-200"
                    : "bg-slate-800 text-slate-200 hover:bg-slate-700 border border-slate-700"
          }`} data-testid="merchant-profile-logo-upload">
            {uploading ? <Loader2 className="animate-spin" size={12}/>
                              : <Upload size={12}/>} Change logo
            <input type="file" accept="image/*" hidden
                        onChange={(e) => uploadLogo(e.target.files?.[0])}/>
          </label>
          <div className="flex-1 min-w-[240px]">
            <div className={`text-[10px] font-black uppercase tracking-widest ${
              light ? "text-purple-600" : "text-cyan-400"
            }`}>{(profile.category_id || "").replace(/_/g, " ")}</div>
            <div className={`mt-1 text-2xl font-black ${
              light ? "text-slate-900" : "text-white"
            }`} data-testid="merchant-profile-name">{profile.name}</div>
            {profile.description && (
              <p className={`mt-1.5 text-sm max-w-xl ${
                light ? "text-slate-600" : "text-slate-400"
              }`}>{profile.description}</p>
            )}
            <div className="mt-3 flex flex-wrap gap-4 text-xs">
              {profile.phone && (
                <span className={`inline-flex items-center gap-1 ${
                  light ? "text-slate-600" : "text-slate-400"
                }`}><Phone size={12}/> {profile.phone}</span>
              )}
              {profile.website && (
                <a href={profile.website} target="_blank" rel="noreferrer"
                        className={`inline-flex items-center gap-1 ${
                          light ? "text-purple-600 hover:text-purple-700"
                                  : "text-cyan-400 hover:text-cyan-300"
                        }`}><Globe size={12}/> {profile.website.replace(/^https?:\/\//, "")}</a>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Locations */}
      <div className={`rounded-2xl p-6 ${
        light ? "bg-white border border-slate-100 shadow-sm"
                : "bg-slate-900 border border-slate-800"
      }`} data-testid="merchant-profile-locations">
        <div className="flex items-center justify-between mb-3">
          <h2 className={`text-sm font-black uppercase tracking-widest ${
            light ? "text-slate-700" : "text-slate-200"
          }`}>Locations · {profile.locations?.length || 0}</h2>
        </div>
        {(!profile.locations || profile.locations.length === 0) ? (
          <div className={`p-6 text-center text-sm rounded-xl ${
            light ? "bg-slate-50 text-slate-500"
                    : "bg-slate-950 text-slate-500 border border-slate-800"
          }`}>No locations added yet.</div>
        ) : (
          <div className="space-y-2">
            {profile.locations.map((loc) => (
              <div key={loc.location_id}
                        data-testid={`merchant-location-${loc.location_id}`}
                        className={`rounded-xl p-4 flex items-start gap-3 ${
                          light ? "bg-slate-50 border border-slate-100"
                                  : "bg-slate-950 border border-slate-800"
                        }`}>
                <MapPin size={16} className={light ? "text-purple-600 mt-0.5"
                                                                            : "text-cyan-400 mt-0.5"}/>
                <div className="flex-1 min-w-0">
                  <div className={`text-sm font-bold ${
                    light ? "text-slate-900" : "text-white"
                  }`}>
                    {loc.name || loc.address}
                    {loc.primary && (
                      <span className={`ml-2 inline-block px-2 py-0.5 rounded-full text-[9px] font-black uppercase tracking-widest ${
                        light ? "bg-purple-100 text-purple-700"
                                : "bg-cyan-500/15 text-cyan-300"
                      }`}>Primary</span>
                    )}
                  </div>
                  <div className={`text-xs mt-0.5 ${
                    light ? "text-slate-600" : "text-slate-400"
                  }`}>{loc.address}, {loc.city}, {loc.country}</div>
                </div>
                {!loc.primary && (
                  <button onClick={() => removeLocation(loc.location_id)}
                                data-testid={`merchant-location-remove-${loc.location_id}`}
                                className={light ? "text-rose-600 hover:bg-rose-50 rounded p-1"
                                                              : "text-rose-400 hover:bg-rose-500/10 rounded p-1"}>
                    <Trash2 size={14}/>
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Hours */}
      {profile.hours && (
        <div className={`rounded-2xl p-6 ${
          light ? "bg-white border border-slate-100 shadow-sm"
                  : "bg-slate-900 border border-slate-800"
        }`} data-testid="merchant-profile-hours">
          <h2 className={`text-sm font-black uppercase tracking-widest mb-3 ${
            light ? "text-slate-700" : "text-slate-200"
          }`}>Business hours</h2>
          <div className="grid grid-cols-2 gap-2 text-xs">
            {["monday","tuesday","wednesday","thursday","friday","saturday","sunday"].map((d) => {
              const h = profile.hours[d];
              return (
                <div key={d} className={`flex items-center justify-between ${
                  light ? "text-slate-700" : "text-slate-300"
                }`}>
                  <span className="capitalize font-semibold">{d}</span>
                  <span className={h?.closed
                                                        ? (light ? "text-slate-400" : "text-slate-500")
                                                        : ""}>
                    {h?.closed ? "Closed" : `${h?.open || "—"} – ${h?.close || "—"}`}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {editing && (
        <EditProfileModal light={light} profile={profile}
                                                  merchantId={merchant.merchant_id}
                                                  onClose={() => setEditing(false)}
                                                  onSuccess={() => { setEditing(false); load(); refresh(); }}/>
      )}
    </div>
  );
}


function EditProfileModal({ light, profile, merchantId, onClose, onSuccess }) {
  const [description, setDescription] = useState(profile.description || "");
  const [phone, setPhone] = useState(profile.phone || "");
  const [website, setWebsite] = useState(profile.website || "");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  const submit = async () => {
    setBusy(true); setErr(null);
    try {
      await axios.put(
        `${API}/merchant/${merchantId}/profile`,
        { description, phone, website },
        { withCredentials: true });
      toast.success("Profile updated");
      onSuccess();
    } catch (e) {
      setErr(e?.response?.data?.detail || e.message);
    } finally { setBusy(false); }
  };

  return (
    <div onClick={onClose}
              className="fixed inset-0 z-[60] bg-black/70 flex items-end sm:items-center justify-center p-0 sm:p-4"
              data-testid="merchant-profile-edit-backdrop">
      <div onClick={(e) => e.stopPropagation()}
                data-testid="merchant-profile-edit-modal"
                className={`w-full sm:max-w-md rounded-t-3xl sm:rounded-3xl p-6 ${
                  light ? "bg-white" : "bg-slate-900 border border-slate-800"
                }`}>
        <div className="flex items-center justify-between mb-4">
          <h3 className={`text-lg font-black ${
            light ? "text-slate-900" : "text-white"
          }`}>Edit profile</h3>
          <button onClick={onClose} className={
            light ? "text-slate-500" : "text-slate-500"}>
            <X size={20}/>
          </button>
        </div>

        <PLabel light={light}>Description</PLabel>
        <textarea rows={3} value={description}
                            onChange={(e) => setDescription(e.target.value)}
                            data-testid="merchant-profile-description-input"
                            className={pTextArea(light)}/>
        <PLabel light={light}>Phone</PLabel>
        <input value={phone} onChange={(e) => setPhone(e.target.value)}
                    data-testid="merchant-profile-phone-input"
                    className={pInput(light)}/>
        <PLabel light={light}>Website</PLabel>
        <input value={website} onChange={(e) => setWebsite(e.target.value)}
                    placeholder="https://…"
                    data-testid="merchant-profile-website-input"
                    className={pInput(light)}/>
        {err && (
          <div className={`text-xs rounded-lg p-2 mt-3 ${
            light ? "bg-rose-50 text-rose-700 border border-rose-100"
                    : "bg-rose-500/10 text-rose-300 border border-rose-500/20"
          }`} data-testid="merchant-profile-edit-error">{String(err)}</div>
        )}
        <button onClick={submit} disabled={busy}
                      data-testid="merchant-profile-save-btn"
                      className="w-full mt-5 h-12 rounded-full font-black text-sm text-white"
                      style={{ background: busy ? "#94a3b8"
                                        : "linear-gradient(135deg,#a855f7,#ec4899)" }}>
          {busy ? "Saving…" : "Save changes"}
        </button>
      </div>
    </div>
  );
}


function PLabel({ light, children }) {
  return <div className={`text-[10px] font-bold uppercase tracking-widest mb-1 mt-3 ${
    light ? "text-slate-500" : "text-slate-500"
  }`}>{children}</div>;
}
function pInput(light) {
  return `w-full h-11 rounded-xl px-3 text-sm outline-none ${
    light ? "bg-slate-50 border border-slate-200 focus:border-purple-500"
            : "bg-slate-950 border border-slate-800 text-slate-200 focus:border-cyan-500"
  }`;
}
function pTextArea(light) {
  return `w-full rounded-xl px-3 py-2 text-sm outline-none resize-y ${
    light ? "bg-slate-50 border border-slate-200 focus:border-purple-500"
            : "bg-slate-950 border border-slate-800 text-slate-200 focus:border-cyan-500"
  }`;
}
