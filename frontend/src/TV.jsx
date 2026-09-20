/**
 * Phase 16c — TV Display surface at `/tv`.
 *
 * Token-paired (no user auth). Renders three modes:
 *   1. No token  → Pairing prompt (6-digit input).
 *   2. Paired, no live room → Venue welcome (QR + room-discovery copy).
 *   3. Paired, live room  → Question / reveal / leaderboard / done.
 *
 * Optimized for 1080p (1920×1080) — chrome reads at viewing distance.
 */
import React, { useEffect, useState } from "react";
import { useTVDisplay } from "@/store/useTVDisplay";

const FRONTEND_BASE = (typeof window !== "undefined" ? window.location.origin : "");

// ─── Helper: lightweight QR code SVG (no extra dep) ──────────────────
// We embed the trivia-join URL into a Google-hosted QR by URL.  In a
// future iteration we'll switch to the `qrcode.react` library; the URL
// approach is sufficient for the TV at typical viewing distance and
// avoids a 25 KB bundle delta for the POC.
function QRBlock({ text, size = 360 }) {
  const src = `https://api.qrserver.com/v1/create-qr-code/?size=${size}x${size}&data=${encodeURIComponent(text)}&qzone=1&color=000000&bgcolor=FFFFFF`;
  return (
    <div className="bg-white p-4 rounded-2xl"
            style={{ width: size + 32, height: size + 32 }}
            data-testid="tv-qr">
      <img src={src} alt="QR code" width={size} height={size} />
    </div>
  );
}

// ─── Pairing prompt ──────────────────────────────────────────────────
function PairingPrompt() {
  const claim         = useTVDisplay((s) => s.claim);
  const claiming     = useTVDisplay((s) => s.claiming);
  const pairingError = useTVDisplay((s) => s.pairingError);
  const [code, setCode] = useState("");

  const onSubmit = (e) => {
    e.preventDefault();
    if (claiming) return;
    claim(code);
  };
  return (
    <div className="min-h-screen bg-bg-base flex items-center justify-center px-12"
          data-testid="tv-pairing">
      <div className="max-w-3xl w-full text-center space-y-10">
        <div className="text-accent-magenta uppercase tracking-[0.4em] text-sm font-mono">
          FUUSIC · TV mode
        </div>
        <h1 className="font-display font-bold text-[clamp(48px,9vw,128px)] tracking-display-tight leading-[0.95]">
          Pair this <span className="text-accent-electric">TV.</span>
        </h1>
        <p className="text-text-secondary text-2xl">
          Ask the staff to generate a code from <span className="font-mono text-text-primary">/venue/tvs</span>.
        </p>
        <form onSubmit={onSubmit} className="space-y-6">
          <input
            type="text"
            inputMode="numeric"
            autoFocus
            placeholder="000-000"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            className="w-full max-w-xl mx-auto block px-8 py-8 rounded-2xl
                              bg-bg-glass border-4 border-white/20
                              font-mono tracking-[0.4em] text-6xl text-center
                              outline-none focus:border-accent-electric"
            data-testid="tv-pairing-input"
          />
          <button
            type="submit"
            disabled={claiming}
            className="px-10 py-5 rounded-full bg-accent-electric text-bg-base
                              font-display font-bold text-2xl tracking-tight
                              disabled:opacity-50 hover:scale-105 transition-transform"
            data-testid="tv-pairing-submit">
            {claiming ? "Pairing…" : "Pair"}
          </button>
          {pairingError && (
            <div className="text-accent-magenta text-xl font-mono"
                  data-testid="tv-pairing-error">
              {pairingError}
            </div>
          )}
        </form>
      </div>
    </div>
  );
}

