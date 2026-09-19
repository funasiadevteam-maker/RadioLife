// RadioLife Social V2 — Dreams & Guidance (web).
// Reflection · entertainment · spiritual guidance — never medical/legal/financial
// advice, no result guaranteed. Reuses the shared /api/social/dreams contract.
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import {
  Moon, Sparkles, Users, BookOpen, Loader2, X, Plus, Send,
  Shield, Star, ChevronLeft, Wand2, MessageCircle, Bookmark, Flag,
  BadgeCheck, Stethoscope, Lock, EyeOff, Clock, Users2, Video,
} from "lucide-react";
import { ClubsTab, AiReadingsTab, LiveTab, PayoutsCard } from "./DreamsExtras";
import { Avatar } from "./SocialV2";

const api = axios.create({
  baseURL: `${process.env.REACT_APP_BACKEND_URL || ""}/api/social/dreams`,
  withCredentials: true,
});

const TABS = [
  { key: "dreams", label: "Dreams", icon: Moon },
  { key: "clubs", label: "Clubs", icon: Users2 },
  { key: "aireadings", label: "AI Readings", icon: Wand2 },
  { key: "live", label: "Live", icon: Video },
  { key: "advisors", label: "Advisors", icon: Users },
  { key: "journal", label: "My Journal", icon: BookOpen },
  { key: "readings", label: "My Readings", icon: Star },
];

const MOOD_TONE = {
  Happy: "#fbbf24", Scary: "#f87171", Confusing: "#a78bfa", Peaceful: "#34d399",
  Sad: "#60a5fa", Exciting: "#f472b6", Strange: "#c084fc", Other: "#94a3b8",
};

const BG = "linear-gradient(180deg,#070512 0%,#0d0a24 45%,#0a0818 100%)";

export default function DreamsGuidance() {
  const navigate = useNavigate();
  const [tab, setTab] = useState("dreams");
  const [config, setConfig] = useState(null);
  const [openDream, setOpenDream] = useState(null);
  const [openAdvisor, setOpenAdvisor] = useState(null);
  const [showShare, setShowShare] = useState(false);
  const [loading, setLoading] = useState(true);

  const loadConfig = useCallback(async () => {
    try { const { data } = await api.get("/config"); setConfig(data); }
    catch (_) {} finally { setLoading(false); }
  }, []);
  useEffect(() => { loadConfig(); }, [loadConfig]);

  const acceptConsent = async () => {
    try { await api.post("/consent"); setConfig((c) => ({ ...c, consent_needed: false })); }
    catch (_) { toast.error("Couldn't save consent."); }
  };

  return (
    <div className="min-h-screen text-white" style={{ background: BG }} data-testid="dreams-guidance">
      {/* soft starfield */}
      <div className="pointer-events-none fixed inset-0 opacity-[0.5]"
           style={{ backgroundImage:
             "radial-gradient(1px 1px at 20% 30%,#fff6,transparent),radial-gradient(1px 1px at 70% 60%,#fff4,transparent),radial-gradient(1.5px 1.5px at 40% 80%,#c4b5fd66,transparent),radial-gradient(1px 1px at 85% 20%,#fff5,transparent)" }} />
      <div className="relative max-w-4xl mx-auto px-4 sm:px-6 pt-6 pb-32">
        <button type="button" onClick={() => navigate("/social")} data-testid="dreams-back"
                className="inline-flex items-center gap-1.5 text-sm text-slate-400 hover:text-white mb-3">
          <ChevronLeft size={16} /> Social
        </button>
        <Header />
        <TabBar tab={tab} setTab={setTab} />
        <div className="mt-6">
          {loading && <Center><Loader2 className="animate-spin text-violet-400" /></Center>}
          {!loading && tab === "dreams" && (
            <DreamsTab config={config} onOpen={setOpenDream} onShare={() => setShowShare(true)} />
          )}
          {!loading && tab === "journal" && (
            <JournalTab onOpen={setOpenDream} onShare={() => setShowShare(true)} />
          )}
          {!loading && tab === "clubs" && <ClubsTab />}
          {!loading && tab === "aireadings" && <AiReadingsTab />}
          {!loading && tab === "live" && <LiveTab />}
          {!loading && tab === "advisors" && (
            <><PayoutsCard /><AdvisorsTab config={config} onOpen={setOpenAdvisor} /></>
          )}
          {!loading && tab === "readings" && <ReadingsTab />}
        </div>

        <DisclaimerBar text={config?.disclaimers?.global} />
      </div>

      {showShare && (
        <ShareModal config={config} onClose={() => setShowShare(false)}
                    onDone={() => { setShowShare(false); setTab("journal"); }} />
      )}
      {openDream && (
        <DreamModal dreamId={openDream} config={config} onClose={() => setOpenDream(null)}
                    onOpenAdvisor={(a) => { setOpenDream(null); setOpenAdvisor(a); }} />
      )}
      {openAdvisor && (
        <AdvisorModal advisorId={openAdvisor} config={config} onClose={() => setOpenAdvisor(null)} />
      )}

      {config?.consent_needed && (
        <ConsentGate config={config} onAccept={acceptConsent} onClose={() => navigate("/social")} />
      )}
    </div>
  );
}

function Header() {
  return (
    <div className="flex items-center gap-4">
      <span className="grid place-items-center w-14 h-14 rounded-2xl shrink-0"
            style={{ background: "linear-gradient(135deg,#4c1d95,#7c3aed)" }}>
        <Moon size={26} className="text-white" />
      </span>
      <div>
        <h1 className="text-3xl sm:text-4xl font-black tracking-tight">Dreams & Guidance</h1>
        <p className="text-slate-400 text-sm mt-0.5">Reflection · guidance · exploration — a community, not a fortune-teller</p>
      </div>
    </div>
  );
}

function TabBar({ tab, setTab }) {
  return (
    <div className="mt-6 flex gap-1.5 overflow-x-auto no-scrollbar" data-testid="dreams-tabs">
      {TABS.map((t) => {
        const active = tab === t.key;
        return (
          <button key={t.key} type="button" onClick={() => setTab(t.key)}
                  data-testid={`dreams-tab-${t.key}`}
                  className={`flex-shrink-0 inline-flex items-center gap-2 px-4 h-11 rounded-full text-sm font-bold transition
                    ${active ? "text-white" : "text-slate-400 hover:text-slate-200 bg-white/[0.03]"}`}
                  style={active ? { background: "linear-gradient(135deg,#7c3aed,#c026d3)" } : undefined}>
            <t.icon size={16} /> {t.label}
          </button>
        );
      })}
    </div>
  );
}

