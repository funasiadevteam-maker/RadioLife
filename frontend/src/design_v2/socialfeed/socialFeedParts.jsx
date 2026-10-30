// Building blocks for SocialFeedHomeV2 — header, moments, composer, together
// row, mode tabs, sidebars, discovery, audio dock, bottom nav.
import { useEffect, useState, useRef } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import axios from "axios";
import { fireConfetti } from "./confetti";
import {
  Home, Users, Headphones, ShoppingBag, Gamepad2, Bell, Coins, Search,
  Plus, Image as ImageIcon, Music2, Mic, MoreHorizontal, MapPin, Play, Pause,
  X, Utensils, Gift, Bookmark, Radio, ListMusic, Sparkles, Moon, Crown, Store,
  Headphones as Head2, Heart, ChevronRight, Camera, Video, Globe, Type,
  Loader2, Check, AlertCircle, ChevronDown, RotateCcw, Square, Upload, SlidersHorizontal, Shield,
} from "lucide-react";
import { useGeoStore } from "@/store/useGeoStore";
import { usePlayerStore } from "@/store/usePlayerStore";
import { useAuth } from "@/AuthContext";
import { initials, pillStyle } from "./sfTheme";
import HomeViewSwitcher from "./HomeViewSwitcher";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

const TOP_NAV = [
  { key: "home", label: "Home", icon: Home, to: "/" },
  { key: "social", label: "Social", icon: Users, to: "/social" },
  { key: "listen", label: "Listen", icon: Headphones, to: "/listen" },
  { key: "shop", label: "Shop", icon: ShoppingBag, to: "/shop" },
  { key: "play", label: "Play", icon: Gamepad2, to: "/play-and-win" },
];

/* ─────────────────────────── Header ─────────────────────────── */
export function SfHeader({ t, appearance }) {
  const { pathname } = useLocation();
  const city = useGeoStore((s) => s.city);
  const [points, setPoints] = useState(null);
  useEffect(() => {
    axios.get(`${API}/bigcoin/me`, { withCredentials: true })
      .then((r) => setPoints(r.data?.balance)).catch(() => {});
  }, []);
  const active = (to) => (to === "/" ? pathname === "/" : pathname.startsWith(to));

  return (
    <header data-testid="sf-header" style={{
      position: "sticky", top: 0, zIndex: 50, background: t.header,
      backdropFilter: "blur(14px)", borderBottom: `1px solid ${t.border}`,
    }}>
      <div style={{ maxWidth: 1240, margin: "0 auto", height: 60, padding: "0 14px", display: "flex", alignItems: "center", gap: 14 }}>
        <Link to="/" style={{ fontWeight: 900, fontSize: 21, letterSpacing: "-.02em", backgroundImage: t.accentGrad, WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent" }}>FUUSIC</Link>

        {/* desktop nav */}
        <nav className="hidden lg:flex" style={{ gap: 4, marginLeft: 8 }}>
          {TOP_NAV.map(({ key, label, icon: Icon, to }) => (
            <Link key={key} to={to} data-testid={`sf-nav-${key}`}
              style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 1, padding: "6px 14px", borderRadius: 11, color: active(to) ? t.accent : t.text2, background: active(to) ? t.accentSoft : "transparent", fontWeight: 700 }}>
              <Icon size={18} /><span style={{ fontSize: 11 }}>{label}</span>
            </Link>
          ))}
        </nav>

        {/* desktop search */}
        <div className="hidden lg:flex" style={{ flex: 1, maxWidth: 360, marginLeft: 8, alignItems: "center", gap: 8, height: 38, padding: "0 12px", borderRadius: 999, background: t.chip, border: `1px solid ${t.border}`, color: t.muted }}>
          <Search size={16} /><span style={{ fontSize: 13 }}>Search music, people, stations…</span>
        </div>

        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 8 }}>
          <span className="hidden sm:inline-flex" style={{ alignItems: "center", gap: 4, color: t.text2, fontSize: 12, fontWeight: 700 }}>
            <MapPin size={14} color={t.accent} />{city || "Dubai"}
          </span>
          <Link to="/wallet" data-testid="sf-points" style={{ display: "inline-flex", alignItems: "center", gap: 5, height: 34, padding: "0 10px", borderRadius: 999, background: t.goldBg, border: `1px solid ${t.gold}44` }}>
            <Coins size={15} color={t.gold} />
            <span style={{ fontFamily: "monospace", fontWeight: 900, fontSize: 13, color: t.gold }}>{points != null ? points.toLocaleString() : "—"}</span>
          </Link>
          <Link to="/notifications" data-testid="sf-bell" style={{ width: 34, height: 34, borderRadius: 999, display: "grid", placeItems: "center", color: t.text2, background: t.chip }}>
            <Bell size={17} />
          </Link>
          <HomeViewSwitcher dark={appearance === "dark"} />
          <Link to="/profile" data-testid="sf-avatar" className="hidden sm:grid" style={{ width: 34, height: 34, borderRadius: 999, placeItems: "center", color: "#fff", fontWeight: 800, background: t.accentGrad }}>U</Link>
        </div>
      </div>
    </header>
  );
}

