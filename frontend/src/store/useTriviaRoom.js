// Phase 16b — Multiplayer trivia room store.
//
// Holds the active room state + the single WS connection.  Components
// (lobby, gameplay, leaderboard) subscribe to slices.  Reconnects on
// transient disconnects with a 2-s backoff.
import { create } from "zustand";

const WS_BACKOFF_MS = 2000;

export const useTriviaRoom = create((set, get) => ({
  // ─── State ──────────────────────────────────────────────────────────
  code:          null,
  ws:             null,
  connected:     false,
  serverSkewMs: 0,        // local_now_ms - server_now_ms
  you:            null,
  room:           null,    // full public room snapshot
  phase:          "lobby",
  question:      null,
  deadlineMs:    null,
  leaderboard:  [],
  finalScores: [],
  sponsorPrizes: [],
  reveal:         null,    // last reveal phase payload
  answersIn:     0,
  totalPlayers: 0,
  error:          null,
  kicked:        null,     // {reason, room_code, kicked_at} when host removed us
  announcement: null,     // Phase 16c — last venue announcement {id,emoji,message,venue_name,broadcast_at}

  // ─── Actions ────────────────────────────────────────────────────────
  connect: (code) => {
    const existing = get().ws;
    if (existing) {
      try { existing.close(); } catch (_) { /* */ }
    }
    set({ code, error: null });

    const backend = process.env.REACT_APP_BACKEND_URL || "";
    const proto   = backend.startsWith("https") ? "wss" : "ws";
    const host    = backend.replace(/^https?:\/\//, "");
    const ws      = new WebSocket(`${proto}://${host}/api/trivia/ws/${code}`);

    ws.onopen = () => set({ connected: true });
    ws.onclose = (ev) => {
      set({ connected: false });
      const { code: c, phase, kicked } = get();
      const closeCode = ev && ev.code;
      // Application-range close codes (4xxx) are FATAL — server told
      // us to stop trying.  Don't reconnect.  Component watches the
      // `kicked` / `error` slices and shows the right toast / redirect.
      //   4001 = kicked by host
      //   4401 = unauthorized
      //   4404 = room_not_found
      //   4409 = room_in_progress (joined mid-game)
      if (closeCode === 4001 || kicked) {
        if (!kicked) set({ kicked: { reason: "removed_by_host", room_code: c } });
        return;
      }
      if (closeCode === 4404 || closeCode === 4409 || closeCode === 4401) {
        // `error` was already set by the dispatcher when the server
        // sent its `{type:"error"}` frame; nothing more to do.
        return;
      }
      // Transient drop — reconnect if the room is still active.
      if (c && phase !== "done") {
        setTimeout(() => get().connect(c), WS_BACKOFF_MS);
      }
    };
    ws.onerror = () => { /* close handler will fire next */ };
    ws.onmessage = (ev) => {
      let msg;
      try { msg = JSON.parse(ev.data); } catch { return; }
      const handle = get()._dispatch;
      handle(msg);
    };
    set({ ws });
  },

  _dispatch: (msg) => {
    switch (msg.type) {
      case "hello": {
        const skew = Date.now() - (msg.server_now || Date.now());
        set({
          serverSkewMs: skew,
          you: msg.you,
          room: msg.room || null,
          phase: msg.room?.phase || "lobby",
        });
        break;
      }
      case "player_joined":
      case "player_left": {
        // Refetch room snapshot via REST (cheap; player list isn't large).
        // The snapshot includes phase + deadline so we stay consistent.
        const c = get().code;
        if (c) {
          fetch(`${process.env.REACT_APP_BACKEND_URL || ""}/api/trivia/rooms/${c}`,
                { credentials: "include" })
            .then((r) => r.json())
            .then((d) => {
              if (d.room) set({ room: d.room });
            }).catch(() => {});
        }
        break;
      }
      case "phase_change": {
        set({
          phase:        msg.phase,
          deadlineMs:  msg.deadline_ms,
          question:    msg.question || null,
          leaderboard: msg.leaderboard || get().leaderboard,
          finalScores: msg.final_scores || get().finalScores,
          // Phase H — sponsor_prizes accompanies the `done` transition.
          sponsorPrizes: msg.sponsor_prizes || get().sponsorPrizes,
          reveal:       msg.phase === "reveal" ? msg : null,
          answersIn:   0,
        });
        break;
      }
      case "answer_received": {
        set({ answersIn: msg.answers_in || 0, totalPlayers: msg.total || 0 });
        break;
      }
      case "error": {
        set({ error: { code: msg.code, message: msg.message } });
        // Hard errors that mean we should give up and bounce back.
        // The component watches `error` for these codes and shows a
        // toast + navigates the user out.
        break;
      }
      case "kicked": {
        // Server is about to close our socket with code 4001.  Set the
        // flag now so the component redirects + toasts (it's possible
        // for the `kicked` frame to arrive a microtask before onclose).
        set({ kicked: {
          reason:     msg.reason || "removed_by_host",
          room_code:  msg.room_code,
          kicked_at:  msg.kicked_at,
        } });
        break;
      }
      case "venue_announcement": {
        // Phase 16c — push notification from the host venue.  We stash
        // it on the store so the component can render a toast/banner
        // and clear it after a few seconds.
        set({ announcement: {
          id:           msg.id,
          venue_name:  msg.venue_name,
          emoji:        msg.emoji,
          message:      msg.message,
          broadcast_at: msg.broadcast_at,
        } });
        break;
      }
      default:
        break;
    }
  },

  sendAnswer: (questionId, choiceId) => {
    const ws = get().ws;
    if (!ws || ws.readyState !== 1) return;
    ws.send(JSON.stringify({
      type: "answer",
      question_id: questionId,
      choice_id: choiceId,
    }));
  },

  disconnect: () => {
    const ws = get().ws;
    if (ws) { try { ws.close(); } catch (_) { /* */ } }
    set({ ws: null, code: null, connected: false, room: null, phase: "lobby",
            question: null, deadlineMs: null, reveal: null, kicked: null });
  },
}));