// ───────────────────────── Dreams feed ─────────────────────────────
function DreamsTab({ config, onOpen, onShare }) {
  const [items, setItems] = useState([]);
  const [mood, setMood] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get(`/?scope=discover${mood ? `&mood=${encodeURIComponent(mood)}` : ""}`);
      setItems(data.items || []);
    } catch (_) {} finally { setLoading(false); }
  }, [mood]);
  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-5">
      <button type="button" onClick={onShare} data-testid="dreams-share-cta"
              className="w-full text-left rounded-3xl p-5 flex items-center gap-4 border border-white/10"
              style={{ background: "linear-gradient(120deg,#1e1b4b,#4c1d95 70%,#6d28d9)" }}>
        <span className="grid place-items-center w-12 h-12 rounded-2xl shrink-0"
              style={{ background: "linear-gradient(135deg,#a855f7,#ec4899)" }}>
          <Plus size={22} />
        </span>
        <div className="flex-1">
          <div className="text-lg font-black">Share a dream</div>
          <div className="text-sm text-violet-200/80">With your name or anonymously — find people who dreamed something like you.</div>
        </div>
      </button>

      <div className="flex gap-1.5 overflow-x-auto no-scrollbar" data-testid="dreams-mood-filter">
        <Chip active={!mood} onClick={() => setMood(null)}>All moods</Chip>
        {(config?.moods || []).map((m) => (
          <Chip key={m} active={mood === m} tone={MOOD_TONE[m]} onClick={() => setMood(mood === m ? null : m)}>{m}</Chip>
        ))}
      </div>

      {loading ? <Center><Loader2 className="animate-spin text-violet-400" /></Center>
        : items.length === 0 ? <Empty>No dreams here yet — be the first to share one. 🌙</Empty>
        : <div className="grid sm:grid-cols-2 gap-3" data-testid="dreams-feed">
            {items.map((d) => <DreamCard key={d.dream_id} d={d} onOpen={onOpen} />)}
          </div>}
    </div>
  );
}

function DreamCard({ d, onOpen }) {
  return (
    <button type="button" onClick={() => onOpen(d.dream_id)} data-testid={`dream-card-${d.dream_id}`}
            className="text-left rounded-2xl p-4 bg-white/[0.04] border border-white/10 hover:bg-white/[0.07] transition">
      <div className="flex items-center gap-2 mb-2">
        {d.author?.anonymous
          ? <span className="grid place-items-center w-7 h-7 rounded-full bg-violet-500/20 text-violet-300"><EyeOff size={14} /></span>
          : <Avatar name={d.author?.name} url={d.author?.avatar_url} size={28} />}
        <span className="text-xs font-bold text-slate-300 truncate">{d.author?.name}</span>
        {d.mood && <span className="ml-auto text-[10px] font-black uppercase tracking-wider px-2 py-0.5 rounded-full"
                         style={{ background: `${MOOD_TONE[d.mood]}22`, color: MOOD_TONE[d.mood] }}>{d.mood}</span>}
      </div>
      {d.title && <div className="text-base font-black mb-1">{d.title}</div>}
      <div className="text-sm text-slate-300 line-clamp-3">{d.description}</div>
      {d.tags?.length > 0 && (
        <div className="flex gap-1.5 flex-wrap mt-2">
          {d.tags.map((t) => <span key={t} className="text-[10px] px-2 py-0.5 rounded-full bg-white/5 text-slate-400">{t}</span>)}
        </div>
      )}
      <div className="flex items-center gap-3 mt-3 text-[11px] text-slate-400">
        <span className="inline-flex items-center gap-1"><Users size={13} /> {d.similar_count} similar</span>
        <span className="inline-flex items-center gap-1"><MessageCircle size={13} /> {d.comment_count}</span>
        {d.advisor_response_count > 0 && <span className="inline-flex items-center gap-1 text-violet-300"><BadgeCheck size={13} /> {d.advisor_response_count}</span>}
        {d.ai_reflection && <span className="inline-flex items-center gap-1 text-fuchsia-300"><Sparkles size={13} /> AI</span>}
      </div>
    </button>
  );
}

// ───────────────────────── Journal ─────────────────────────────────
function JournalTab({ onOpen, onShare }) {
  const [mine, setMine] = useState([]);
  const [saved, setSaved] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [m, s] = await Promise.all([api.get("/?scope=mine"), api.get("/me/saved")]);
      setMine(m.data.items || []); setSaved(s.data.items || []);
    } catch (_) {} finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  if (loading) return <Center><Loader2 className="animate-spin text-violet-400" /></Center>;
  return (
    <div className="space-y-6" data-testid="dreams-journal">
      <button type="button" onClick={onShare} data-testid="journal-share-cta"
              className="inline-flex items-center gap-2 h-11 px-5 rounded-full text-sm font-bold text-white"
              style={{ background: "linear-gradient(135deg,#7c3aed,#c026d3)" }}>
        <Plus size={16} /> New dream
      </button>
      <div>
        <SectionTitle><Lock size={12} className="inline mr-1" /> Your dreams ({mine.length})</SectionTitle>
        {mine.length === 0 ? <Empty>Your journal is private by default. Record a dream to explore it later.</Empty>
          : <div className="grid sm:grid-cols-2 gap-3">{mine.map((d) => <DreamCard key={d.dream_id} d={d} onOpen={onOpen} />)}</div>}
      </div>
      {saved.length > 0 && (
        <div>
          <SectionTitle><Bookmark size={12} className="inline mr-1" /> Saved</SectionTitle>
          <div className="grid sm:grid-cols-2 gap-3">{saved.map((d) => <DreamCard key={d.dream_id} d={d} onOpen={onOpen} />)}</div>
        </div>
      )}
    </div>
  );
}