/* ─────────────────────────── Moments ─────────────────────────── */
export function MomentsRow({ t, moments }) {
  const nav = useNavigate();
  const list = moments || [];
  return (
    <div className="sf-noscroll" data-testid="sf-moments" style={{ display: "flex", gap: 12, overflowX: "auto", padding: "2px 2px 2px", background: t.card, border: `1px solid ${t.border}`, borderRadius: 18, boxShadow: t.shadow, paddingLeft: 12, paddingRight: 12, paddingTop: 12, paddingBottom: 12 }}>
      <Momentcircle t={t} add onClick={() => nav("/social")} label="Add" />
      {list.slice(0, 14).map((m, i) => (
        <Momentcircle key={m._id || m.id || i} t={t}
          img={m.media_url || m.author?.avatar_url}
          label={(m.author?.name || m.user_name || "You").split(" ")[0]}
          live={m.context?.live}
          onClick={() => nav("/social")} />
      ))}
      {list.length === 0 && <span style={{ fontSize: 12.5, color: t.muted, alignSelf: "center" }}>Share your first Moment →</span>}
    </div>
  );
}
function Momentcircle({ t, img, label, add, live, onClick }) {
  return (
    <button onClick={onClick} className="sf-press" style={{ flex: "0 0 auto", width: 62, border: "none", background: "transparent", cursor: "pointer", textAlign: "center" }}>
      <span style={{ position: "relative", display: "block", width: 58, height: 58, borderRadius: 999, margin: "0 auto", padding: 2, background: add ? t.chip : t.accentGrad }}>
        {add ? (
          <span style={{ width: "100%", height: "100%", borderRadius: 999, display: "grid", placeItems: "center", background: t.card, color: t.accent }}><Plus size={22} /></span>
        ) : img ? (
          <img src={img} alt="" loading="lazy" style={{ width: "100%", height: "100%", borderRadius: 999, objectFit: "cover", border: `2px solid ${t.card}` }} />
        ) : (
          <span style={{ width: "100%", height: "100%", borderRadius: 999, display: "grid", placeItems: "center", background: t.card, color: t.text2, fontWeight: 800 }}>{initials(label)}</span>
        )}
        {live && <span style={{ position: "absolute", bottom: 0, left: "50%", transform: "translateX(-50%)", fontSize: 8, fontWeight: 900, color: "#fff", background: t.live, padding: "1px 5px", borderRadius: 999 }}>LIVE</span>}
      </span>
      <span className="sf-clamp2" style={{ display: "block", fontSize: 11, color: t.text2, marginTop: 4 }}>{label}</span>
    </button>
  );
}

/* ─────────────────────────── Composer ─────────────────────────── */
// The FUUSIC Post Composer — Text / Camera / Photo-Video with real upload,
// preview, audience choice and publish. No "paste image URL" anywhere.
export function Composer({ t, onPosted }) {
  const [open, setOpen] = useState(false);
  const [intent, setIntent] = useState(null); // null | "camera" | "gallery" | "voice"
  const start = (i) => { setIntent(i); setOpen(true); };
  const QA = [
    { icon: Type, label: "Text", c: "#ec4899", onClick: () => start(null) },
    { icon: Camera, label: "Camera", c: "#22c55e", onClick: () => start("camera") },
    { icon: ImageIcon, label: "Photo", c: t.accent, onClick: () => start("gallery") },
    { icon: Mic, label: "Voice", c: "#f59e0b", onClick: () => start("voice") },
    { icon: MoreHorizontal, label: "More", c: t.text2, onClick: () => start(null) },
  ];
  return (
    <>
      <div data-testid="sf-composer" style={{ background: t.card, border: `1px solid ${t.border}`, borderRadius: 18, boxShadow: t.shadow, padding: 12 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ width: 40, height: 40, borderRadius: 999, flexShrink: 0, display: "grid", placeItems: "center", color: "#fff", fontWeight: 800, background: t.accentGrad }}>U</span>
          <button onClick={() => start(null)} data-testid="sf-composer-open" className="sf-press"
            style={{ flex: 1, textAlign: "left", padding: "10px 16px", borderRadius: 999, border: `1px solid ${t.border}`, background: t.chip, color: t.muted, cursor: "pointer", fontSize: 14 }}>
            What's on your mind?
          </button>
        </div>
        <div style={{ display: "flex", gap: 2, marginTop: 10, borderTop: `1px solid ${t.border}`, paddingTop: 8 }}>
          {QA.map(({ icon: Icon, label, c, onClick }) => (
            <button key={label} onClick={onClick} data-testid={`sf-qa-${label.toLowerCase()}`} className="sf-press"
              style={{ flex: 1, display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 6, padding: "8px 4px", borderRadius: 10, border: "none", background: "transparent", color: t.text2, fontWeight: 700, fontSize: 12.5, cursor: "pointer" }}>
              <Icon size={17} color={c} /><span className="hidden sm:inline">{label}</span>
            </button>
          ))}
        </div>
      </div>
      {open && (
        <PostComposerModal t={t} intent={intent}
          onClose={() => setOpen(false)}
          onPosted={() => { setOpen(false); onPosted && onPosted(); }} />
      )}
    </>
  );
}

const AUDIENCES = [
  { k: "public", label: "Public", Icon: Globe, hint: "Anyone on FUUSIC" },
  { k: "friends", label: "Friends", Icon: Users, hint: "Only your friends" },
];

// Live in-app camera capture (getUserMedia). Falls back gracefully when the
// camera is unavailable/denied — the user can still use "Photo / Video".
function CameraCapture({ t, onBlob, onCancel }) {
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const [ready, setReady] = useState(false);
  const [err, setErr] = useState(null);
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: "environment" }, audio: false });
        if (!active) { stream.getTracks().forEach((tr) => tr.stop()); return; }
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play().catch(() => {});
        }
        setReady(true);
      } catch (_e) { setErr("Camera unavailable or permission denied. Use Photo / Video instead."); }
    })();
    return () => { active = false; streamRef.current?.getTracks().forEach((tr) => tr.stop()); };
  }, []);
  const snap = () => {
    const v = videoRef.current; if (!v) return;
    const c = document.createElement("canvas");
    c.width = v.videoWidth || 720; c.height = v.videoHeight || 1280;
    c.getContext("2d").drawImage(v, 0, 0, c.width, c.height);
    c.toBlob((blob) => {
      if (!blob) return;
      streamRef.current?.getTracks().forEach((tr) => tr.stop());
      onBlob(new File([blob], `camera_${Date.now()}.jpg`, { type: "image/jpeg" }));
    }, "image/jpeg", 0.9);
  };
  return (
    <div style={{ padding: 16 }} data-testid="sf-camera-capture">
      {err ? (
        <div data-testid="sf-camera-error" style={{ display: "flex", alignItems: "center", gap: 7, padding: "10px 12px", borderRadius: 10, background: `${t.live}18`, color: t.live, fontSize: 13, fontWeight: 600 }}>
          <AlertCircle size={16} /> {err}
        </div>
      ) : (
        <video ref={videoRef} playsInline muted data-testid="sf-camera-video"
          style={{ width: "100%", maxHeight: 360, objectFit: "cover", borderRadius: 14, background: "#000", display: "block" }} />
      )}
      <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
        <button onClick={onCancel} data-testid="sf-camera-cancel" className="sf-press"
          style={{ flex: 1, padding: "11px", borderRadius: 11, border: `1px solid ${t.border}`, background: "transparent", color: t.text2, fontWeight: 700, cursor: "pointer" }}>
          Back
        </button>
        {!err && (
          <button onClick={snap} disabled={!ready} data-testid="sf-camera-snap" className="sf-press"
            style={{ flex: 2, display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 8, padding: "11px", borderRadius: 11, border: "none", background: t.accentGrad, color: "#fff", fontWeight: 800, cursor: "pointer", opacity: ready ? 1 : 0.6 }}>
            <Camera size={17} /> Take Photo
          </button>
        )}
      </div>
    </div>
  );
}

