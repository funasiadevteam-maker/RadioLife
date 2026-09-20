// Dreams & Guidance — Phase 2 web surfaces: Clubs, AI Readings, Live Q&A,
// and the advisor Payouts card. Each talks to its own /api/social/* prefix.
import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import {
  Loader2, Sparkles, Wand2, Moon, Users2, Video, Radio, X, Send,
  Star, Trash2, ChevronLeft, DollarSign, ExternalLink, Plus, Dot,
  Lock, Heart, Users, Bell, Rocket, Layers, ChevronRight, Share2, Check,
  BarChart3, Download, Flame,
} from "lucide-react";

const B = process.env.REACT_APP_BACKEND_URL || "";
const readingsApi = axios.create({ baseURL: `${B}/api/social/readings`, withCredentials: true });
const clubsApi = axios.create({ baseURL: `${B}/api/social/clubs`, withCredentials: true });
const liveApi = axios.create({ baseURL: `${B}/api/social/live`, withCredentials: true });
const payoutsApi = axios.create({ baseURL: `${B}/api/social/payouts`, withCredentials: true });
const adsApi = axios.create({ baseURL: `${B}/api/social/ads`, withCredentials: true });
const socialApi = axios.create({ baseURL: `${B}/api/social`, withCredentials: true });

const card = "rounded-3xl bg-white/[0.03] border border-white/[0.06] p-5";
const grad = { background: "linear-gradient(135deg,#7c3aed,#c026d3)" };
const money = (c) => `$${((c || 0) / 100).toFixed(2)}`;
const Spin = () => <div className="py-16 grid place-items-center"><Loader2 className="animate-spin text-violet-400" /></div>;

function Empty({ icon: Icon, title, sub }) {
  return (
    <div className="py-14 text-center">
      <Icon className="mx-auto text-violet-400/70 mb-3" size={30} />
      <p className="font-bold">{title}</p>
      {sub && <p className="text-sm text-slate-400 mt-1">{sub}</p>}
    </div>
  );
}