// ───────────────────────── Advisors ────────────────────────────────
function AdvisorsTab({ config, onOpen }) {
  const [data, setData] = useState(null);
  const [cat, setCat] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showApply, setShowApply] = useState(false);
  const [me, setMe] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [a, m] = await Promise.all([
        api.get(`/advisors${cat ? `?category=${cat}` : ""}`),
        api.get("/advisors/me"),
      ]);
      setData(a.data); setMe(m.data.advisor);
    } catch (_) {} finally { setLoading(false); }
  }, [cat]);
  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-5" data-testid="dreams-advisors">
      {me ? <MyAdvisorPanel me={me} reload={load} />
        : <button type="button" onClick={() => setShowApply(true)} data-testid="advisor-apply-cta"
                  className="w-full text-left rounded-2xl p-4 border border-white/10 bg-white/[0.04] hover:bg-white/[0.07] flex items-center gap-3">
            <span className="grid place-items-center w-10 h-10 rounded-xl bg-violet-500/20 text-violet-300"><Wand2 size={18} /></span>
            <div><div className="text-sm font-black">Become an advisor</div>
              <div className="text-xs text-slate-400">Offer reflections & private readings — verified & reviewed.</div></div>
          </button>}

      <div className="flex gap-1.5 overflow-x-auto no-scrollbar">
        <Chip active={!cat} onClick={() => setCat(null)}>All</Chip>
        {(config?.advisor_categories || []).map((c) => (
          <Chip key={c.key} active={cat === c.key} onClick={() => setCat(cat === c.key ? null : c.key)}>{c.label}</Chip>
        ))}
      </div>

      {loading ? <Center><Loader2 className="animate-spin text-violet-400" /></Center>
        : (data?.items || []).length === 0 ? <Empty>No advisors in this category yet.</Empty>
        : <div className="grid sm:grid-cols-2 gap-3" data-testid="advisor-list">
            {data.items.map((a) => <AdvisorCard key={a.advisor_id} a={a} onOpen={onOpen} />)}
          </div>}

      {showApply && <ApplyModal config={config} onClose={() => setShowApply(false)} onDone={() => { setShowApply(false); load(); }} />}
    </div>
  );
}

function AdvisorCard({ a, onOpen }) {
  return (
    <button type="button" onClick={() => onOpen(a.advisor_id)} data-testid={`advisor-card-${a.advisor_id}`}
            className="text-left rounded-2xl p-4 bg-white/[0.04] border border-white/10 hover:bg-white/[0.07] transition">
      <div className="flex items-center gap-3">
        <Avatar name={a.display_name} url={a.photo_url} size={44} />
        <div className="min-w-0 flex-1">
          <div className="text-sm font-black truncate">{a.display_name}</div>
          <div className="text-[11px] text-violet-300 truncate">{a.category_label}</div>
        </div>
        <AdvisorBadges a={a} compact />
      </div>
      <div className="text-xs text-slate-400 mt-2 line-clamp-2">{a.bio}</div>
      <div className="flex items-center gap-3 mt-2 text-[11px] text-slate-400">
        <span className="inline-flex items-center gap-1"><Star size={12} className="text-amber-400" /> {a.rating} · {a.review_count}</span>
        {a.languages?.length > 0 && <span>{a.languages.join(", ")}</span>}
      </div>
    </button>
  );
}

function AdvisorBadges({ a, compact }) {
  const b = a.badges || {};
  return (
    <div className="flex gap-1 flex-wrap justify-end">
      {b.professional_license_verified && (
        <span title="Professional License Verified" className="inline-flex items-center gap-1 text-[9px] font-black uppercase px-1.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300">
          <Stethoscope size={10} />{!compact && " Licensed"}</span>)}
      {b.spiritual_approved && (
        <span title="Spiritual Advisor Approved" className="inline-flex items-center gap-1 text-[9px] font-black uppercase px-1.5 py-0.5 rounded-full bg-violet-500/20 text-violet-300">
          <Sparkles size={10} />{!compact && " Spiritual"}</span>)}
      {b.identity_verified && (
        <span title="Identity Verified" className="inline-flex items-center gap-1 text-[9px] font-black uppercase px-1.5 py-0.5 rounded-full bg-cyan-500/20 text-cyan-300">
          <BadgeCheck size={10} />{!compact && " ID"}</span>)}
    </div>
  );
}