// Voice-note recorder (MediaRecorder) with record / stop / preview / re-record,
// plus an "upload an audio file instead" escape hatch.
function VoiceRecorder({ t, onBlob, onCancel, onUploadClick }) {
  const [phase, setPhase] = useState("idle"); // idle | recording | recorded
  const [secs, setSecs] = useState(0);
  const [url, setUrl] = useState(null);
  const [err, setErr] = useState(null);
  const mrRef = useRef(null);
  const chunksRef = useRef([]);
  const streamRef = useRef(null);
  const timerRef = useRef(null);
  const blobRef = useRef(null);
  const supported = typeof window !== "undefined" && !!navigator.mediaDevices?.getUserMedia && typeof window.MediaRecorder !== "undefined";

  const stop = () => {
    clearInterval(timerRef.current);
    try { if (mrRef.current && mrRef.current.state !== "inactive") mrRef.current.stop(); } catch (_e) { /* noop */ }
  };
  const begin = async () => {
    setErr(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const mime = window.MediaRecorder.isTypeSupported?.("audio/webm") ? "audio/webm" : "";
      const mr = new window.MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
      chunksRef.current = [];
      mr.ondataavailable = (e) => { if (e.data && e.data.size) chunksRef.current.push(e.data); };
      mr.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: mr.mimeType || "audio/webm" });
        blobRef.current = blob;
        setUrl(URL.createObjectURL(blob));
        setPhase("recorded");
        streamRef.current?.getTracks().forEach((tr) => tr.stop());
      };
      mrRef.current = mr;
      mr.start();
      setPhase("recording"); setSecs(0);
      timerRef.current = setInterval(() => setSecs((s) => {
        if (s >= 120) { stop(); return s; }
        return s + 1;
      }), 1000);
    } catch (_e) { setErr("Microphone unavailable or permission denied."); }
  };
  const use = () => {
    const b = blobRef.current; if (!b) return;
    const ext = (b.type || "").includes("ogg") ? "ogg" : (b.type || "").includes("mp4") ? "m4a" : "webm";
    onBlob(new File([b], `voice_${Date.now()}.${ext}`, { type: b.type || "audio/webm" }));
  };
  const reset = () => { setPhase("idle"); setSecs(0); setUrl(null); blobRef.current = null; };
  useEffect(() => () => {
    clearInterval(timerRef.current);
    streamRef.current?.getTracks().forEach((tr) => tr.stop());
  }, []);
  const mmss = `${String(Math.floor(secs / 60)).padStart(1, "0")}:${String(secs % 60).padStart(2, "0")}`;

  return (
    <div style={{ padding: 16 }} data-testid="sf-voice-recorder">
      <div style={{ borderRadius: 16, border: `1px solid ${t.border}`, background: t.cardAlt, padding: "26px 16px", textAlign: "center" }}>
        {err && (
          <div data-testid="sf-voice-error" style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 7, marginBottom: 14, color: t.live, fontSize: 13, fontWeight: 600 }}>
            <AlertCircle size={15} /> {err}
          </div>
        )}
        {phase === "recorded" && url ? (
          <>
            <audio src={url} controls data-testid="sf-voice-preview" style={{ width: "100%", marginBottom: 14 }} />
            <div style={{ display: "flex", gap: 8, justifyContent: "center" }}>
              <button onClick={reset} data-testid="sf-voice-reset" className="sf-press"
                style={{ display: "inline-flex", alignItems: "center", gap: 7, padding: "10px 16px", borderRadius: 999, border: `1px solid ${t.border}`, background: "transparent", color: t.text2, fontWeight: 700, cursor: "pointer" }}>
                <RotateCcw size={15} /> Re-record
              </button>
              <button onClick={use} data-testid="sf-voice-use" className="sf-press"
                style={{ display: "inline-flex", alignItems: "center", gap: 7, padding: "10px 20px", borderRadius: 999, border: "none", background: t.accentGrad, color: "#fff", fontWeight: 800, cursor: "pointer" }}>
                <Check size={15} /> Use recording
              </button>
            </div>
          </>
        ) : (
          <>
            <div style={{ fontSize: 30, fontWeight: 900, color: t.text, letterSpacing: 1, marginBottom: 4 }} data-testid="sf-voice-timer">{mmss}</div>
            <div style={{ fontSize: 12.5, color: t.muted, marginBottom: 18 }}>
              {phase === "recording" ? "Recording… tap to stop" : "Tap the mic to record a voice note (max 2 min)"}
            </div>
            <button onClick={phase === "recording" ? stop : begin} disabled={!supported}
              data-testid="sf-voice-toggle" className="sf-press"
              style={{ width: 72, height: 72, borderRadius: 999, border: "none", cursor: supported ? "pointer" : "not-allowed",
                background: phase === "recording" ? t.live : t.accentGrad, display: "inline-grid", placeItems: "center",
                boxShadow: phase === "recording" ? `0 0 0 8px ${t.live}22` : "0 8px 22px rgba(168,85,247,.32)", opacity: supported ? 1 : 0.5 }}>
              {phase === "recording" ? <Square size={26} color="#fff" fill="#fff" /> : <Mic size={28} color="#fff" />}
            </button>
          </>
        )}
      </div>
      <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
        <button onClick={onCancel} data-testid="sf-voice-cancel" className="sf-press"
          style={{ flex: 1, padding: "11px", borderRadius: 11, border: `1px solid ${t.border}`, background: "transparent", color: t.text2, fontWeight: 700, cursor: "pointer" }}>
          Back
        </button>
        <button onClick={onUploadClick} data-testid="sf-voice-upload" className="sf-press"
          style={{ flex: 1, display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 7, padding: "11px", borderRadius: 11, border: `1px solid ${t.border}`, background: t.chip, color: t.text, fontWeight: 700, cursor: "pointer" }}>
          <Upload size={16} /> Upload file
        </button>
      </div>
    </div>
  );
}


