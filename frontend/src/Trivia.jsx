// Phase 16a — Trivia category picker.  Live single-player gameplay
// lives at /trivia/play (see TriviaPlay.jsx).  Phase 16b (multiplayer
// venue lobbies) replaces the mocked venue cards lower on this page.
import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { Brain, ChevronRight, Trophy, Sparkles, Users, Plus } from "lucide-react";
import { Card, Button, Chip, LiveDot } from "@/shell/primitives";
import { API } from "@/AuthContext";

export default function Trivia() {
  const navigate = useNavigate();
  const [cats, setCats]       = useState([]);
  const [market, setMarket]   = useState("");
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [c, h] = await Promise.all([
          axios.get(`${API}/trivia/categories`),
          axios.get(`${API}/trivia/me/history?limit=5`).catch(() => ({ data: { items: [] } })),
        ]);
        if (cancelled) return;
        setCats(c.data?.categories || []);
        setMarket(c.data?.market || "");
        setHistory(h.data?.items || []);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const startCategory = (cat) => {
    // Phase UX.1 — single-click immediate start.  Pass the topic name
    // through router state so the next page can show
    // "Generating your <topic> trivia…" while the AI batch loads.
    navigate(`/trivia/play?cat=${encodeURIComponent(cat.id)}`,
                      { state: { categoryName: cat.name, categoryIcon: cat.icon } });
  };

  return (
    <div data-testid="trivia-root"
            className="grid grid-cols-1 lg:grid-cols-12 gap-6 pb-24">
      <section className="lg:col-span-8 lg:col-start-3 space-y-6">
        <header className="space-y-2">
          <div className="text-[10px] font-mono uppercase tracking-widest
                                text-text-secondary flex items-center gap-2">
            <LiveDot /> Trivia · {market ? market.toUpperCase() : "…"}
          </div>
          <h1 className="font-display font-bold text-4xl sm:text-5xl
                                tracking-display-tight">
            Pick a topic, <span className="text-accent-magenta">play solo</span>
            <span className="text-text-secondary"> or </span>
            <span className="text-accent-electric">with friends.</span>
          </h1>
          <p className="text-text-secondary text-sm max-w-lg">
            10 questions, server-timed, AI-generated for your city.  Earn
            BigPoints on every session.  Host a live room and beat your crew.
          </p>
          <div className="flex flex-wrap gap-3 pt-2">
            <Button variant="primary" onClick={() => navigate("/trivia/rooms/create")}
                        data-testid="trivia-create-room-btn">
              <Plus size={14} /> Host live room
            </Button>
            <Button variant="ghost" onClick={() => navigate("/trivia/join")}
                        data-testid="trivia-join-room-btn">
              <Users size={14} /> Join with code
            </Button>
          </div>
        </header>

        {/* ── Category grid ─────────────────────────────────────────── */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3"
                data-testid="trivia-categories">
          {loading && (
            <Card className="p-5 text-sm text-text-secondary col-span-full">
              Loading categories…
            </Card>
          )}
          {!loading && cats.length === 0 && (
            <Card className="p-5 text-sm text-text-secondary col-span-full">
              No active categories for your market yet.  Check back soon.
            </Card>
          )}
          {cats.map((c) => (
            <Card
              key={c.id}
              hoverable
              className="p-5 cursor-pointer flex items-center gap-4"
              data-testid={`trivia-category-${c.id}`}
              onClick={() => startCategory(c)}
            >
              <div className="w-12 h-12 rounded-token-md grid place-items-center
                                    bg-accent-magenta/15 text-accent-magenta
                                    text-2xl select-none flex-shrink-0">
                {c.icon || <Brain size={22} />}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <h3 className="font-display font-bold text-lg
                                        tracking-display-tight">{c.name}</h3>
                  {c.market !== "global" && (
                    <Chip tone="electric" className="text-[9px]">
                      {c.market?.toUpperCase()}
                    </Chip>
                  )}
                </div>
                {c.tagline && (
                  <div className="text-xs text-text-secondary font-mono mt-1">
                    {c.tagline}
                  </div>
                )}
              </div>
              <ChevronRight size={18} className="text-text-faint" />
            </Card>
          ))}
        </div>

        {/* ── Past sessions ─────────────────────────────────────────── */}
        {history.length > 0 && (
          <section data-testid="trivia-history" className="space-y-2">
            <div className="text-[10px] font-mono uppercase tracking-widest
                                  text-text-secondary">
              Your recent runs
            </div>
            <Card className="p-4 divide-y divide-white/[0.06]">
              {history.map((h) => (
                <div key={h.session_id}
                      className="py-2 flex items-center justify-between
                                          text-sm">
                  <div className="font-mono text-text-secondary">
                    {h.category_slug || "—"} · diff {h.difficulty}
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="font-display font-bold text-accent-electric">
                      {h.final_score}
                    </span>
                    <span className="text-accent-gold font-mono text-xs">
                      +{h.bigcoin_awarded} BigPoints
                    </span>
                  </div>
                </div>
              ))}
            </Card>
          </section>
        )}
      </section>

      <aside className="lg:col-span-2 lg:col-end-13 lg:col-start-9 lg:row-start-1
                              hidden lg:block space-y-4">
        <Card className="p-5">
          <div className="flex items-center gap-2 mb-3">
            <Sparkles size={16} className="text-accent-gold" />
            <span className="font-display font-bold tracking-display-tight">
              How it works
            </span>
          </div>
          <ul className="space-y-2 font-mono text-xs text-text-secondary">
            <li>• 10 questions per session.</li>
            <li>• 30s server-timed window per question.</li>
            <li>• 100 pts correct · +50 if &lt; 3s · +25 if &lt; 6s.</li>
            <li>• Score ÷ 10 = BigPoints reward.</li>
            <li>• No repeats within 90 days.</li>
          </ul>
        </Card>
        <Card className="p-5">
          <div className="flex items-center gap-2 mb-3">
            <Trophy size={16} className="text-accent-gold" />
            <span className="font-display font-bold tracking-display-tight">
              Live rooms
            </span>
          </div>
          <p className="text-xs text-text-secondary mb-3">
            Host a private trivia room.  Share a 10-char code, race
            your friends, climb the live leaderboard.  Top 3 earn
            BigPoints multipliers.
          </p>
          <Button variant="ghost" size="sm"
                      onClick={() => navigate("/trivia/rooms/create")}
                      data-testid="trivia-sidebar-host-btn">
            <Plus size={12} /> Host room
          </Button>
        </Card>
      </aside>
    </div>
  );
}