function MyAdvisorPanel({ me, reload }) {
  const [inbox, setInbox] = useState([]);
  const [showSvc, setShowSvc] = useState(false);
  const approved = me.status === "approved";

  const loadInbox = useCallback(async () => {
    if (!approved) return;
    try { const { data } = await api.get("/advisor/bookings"); setInbox(data.items || []); } catch (_) {}
  }, [approved]);
  useEffect(() => { loadInbox(); }, [loadInbox]);

  return (
    <div className="rounded-2xl p-4 border border-violet-500/30 bg-violet-500/[0.06]" data-testid="my-advisor-panel">
      <div className="flex items-center gap-3">
        <Avatar name={me.display_name} url={me.photo_url} size={40} />
        <div className="flex-1">
          <div className="text-sm font-black">{me.display_name}</div>
          <div className="text-[11px] text-violet-300">{me.category_label}</div>
        </div>
        <span className={`text-[10px] font-black uppercase px-2 py-1 rounded-full ${
          approved ? "bg-emerald-500/20 text-emerald-300" : "bg-amber-500/20 text-amber-300"}`}>{me.status}</span>
      </div>
      {approved && (
        <>
          <div className="mt-3 flex items-center justify-between">
            <div className="text-xs text-slate-400">{(me.services || []).length} services · {inbox.length} paid requests</div>
            <button type="button" onClick={() => setShowSvc(true)} data-testid="advisor-add-service"
                    className="text-xs font-bold text-violet-300 hover:text-white inline-flex items-center gap-1"><Plus size={13} /> Add service</button>
          </div>
          {inbox.map((b) => <AdvisorInboxRow key={b.booking_id} b={b} reload={loadInbox} />)}
        </>
      )}
      {!approved && <div className="text-xs text-slate-400 mt-2">Your application is being reviewed. You'll be able to add services once approved.</div>}
      {showSvc && <ServiceModal config={{}} onClose={() => setShowSvc(false)} onDone={() => { setShowSvc(false); reload(); }} />}
    </div>
  );
}

function AdvisorInboxRow({ b, reload }) {
  const [resp, setResp] = useState("");
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const deliver = async () => {
    if (resp.trim().length < 2) return;
    setBusy(true);
    try { await api.post(`/advisor/bookings/${b.booking_id}/deliver`, { response_text: resp.trim() });
      toast.success("Reading delivered"); setOpen(false); reload(); }
    catch (_) { toast.error("Couldn't deliver"); } finally { setBusy(false); }
  };
  return (
    <div className="mt-2 rounded-xl p-3 bg-white/[0.04] border border-white/10" data-testid={`advisor-inbox-${b.booking_id}`}>
      <div className="flex items-center justify-between">
        <div className="text-xs font-bold">{b.service_title} · {b.user_name}</div>
        <span className="text-[10px] font-black uppercase px-2 py-0.5 rounded-full bg-white/10 text-slate-300">{b.status}</span>
      </div>
      {b.question && <div className="text-xs text-slate-400 mt-1">“{b.question}”</div>}
      {b.status !== "delivered" ? (
        open ? (
          <div className="mt-2">
            <textarea value={resp} onChange={(e) => setResp(e.target.value)} rows={3} data-testid={`advisor-deliver-input-${b.booking_id}`}
                      placeholder="Write your reflective reading…"
                      className="w-full rounded-xl bg-black/30 border border-white/10 p-2 text-sm outline-none focus:border-violet-400/60" />
            <button type="button" onClick={deliver} disabled={busy} data-testid={`advisor-deliver-btn-${b.booking_id}`}
                    className="mt-2 inline-flex items-center gap-1.5 h-9 px-4 rounded-full text-xs font-bold text-white" style={{ background: "linear-gradient(135deg,#7c3aed,#c026d3)" }}>
              {busy ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />} Deliver
            </button>
          </div>
        ) : <button type="button" onClick={() => setOpen(true)} className="mt-2 text-xs font-bold text-violet-300">Respond →</button>
      ) : <div className="text-[11px] text-emerald-300 mt-1">✓ Delivered</div>}
    </div>
  );
}

// ───────────────────────── My Readings ─────────────────────────────
function ReadingsTab() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => {
    setLoading(true);
    try { const { data } = await api.get("/bookings"); setItems(data.items || []); }
    catch (_) {} finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  if (loading) return <Center><Loader2 className="animate-spin text-violet-400" /></Center>;
  if (items.length === 0) return <Empty data-testid="readings-empty">No readings yet — find an advisor and request a private reading.</Empty>;
  return (
    <div className="space-y-3" data-testid="dreams-readings">
      {items.map((b) => <ReadingRow key={b.booking_id} b={b} reload={load} />)}
    </div>
  );
}

function ReadingRow({ b, reload }) {
  const [busy, setBusy] = useState(false);
  const [rating, setRating] = useState(5);
  const [showReview, setShowReview] = useState(false);
  const checkStatus = async () => {
    setBusy(true);
    try { const { data } = await api.get(`/bookings/${b.booking_id}/status`);
      if (data.payment_status === "paid") { toast.success("Payment confirmed"); reload(); }
      else toast.info("Still pending payment"); }
    catch (_) {} finally { setBusy(false); }
  };
  const submitReview = async () => {
    setBusy(true);
    try { await api.post(`/bookings/${b.booking_id}/review`, { rating }); toast.success("Thanks for your review!"); setShowReview(false); reload(); }
    catch (e) { toast.error(e?.response?.data?.detail?.code || "Couldn't submit"); } finally { setBusy(false); }
  };
  return (
    <div className="rounded-2xl p-4 bg-white/[0.04] border border-white/10" data-testid={`reading-${b.booking_id}`}>
      <div className="flex items-center gap-2">
        <div className="flex-1"><div className="text-sm font-black">{b.service_title}</div>
          <div className="text-[11px] text-violet-300">{b.advisor_name} · {b.advisor_category_label}</div></div>
        <span className="text-[10px] font-black uppercase px-2 py-1 rounded-full bg-white/10 text-slate-300">{b.status}</span>
      </div>
      {b.response?.text && (
        <div className="mt-3 rounded-xl p-3 bg-violet-500/[0.08] border border-violet-500/20 text-sm text-slate-200 whitespace-pre-wrap" data-testid={`reading-response-${b.booking_id}`}>
          {b.response.text}
        </div>
      )}
      <div className="mt-3 flex items-center gap-2">
        {b.payment_status !== "paid" && (
          <button type="button" onClick={checkStatus} disabled={busy} data-testid={`reading-check-${b.booking_id}`}
                  className="text-xs font-bold h-9 px-4 rounded-full bg-white/10 hover:bg-white/20">
            {busy ? <Loader2 size={14} className="animate-spin" /> : "Check payment"}</button>)}
        {b.status === "delivered" && !b.reviewed && !showReview && (
          <button type="button" onClick={() => setShowReview(true)} data-testid={`reading-review-${b.booking_id}`}
                  className="text-xs font-bold h-9 px-4 rounded-full bg-white/10 hover:bg-white/20">Leave a review</button>)}
        {b.reviewed && <span className="text-[11px] text-emerald-300">✓ Reviewed</span>}
      </div>
      {showReview && (
        <div className="mt-3 flex items-center gap-2">
          {[1, 2, 3, 4, 5].map((n) => (
            <button key={n} type="button" onClick={() => setRating(n)} data-testid={`reading-star-${b.booking_id}-${n}`}>
              <Star size={20} className={n <= rating ? "text-amber-400 fill-amber-400" : "text-slate-600"} /></button>))}
          <button type="button" onClick={submitReview} disabled={busy} className="ml-2 text-xs font-bold h-9 px-4 rounded-full text-white" style={{ background: "linear-gradient(135deg,#7c3aed,#c026d3)" }}>Submit</button>
        </div>
      )}
    </div>
  );
}

// ───────────────────────── Dream detail modal ──────────────────────
function DreamModal({ dreamId, config, onClose }) {
  const [d, setD] = useState(null);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [reflecting, setReflecting] = useState(false);

  const load = useCallback(async () => {
    try { const { data } = await api.get(`/${dreamId}`); setD(data); } catch (_) { onClose(); }
  }, [dreamId, onClose]);
  useEffect(() => { load(); }, [load]);

  const act = async (fn, ok) => { try { await fn(); if (ok) toast.success(ok); await load(); } catch (e) { toast.error(e?.response?.data?.detail?.code || "Action failed"); } };
  const reflect = async () => {
    setReflecting(true);
    try { const { data } = await api.post(`/${dreamId}/reflect`); setD((x) => ({ ...x, ai_reflection: data.ai_reflection })); }
    catch (_) { toast.error("Reflection unavailable right now."); } finally { setReflecting(false); }
  };
  const send = async () => {
    if (comment.trim().length < 1) return;
    setBusy(true);
    try { await api.post(`/${dreamId}/comments`, { text: comment.trim() }); setComment(""); await load(); }
    catch (_) { toast.error("Couldn't post"); } finally { setBusy(false); }
  };

  const ref = d?.ai_reflection;
  return (
    <Modal onClose={onClose} testid="dream-modal">
      {!d ? <Center><Loader2 className="animate-spin text-violet-400" /></Center> : (
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            {d.author?.anonymous ? <span className="grid place-items-center w-9 h-9 rounded-full bg-violet-500/20 text-violet-300"><EyeOff size={16} /></span>
              : <Avatar name={d.author?.name} url={d.author?.avatar_url} size={36} />}
            <div className="flex-1"><div className="text-sm font-bold">{d.author?.name}</div>
              {d.mood && <div className="text-[11px]" style={{ color: MOOD_TONE[d.mood] }}>{d.mood}</div>}</div>
          </div>
          {d.title && <h3 className="text-xl font-black">{d.title}</h3>}
          <p className="text-sm text-slate-200 whitespace-pre-wrap">{d.description}</p>
          {d.tags?.length > 0 && <div className="flex gap-1.5 flex-wrap">{d.tags.map((t) => <span key={t} className="text-[10px] px-2 py-0.5 rounded-full bg-white/5 text-slate-400">{t}</span>)}</div>}

          <div className="flex flex-wrap gap-2">
            <ActBtn active={d.my_similar} onClick={() => act(() => api.post(`/${dreamId}/similar`), null)} tid="dream-similar-btn" icon={Users}>{d.my_similar ? "You dreamed this too" : "I had a similar dream"} ({d.similar_count})</ActBtn>
            <ActBtn active={d.saved} onClick={() => act(() => d.saved ? api.delete(`/${dreamId}/save`) : api.post(`/${dreamId}/save`), null)} tid="dream-save-btn" icon={Bookmark}>{d.saved ? "Saved" : "Save"}</ActBtn>
            <ActBtn onClick={() => { const r = prompt("Report this dream — why?"); if (r) act(() => api.post(`/${dreamId}/report`, { reason: r }), "Reported for review"); }} tid="dream-report-btn" icon={Flag}>Report</ActBtn>
          </div>

          {/* AI reflection */}
          <div className="rounded-2xl border border-fuchsia-500/25 bg-fuchsia-500/[0.06] p-4" data-testid="dream-ai-block">
            <div className="flex items-center gap-2 mb-2"><Sparkles size={16} className="text-fuchsia-300" /><span className="text-sm font-black">Explore with AI</span></div>
            {!ref ? (
              <button type="button" onClick={reflect} disabled={reflecting} data-testid="dream-reflect-btn"
                      className="inline-flex items-center gap-2 h-10 px-4 rounded-full text-sm font-bold text-white" style={{ background: "linear-gradient(135deg,#c026d3,#7c3aed)" }}>
                {reflecting ? <Loader2 size={16} className="animate-spin" /> : <Wand2 size={16} />} Reflect on this dream
              </button>
            ) : (
              <div className="space-y-2" data-testid="dream-ai-reflection">
                <div className="text-[11px] italic text-fuchsia-200/90">{ref.header}</div>
                {(ref.symbolic_readings || []).map((s, i) => <p key={i} className="text-sm text-slate-200">• {s}</p>)}
                {ref.questions_to_consider?.length > 0 && (
                  <div className="pt-1"><div className="text-[11px] font-black uppercase text-slate-400">Questions to consider</div>
                    {ref.questions_to_consider.map((q, i) => <p key={i} className="text-sm text-slate-300">— {q}</p>)}</div>)}
                {ref.gentle_note && <p className="text-xs text-slate-400 pt-1">{ref.gentle_note}</p>}
                {ref.safety_note && <p className="text-xs text-amber-300 pt-1 flex items-start gap-1"><Shield size={13} className="mt-0.5 shrink-0" /> {ref.safety_note}</p>}
              </div>
            )}
          </div>

          {/* Comments */}
          <div>
            <SectionTitle>Comments ({d.comment_count})</SectionTitle>
            <div className="space-y-2 max-h-64 overflow-y-auto no-scrollbar" data-testid="dream-comments">
              {(d.comments || []).map((c) => (
                <div key={c.id} className="rounded-xl p-3 bg-white/[0.04] border border-white/10">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold">{c.name}</span>
                    {c.is_advisor && <span className="text-[9px] font-black uppercase px-1.5 py-0.5 rounded-full bg-violet-500/20 text-violet-300 inline-flex items-center gap-1"><BadgeCheck size={10} /> {c.advisor_category_label}</span>}
                  </div>
                  <div className="text-sm text-slate-300 mt-0.5">{c.text}</div>
                </div>
              ))}
              {(d.comments || []).length === 0 && <div className="text-xs text-slate-500">No comments yet — say something supportive.</div>}
            </div>
            <div className="mt-2 flex gap-2">
              <input value={comment} onChange={(e) => setComment(e.target.value)} data-testid="dream-comment-input"
                     placeholder="Add a supportive comment…" onKeyDown={(e) => e.key === "Enter" && send()}
                     className="flex-1 rounded-full bg-white/[0.05] border border-white/10 px-4 py-2.5 text-sm outline-none focus:border-violet-400/60" />
              <button type="button" onClick={send} disabled={busy} data-testid="dream-comment-send"
                      className="grid place-items-center w-11 h-11 rounded-full text-white shrink-0" style={{ background: "linear-gradient(135deg,#7c3aed,#c026d3)" }}>
                {busy ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}</button>
            </div>
          </div>
        </div>
      )}
    </Modal>
  );
}

// ───────────────────────── Advisor detail modal ────────────────────
function AdvisorModal({ advisorId, config, onClose }) {
  const [a, setA] = useState(null);
  const [booking, setBooking] = useState(null);   // selected service
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [accepted, setAccepted] = useState(false);

  const load = useCallback(async () => {
    try { const { data } = await api.get(`/advisors/${advisorId}`); setA(data); } catch (_) { onClose(); }
  }, [advisorId, onClose]);
  useEffect(() => { load(); }, [load]);

  const book = async (svc) => {
    if (!accepted) { toast.info("Please accept the advisor terms first."); return; }
    setBusy(true);
    try {
      const { data } = await api.post("/bookings/checkout", {
        advisor_id: advisorId, service_id: svc.service_id,
        question: question.trim() || undefined, origin_url: window.location.origin,
      });
      if (data.checkout_url) { window.open(data.checkout_url, "_blank"); toast.info("Complete payment in the new tab, then check My Readings."); }
      else toast.success("Booked! See it under My Readings.");
      onClose();
    } catch (e) { toast.error(e?.response?.data?.detail?.code || "Couldn't book"); } finally { setBusy(false); }
  };

  return (
    <Modal onClose={onClose} testid="advisor-modal">
      {!a ? <Center><Loader2 className="animate-spin text-violet-400" /></Center> : (
        <div className="space-y-4">
          <div className="flex items-center gap-3">
            <Avatar name={a.display_name} url={a.photo_url} size={56} />
            <div className="flex-1"><div className="text-lg font-black">{a.display_name}</div>
              <div className="text-xs text-violet-300">{a.category_label}</div>
              <div className="text-[11px] text-slate-400 mt-0.5 inline-flex items-center gap-1"><Star size={12} className="text-amber-400" /> {a.rating} · {a.review_count} reviews</div>
            </div>
          </div>
          <AdvisorBadges a={a} />
          <p className="text-sm text-slate-300">{a.bio}</p>

          <div>
            <SectionTitle>Private readings</SectionTitle>
            {a.disclaimer && (
              <label className="flex items-start gap-2 mb-3 text-xs text-slate-400" data-testid="advisor-terms">
                <input type="checkbox" checked={accepted} onChange={(e) => setAccepted(e.target.checked)} data-testid="advisor-terms-check" className="mt-0.5" />
                <span>{a.disclaimer} <span className="text-slate-500">I understand.</span></span>
              </label>
            )}
            {(a.services || []).length === 0 ? <Empty>This advisor hasn't listed a paid reading yet.</Empty> : (
              <>
                <input value={question} onChange={(e) => setQuestion(e.target.value)} data-testid="advisor-question-input"
                       placeholder="Optional — what would you like them to focus on?"
                       className="w-full rounded-xl bg-white/[0.05] border border-white/10 px-4 py-2.5 text-sm outline-none focus:border-violet-400/60 mb-3" />
                <div className="space-y-2">
                  {a.services.map((s) => (
                    <div key={s.service_id} className="rounded-xl p-3 bg-white/[0.04] border border-white/10 flex items-center gap-3" data-testid={`advisor-service-${s.service_id}`}>
                      <div className="flex-1"><div className="text-sm font-bold">{s.title}</div>
                        <div className="text-[11px] text-slate-400 flex items-center gap-2"><Clock size={11} /> {s.duration_min}m · {s.delivery.replace("_", " ")}{s.delivery_hours ? ` · in ${s.delivery_hours}h` : ""}</div></div>
                      <button type="button" onClick={() => book(s)} disabled={busy} data-testid={`advisor-book-${s.service_id}`}
                              className="text-sm font-black h-10 px-4 rounded-full text-white shrink-0" style={{ background: "linear-gradient(135deg,#7c3aed,#c026d3)" }}>
                        {busy ? <Loader2 size={15} className="animate-spin" /> : (s.price_cents > 0 ? `$${(s.price_cents / 100).toFixed(0)}` : "Free")}</button>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>

          {(a.reviews || []).length > 0 && (
            <div><SectionTitle>Reviews</SectionTitle>
              {a.reviews.map((r, i) => (
                <div key={i} className="rounded-xl p-3 bg-white/[0.04] border border-white/10 mb-2">
                  <div className="flex items-center gap-1"><span className="text-xs font-bold">{r.user_name}</span>
                    <span className="ml-auto inline-flex">{Array.from({ length: r.rating }).map((_, j) => <Star key={j} size={12} className="text-amber-400 fill-amber-400" />)}</span></div>
                  {r.comment && <div className="text-xs text-slate-400 mt-1">{r.comment}</div>}
                </div>))}
            </div>
          )}
        </div>
      )}
    </Modal>
  );
}

// ───────────────────────── Share / apply / service modals ──────────
function ShareModal({ config, onClose, onDone }) {
  const [f, setF] = useState({ title: "", description: "", mood: "", tags: [], visibility: "friends", anonymous: false });
  const [busy, setBusy] = useState(false);
  const toggleTag = (t) => setF((x) => ({ ...x, tags: x.tags.includes(t) ? x.tags.filter((y) => y !== t) : [...x.tags, t].slice(0, 8) }));
  const submit = async () => {
    if (f.description.trim().length < 1) { toast.info("Describe your dream first."); return; }
    setBusy(true);
    try { await api.post("", { ...f, title: f.title.trim() || undefined, mood: f.mood || undefined }); toast.success("Dream shared 🌙"); onDone(); }
    catch (e) { toast.error(e?.response?.data?.detail?.code || "Couldn't share"); } finally { setBusy(false); }
  };
  return (
    <Modal onClose={onClose} testid="share-modal">
      <div className="space-y-4">
        <h3 className="text-xl font-black">Share a dream</h3>
        <input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} data-testid="share-title"
               placeholder="Title (optional)" className="w-full rounded-xl bg-white/[0.05] border border-white/10 px-4 py-2.5 text-sm outline-none focus:border-violet-400/60" />
        <textarea value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} rows={4} data-testid="share-description"
                  placeholder="What happened in your dream?" className="w-full rounded-xl bg-white/[0.05] border border-white/10 px-4 py-2.5 text-sm outline-none focus:border-violet-400/60" />
        <div>
          <div className="text-[11px] font-black uppercase text-slate-400 mb-2">Mood</div>
          <div className="flex gap-1.5 flex-wrap">{(config?.moods || []).map((m) => (
            <Chip key={m} active={f.mood === m} tone={MOOD_TONE[m]} onClick={() => setF({ ...f, mood: f.mood === m ? "" : m })}>{m}</Chip>))}</div>
        </div>
        <div>
          <div className="text-[11px] font-black uppercase text-slate-400 mb-2">Tags</div>
          <div className="flex gap-1.5 flex-wrap">{(config?.tags || []).map((t) => (
            <Chip key={t} active={f.tags.includes(t)} onClick={() => toggleTag(t)}>{t}</Chip>))}</div>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {["only_me", "friends", "public"].map((v) => (
            <Chip key={v} active={f.visibility === v} onClick={() => setF({ ...f, visibility: v })}>
              {v === "only_me" ? "Only me" : v === "friends" ? "Friends" : "Public"}</Chip>))}
        </div>
        <label className="flex items-center gap-2 text-sm text-slate-300" data-testid="share-anon">
          <input type="checkbox" checked={f.anonymous} onChange={(e) => setF({ ...f, anonymous: e.target.checked })} data-testid="share-anon-check" />
          <EyeOff size={15} /> Share anonymously
          <span className="text-[11px] text-slate-500">(hidden from other users)</span>
        </label>
        <button type="button" onClick={submit} disabled={busy} data-testid="share-submit"
                className="w-full h-12 rounded-full font-black text-white" style={{ background: "linear-gradient(135deg,#7c3aed,#c026d3)" }}>
          {busy ? <Loader2 className="animate-spin mx-auto" /> : "Share dream"}</button>
      </div>
    </Modal>
  );
}

function ApplyModal({ config, onClose, onDone }) {
  const [f, setF] = useState({ display_name: "", category: "", bio: "", languages: "", experience_years: "", credentials: "" });
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    if (!f.display_name || !f.category || f.bio.trim().length < 10) { toast.info("Fill name, category and a short bio."); return; }
    setBusy(true);
    try {
      await api.post("/advisors/apply", {
        display_name: f.display_name, category: f.category, bio: f.bio,
        languages: f.languages.split(",").map((s) => s.trim()).filter(Boolean),
        experience_years: f.experience_years ? Number(f.experience_years) : undefined,
        credentials: f.credentials || undefined,
      });
      toast.success("Application submitted — pending review."); onDone();
    } catch (e) { toast.error(e?.response?.data?.detail?.code || "Couldn't apply"); } finally { setBusy(false); }
  };
  return (
    <Modal onClose={onClose} testid="apply-modal">
      <div className="space-y-3">
        <h3 className="text-xl font-black">Become an advisor</h3>
        <input value={f.display_name} onChange={(e) => setF({ ...f, display_name: e.target.value })} data-testid="apply-name" placeholder="Display name" className="w-full rounded-xl bg-white/[0.05] border border-white/10 px-4 py-2.5 text-sm outline-none focus:border-violet-400/60" />
        <select value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })} data-testid="apply-category" className="w-full rounded-xl bg-white/[0.05] border border-white/10 px-4 py-2.5 text-sm outline-none focus:border-violet-400/60">
          <option value="" className="bg-slate-900">Choose a category…</option>
          {(config?.advisor_categories || []).map((c) => <option key={c.key} value={c.key} className="bg-slate-900">{c.label}</option>)}
        </select>
        <textarea value={f.bio} onChange={(e) => setF({ ...f, bio: e.target.value })} rows={3} data-testid="apply-bio" placeholder="Short bio (min 10 chars)" className="w-full rounded-xl bg-white/[0.05] border border-white/10 px-4 py-2.5 text-sm outline-none focus:border-violet-400/60" />
        <input value={f.languages} onChange={(e) => setF({ ...f, languages: e.target.value })} data-testid="apply-languages" placeholder="Languages (comma separated)" className="w-full rounded-xl bg-white/[0.05] border border-white/10 px-4 py-2.5 text-sm outline-none focus:border-violet-400/60" />
        <input value={f.experience_years} onChange={(e) => setF({ ...f, experience_years: e.target.value })} data-testid="apply-experience" placeholder="Years of experience" type="number" className="w-full rounded-xl bg-white/[0.05] border border-white/10 px-4 py-2.5 text-sm outline-none focus:border-violet-400/60" />
        <input value={f.credentials} onChange={(e) => setF({ ...f, credentials: e.target.value })} data-testid="apply-credentials" placeholder="Credentials / license (if licensed professional)" className="w-full rounded-xl bg-white/[0.05] border border-white/10 px-4 py-2.5 text-sm outline-none focus:border-violet-400/60" />
        <p className="text-[11px] text-slate-500">Spiritual and licensed-professional advisors are verified separately. Licensed badges require verified credentials.</p>
        <button type="button" onClick={submit} disabled={busy} data-testid="apply-submit" className="w-full h-12 rounded-full font-black text-white" style={{ background: "linear-gradient(135deg,#7c3aed,#c026d3)" }}>{busy ? <Loader2 className="animate-spin mx-auto" /> : "Submit application"}</button>
      </div>
    </Modal>
  );
}