export function PostComposerModal({ t, intent, onClose, onPosted }) {
  const [text, setText] = useState("");
  const [media, setMedia] = useState(null); // {url, media_type, name}
  const [uploading, setUploading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [audience, setAudience] = useState("public");
  const [audOpen, setAudOpen] = useState(false);
  const [err, setErr] = useState(null);
  const [done, setDone] = useState(false);
  const [view, setView] = useState("form"); // form | camera | voice
  const galleryRef = useRef(null);
  const cameraRef = useRef(null);
  const audioRef = useRef(null);

  useEffect(() => {
    if (intent === "camera") setView("camera");
    else if (intent === "voice") setView("voice");
    else if (intent === "gallery") galleryRef.current?.click();
  }, [intent]);

  const uploadFile = async (file) => {
    if (!file) return;
    setErr(null); setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const r = await axios.post(`${API}/social/media/upload`, fd, {
        withCredentials: true, headers: { "Content-Type": "multipart/form-data" } });
      setMedia({ url: r.data?.url, key: r.data?.key, media_type: r.data?.media_type, name: file.name || "upload" });
      setView("form");
    } catch (_e) {
      setErr("Upload failed — please try again.");
    } finally { setUploading(false); }
  };

  const onFile = (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    uploadFile(file);
  };

  const publish = async () => {
    if (!text.trim() && !media) { setErr("Add a caption or a photo first."); return; }
    setBusy(true); setErr(null);
    try {
      await axios.post(`${API}/social/moments`, {
        caption: text.trim(),
        media_url: media?.url || null,
        media_key: media?.key || null,
        media_type: media?.media_type || null,
        visibility: audience,
      }, { withCredentials: true });
      setDone(true);
      // Celebrate the first post of the day landing on the member's own wall.
      try {
        const k = `fuusic_confetti_${new Date().toISOString().slice(0, 10)}`;
        if (!localStorage.getItem(k)) { localStorage.setItem(k, "1"); fireConfetti(); }
      } catch (_e) { /* storage blocked */ }
      setTimeout(() => onPosted && onPosted(), 650);
    } catch (_e) {
      // Keep the content so the user can retry — never discard on failure.
      setErr("Couldn't share your post. Your content is safe — tap Share to retry.");
    } finally { setBusy(false); }
  };

  const Aud = AUDIENCES.find((a) => a.k === audience) || AUDIENCES[0];
  return (
    <div data-testid="sf-composer-modal" onClick={onClose}
      style={{ position: "fixed", inset: 0, zIndex: 100, background: "rgba(8,11,22,.55)", backdropFilter: "blur(4px)", display: "grid", placeItems: "center", padding: 14 }}>
      <div onClick={(e) => e.stopPropagation()} className="sf-fade-in"
        style={{ width: "100%", maxWidth: 520, background: t.card, border: `1px solid ${t.border}`, borderRadius: 20, boxShadow: t.shadow, overflow: "hidden" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "14px 16px", borderBottom: `1px solid ${t.border}` }}>
          <span style={{ fontWeight: 900, fontSize: 16, color: t.text }}>Create Post</span>
          <button onClick={onClose} data-testid="sf-composer-close" className="sf-press" style={{ width: 32, height: 32, borderRadius: 999, border: "none", background: t.chip, color: t.text2, cursor: "pointer", display: "grid", placeItems: "center" }}><X size={18} /></button>
        </div>

        {/* Hidden file inputs — always mounted so the camera/voice views can reach them */}
        <input ref={cameraRef} type="file" accept="image/*" capture="environment" onChange={onFile} style={{ display: "none" }} />
        <input ref={galleryRef} type="file" accept="image/*,video/*" onChange={onFile} style={{ display: "none" }} />
        <input ref={audioRef} type="file" accept="audio/*" onChange={onFile} style={{ display: "none" }} />

        {done ? (
          <div style={{ padding: "44px 20px", textAlign: "center" }}>
            <span style={{ width: 60, height: 60, borderRadius: 999, display: "inline-grid", placeItems: "center", background: t.accentSoft, marginBottom: 12 }}><Check size={30} color={t.accent} /></span>
            <div style={{ fontWeight: 800, fontSize: 17, color: t.text }}>Your post has been shared!</div>
          </div>
        ) : view === "camera" ? (
          <CameraCapture t={t} onBlob={uploadFile} onCancel={() => setView("form")} />
        ) : view === "voice" ? (
          <VoiceRecorder t={t} onBlob={uploadFile} onCancel={() => setView("form")} onUploadClick={() => audioRef.current?.click()} />
        ) : (
          <div style={{ padding: 16 }}>
            {/* audience picker */}
            <div style={{ position: "relative", marginBottom: 10 }}>
              <button onClick={() => setAudOpen((v) => !v)} data-testid="sf-composer-audience" className="sf-press"
                style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "6px 12px", borderRadius: 999, border: `1px solid ${t.border}`, background: t.chip, color: t.text, fontWeight: 700, fontSize: 13, cursor: "pointer" }}>
                <Aud.Icon size={14} color={t.accent} /> {Aud.label} <ChevronDown size={14} />
              </button>
              {audOpen && (
                <div style={{ position: "absolute", top: "100%", left: 0, marginTop: 6, width: 220, background: t.card, border: `1px solid ${t.border}`, borderRadius: 12, boxShadow: t.shadow, padding: 6, zIndex: 10 }}>
                  {AUDIENCES.map((a) => (
                    <button key={a.k} data-testid={`sf-audience-${a.k}`} onClick={() => { setAudience(a.k); setAudOpen(false); }} className="sf-press"
                      style={{ display: "flex", alignItems: "center", gap: 10, width: "100%", textAlign: "left", background: audience === a.k ? t.accentSoft : "transparent", border: "none", borderRadius: 9, padding: "9px 10px", cursor: "pointer" }}>
                      <a.Icon size={16} color={t.accent} />
                      <span><span style={{ display: "block", fontWeight: 700, fontSize: 13.5, color: t.text }}>{a.label}</span><span style={{ display: "block", fontSize: 11.5, color: t.muted }}>{a.hint}</span></span>
                    </button>
                  ))}
                </div>
              )}
            </div>

            <textarea autoFocus value={text} onChange={(e) => setText(e.target.value)} data-testid="sf-composer-input"
              placeholder="Share a moment with FUUSIC…" rows={4}
              style={{ width: "100%", resize: "vertical", padding: 12, borderRadius: 12, border: `1px solid ${t.border}`, background: t.cardAlt, color: t.text, fontSize: 15, outline: "none" }} />

            {/* media preview */}
            {uploading && (
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 10, color: t.text2, fontSize: 13 }}>
                <Loader2 size={16} className="sf-spin" /> Uploading…
              </div>
            )}
            {media && !uploading && (
              <div data-testid="sf-composer-preview" style={{ position: "relative", marginTop: 10, borderRadius: 14, overflow: "hidden", border: `1px solid ${t.border}`, background: t.cardAlt }}>
                {media.media_type === "video"
                  ? <video src={media.url} controls style={{ width: "100%", maxHeight: 300, display: "block" }} />
                  : (media.media_type === "audio" || media.media_type === "voice")
                  ? <div style={{ padding: 14 }}><audio src={media.url} controls data-testid="sf-composer-audio-preview" style={{ width: "100%" }} /></div>
                  : <img src={media.url} alt="" style={{ width: "100%", maxHeight: 300, objectFit: "cover", display: "block" }} />}
                <button onClick={() => setMedia(null)} data-testid="sf-composer-remove-media" className="sf-press"
                  style={{ position: "absolute", top: 8, right: 8, width: 30, height: 30, borderRadius: 999, border: "none", cursor: "pointer", background: "rgba(0,0,0,.6)", color: "#fff", display: "grid", placeItems: "center" }}><X size={16} /></button>
              </div>
            )}

            {err && (
              <div data-testid="sf-composer-error" style={{ display: "flex", alignItems: "center", gap: 7, marginTop: 10, padding: "8px 11px", borderRadius: 10, background: `${t.live}18`, color: t.live, fontSize: 12.5, fontWeight: 600 }}>
                <AlertCircle size={15} /> {err}
              </div>
            )}

            {/* attach actions */}
            <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
              <button onClick={() => setView("camera")} data-testid="sf-composer-camera" className="sf-press"
                style={{ flex: 1, display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 7, padding: "10px", borderRadius: 11, border: `1px solid ${t.border}`, background: t.chip, color: t.text, fontWeight: 700, fontSize: 13, cursor: "pointer" }}>
                <Camera size={17} color="#22c55e" /> Camera
              </button>
              <button onClick={() => galleryRef.current?.click()} data-testid="sf-composer-gallery" className="sf-press"
                style={{ flex: 1, display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 7, padding: "10px", borderRadius: 11, border: `1px solid ${t.border}`, background: t.chip, color: t.text, fontWeight: 700, fontSize: 13, cursor: "pointer" }}>
                <ImageIcon size={17} color={t.accent} /> Photo
              </button>
              <button onClick={() => setView("voice")} data-testid="sf-composer-voice" className="sf-press"
                style={{ flex: 1, display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 7, padding: "10px", borderRadius: 11, border: `1px solid ${t.border}`, background: t.chip, color: t.text, fontWeight: 700, fontSize: 13, cursor: "pointer" }}>
                <Mic size={17} color="#f59e0b" /> Voice
              </button>
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 14 }}>
              <button onClick={onClose} className="sf-press" style={{ padding: "10px 18px", borderRadius: 999, border: `1px solid ${t.border}`, background: "transparent", color: t.text2, fontWeight: 700, cursor: "pointer" }}>Cancel</button>
              <button onClick={publish} disabled={busy || uploading} data-testid="sf-composer-post" className="sf-press"
                style={{ padding: "10px 24px", borderRadius: 999, border: "none", background: t.accentGrad, color: "#fff", fontWeight: 800, cursor: "pointer", opacity: busy || uploading ? .6 : 1, display: "inline-flex", alignItems: "center", gap: 7 }}>
                {busy ? <><Loader2 size={15} className="sf-spin" /> Sharing…</> : "Share"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/* ─────────────────────── Together quick actions ─────────────────────── */
const TOGETHER = [
  { label: "Listen\nTogether", icon: Headphones, to: "/listen" },
  { label: "Play\nTogether", icon: Gamepad2, to: "/play-and-win" },
  { label: "Go\nTogether", icon: MapPin, to: "/social" },
  { label: "Shop\nTogether", icon: ShoppingBag, to: "/shop" },
];
export function TogetherRow({ t }) {
  const nav = useNavigate();
  return (
    <div data-testid="sf-together" style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 8 }}>
      {TOGETHER.map(({ label, icon: Icon, to }) => (
        <button key={label} onClick={() => nav(to)} className="sf-press"
          style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6, padding: "12px 4px", borderRadius: 14, border: `1px solid ${t.border}`, background: t.card, boxShadow: t.shadow, cursor: "pointer" }}>
          <span style={{ width: 38, height: 38, borderRadius: 11, display: "grid", placeItems: "center", background: t.accentSoft }}><Icon size={18} color={t.accent} /></span>
          <span style={{ fontSize: 11, fontWeight: 800, color: t.text, whiteSpace: "pre-line", textAlign: "center", lineHeight: 1.15 }}>{label}</span>
        </button>
      ))}
    </div>
  );
}