// ─── Welcome screen (paired, no live room) ───────────────────────────
function VenueWelcome({ venue }) {
  const joinUrl = `${FRONTEND_BASE}/trivia`;
  return (
    <div className="min-h-screen bg-bg-base flex items-center justify-center px-16"
          data-testid="tv-welcome">
      <div className="grid grid-cols-[1.4fr_1fr] gap-16 w-full max-w-7xl">
        <div className="space-y-8 self-center">
          <div className="text-accent-magenta uppercase tracking-[0.4em] font-mono">
            Welcome to
          </div>
          <h1 className="font-display font-bold leading-[0.92] tracking-display-tight"
                style={{ fontSize: "clamp(64px,10vw,168px)" }}>
            {venue?.name || "FUUSIC Venue"}
          </h1>
          <p className="text-text-secondary text-3xl max-w-2xl leading-snug">
            Live trivia, every hour.  Win drinks, food, and on-house perks
            from your favourite spot.
          </p>
          <div className="pt-4 flex items-center gap-6">
            <div className="h-3 w-32 rounded-full bg-accent-electric" />
            <span className="font-mono text-text-secondary text-lg uppercase tracking-widest">
              {venue?.market || "dubai"} · powered by FUUSIC
            </span>
          </div>
        </div>
        <div className="self-center justify-self-end flex flex-col items-center gap-6"
              data-testid="tv-welcome-qr-block">
          <QRBlock text={joinUrl} size={360} />
          <div className="text-center space-y-2">
            <div className="font-display font-bold text-3xl">
              Scan to join
            </div>
            <div className="font-mono text-text-secondary text-xl">
              or visit <span className="text-text-primary">{FRONTEND_BASE.replace(/^https?:\/\//, "")}/trivia/join</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Live room view ──────────────────────────────────────────────────
function LiveRoom({ room, venue }) {
  const phase         = useTVDisplay((s) => s.phase);
  const question     = useTVDisplay((s) => s.question);
  const reveal        = useTVDisplay((s) => s.reveal);
  const leaderboard = useTVDisplay((s) => s.leaderboard);
  const finalScores = useTVDisplay((s) => s.finalScores);
  const deadlineMs  = useTVDisplay((s) => s.deadlineMs);

  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 100);
    return () => clearInterval(t);
  }, []);

  const remainingMs = deadlineMs ? Math.max(0, deadlineMs - now) : 0;
  const phaseTotalMs = phase === "question" ? 15000 : (phase === "reveal" ? 4000 : 5000);
  const pct = deadlineMs ? Math.max(0, Math.min(100, (remainingMs / phaseTotalMs) * 100)) : 0;

  const top5 = (leaderboard || []).slice(0, 5);

  return (
    <div className="min-h-screen bg-bg-base relative px-12 py-8 grid grid-cols-[1.6fr_1fr] gap-12"
          data-testid="tv-live">
      {/* Top-left venue logo */}
      <div className="absolute top-8 left-12 flex items-center gap-4">
        <div className="h-3 w-3 rounded-full bg-accent-electric animate-pulse" />
        <span className="font-display font-bold text-2xl tracking-display-tight">
          {venue?.name}
        </span>
      </div>
      {/* Bottom-right room code */}
      <div className="absolute bottom-8 right-12 font-mono text-text-secondary text-lg"
            data-testid="tv-live-roomcode">
        Late?  Join with code <span className="text-accent-electric text-2xl ml-2">{room?.code}</span>
      </div>

      {/* Question pane */}
      <div className="flex flex-col justify-center space-y-10">
        {phase === "question" && question && (
          <>
            <div className="text-accent-magenta uppercase tracking-[0.4em] font-mono text-base"
                  data-testid="tv-q-num">
              Question {(room?.current_index ?? 0) + 1} of {room?.total_questions || 10}
            </div>
            <h1 className="font-display font-bold leading-[1.0] tracking-display-tight"
                  style={{ fontSize: "clamp(48px,5.5vw,96px)" }}
                  data-testid="tv-q-prompt">
              {question.prompt}
            </h1>
            <div className="grid grid-cols-2 gap-6 pt-4">
              {(question.choices || []).map((c, idx) => (
                <div key={c.id}
                      data-testid={`tv-q-choice-${c.id}`}
                      className="px-8 py-6 rounded-2xl bg-bg-glass border border-white/[0.08]
                                        flex items-center gap-6">
                  <div className="h-12 w-12 rounded-full bg-accent-electric/20 text-accent-electric
                                          flex items-center justify-center font-display font-bold text-2xl">
                    {String.fromCharCode(65 + idx)}
                  </div>
                  <div className="font-display font-bold text-3xl">{c.text}</div>
                </div>
              ))}
            </div>
          </>
        )}
        {phase === "reveal" && reveal && (
          <div className="space-y-10" data-testid="tv-reveal">
            <div className="text-accent-electric uppercase tracking-[0.4em] font-mono text-base">
              Reveal
            </div>
            <div className="font-display font-bold text-7xl tracking-display-tight">
              Correct: <span className="text-accent-electric">
                {(question?.choices || []).find((c) => c.id === reveal.correct_choice_id)?.text || "—"}
              </span>
            </div>
            <div className="text-text-secondary text-2xl">
              {reveal.fastest_user_name
                ? <>Fastest: <span className="text-text-primary">{reveal.fastest_user_name}</span></>
                : "Next question loading…"}
            </div>
          </div>
        )}
        {phase === "leaderboard" && (
          <div className="space-y-8" data-testid="tv-mid-leaderboard">
            <div className="text-accent-magenta uppercase tracking-[0.4em] font-mono text-base">
              Standings
            </div>
            <h2 className="font-display font-bold text-7xl">Next question in…</h2>
          </div>
        )}
        {phase === "done" && (
          <div className="space-y-8" data-testid="tv-final">
            <div className="text-accent-gold uppercase tracking-[0.4em] font-mono text-base">
              Final
            </div>
            <h2 className="font-display font-bold text-7xl">
              {finalScores[0]?.name || "—"} wins
            </h2>
            <div className="text-text-secondary text-2xl">
              See staff to redeem your prize.
            </div>
          </div>
        )}
        {phase === "lobby" && (
          <div className="space-y-8" data-testid="tv-lobby">
            <div className="text-accent-electric uppercase tracking-[0.4em] font-mono text-base">
              Lobby · waiting to start
            </div>
            <h2 className="font-display font-bold text-7xl">
              Players joining…
            </h2>
          </div>
        )}

        {deadlineMs && (phase === "question" || phase === "reveal" || phase === "leaderboard") && (
          <div className="pt-4">
            <div className="h-3 w-full rounded-full bg-white/[0.08] overflow-hidden">
              <div
                className="h-full bg-accent-electric transition-[width] duration-100"
                style={{ width: `${pct}%` }}
                data-testid="tv-timer-bar"
              />
            </div>
            <div className="pt-2 font-mono text-text-secondary text-lg">
              {(remainingMs / 1000).toFixed(1)}s
            </div>
          </div>
        )}
      </div>

      {/* Side leaderboard */}
      <div className="flex flex-col justify-center" data-testid="tv-side-leaderboard">
        <div className="text-text-secondary uppercase tracking-[0.4em] font-mono text-sm mb-6">
          Top 5
        </div>
        <div className="space-y-3">
          {top5.length === 0 && (
            <div className="text-text-secondary text-xl">No scores yet…</div>
          )}
          {top5.map((p, i) => (
            <div key={p.user_id || i}
                  data-testid={`tv-lb-row-${i}`}
                  className="px-6 py-5 rounded-2xl bg-bg-glass border border-white/[0.08]
                                    flex items-center gap-6">
              <div className="font-display font-bold text-3xl text-accent-magenta w-10">
                {i + 1}
              </div>
              <div className="flex-1 font-display font-bold text-2xl truncate">
                {p.name}
              </div>
              <div className="font-mono text-accent-electric text-2xl">
                {p.score}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ─── Announcement overlay (used in all paired states) ────────────────
function AnnouncementOverlay() {
  const a = useTVDisplay((s) => s.announcement);
  if (!a) return null;
  return (
    <div className="fixed inset-0 bg-bg-base/70 backdrop-blur-md
                              flex items-center justify-center z-50 px-16
                              animate-in fade-in"
          data-testid="tv-announcement">
      <div className="rounded-3xl bg-bg-glass border-2 border-accent-magenta
                              px-20 py-14 max-w-5xl text-center space-y-6">
        {a.emoji && (
          <div className="text-9xl leading-none">{a.emoji}</div>
        )}
        <div className="font-display font-bold leading-[0.95] tracking-display-tight"
              style={{ fontSize: "clamp(48px,7vw,128px)" }}>
          {a.message}
        </div>
        <div className="font-mono text-text-secondary text-lg uppercase tracking-widest">
          A message from the venue
        </div>
      </div>
    </div>
  );
}

// ─── Revoked banner ──────────────────────────────────────────────────
function RevokedBanner() {
  const unpair = useTVDisplay((s) => s.unpair);
  useEffect(() => {
    // Auto-reset to the pairing prompt after 6 s.
    const t = setTimeout(() => unpair(), 6000);
    return () => clearTimeout(t);
  }, [unpair]);
  return (
    <div className="min-h-screen bg-bg-base flex items-center justify-center px-12"
          data-testid="tv-revoked">
      <div className="text-center space-y-6">
        <div className="text-accent-magenta uppercase tracking-[0.4em] font-mono">
          TV unpaired
        </div>
        <h1 className="font-display font-bold text-7xl tracking-display-tight">
          This TV has been unpaired.
        </h1>
        <p className="text-text-secondary text-2xl">
          Ask staff to issue a new pairing code.
        </p>
      </div>
    </div>
  );
}

// ─── Entrypoint ──────────────────────────────────────────────────────
export default function TVDisplay() {
  const token       = useTVDisplay((s) => s.token);
  const venue        = useTVDisplay((s) => s.venue);
  const currentRoom = useTVDisplay((s) => s.currentRoom);
  const phase        = useTVDisplay((s) => s.phase);
  const revoked      = useTVDisplay((s) => s.revoked);
  const connect      = useTVDisplay((s) => s.connect);

  useEffect(() => {
    if (token) connect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (revoked) return <RevokedBanner />;
  if (!token) return <PairingPrompt />;

  const showLive = currentRoom && phase !== "done";
  return (
    <>
      {showLive ? (
        <LiveRoom room={currentRoom} venue={venue} />
      ) : (
        <VenueWelcome venue={venue} />
      )}
      <AnnouncementOverlay />
    </>
  );
}