function ServiceModal({ onClose, onDone }) {
  const [f, setF] = useState({ title: "", delivery: "written", price_cents: "2900", duration_min: "30", delivery_hours: "24", description: "" });
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    if (f.title.trim().length < 2) { toast.info("Give the service a title."); return; }
    setBusy(true);
    try {
      await api.post("/advisors/me/services", {
        title: f.title, delivery: f.delivery, price_cents: Number(f.price_cents) || 0,
        duration_min: Number(f.duration_min) || 30, delivery_hours: Number(f.delivery_hours) || 24,
        description: f.description || undefined,
      });
      toast.success("Service added"); onDone();
    } catch (e) { toast.error(e?.response?.data?.detail?.code || "Couldn't add"); } finally { setBusy(false); }
  };
  return (
    <Modal onClose={onClose} testid="service-modal">
      <div className="space-y-3">
        <h3 className="text-xl font-black">Add a service</h3>
        <input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} data-testid="service-title" placeholder="e.g. 30-min Written Dream Reading" className="w-full rounded-xl bg-white/[0.05] border border-white/10 px-4 py-2.5 text-sm outline-none focus:border-violet-400/60" />
        <select value={f.delivery} onChange={(e) => setF({ ...f, delivery: e.target.value })} data-testid="service-delivery" className="w-full rounded-xl bg-white/[0.05] border border-white/10 px-4 py-2.5 text-sm outline-none focus:border-violet-400/60">
          {["written", "voice", "video_recorded", "live_video", "live_audio"].map((d) => <option key={d} value={d} className="bg-slate-900">{d.replace("_", " ")}</option>)}
        </select>
        <div className="grid grid-cols-3 gap-2">
          <input value={f.price_cents} onChange={(e) => setF({ ...f, price_cents: e.target.value })} data-testid="service-price" placeholder="Price ¢" type="number" className="rounded-xl bg-white/[0.05] border border-white/10 px-3 py-2.5 text-sm outline-none focus:border-violet-400/60" />
          <input value={f.duration_min} onChange={(e) => setF({ ...f, duration_min: e.target.value })} placeholder="Mins" type="number" className="rounded-xl bg-white/[0.05] border border-white/10 px-3 py-2.5 text-sm outline-none focus:border-violet-400/60" />
          <input value={f.delivery_hours} onChange={(e) => setF({ ...f, delivery_hours: e.target.value })} placeholder="Hrs" type="number" className="rounded-xl bg-white/[0.05] border border-white/10 px-3 py-2.5 text-sm outline-none focus:border-violet-400/60" />
        </div>
        <textarea value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} rows={2} data-testid="service-desc" placeholder="Description" className="w-full rounded-xl bg-white/[0.05] border border-white/10 px-4 py-2.5 text-sm outline-none focus:border-violet-400/60" />
        <button type="button" onClick={submit} disabled={busy} data-testid="service-submit" className="w-full h-12 rounded-full font-black text-white" style={{ background: "linear-gradient(135deg,#7c3aed,#c026d3)" }}>{busy ? <Loader2 className="animate-spin mx-auto" /> : "Add service"}</button>
      </div>
    </Modal>
  );
}