/* ─────────────────────────── Mode tabs ─────────────────────────── */
export function ModeTabs({ t, mode, setMode, onSettings }) {
  const Tab = ({ k, label }) => (
    <button onClick={() => setMode(k)} data-testid={`sf-mode-${k}`} className="sf-press"
      style={{ flex: 1, padding: "10px", borderRadius: 11, border: "none", cursor: "pointer", fontWeight: 800, fontSize: 13.5, background: mode === k ? t.accentSoft : "transparent", color: mode === k ? t.accent : t.text2, borderBottom: mode === k ? `2px solid ${t.accent}` : "2px solid transparent" }}>
      {label}
    </button>
  );
  return (
    <div style={{ display: "flex", gap: 4, background: t.card, border: `1px solid ${t.border}`, borderRadius: 14, padding: 4, boxShadow: t.shadow }}>
      <Tab k="following" label="Following" />
      <Tab k="for_you" label="For You" />
      {onSettings && (
        <button onClick={onSettings} data-testid="sf-feed-settings" title="My Feed Preferences" className="sf-press"
          style={{ flex: "0 0 auto", width: 44, borderRadius: 11, border: "none", cursor: "pointer", background: "transparent", color: t.text2, display: "grid", placeItems: "center" }}>
          <SlidersHorizontal size={18} />
        </button>
      )}
    </div>
  );
}

