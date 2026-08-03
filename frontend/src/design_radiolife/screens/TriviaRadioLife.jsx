/** Phase C — RadioLife (light) variant of the /trivia landing.
 *
 *  Mounted by RadioLifeOverlay when pathname === "/trivia" and
 *  useDesignVariant() === "radiolife".  Renders the same catalog of
 *  categories + Host/Join CTAs the Legacy page shows, but in light
 *  theme and mobile-first stack.
 */
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import axios from "axios";
import { Brain, Users, Plus, ChevronRight, Loader2 } from "lucide-react";
import { API } from "@/AuthContext";

export default function TriviaRadioLife() {
  const navigate = useNavigate();
  const [cats,    setCats]    = useState([]);
  const [qsets,  setQsets]  = useState([]);
  const [loading, setLoading] = useState(true);
  const [busyCat, setBusyCat] = useState(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [c, s] = await Promise.all([
          axios.get(`${API}/trivia/categories`).catch(
            () => ({ data: {} })),
          axios.get(`${API}/trivia/question-sets`).catch(
            () => ({ data: {} })),
        ]);
        if (cancelled) return;
        setCats(c.data?.categories || []);
        setQsets(s.data?.items || []);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const hostRoom = async (cat) => {
    if (busyCat) return;
    setBusyCat(cat.id);
    try {
      const r = await axios.post(`${API}/trivia/rooms`,
        { category_id: cat.id, is_private: false },
        { withCredentials: true });
      navigate(`/trivia/rooms/${r.data.room_code}`);
    } catch (_e) {
      // silent — the create form (Legacy) is a good fallback
    } finally { setBusyCat(null); }
  };

  return (
    <div className="px-4 pt-6 pb-6 space-y-6"
              data-testid="rl-trivia-page">
      <header>
        <div className="text-[10px] uppercase tracking-widest font-mono
                                        text-violet-500 mb-1">Trivia</div>
        <h1 className="text-2xl font-black tracking-tight text-slate-900">
          Play live with friends
        </h1>
        <p className="text-slate-500 text-sm mt-1">
          Pick a topic, host a room, share the code.  10 questions, 15 s
          each.
        </p>
      </header>

      {/* Primary CTAs */}
      <div className="grid grid-cols-2 gap-3">
        <Link to="/trivia/rooms/create"
                    className="rounded-2xl bg-violet-500 text-white p-4
                                              shadow-lg shadow-violet-500/20 flex flex-col
                                              items-start gap-1 hover:bg-violet-400
                                              transition"
                    data-testid="rl-trivia-host-cta">
          <Plus size={22} />
          <div className="font-bold text-sm">Host a room</div>
          <div className="text-[11px] opacity-90">Pick a topic + share</div>
        </Link>
        <Link to="/trivia/join"
                    className="rounded-2xl bg-white text-slate-900 p-4
                                              border border-slate-200 shadow-sm flex
                                              flex-col items-start gap-1 hover:border-violet-500
                                              transition"
                    data-testid="rl-trivia-join-cta">
          <Users size={22} className="text-violet-500" />
          <div className="font-bold text-sm">Join by code</div>
          <div className="text-[11px] text-slate-500">Enter BFM-XXXXXX</div>
        </Link>
      </div>

      {/* Solo practice — categories */}
      <section data-testid="rl-trivia-categories">
        <div className="text-[11px] uppercase tracking-widest font-mono
                                        text-slate-400 mb-2">
          Solo practice
        </div>
        {loading ? (
          <div className="p-8 flex justify-center">
            <Loader2 className="w-5 h-5 animate-spin text-violet-500" />
          </div>
        ) : cats.length === 0 ? (
          <div className="p-6 rounded-xl border border-slate-200
                                          bg-white text-center text-slate-500 text-sm">
            No categories available yet.
          </div>
        ) : (
          <ul className="grid grid-cols-2 gap-3">
            {cats.map((c) => (
              <li key={c.id}
                      data-testid={`rl-trivia-cat-${c.id}`}>
                <button
                  type="button"
                  onClick={() => navigate(
                    `/trivia/play?cat=${encodeURIComponent(c.id)}`,
                    { state: {
                        categoryName: c.name,
                        categoryIcon: c.icon,
                      } })}
                  className="w-full rounded-2xl border border-slate-200
                                                  bg-white p-3 flex items-center gap-3
                                                  hover:border-violet-500 transition
                                                  text-left">
                  <div className="w-10 h-10 rounded-full bg-violet-100
                                                  flex items-center justify-center
                                                  text-xl">
                    {c.icon || <Brain size={18}
                                                          className="text-violet-600" />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-semibold text-slate-900
                                                    truncate">
                      {c.name}
                    </div>
                    {c.tagline && (
                      <div className="text-[11px] text-slate-500 truncate">
                        {c.tagline}
                      </div>
                    )}
                  </div>
                  <ChevronRight size={14} className="text-slate-400" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Pre-baked question sets (Phase C) */}
      {qsets.length > 0 && (
        <section data-testid="rl-trivia-qsets">
          <div className="text-[11px] uppercase tracking-widest font-mono
                                          text-slate-400 mb-2">
            Pre-baked sets
          </div>
          <ul className="space-y-2">
            {qsets.map((s) => (
              <li key={s.id}
                      data-testid={`rl-trivia-qset-${s.id}`}
                      className="rounded-xl border border-slate-200 bg-white
                                              p-3 flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-violet-100
                                                flex items-center justify-center">
                  <Brain size={18} className="text-violet-600" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-semibold text-slate-900
                                                  truncate">
                    {s.title}
                  </div>
                  <div className="text-[11px] text-slate-500">
                    {s.category} · {s.question_count} Qs · {s.difficulty}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