// ───────────────────────── Consent gate ────────────────────────────
function ConsentGate({ config, onAccept, onClose }) {
  const [ack, setAck] = useState(false);
  return (
    <div className="fixed inset-0 z-[70] grid place-items-center bg-black/70 backdrop-blur-sm px-4" data-testid="consent-gate">
      <div className="max-w-md w-full rounded-3xl p-6 border border-violet-500/30" style={{ background: "linear-gradient(180deg,#12102b,#0d0a24)" }}>
        <span className="grid place-items-center w-14 h-14 rounded-2xl mb-4" style={{ background: "linear-gradient(135deg,#7c3aed,#c026d3)" }}><Moon size={26} /></span>
        <h3 className="text-2xl font-black">Welcome to Dreams & Guidance</h3>
        <p className="text-sm text-slate-300 mt-3">{config?.disclaimers?.global}</p>
        <label className="flex items-start gap-2 mt-4 text-sm text-slate-300">
          <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} data-testid="consent-check" className="mt-0.5" />
          <span>I understand these AI and spiritual readings are for entertainment and reflection, and are not guaranteed or professional advice.</span>
        </label>
        <div className="flex gap-2 mt-5">
          <button type="button" onClick={onClose} className="flex-1 h-12 rounded-full font-bold bg-white/10 hover:bg-white/20" data-testid="consent-decline">Not now</button>
          <button type="button" onClick={onAccept} disabled={!ack} data-testid="consent-accept"
                  className="flex-1 h-12 rounded-full font-black text-white disabled:opacity-40" style={{ background: "linear-gradient(135deg,#7c3aed,#c026d3)" }}>Enter</button>
        </div>
      </div>
    </div>
  );
}