/* ─────────────────────────── Left sidebar ─────────────────────────── */
const SIDE_MAIN = [
  { label: "Home", icon: Home, to: "/" },
  { label: "Social", icon: Users, to: "/social" },
  { label: "Listen", icon: Headphones, to: "/listen" },
  { label: "Shop", icon: ShoppingBag, to: "/shop" },
  { label: "Play", icon: Gamepad2, to: "/play-and-win" },
  { label: "Dining Club", icon: Utensils, to: "/dining" },
  { label: "Rewards", icon: Gift, to: "/wallet" },
  { label: "Following", icon: Heart, to: "/me/following" },
  { label: "Saved", icon: Bookmark, to: "/me/saved" },
];
const SIDE_MORE = [
  { label: "My AI Radio", icon: Sparkles, to: "/radio" },
  { label: "Live Radio", icon: Radio, to: "/live-radio" },
  { label: "My Playlists", icon: ListMusic, to: "/listen" },
  { label: "Dreams", icon: Moon, to: "/social/dreams" },
  { label: "Tarot", icon: Sparkles, to: "/social/tarot" },
];
export function LeftSidebar({ t }) {
  const { pathname } = useLocation();
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const Item = ({ label, icon: Icon, to }) => {
    const active = to === "/" ? pathname === "/" : pathname.startsWith(to);
    return (
      <Link to={to} data-testid={`sf-side-${label.toLowerCase().replace(/\s+/g, "-")}`}
        style={{ display: "flex", alignItems: "center", gap: 12, padding: "9px 12px", borderRadius: 11, color: active ? t.accent : t.text, background: active ? t.accentSoft : "transparent", fontWeight: active ? 800 : 600, fontSize: 14 }}>
        <Icon size={18} color={active ? t.accent : t.text2} />{label}
      </Link>
    );
  };
  return (
    <aside className="hidden lg:block sf-noscroll" data-testid="sf-leftnav"
      style={{ flex: "0 0 232px", position: "sticky", top: 76, alignSelf: "flex-start", maxHeight: "calc(100vh - 92px)", overflowY: "auto" }}>
      <div style={{ background: t.card, border: `1px solid ${t.border}`, borderRadius: 18, boxShadow: t.shadow, padding: 8 }}>
        <Link to="/profile" style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 10px 12px", borderBottom: `1px solid ${t.border}`, marginBottom: 6 }}>
          <span style={{ width: 42, height: 42, borderRadius: 999, display: "grid", placeItems: "center", color: "#fff", fontWeight: 800, background: t.accentGrad }}>U</span>
          <span><span style={{ display: "block", fontWeight: 800, color: t.text, fontSize: 14 }}>Your Profile</span><span style={{ display: "block", fontSize: 12, color: t.muted }}>View activity</span></span>
        </Link>
        {SIDE_MAIN.map((i) => <Item key={i.label} {...i} />)}
        <div style={{ fontSize: 10, fontWeight: 800, letterSpacing: ".12em", textTransform: "uppercase", color: t.muted, padding: "12px 12px 4px" }}>Explore more</div>
        {SIDE_MORE.map((i) => <Item key={i.label} {...i} />)}
        {isAdmin && (
          <>
            <div style={{ fontSize: 10, fontWeight: 800, letterSpacing: ".12em", textTransform: "uppercase", color: t.muted, padding: "12px 12px 4px" }}>Admin</div>
            <Item label="Admin" icon={Shield} to="/admin" />
          </>
        )}
      </div>
    </aside>
  );
}

