// Dreams & Guidance — Phase 2 web surfaces: Clubs, AI Readings, Live Q&A,
// and the advisor Payouts card. Each talks to its own /api/social/* prefix.
import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import {
  Loader2, Sparkles, Wand2, Moon, Users2, Video, Radio, X, Send,
  Star, Trash2, ChevronLeft, DollarSign, ExternalLink, Plus, Dot,
} from "lucide-react";

const B = process.env.REACT_APP_BACKEND_URL || "";
const readingsApi = axios.create({ baseURL: `${B}/api/social/readings`, withCredentials: true });
const clubsApi = axios.create({ baseURL: `${B}/api/social/clubs`, withCredentials: true });
const liveApi = axios.create({ baseURL: `${B}/api/social/live`, withCredentials: true });
const payoutsApi = axios.create({ baseURL: `${B}/api/social/payouts`, withCredentials: true });

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
    try { await clubsApi.post(`/${slug}/dreams`, { title, description: desc, anonymous: anon }); toast.success("Shared to club"); onDone(); }
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
    } catch (_) { toast.error("Couldn't generate a reading."); } finally { setBusy(false); }
  };

  const KINDS = [
    { key: "horoscope", label: "Horoscope", icon: Sparkles },
    { key: "tarot", label: "Tarot", icon: Wand2 },
    { key: "numerology", label: "Numerology", icon: Star },
  ];
  return (
    <div data-testid="ai-readings">
      <div className="rounded-2xl bg-amber-400/10 border border-amber-400/20 px-4 py-2.5 text-[11px] text-amber-200/90 mb-4">
        ✦ AI-GENERATED · for entertainment &amp; reflection only — not advice, not a guaranteed prediction.
      </div>
      <div className="flex gap-1.5 mb-4">
        {KINDS.map((k) => (
          <button key={k.key} type="button" onClick={() => { setKind(k.key); setResult(null); }}
                  data-testid={`reading-kind-${k.key}`}
                  className={`flex-1 inline-flex items-center justify-center gap-2 h-11 rounded-full text-sm font-bold ${kind === k.key ? "text-white" : "bg-white/[0.03] text-slate-400"}`}
                  style={kind === k.key ? grad : undefined}>
            <k.icon size={16} /> {k.label}
          </button>
        ))}
      </div>

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
      <p className="text-[11px] text-slate-500 mb-3">Full live audio/video plays in the RadioLife mobile app. The question queue works everywhere.</p>
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
            ? `🎧 You're connected to the ${s.mode} room. Full ${s.mode} plays in the RadioLife app; ask questions below.`
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