// ───────────────────────── Shared bits ─────────────────────────────
function Modal({ children, onClose, testid }) {
  return (
    <div className="fixed inset-0 z-[60] flex items-end sm:items-center justify-center bg-black/70 backdrop-blur-sm" onClick={onClose} data-testid={testid}>
      <div className="w-full sm:max-w-lg max-h-[90vh] overflow-y-auto no-scrollbar rounded-t-3xl sm:rounded-3xl p-5 border border-white/10"
           style={{ background: "linear-gradient(180deg,#12102b,#0b0918)" }} onClick={(e) => e.stopPropagation()}>
        <button type="button" onClick={onClose} data-testid="modal-close" className="ml-auto grid place-items-center w-9 h-9 rounded-full bg-white/10 hover:bg-white/20 mb-2"><X size={16} /></button>
        {children}
      </div>
    </div>
  );
}
function Center({ children }) { return <div className="flex justify-center py-16">{children}</div>; }
function Empty({ children, ...p }) { return <div {...p} className="rounded-2xl border border-white/10 bg-white/[0.03] p-6 text-center text-sm text-slate-400">{children}</div>; }
function SectionTitle({ children }) { return <div className="text-xs font-black uppercase tracking-[0.18em] text-slate-400 mb-3">{children}</div>; }
function Chip({ children, active, tone, onClick }) {
  return (
    <button type="button" onClick={onClick}
            className={`flex-shrink-0 px-3.5 h-9 rounded-full text-xs font-bold transition border ${active ? "text-white border-transparent" : "text-slate-300 border-white/10 bg-white/[0.03]"}`}
            style={active ? { background: tone ? `${tone}33` : "linear-gradient(135deg,#7c3aed,#c026d3)", color: tone || "#fff", borderColor: tone ? `${tone}66` : "transparent" } : undefined}>
      {children}
    </button>
  );
}
function ActBtn({ children, onClick, active, icon: Icon, tid }) {
  return (
    <button type="button" onClick={onClick} data-testid={tid}
            className={`inline-flex items-center gap-1.5 h-9 px-3.5 rounded-full text-xs font-bold border ${active ? "bg-violet-500/25 text-violet-200 border-violet-500/40" : "bg-white/[0.05] text-slate-300 border-white/10 hover:bg-white/10"}`}>
      <Icon size={14} /> {children}
    </button>
  );
}
function DisclaimerBar({ text }) {
  if (!text) return null;
  return (
    <div className="mt-10 rounded-2xl border border-white/10 bg-white/[0.02] p-4 flex items-start gap-2" data-testid="dreams-disclaimer">
      <Shield size={15} className="text-slate-500 mt-0.5 shrink-0" />
      <p className="text-[11px] text-slate-500 leading-relaxed">{text}</p>
    </div>
  );
}