/* ─────────────────────────── Right rail ─────────────────────────── */
function RailSection({ t, title, children }) {
  return (
    <div style={{ background: t.card, border: `1px solid ${t.border}`, borderRadius: 18, boxShadow: t.shadow, padding: 12, marginBottom: 14 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <span style={{ fontWeight: 800, fontSize: 14, color: t.text }}>{title}</span>
      </div>
      {children}
    </div>
  );
}
function FollowRow({ t, c, onFollow }) {
  const [done, setDone] = useState(false);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "6px 0" }}>
      {c.image ? <img src={c.image} alt="" loading="lazy" style={{ width: 40, height: 40, borderRadius: 999, objectFit: "cover" }} />
        : <span style={{ width: 40, height: 40, borderRadius: 999, display: "grid", placeItems: "center", color: "#fff", background: t.accentGrad, fontWeight: 800 }}>{initials(c.title)}</span>}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontWeight: 700, fontSize: 13, color: t.text, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{c.title}</div>
        <div style={{ fontSize: 11.5, color: t.muted, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{c.subtitle || c.hint}</div>
      </div>
      <button onClick={() => { setDone(true); onFollow && onFollow(c.follow_id || c.id); }} data-testid="sf-follow"
        className="sf-press" style={{ fontSize: 12, fontWeight: 800, color: done ? t.text2 : t.accent, background: done ? t.chip : t.accentSoft, border: "none", borderRadius: 999, padding: "6px 14px", cursor: "pointer" }}>
        {done ? "Following" : "Follow"}
      </button>
    </div>
  );
}
function MediaRow({ t, c, onClick }) {
  return (
    <button onClick={onClick} className="sf-press" style={{ width: "100%", display: "flex", alignItems: "center", gap: 10, padding: "6px 0", border: "none", background: "transparent", cursor: "pointer", textAlign: "left" }}>
      {c.image ? <img src={c.image} alt="" loading="lazy" style={{ width: 44, height: 44, borderRadius: 12, objectFit: "cover" }} />
        : <span style={{ width: 44, height: 44, borderRadius: 12, background: t.accentSoft, display: "grid", placeItems: "center" }}><Radio size={18} color={t.accent} /></span>}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontWeight: 700, fontSize: 13, color: t.text, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{c.title}</div>
        <div style={{ fontSize: 11.5, color: t.muted, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{c.subtitle}</div>
      </div>
      {c.badge && <span style={{ fontSize: 9.5, fontWeight: 900, color: "#fff", background: c.kind === "live" ? t.live : t.accent, padding: "3px 7px", borderRadius: 999 }}>{c.badge}</span>}
    </button>
  );
}
const HOUSE = [
  { id: "promo-premium", icon: Crown, title: "FUUSIC Premium", subtitle: "Ad-free · 6 skips/hr", cta: "Upgrade", to: "/wallet" },
  { id: "promo-business", icon: Store, title: "FUUSIC for Business", subtitle: "Go Live. Run Offers. Grow.", cta: "Learn More", to: "/shop" },
];
function PromoCard({ t, p, sample }) {
  const nav = useNavigate();
  const Icon = p.icon;
  return (
    <button onClick={() => nav(p.to || "/shop")} className="sf-press" data-testid="sf-promo"
      style={{ width: "100%", display: "flex", alignItems: "center", gap: 10, padding: 10, marginBottom: 8, borderRadius: 14, border: `1px solid ${t.border}`, background: t.cardAlt, cursor: "pointer", textAlign: "left" }}>
      {p.image ? <img src={p.image} alt="" loading="lazy" style={{ width: 40, height: 40, borderRadius: 10, objectFit: "cover" }} />
        : <span style={{ width: 40, height: 40, borderRadius: 10, display: "grid", placeItems: "center", background: t.accentGrad }}>{Icon ? <Icon size={18} color="#fff" /> : <Sparkles size={18} color="#fff" />}</span>}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontWeight: 800, fontSize: 13, color: t.text }}>{p.title}{sample && <span style={{ fontSize: 9, fontWeight: 800, color: t.muted, marginLeft: 6, border: `1px solid ${t.border}`, padding: "1px 5px", borderRadius: 6 }}>SAMPLE</span>}</div>
        <div className="sf-clamp2" style={{ fontSize: 11.5, color: t.muted }}>{p.subtitle}</div>
      </div>
      <span style={{ fontSize: 11.5, fontWeight: 800, color: t.accent, background: t.accentSoft, padding: "6px 12px", borderRadius: 999, whiteSpace: "nowrap" }}>{p.cta || "Open"}</span>
    </button>
  );
}

export function RightRail({ t, rail, onFollow }) {
  const nav = useNavigate();
  const follows = rail.filter((c) => c.kind === "follow").slice(0, 4);
  const lives = rail.filter((c) => ["live", "station", "event"].includes(c.kind)).slice(0, 3);
  const sponsored = rail.filter((c) => c.kind === "sponsored").slice(0, 4);
  return (
    <aside className="hidden lg:block sf-noscroll" data-testid="sf-rightrail"
      style={{ flex: "0 0 300px", position: "sticky", top: 76, alignSelf: "flex-start", maxHeight: "calc(100vh - 92px)", overflowY: "auto" }}>
      {follows.length > 0 && (
        <RailSection t={t} title="Suggested for You">
          {follows.map((c) => <FollowRow key={c.id} t={t} c={c} onFollow={onFollow} />)}
        </RailSection>
      )}
      {lives.length > 0 && (
        <RailSection t={t} title="Trending / Live Now">
          {lives.map((c) => <MediaRow key={c.id} t={t} c={c} onClick={() => nav(c.to || "/listen")} />)}
        </RailSection>
      )}
      <RailSection t={t} title="Sponsored & Discover">
        {HOUSE.map((p) => <PromoCard key={p.id} t={t} p={p} />)}
        {sponsored.map((c) => <PromoCard key={c.id} t={t} p={{ ...c, subtitle: c.subtitle, cta: c.cta, to: c.to, image: c.image }} sample />)}
      </RailSection>
    </aside>
  );
}

/* ───────────────────── Mobile inline discovery ───────────────────── */
export function InlineDiscovery({ t, rail, onFollow }) {
  const nav = useNavigate();
  const follows = rail.filter((c) => c.kind === "follow").slice(0, 3);
  const lives = rail.filter((c) => ["live", "station", "event"].includes(c.kind)).slice(0, 3);
  const sponsored = rail.filter((c) => c.kind === "sponsored").slice(0, 4);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      {follows.length > 0 && (
        <RailSection t={t} title="People You May Know">
          {follows.map((c) => <FollowRow key={c.id} t={t} c={c} onFollow={onFollow} />)}
        </RailSection>
      )}
      {lives.length > 0 && (
        <RailSection t={t} title="Live Now">
          {lives.map((c) => <MediaRow key={c.id} t={t} c={c} onClick={() => nav(c.to || "/listen")} />)}
        </RailSection>
      )}
      <RailSection t={t} title="Sponsored & Discover">
        {HOUSE.map((p) => <PromoCard key={p.id} t={t} p={p} />)}
        {sponsored.map((c) => <PromoCard key={c.id} t={t} p={{ ...c }} sample />)}
      </RailSection>
    </div>
  );
}