// ═══════════════════════════ CLUBS ═════════════════════════════════
export function ClubsTab() {
  const [clubs, setClubs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(null);

  const load = useCallback(async () => {
    try { const { data } = await clubsApi.get(""); setClubs(data.items || []); }
    catch (_) {} finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  if (loading) return <Spin />;
  if (open) return <ClubDetail slug={open} onBack={() => { setOpen(null); load(); }} />;
  return (
    <div className="grid sm:grid-cols-2 gap-3" data-testid="clubs-list">
      {clubs.map((c) => (
        <button key={c.slug} type="button" onClick={() => setOpen(c.slug)}
                data-testid={`club-card-${c.slug}`}
                className={`${card} text-left flex items-center gap-4 hover:border-violet-400/40 transition`}>
          <span className="grid place-items-center w-12 h-12 rounded-2xl shrink-0"
                style={{ background: `${c.color}22`, color: c.color }}>
            <Users2 size={22} />
          </span>
          <div className="min-w-0 flex-1">
            <div className="font-black flex items-center gap-2">
              {c.name}
              {c.is_member && <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-violet-500/20 text-violet-200">Joined</span>}
            </div>
            <div className="text-xs text-slate-400 truncate">{c.description}</div>
            <div className="text-[11px] text-slate-500 mt-1">{c.member_count} members · {c.dream_count} dreams</div>
          </div>
        </button>
      ))}
    </div>
  );
}

function ClubDetail({ slug, onBack }) {
  const [data, setData] = useState(null);
  const [showPost, setShowPost] = useState(false);
  const load = useCallback(async () => {
    try { const { data } = await clubsApi.get(`/${slug}`); setData(data); } catch (_) {}
  }, [slug]);
  useEffect(() => { load(); }, [load]);
  if (!data) return <Spin />;
  const toggle = async () => {
    try {
      await clubsApi.post(`/${slug}/${data.is_member ? "leave" : "join"}`);
      load();
    } catch (_) { toast.error("Try again."); }
  };
  return (
    <div data-testid="club-detail">
      <button type="button" onClick={onBack} className="inline-flex items-center gap-1.5 text-sm text-slate-400 hover:text-white mb-3">
        <ChevronLeft size={16} /> Clubs
      </button>
      <div className={`${card} mb-4`} style={{ borderColor: `${data.color}44` }}>
        <div className="flex items-center gap-4">
          <span className="grid place-items-center w-14 h-14 rounded-2xl shrink-0" style={{ background: `${data.color}22`, color: data.color }}>
            <Users2 size={26} />
          </span>
          <div className="flex-1 min-w-0">
            <h2 className="text-2xl font-black">{data.name}</h2>
            <p className="text-sm text-slate-400">{data.description}</p>
            <p className="text-[11px] text-slate-500 mt-1">{data.member_count} members · {data.dream_count} dreams</p>
          </div>
        </div>
        <div className="flex gap-2 mt-4">
          <button type="button" onClick={toggle} data-testid="club-join-toggle"
                  className={`h-10 px-5 rounded-full text-sm font-bold ${data.is_member ? "bg-white/[0.06] text-slate-200" : "text-white"}`}
                  style={data.is_member ? undefined : grad}>
            {data.is_member ? "Leave club" : "Join club"}
          </button>
          <button type="button" onClick={() => setShowPost(true)} data-testid="club-post-cta"
                  className="h-10 px-5 rounded-full text-sm font-bold text-white flex items-center gap-2" style={grad}>
            <Plus size={16} /> Share a dream here
          </button>
        </div>
      </div>
      {(data.dreams || []).length === 0
        ? <Empty icon={Moon} title="No dreams yet" sub="Be the first to share one in this club." />
        : <div className="space-y-3">
            {data.dreams.map((d) => (
              <div key={d.dream_id} className={card} data-testid={`club-dream-${d.dream_id}`}>
                {d.title && <div className="font-black mb-1">{d.title}</div>}
                <p className="text-sm text-slate-300">{d.description}</p>
                <div className="text-[11px] text-slate-500 mt-2">{d.author?.name} · {d.mood || "Dream"}</div>
              </div>
            ))}
          </div>}
      {showPost && <ClubPostModal slug={slug} onClose={() => setShowPost(false)} onDone={() => { setShowPost(false); load(); }} />}
    </div>
  );
}

function ClubPostModal({ slug, onClose, onDone }) {
  const [desc, setDesc] = useState("");
  const [title, setTitle] = useState("");
  const [anon, setAnon] = useState(false);
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    if (!desc.trim()) return;
    setBusy(true);
    try { const { data } = await clubsApi.post(`/${slug}/dreams`, { title, description: desc, anonymous: anon }); toast.success(data?.points_awarded ? "Shared to club  +1 point" : "Shared to club"); onDone(); }
    catch (_) { toast.error("Couldn't post."); } finally { setBusy(false); }
  };
  return (
    <Modal onClose={onClose} title="Share a dream to this club">
      <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Title (optional)"
             data-testid="club-post-title" className="w-full rounded-xl bg-white/[0.05] border border-white/10 px-3 py-2.5 text-sm mb-2 outline-none" />
      <textarea value={desc} onChange={(e) => setDesc(e.target.value)} rows={5} placeholder="Describe your dream…"
                data-testid="club-post-desc" className="w-full rounded-xl bg-white/[0.05] border border-white/10 px-3 py-2.5 text-sm outline-none" />
      <label className="flex items-center gap-2 mt-3 text-sm text-slate-300">
        <input type="checkbox" checked={anon} onChange={(e) => setAnon(e.target.checked)} data-testid="club-post-anon" /> Share anonymously
      </label>
      <button type="button" onClick={submit} disabled={busy} data-testid="club-post-submit"
              className="mt-4 w-full h-11 rounded-full font-bold text-white" style={grad}>
        {busy ? "Sharing…" : "Share dream"}
      </button>
    </Modal>
  );
}

// ═══════════════════════════ AI READINGS ═══════════════════════════
export function AiReadingsTab() {
  const [kind, setKind] = useState("horoscope");
  const [history, setHistory] = useState([]);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  // inputs
  const [dob, setDob] = useState("");
  const [timeframe, setTimeframe] = useState("today");
  const [question, setQuestion] = useState("");
  const [spread, setSpread] = useState("three");
  const [name, setName] = useState("");

  const loadHistory = useCallback(async () => {
    try { const { data } = await readingsApi.get(""); setHistory(data.items || []); } catch (_) {}
  }, []);
  useEffect(() => { loadHistory(); }, [loadHistory]);

  const run = async () => {
    setBusy(true); setResult(null);
    try {
      let data;
      if (kind === "horoscope") { if (!dob) { toast.error("Add your birth date."); setBusy(false); return; } ({ data } = await readingsApi.post("/horoscope", { dob, timeframe })); }
      else if (kind === "tarot") { ({ data } = await readingsApi.post("/tarot", { question, spread })); }
      else { if (!dob) { toast.error("Add your birth date."); setBusy(false); return; } ({ data } = await readingsApi.post("/numerology", { full_name: name, dob })); }
      setResult(data); loadHistory();
      window.dispatchEvent(new Event("dreams-streak-refresh"));
    } catch (_) { toast.error("Couldn't generate a reading."); } finally { setBusy(false); }
  };

  const KINDS = [
    { key: "horoscope", label: "Horoscope", icon: Sparkles },
    { key: "tarot", label: "Tarot", icon: Wand2 },
    { key: "numerology", label: "Numerology", icon: Star },
    { key: "compat", label: "Match", icon: Heart },
  ];
  return (
    <div data-testid="ai-readings">
      <DailyCard />
      <div className="rounded-2xl bg-amber-400/10 border border-amber-400/20 px-4 py-2.5 text-[11px] text-amber-200/90 mb-4">
        ✦ AI-GENERATED · for entertainment &amp; reflection only — not advice, not a guaranteed prediction.
      </div>
      <div className="flex gap-1.5 mb-4">
        {KINDS.map((k) => (
          <button key={k.key} type="button" onClick={() => { setKind(k.key); setResult(null); }}
                  data-testid={`reading-kind-${k.key}`}
                  className={`flex-1 inline-flex items-center justify-center gap-1.5 h-11 rounded-full text-sm font-bold ${kind === k.key ? "text-white" : "bg-white/[0.03] text-slate-400"}`}
                  style={kind === k.key ? grad : undefined}>
            <k.icon size={16} /> {k.label}
          </button>
        ))}
      </div>

      {kind === "compat" ? <CompatibilityPanel /> : (<>
      <div className={`${card} mb-4`}>
        {kind === "horoscope" && (
          <div className="space-y-3">
            <Field label="Your birth date"><input type="date" value={dob} onChange={(e) => setDob(e.target.value)} data-testid="horo-dob" className="w-full rounded-xl bg-white/[0.05] border border-white/10 px-3 py-2.5 text-sm outline-none [color-scheme:dark]" /></Field>
            <div className="flex gap-2">
              {["today", "week", "month"].map((t) => (
                <button key={t} type="button" onClick={() => setTimeframe(t)} data-testid={`horo-tf-${t}`}
                        className={`flex-1 h-10 rounded-full text-sm font-bold ${timeframe === t ? "text-white" : "bg-white/[0.05] text-slate-400"}`}
                        style={timeframe === t ? grad : undefined}>{t[0].toUpperCase() + t.slice(1)}</button>
              ))}
            </div>
          </div>
        )}
        {kind === "tarot" && (
          <div className="space-y-3">
            <Field label="Your question (optional)"><input value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="What should I focus on?" data-testid="tarot-q" className="w-full rounded-xl bg-white/[0.05] border border-white/10 px-3 py-2.5 text-sm outline-none" /></Field>
            <div className="flex gap-2">
              {[["one", "1 card"], ["three", "3 cards"]].map(([k, l]) => (
                <button key={k} type="button" onClick={() => setSpread(k)} data-testid={`tarot-spread-${k}`}
                        className={`flex-1 h-10 rounded-full text-sm font-bold ${spread === k ? "text-white" : "bg-white/[0.05] text-slate-400"}`}
                        style={spread === k ? grad : undefined}>{l}</button>
              ))}
            </div>
          </div>
        )}
        {kind === "numerology" && (
          <div className="space-y-3">
            <Field label="Full name (optional)"><input value={name} onChange={(e) => setName(e.target.value)} placeholder="Your full name" data-testid="num-name" className="w-full rounded-xl bg-white/[0.05] border border-white/10 px-3 py-2.5 text-sm outline-none" /></Field>
            <Field label="Your birth date"><input type="date" value={dob} onChange={(e) => setDob(e.target.value)} data-testid="num-dob" className="w-full rounded-xl bg-white/[0.05] border border-white/10 px-3 py-2.5 text-sm outline-none [color-scheme:dark]" /></Field>
          </div>
        )}
        <button type="button" onClick={run} disabled={busy} data-testid="reading-generate"
                className="mt-4 w-full h-11 rounded-full font-bold text-white flex items-center justify-center gap-2" style={grad}>
          {busy ? <Loader2 className="animate-spin" size={18} /> : <Sparkles size={18} />} {busy ? "Reading the signs…" : "Generate reading"}
        </button>
      </div>

      {result && <ReadingResult r={result} />}

      {history.length > 0 && (
        <div className="mt-6">
          <div className="text-xs font-bold text-slate-400 mb-2 uppercase tracking-wide">Your readings</div>
          <div className="space-y-2">
            {history.map((r) => (
              <button key={r.reading_id} type="button" onClick={() => setResult(r)} data-testid={`reading-hist-${r.reading_id}`}
                      className="w-full text-left rounded-2xl bg-white/[0.03] border border-white/[0.06] px-4 py-3 flex items-center gap-3 hover:border-violet-400/30">
                <span className="text-violet-300"><Star size={15} /></span>
                <span className="flex-1 min-w-0"><span className="font-bold text-sm block truncate">{r.title}</span><span className="text-[11px] text-slate-500 capitalize">{r.type}</span></span>
              </button>
            ))}
          </div>
        </div>
      )}
      </>)}
    </div>
  );
}

function ReadingResult({ r }) {
  const res = r.result || {};
  return (
    <div className={card} data-testid="reading-result">
      <div className="text-[10px] font-bold text-amber-300/80 uppercase tracking-wider mb-1">{r.label}</div>
      <h3 className="text-xl font-black">{res.headline || r.title}</h3>
      {r.cards && (
        <div className="flex gap-2 my-3 flex-wrap">
          {r.cards.map((c, i) => (
            <span key={i} className="rounded-xl bg-violet-500/10 border border-violet-400/20 px-3 py-2 text-xs" data-testid={`tarot-card-${i}`}>
              <span className="text-violet-200 font-bold">{c.name}</span>
              <span className="text-slate-400"> · {c.orientation} · {c.position}</span>
            </span>
          ))}
        </div>
      )}
      {res.life_path !== undefined && (
        <div className="my-2 text-sm text-violet-200 font-bold">Life Path {res.life_path} — {res.life_path_meaning}</div>
      )}
      <p className="text-sm text-slate-300 mt-2 leading-relaxed">{res.summary}</p>
      {Array.isArray(res.themes) && res.themes.length > 0 && (
        <div className="flex gap-2 flex-wrap mt-3">
          {res.themes.map((t, i) => <span key={i} className="text-[11px] px-2.5 py-1 rounded-full bg-white/[0.05] text-slate-300">{t}</span>)}
        </div>
      )}
      {Array.isArray(res.guidance) && (
        <ul className="mt-3 space-y-1.5">
          {res.guidance.map((g, i) => <li key={i} className="text-sm text-slate-300 flex gap-2"><Dot className="text-violet-400 shrink-0" /> {g}</li>)}
        </ul>
      )}
      {res.affirmation && (
        <div className="mt-4 rounded-2xl bg-violet-500/10 border border-violet-400/20 px-4 py-3 text-sm italic text-violet-100">“{res.affirmation}”</div>
      )}
      <p className="text-[11px] text-slate-500 mt-3">{r.disclaimer}</p>
    </div>
  );
}

// ─────────────────────────── Daily + Reminders ─────────────────────
function DailyCard() {
  const [d, setD] = useState(null);
  const [rem, setRem] = useState({ enabled: false, hour: 9 });
  const [open, setOpen] = useState(false);
  const [detail, setDetail] = useState(null);
  const [dl, setDl] = useState(false);
  useEffect(() => {
    readingsApi.get("/daily").then(({ data }) => setD(data)).catch(() => {});
    readingsApi.get("/reminders").then(({ data }) => setRem(data)).catch(() => {});
  }, []);
  const toggle = async () => {
    const next = {
      enabled: !rem.enabled, hour: rem.hour,
      utc_offset_minutes: -new Date().getTimezoneOffset(),
      tz: Intl.DateTimeFormat().resolvedOptions().timeZone,
    };
    setRem(next);
    try { await readingsApi.put("/reminders", next); toast.success(next.enabled ? "Daily nudge on — at your local hour" : "Reminders off"); } catch (_) {}
  };
  const openDetail = async () => {
    setOpen(true);
    if (!detail) {
      setDl(true);
      try { const { data } = await readingsApi.post("/daily/detail"); setDetail(data.detail); } catch (_) {} finally { setDl(false); }
    }
  };
  if (!d) return null;
  return (
    <div className="rounded-3xl p-5 mb-4 border border-violet-500/25" style={{ background: "linear-gradient(135deg,#1e1b4b,#4c1d95)" }} data-testid="daily-card">
      <div className="flex items-center gap-2 mb-2">
        <Sparkles size={16} className="text-amber-300" />
        <span className="font-black">Today’s reading</span>
        <button type="button" onClick={toggle} data-testid="daily-reminder-toggle"
                className={`ml-auto inline-flex items-center gap-1.5 text-[11px] font-bold px-3 h-8 rounded-full ${rem.enabled ? "bg-emerald-500/20 text-emerald-200" : "bg-white/[0.06] text-slate-300"}`}>
          <Bell size={13} /> {rem.enabled ? "Nudge on" : "Remind me"}
        </button>
      </div>
      <div className="text-lg font-black text-white">{d.basic?.headline}</div>
      <p className="text-sm text-violet-100/90 mt-1">{d.basic?.summary}</p>
      <div className="mt-3 flex items-center gap-2 flex-wrap">
        <span className="text-[11px] px-2.5 py-1 rounded-full bg-white/[0.08] text-violet-100" data-testid="daily-card-name">
          🃏 {d.card?.name} · {d.card?.orientation}
        </span>
        {d.sign && <span className="text-[11px] px-2.5 py-1 rounded-full bg-white/[0.08] text-violet-100">{d.sign}</span>}
      </div>
      {d.detail_locked ? (
        <button type="button" onClick={() => setOpen(true)} data-testid="daily-unlock"
                className="mt-3 w-full h-11 rounded-full font-bold text-white inline-flex items-center justify-center gap-2 bg-white/[0.08] border border-amber-400/30">
          <Lock size={15} className="text-amber-300" /> Unlock full daily tarot — Premium
        </button>
      ) : (
        <button type="button" onClick={openDetail} data-testid="daily-detail"
                className="mt-3 w-full h-11 rounded-full font-bold text-white inline-flex items-center justify-center gap-2" style={grad}>
          Read your full daily tarot <ChevronRight size={16} />
        </button>
      )}
      {open && (
        <Modal onClose={() => setOpen(false)} title="Your daily tarot">
          {d.detail_locked ? (
            <div className="text-center py-4" data-testid="daily-premium-gate">
              <Lock className="mx-auto text-amber-300 mb-2" size={26} />
              <p className="font-bold">Premium daily tarot</p>
              <p className="text-sm text-slate-400 mt-1">{d.upgrade}</p>
              <div className="mt-3 rounded-2xl bg-white/[0.04] px-4 py-3 text-sm text-slate-300">
                Free today: <b>{d.card?.name}</b> ({d.card?.orientation}). Premium unlocks the full interpretation, themes &amp; guidance every day.
              </div>
            </div>
          ) : dl ? <Spin /> : <ReadingResult r={{ ...d, title: "Daily tarot", result: detail, label: d.label, disclaimer: d.disclaimer, cards: [{ name: d.card?.name, orientation: d.card?.orientation, position: "Today" }] }} />}
        </Modal>
      )}
    </div>
  );
}

// ─────────────────────────── Compatibility ─────────────────────────
function CompatibilityPanel() {
  const [cands, setCands] = useState([]);
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState(null);
  const [lastUid, setLastUid] = useState(null);
  const [sharing, setSharing] = useState(false);
  const [shared, setShared] = useState(null);
  useEffect(() => { socialApi.get("/compatibility/candidates").then(({ data }) => setCands(data.items || [])).catch(() => {}); }, []);
  const run = async (uid) => {
    setBusy(true); setRes(null); setShared(null); setLastUid(uid);
    try { const { data } = await socialApi.post("/compatibility", { target_user_id: uid }); setRes(data); }
    catch (_) { toast.error("Couldn't compute a match."); } finally { setBusy(false); }
  };
  const share = async () => {
    if (!lastUid) return;
    setSharing(true);
    try {
      const { data } = await socialApi.post("/compatibility/share", { target_user_id: lastUid });
      setShared(data);
      window.dispatchEvent(new Event("dreams-streak-refresh"));
      const url = `${B}${data.share_path || data.path}`;
      if (navigator.share) { try { await navigator.share({ title: "Our dream match", text: `Our dream match: ${res?.score}% ✨`, url }); } catch (_) {} }
      else { await navigator.clipboard.writeText(url); }
      toast.success(data?.points_awarded ? "Match card shared 💫  +1 point" : "Share link copied 💫");
    } catch (_) { toast.error("Couldn't create a share link."); } finally { setSharing(false); }
  };
  const download = async () => {
    if (!shared?.image_url) return;
    try {
      const r = await fetch(shared.image_url); const b = await r.blob();
      const u = URL.createObjectURL(b); const a = document.createElement("a");
      a.href = u; a.download = `dream-match-${shared.card_id}.png`;
      document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(u);
    } catch (_) { toast.error("Couldn't download the image."); }
  };
  return (
    <div data-testid="compat-panel">
      <div className={`${card} mb-4`}>
        <div className="flex items-center gap-2 mb-1"><Heart size={16} className="text-rose-300" /><span className="font-black">Dream compatibility</span></div>
        <p className="text-[11px] text-slate-400 mb-3">A playful match from your shared dream themes &amp; star signs — just for fun.</p>
        {cands.length === 0 ? (
          <Empty icon={Users} title="Add a friend first" sub="Match works with people on your friends list." />
        ) : (
          <div className="space-y-2">
            {cands.map((c) => (
              <button key={c.user_id} type="button" onClick={() => run(c.user_id)} disabled={busy} data-testid={`compat-friend-${c.user_id}`}
                      className="w-full flex items-center gap-3 rounded-2xl bg-white/[0.04] border border-white/[0.06] px-4 py-3 hover:border-rose-400/30">
                <span className="w-9 h-9 rounded-full bg-violet-500/20 grid place-items-center text-sm font-black text-violet-200">{(c.name || "?")[0]}</span>
                <span className="flex-1 text-left font-bold text-sm">{c.name}</span>
                <Heart size={16} className="text-rose-300" />
              </button>
            ))}
          </div>
        )}
      </div>
      {busy && <Spin />}
      {res && (
        <div className="rounded-3xl p-5 text-center border border-rose-400/25" style={{ background: "linear-gradient(135deg,#4c1d95,#be185d)" }} data-testid="compat-result">
          {shared?.image_url && (
            <img src={shared.image_url} alt="Dream match card" data-testid="compat-card-art"
                 className="w-full rounded-2xl border border-white/15 mb-4" style={{ aspectRatio: "1200 / 630", objectFit: "cover" }} />
          )}
          <div className="text-[10px] font-bold text-amber-200/90 uppercase tracking-wider">{res.label}</div>
          <div className="text-5xl font-black text-white my-1">{res.score}%</div>
          <div className="text-lg font-black text-white">{res.headline}</div>
          <p className="text-sm text-rose-100/90 mt-2">{res.blurb}</p>
          {res.shared_themes?.length > 0 && (
            <div className="flex gap-2 flex-wrap justify-center mt-3">
              {res.shared_themes.map((t, i) => <span key={i} className="text-[11px] px-2.5 py-1 rounded-full bg-white/[0.12] text-white">{t}</span>)}
            </div>
          )}
          <p className="text-[11px] text-rose-100/70 mt-3">{res.shared_note}</p>
          <div className="flex gap-2 mt-4">
            <button type="button" onClick={share} disabled={sharing} data-testid="compat-share"
                    className="flex-1 h-11 rounded-full font-bold text-white inline-flex items-center justify-center gap-2 bg-white/[0.14]">
              {sharing ? <Loader2 size={16} className="animate-spin" /> : <Share2 size={16} />} Share match card
            </button>
            {shared?.image_url && (
              <button type="button" onClick={download} data-testid="compat-download"
                      className="h-11 px-5 rounded-full font-bold text-white inline-flex items-center justify-center gap-2 bg-white/[0.14]">
                <Download size={16} />
              </button>
            )}
          </div>
          <p className="text-[10px] text-rose-100/60 mt-2">{res.disclaimer}</p>
        </div>
      )}
    </div>
  );
}

// ─────────────────────────── Streak badge (🔥) ─────────────────────
export function StreakBadge() {
  const [s, setS] = useState(null);
  const load = useCallback(() => {
    socialApi.get("/dreams/streak").then(({ data }) => setS(data)).catch(() => {});
  }, []);
  useEffect(() => {
    load();
    const on = () => load();
    window.addEventListener("dreams-streak-refresh", on);
    return () => window.removeEventListener("dreams-streak-refresh", on);
  }, [load]);
  if (!s) return null;
  const active = s.current > 0;
  return (
    <div data-testid="streak-badge"
         title={active ? `${s.current}-day streak · best ${s.longest}` : "Share or read daily to start a streak"}
         className={`inline-flex items-center gap-1.5 h-9 px-3 rounded-full text-sm font-black border ${active ? "border-amber-400/40 text-amber-200 bg-amber-400/10" : "border-white/10 text-slate-400 bg-white/[0.03]"}`}>
      <Flame size={15} className={active ? "text-amber-300 fill-amber-400/40" : "text-slate-500"} />
      {s.current}
    </div>
  );
}

// ─────────────────────────── Dream Clusters ────────────────────────
export function ClustersStrip() {
  const [clusters, setClusters] = useState([]);
  const [theme, setTheme] = useState(null);
  useEffect(() => { socialApi.get("/clusters").then(({ data }) => setClusters(data.clusters || [])).catch(() => {}); }, []);
  if (clusters.length === 0) return null;
  return (
    <div className="mb-4" data-testid="clusters-strip">
      <div className="flex items-center gap-2 mb-2"><Layers size={15} className="text-violet-300" /><span className="text-xs font-bold text-slate-300 uppercase tracking-wide">Dream clusters · people who dreamed the same</span></div>
      <div className="flex gap-2 overflow-x-auto pb-1 -mx-1 px-1" style={{ scrollbarWidth: "none" }}>
        {clusters.map((c) => (
          <button key={c.theme} type="button" onClick={() => setTheme(c)} data-testid={`cluster-chip-${c.theme}`}
                  className="shrink-0 rounded-2xl bg-white/[0.04] border border-white/[0.06] px-4 py-2.5 text-left hover:border-violet-400/40">
            <div className="font-bold text-sm whitespace-nowrap">{c.label}</div>
            <div className="text-[11px] text-violet-300">{c.count} dreamed this</div>
          </button>
        ))}
      </div>
      {theme && <ClusterModal cluster={theme} onClose={() => setTheme(null)} />}
    </div>
  );
}

function ClusterModal({ cluster, onClose }) {
  const [items, setItems] = useState(null);
  const [following, setFollowing] = useState(!!cluster.following);
  useEffect(() => { socialApi.get(`/clusters/${cluster.theme}`).then(({ data }) => setItems(data.items || [])).catch(() => setItems([])); }, [cluster.theme]);
  const toggleFollow = async () => {
    const next = !following; setFollowing(next);
    try {
      if (next) await socialApi.post(`/clusters/${cluster.theme}/follow`);
      else await socialApi.delete(`/clusters/${cluster.theme}/follow`);
      toast.success(next ? "Following — we'll alert you on new dreams" : "Unfollowed");
    } catch (_) { setFollowing(!next); }
  };
  return (
    <Modal onClose={onClose} title={`${cluster.label} · ${cluster.count} dreams`}>
      <button type="button" onClick={toggleFollow} data-testid="cluster-follow"
              className={`w-full h-10 rounded-full text-sm font-bold inline-flex items-center justify-center gap-2 mb-3 ${following ? "bg-emerald-500/20 text-emerald-200" : "text-white"}`}
              style={following ? undefined : { background: "linear-gradient(135deg,#7c3aed,#c026d3)" }}>
        {following ? <><Check size={16} /> Following</> : <><Bell size={16} /> Follow this cluster</>}
      </button>
      <div className="max-h-[55vh] overflow-y-auto space-y-2" data-testid="cluster-modal">
        {items === null ? <Spin /> : items.length === 0 ? <Empty icon={Moon} title="No dreams yet" /> : items.map((d) => (
          <div key={d.dream_id} className="rounded-2xl bg-white/[0.03] border border-white/[0.06] px-4 py-3" data-testid={`cluster-dream-${d.dream_id}`}>
            <div className="text-sm font-bold">{d.title || "Untitled dream"}</div>
            <div className="text-xs text-slate-400 mt-0.5 line-clamp-2">{d.description}</div>
            <div className="text-[11px] text-violet-300 mt-1">{d.author?.name || "Anonymous Dreamer"} · {d.similar_count} similar</div>
          </div>
        ))}
      </div>
    </Modal>
  );
}

// ═══════════════════════════ LIVE Q&A ══════════════════════════════
export function LiveTab() {
  const [status, setStatus] = useState("live");
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(null);
  const [showHost, setShowHost] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try { const { data } = await liveApi.get(`/sessions?status=${status}`); setItems(data.items || []); }
    catch (_) {} finally { setLoading(false); }
  }, [status]);
  useEffect(() => { load(); }, [load]);

  if (open) return <LiveRoom sessionId={open} onBack={() => { setOpen(null); load(); }} />;
  return (
    <div data-testid="live-tab">
      <div className="flex items-center justify-between mb-4">
        <div className="flex gap-1.5">
          {[["live", "Live now"], ["upcoming", "Upcoming"], ["past", "Past"]].map(([k, l]) => (
            <button key={k} type="button" onClick={() => setStatus(k)} data-testid={`live-filter-${k}`}
                    className={`h-9 px-4 rounded-full text-xs font-bold ${status === k ? "text-white" : "bg-white/[0.05] text-slate-400"}`}
                    style={status === k ? grad : undefined}>{l}</button>
          ))}
        </div>
        <button type="button" onClick={() => setShowHost(true)} data-testid="live-host-cta"
                className="h-9 px-4 rounded-full text-xs font-bold text-white flex items-center gap-1.5" style={grad}>
          <Video size={15} /> Host
        </button>
      </div>
      {loading ? <Spin /> : items.length === 0 ? (
        <Empty icon={Radio} title={status === "live" ? "No live sessions right now" : "Nothing here yet"}
               sub="Verified advisors can host live dream Q&A sessions." />
      ) : (
        <div className="space-y-3">
          {items.map((s) => (
            <button key={s.session_id} type="button" onClick={() => setOpen(s.session_id)} data-testid={`live-card-${s.session_id}`}
                    className={`${card} w-full text-left flex items-center gap-4 hover:border-violet-400/40`}>
              <span className="grid place-items-center w-12 h-12 rounded-2xl shrink-0" style={grad}>
                {s.mode === "video" ? <Video size={22} className="text-white" /> : <Radio size={22} className="text-white" />}
              </span>
              <div className="flex-1 min-w-0">
                <div className="font-black truncate flex items-center gap-2">
                  {s.status === "live" && <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-rose-500/20 text-rose-300 animate-pulse">● LIVE</span>}
                  {s.featured && <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-400/20 text-amber-200" data-testid={`live-featured-${s.session_id}`}>★ Featured</span>}
                  {s.title}
                </div>
                <div className="text-xs text-slate-400 truncate">{s.advisor_name} · {s.advisor_category_label}</div>
                <div className="text-[11px] text-slate-500 mt-0.5">{s.viewer_count} watching · {s.question_count} questions</div>
              </div>
            </button>
          ))}
        </div>
      )}
      {showHost && <HostModal onClose={() => setShowHost(false)} onDone={(id) => { setShowHost(false); setStatus("live"); setOpen(id); }} />}
    </div>
  );
}

function HostModal({ onClose, onDone }) {
  const [title, setTitle] = useState("");
  const [desc, setDesc] = useState("");
  const [mode, setMode] = useState("audio");
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    if (!title.trim()) return;
    setBusy(true);
    try { const { data } = await liveApi.post("/sessions", { title, description: desc, mode }); toast.success("You're live!"); onDone(data.session_id); }
    catch (e) { toast.error(e?.response?.status === 403 ? "Only verified advisors can host." : "Couldn't start."); }
    finally { setBusy(false); }
  };
  return (
    <Modal onClose={onClose} title="Host a live dream Q&A">
      <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Session title" data-testid="host-title"
             className="w-full rounded-xl bg-white/[0.05] border border-white/10 px-3 py-2.5 text-sm mb-2 outline-none" />
      <textarea value={desc} onChange={(e) => setDesc(e.target.value)} rows={3} placeholder="What's this session about?" data-testid="host-desc"
                className="w-full rounded-xl bg-white/[0.05] border border-white/10 px-3 py-2.5 text-sm mb-3 outline-none" />
      <div className="flex gap-2 mb-3">
        {[["audio", "Audio", Radio], ["video", "Video", Video]].map(([k, l, I]) => (
          <button key={k} type="button" onClick={() => setMode(k)} data-testid={`host-mode-${k}`}
                  className={`flex-1 h-10 rounded-full text-sm font-bold inline-flex items-center justify-center gap-2 ${mode === k ? "text-white" : "bg-white/[0.05] text-slate-400"}`}
                  style={mode === k ? grad : undefined}><I size={15} /> {l}</button>
        ))}
      </div>
      <p className="text-[11px] text-slate-500 mb-3">Full live audio/video plays in the FUUSIC mobile app. The question queue works everywhere.</p>
      <button type="button" onClick={submit} disabled={busy} data-testid="host-submit"
              className="w-full h-11 rounded-full font-bold text-white" style={grad}>{busy ? "Starting…" : "Go live"}</button>
    </Modal>
  );
}

function LiveRoom({ sessionId, onBack }) {
  const [s, setS] = useState(null);
  const [q, setQ] = useState("");
  const load = useCallback(async () => {
    try { const { data } = await liveApi.get(`/sessions/${sessionId}`); setS(data); } catch (_) {}
  }, [sessionId]);
  useEffect(() => { load(); const t = setInterval(load, 5000); return () => clearInterval(t); }, [load]);
  if (!s) return <Spin />;
  const ask = async () => {
    if (!q.trim()) return;
    try { await liveApi.post(`/sessions/${sessionId}/questions`, { text: q }); setQ(""); load(); }
    catch (_) { toast.error("Couldn't send."); }
  };
  const answer = async (qid) => { try { await liveApi.post(`/questions/${qid}/answer`); load(); } catch (_) {} };
  const end = async () => { try { await liveApi.post(`/sessions/${sessionId}/end`); toast.success("Session ended"); onBack(); } catch (_) {} };
  return (
    <div data-testid="live-room">
      <button type="button" onClick={onBack} className="inline-flex items-center gap-1.5 text-sm text-slate-400 hover:text-white mb-3"><ChevronLeft size={16} /> Live</button>
      <div className={`${card} mb-4`}>
        <div className="flex items-center gap-3">
          <span className="grid place-items-center w-12 h-12 rounded-2xl shrink-0" style={grad}>{s.mode === "video" ? <Video size={22} className="text-white" /> : <Radio size={22} className="text-white" />}</span>
          <div className="flex-1 min-w-0">
            <div className="font-black flex items-center gap-2">
              {s.status === "live" && <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-rose-500/20 text-rose-300">● LIVE</span>}
              {s.title}
            </div>
            <div className="text-xs text-slate-400">{s.advisor_name} · {s.advisor_category_label}</div>
          </div>
        </div>
        <div className="mt-3 rounded-2xl bg-violet-500/10 border border-violet-400/20 px-4 py-3 text-sm text-violet-100">
          {s.status !== "live" ? "This session has ended." : s.join_token
            ? `🎧 You're connected to the ${s.mode} room. Full ${s.mode} plays in the FUUSIC app; ask questions below.`
            : "Ask your questions below — the advisor answers live."}
        </div>
        {s.is_host && s.status === "live" && (
          <button type="button" onClick={end} data-testid="live-end" className="mt-3 h-10 px-5 rounded-full text-sm font-bold bg-rose-500/20 text-rose-200">End session</button>
        )}
      </div>

      <div className="text-xs font-bold text-slate-400 mb-2 uppercase tracking-wide">Questions ({s.questions?.length || 0})</div>
      {s.status === "live" && (
        <div className="flex gap-2 mb-4">
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask about your dream…" data-testid="live-question-input"
                 className="flex-1 rounded-full bg-white/[0.05] border border-white/10 px-4 py-2.5 text-sm outline-none" />
          <button type="button" onClick={ask} data-testid="live-question-send" className="w-11 h-11 rounded-full grid place-items-center text-white" style={grad}><Send size={17} /></button>
        </div>
      )}
      <div className="space-y-2">
        {(s.questions || []).map((qq) => (
          <div key={qq.id} className="rounded-2xl bg-white/[0.03] border border-white/[0.06] px-4 py-3" data-testid={`live-q-${qq.id}`}>
            <div className="flex items-start gap-2">
              <span className="flex-1 text-sm text-slate-200"><span className="font-bold text-violet-200">{qq.name}</span> · {qq.text}</span>
              {qq.answered ? <span className="text-[10px] font-bold text-emerald-300 shrink-0">Answered</span>
                : s.is_host && <button type="button" onClick={() => answer(qq.id)} data-testid={`live-answer-${qq.id}`} className="text-[11px] font-bold text-violet-300 shrink-0">Mark answered</button>}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ═══════════════════════ ADVISOR PAYOUTS ═══════════════════════════
export function PayoutsCard() {
  const [data, setData] = useState(undefined);   // undefined=loading, null=not advisor
  const load = useCallback(async () => {
    try { const { data } = await payoutsApi.get("/status"); setData(data); }
    catch (_) { setData(null); }
  }, []);
  useEffect(() => { load(); }, [load]);
  if (data === undefined || data === null) return null;
  const onboarded = data.payouts_enabled;
  const start = async () => {
    try { const { data: r } = await payoutsApi.post("/onboarding/start", { origin_url: window.location.origin }); window.open(r.onboarding_url, "_blank"); }
    catch (_) { toast.error("Couldn't start onboarding."); }
  };
  const refresh = async () => { try { await payoutsApi.post("/status/refresh"); load(); toast.success("Refreshed"); } catch (_) { toast.error("Try again."); } };
  const e = data.earnings || {};
  return (
    <div className={`${card} mb-4`} data-testid="advisor-payouts">
      <div className="flex items-center gap-2 mb-3"><DollarSign size={18} className="text-emerald-300" /><span className="font-black">Earnings &amp; payouts</span>
        <span className="ml-auto text-[11px] text-slate-500">Platform fee {data.commission_pct}%</span></div>
      <div className="grid grid-cols-3 gap-2 mb-3">
        <Stat label="Paid out" value={money(e.paid_cents)} />
        <Stat label="Pending" value={money(e.pending_cents)} />
        <Stat label="On hold" value={money(e.held_cents)} />
      </div>
      {onboarded ? (
        <div className="flex items-center gap-2 text-sm text-emerald-300 font-bold"><span>✓ Payouts enabled</span>
          <button type="button" onClick={refresh} className="ml-auto text-xs text-slate-400 underline">Refresh</button></div>
      ) : (
        <div>
          <p className="text-xs text-slate-400 mb-2">Connect a payout account (Stripe, test mode in preview) to receive your share of paid readings.</p>
          <div className="flex gap-2">
            <button type="button" onClick={start} data-testid="payouts-onboard" className="h-10 px-4 rounded-full text-sm font-bold text-white flex items-center gap-2" style={grad}><ExternalLink size={15} /> Set up payouts</button>
            <button type="button" onClick={refresh} data-testid="payouts-refresh" className="h-10 px-4 rounded-full text-sm font-bold bg-white/[0.06] text-slate-200">I've finished</button>
          </div>
        </div>
      )}
      <GetFeatured />
    </div>
  );
}

function GetFeatured() {
  const [cfg, setCfg] = useState(null);
  const [surface, setSurface] = useState("both");
  const [an, setAn] = useState(null);
  const load = useCallback(async () => {
    try { const { data } = await adsApi.get("/config"); setCfg(data); } catch (_) {}
    try { const { data } = await adsApi.get("/analytics"); setAn(data); } catch (_) {}
  }, []);
  useEffect(() => { load(); }, [load]);
  if (!cfg || !cfg.is_advisor) return null;
  const active = cfg.active_promotion;
  const buy = async (tier) => {
    try {
      const { data } = await adsApi.post("/checkout", { tier, surface, origin_url: window.location.origin });
      window.open(data.checkout_url, "_blank");
      toast.success("Complete checkout, then refresh.");
    } catch (e) { toast.error(e?.response?.status === 403 ? "Advisors only." : "Couldn't start checkout."); }
  };
  return (
    <div className="mt-4 pt-4 border-t border-white/[0.06]" data-testid="get-featured">
      <div className="flex items-center gap-2 mb-1"><Rocket size={16} className="text-amber-300" /><span className="font-black">Get featured</span>
        <button type="button" onClick={load} className="ml-auto text-xs text-slate-400 underline">Refresh</button></div>
      {an && an.totals && (an.totals.views > 0 || an.totals.bookings > 0 || (an.promotions || []).length > 0) && (
        <div className="rounded-2xl bg-white/[0.04] border border-white/[0.06] p-3 mb-3" data-testid="ad-analytics">
          <div className="flex items-center gap-1.5 mb-2"><BarChart3 size={13} className="text-violet-300" /><span className="text-[11px] font-bold text-slate-300 uppercase tracking-wide">Promotion impact</span></div>
          <div className="grid grid-cols-3 gap-2">
            <Stat label="Profile views" value={an.totals.views} />
            <Stat label="Bookings" value={an.totals.bookings} />
            <Stat label="Revenue" value={money(an.totals.revenue_cents)} />
          </div>
        </div>
      )}
      {active ? (
        <div className="rounded-2xl bg-amber-400/10 border border-amber-400/25 px-4 py-3 text-sm text-amber-100" data-testid="featured-active">
          ★ Featured on {active.surface_label} until {new Date(active.ends_at).toLocaleDateString()}.
        </div>
      ) : (<>
        <p className="text-[11px] text-slate-400 mb-2">Pin yourself to the top with a Featured badge. Doesn’t affect reviews or fairness.</p>
        <div className="flex gap-2 mb-2">
          {cfg.surfaces.map((s) => (
            <button key={s.key} type="button" onClick={() => setSurface(s.key)} data-testid={`feature-surface-${s.key}`}
                    className={`flex-1 h-9 rounded-full text-[11px] font-bold ${surface === s.key ? "text-white" : "bg-white/[0.05] text-slate-400"}`}
                    style={surface === s.key ? grad : undefined}>{s.label}</button>
          ))}
        </div>
        <div className="grid grid-cols-3 gap-2">
          {cfg.tiers.map((t) => (
            <button key={t.key} type="button" onClick={() => buy(t.key)} data-testid={`feature-tier-${t.key}`}
                    className="rounded-2xl bg-white/[0.04] border border-white/[0.06] px-2 py-3 text-center hover:border-amber-400/40">
              <div className="text-sm font-black">{money(t.price_cents)}</div>
              <div className="text-[10px] text-slate-500">{t.label}</div>
            </button>
          ))}
        </div>
      </>)}
    </div>
  );
}

function Stat({ label, value }) {
  return <div className="rounded-2xl bg-white/[0.04] px-3 py-2.5 text-center"><div className="text-lg font-black">{value}</div><div className="text-[10px] text-slate-500 uppercase tracking-wide">{label}</div></div>;
}

// ───────────────────────── shared bits ─────────────────────────────
function Field({ label, children }) {
  return <label className="block"><span className="text-[11px] text-slate-400 block mb-1">{label}</span>{children}</label>;
}

function Modal({ title, children, onClose }) {
  return (
    <div className="fixed inset-0 z-50 grid place-items-end sm:place-items-center bg-black/70 p-0 sm:p-4" onClick={onClose}>
      <div className="w-full sm:max-w-md bg-[#0d0a24] border border-white/10 rounded-t-3xl sm:rounded-3xl p-5" onClick={(e) => e.stopPropagation()} data-testid="dreams-modal">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-black text-lg">{title}</h3>
          <button type="button" onClick={onClose} className="w-9 h-9 grid place-items-center rounded-full bg-white/[0.06]"><X size={18} /></button>
        </div>
        {children}
      </div>
    </div>
  );
}


// ─────────────────────────── Alerts bell ───────────────────────────
export function AlertsBell() {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState({ items: [], unread: 0 });
  const load = useCallback(async () => {
    try { const { data } = await socialApi.get("/alerts"); setData(data); } catch (_) {}
  }, []);
  useEffect(() => { load(); const t = setInterval(load, 60000); return () => clearInterval(t); }, [load]);
  const openList = async () => {
    setOpen(true);
    try { await socialApi.post("/alerts/read", {}); setData((d) => ({ ...d, unread: 0 })); } catch (_) {}
  };
  return (
    <>
      <button type="button" onClick={openList} data-testid="alerts-bell"
              className="relative w-10 h-10 rounded-full grid place-items-center bg-white/[0.06] hover:bg-white/[0.1]">
        <Bell size={18} />
        {data.unread > 0 && (
          <span data-testid="alerts-badge" className="absolute -top-0.5 -right-0.5 min-w-[20px] h-5 px-1 rounded-full bg-rose-500 text-[10px] font-black grid place-items-center">{data.unread}</span>
        )}
      </button>
      {open && (
        <Modal onClose={() => setOpen(false)} title="Cluster alerts">
          <div className="max-h-[60vh] overflow-y-auto space-y-2" data-testid="alerts-list">
            {data.items.length === 0 ? (
              <Empty icon={Bell} title="No alerts yet" sub="Follow a dream cluster to get pinged when a new dream lands in it." />
            ) : data.items.map((a) => (
              <div key={a.id} data-testid={`alert-${a.id}`}
                   className={`rounded-2xl px-4 py-3 border ${a.read ? "bg-white/[0.02] border-white/[0.05]" : "bg-violet-500/10 border-violet-400/25"}`}>
                <div className="text-sm font-bold">{a.title}</div>
                <div className="text-[11px] text-violet-300 mt-0.5">New in {a.theme_label}</div>
              </div>
            ))}
          </div>
        </Modal>
      )}
    </>
  );
}