/* ─────────────────────────── Audio dock ─────────────────────────── */
export function AudioDock({ t }) {
  const name = usePlayerStore((s) => s.activeChannelName);
  const slug = usePlayerStore((s) => s.activeChannel);
  const seg = usePlayerStore((s) => s.currentSeg);
  const playing = usePlayerStore((s) => s.playing);
  const thumb = usePlayerStore((s) => s.activeChannelThumb);
  const [hidden, setHidden] = useState(false);
  if (!name || hidden) return null;
  const toggle = () => window.dispatchEvent(new CustomEvent("bigfm:player:toggle"));
  const sub = seg?.track_title ? `${seg.track_title}${seg.track_artist ? " · " + seg.track_artist : ""}` : "Live";
  const nowPlayingHref = slug ? `/now-playing?ch=${encodeURIComponent(slug)}` : "/now-playing";
  return (
    <div data-testid="sf-audio-dock" style={{ position: "fixed", left: 0, right: 0, bottom: 62, zIndex: 45, padding: "0 10px" }}>
      <div className="lg:max-w-[640px] lg:mx-auto" style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 10px", borderRadius: 14, background: t.card, border: `1px solid ${t.border}`, boxShadow: "0 -4px 20px rgba(0,0,0,.25)" }}>
        <Link to={nowPlayingHref} data-testid="sf-dock-expand" style={{ display: "flex", alignItems: "center", gap: 10, flex: 1, minWidth: 0, textDecoration: "none", color: "inherit" }}>
          {thumb ? <img src={thumb} alt="" style={{ width: 40, height: 40, borderRadius: 10, objectFit: "cover" }} />
            : <span style={{ width: 40, height: 40, borderRadius: 10, display: "grid", placeItems: "center", background: t.accentGrad }}><Radio size={18} color="#fff" /></span>}
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontWeight: 800, fontSize: 13, color: t.text, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{name}</div>
            <div style={{ fontSize: 11.5, color: t.muted, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{sub}</div>
          </div>
        </Link>
        <button onClick={toggle} data-testid="sf-dock-toggle" className="sf-press" style={{ width: 40, height: 40, borderRadius: 999, border: "none", cursor: "pointer", background: t.accentGrad, display: "grid", placeItems: "center" }}>
          {playing ? <Pause size={18} color="#fff" fill="#fff" /> : <Play size={18} color="#fff" fill="#fff" />}
        </button>
        <button onClick={() => setHidden(true)} aria-label="Close" className="sf-press" style={{ width: 32, height: 32, borderRadius: 999, border: "none", cursor: "pointer", background: "transparent", color: t.text2 }}><X size={18} /></button>
      </div>
    </div>
  );
}

/* ─────────────────────────── Bottom nav (mobile) ─────────────────────────── */
export function BottomNav({ t }) {
  const { pathname } = useLocation();
  return (
    <nav className="lg:hidden" data-testid="sf-bottomnav" style={{ position: "fixed", left: 0, right: 0, bottom: 0, zIndex: 46, display: "flex", background: t.card, borderTop: `1px solid ${t.border}`, paddingBottom: "env(safe-area-inset-bottom)" }}>
      {TOP_NAV.map(({ key, label, icon: Icon, to }) => {
        const active = to === "/" ? pathname === "/" : pathname.startsWith(to);
        return (
          <Link key={key} to={to} data-testid={`sf-bn-${key}`} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 2, padding: "8px 0 10px", color: active ? t.accent : t.text2 }}>
            <Icon size={21} />
            <span style={{ fontSize: 10, fontWeight: active ? 800 : 600 }}>{label}</span>
          </Link>
        );
      })}
    </nav>
  );
}

/* ─────────────────────────── States ─────────────────────────── */
export function FeedSkeleton({ t }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      {[0, 1, 2].map((i) => (
        <div key={i} style={{ background: t.card, border: `1px solid ${t.border}`, borderRadius: 18, padding: 14 }}>
          <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
            <span style={{ width: 40, height: 40, borderRadius: 999, background: t.chip }} />
            <span style={{ flex: 1 }}><span style={{ display: "block", width: "40%", height: 12, borderRadius: 6, background: t.chip, marginBottom: 6 }} /><span style={{ display: "block", width: "25%", height: 10, borderRadius: 6, background: t.chip }} /></span>
          </div>
          <div style={{ height: 160, borderRadius: 12, background: t.chip, marginTop: 12 }} />
        </div>
      ))}
    </div>
  );
}
export function EmptyState({ t, mode, onDiscover }) {
  return (
    <div data-testid="sf-empty" style={{ textAlign: "center", padding: "40px 20px", background: t.card, border: `1px solid ${t.border}`, borderRadius: 18 }}>
      <span style={{ width: 56, height: 56, borderRadius: 999, display: "inline-grid", placeItems: "center", background: t.accentSoft, marginBottom: 12 }}><Users size={26} color={t.accent} /></span>
      <div style={{ fontWeight: 800, fontSize: 16, color: t.text }}>
        {mode === "following" ? "Your Following feed is quiet" : "Nothing to show yet"}
      </div>
      <div style={{ fontSize: 13.5, color: t.muted, margin: "6px 0 16px" }}>
        {mode === "following" ? "Follow people, stations and businesses to see their activity here." : "Check back soon for fresh activity."}
      </div>
      {mode === "following" && (
        <button onClick={onDiscover} className="sf-press" style={{ ...pillStyle(t), width: "auto", display: "inline-flex", alignItems: "center", gap: 6, padding: "10px 22px" }}>
          Discover on For You <ChevronRight size={16} />
        </button>
      )}
    </div>
  );
}
