/**
 * Phase 16c — Zustand store for the TV display surface.
 *
 * Connects to /api/tv/ws?token=<tv_token>, persists the token in
 * localStorage, surfaces a single source of truth for the TV UI.
 * No reconnect on a 4001 close (revoked); 2-s back-off on transient
 * drops while the token is still valid.
 */
import { create } from "zustand";
import axios from "axios";

const API           = process.env.REACT_APP_BACKEND_URL || "";
const TOKEN_KEY     = "bigfm_tv_token";
const RECONNECT_MS = 2000;

const readToken  = () => { try { return localStorage.getItem(TOKEN_KEY) || null; } catch { return null; } };
const writeToken = (t) => { try { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY); } catch {/* */} };

export const useTVDisplay = create((set, get) => ({
  token:           readToken(),
  ws:               null,
  connected:       false,
  serverSkewMs:   0,
  venue:            null,
  tvId:             null,
  activeRooms:    [],
  currentRoom:    null,
  question:        null,
  reveal:           null,
  leaderboard:    [],
  finalScores:    [],
  phase:            "lobby",
  deadlineMs:      null,
  announcement:  null,    // {emoji,message,broadcast_at,id}
  revoked:         false,
  pairingError:   null,
  claiming:        false,

  // ─── Claim a pairing code → tv_token ───────────────────────────────
  claim: async (pairingCode) => {
    set({ claiming: true, pairingError: null });
    try {
      const { data } = await axios.post(`${API}/tv/claim`,
                                                    { pairing_code: pairingCode });
      writeToken(data.tv_token);
      set({ token: data.tv_token, venue: data.venue, tvId: data.tv_id,
              claiming: false, revoked: false });
      // Immediately open the WS now that we have a token.
      get().connect();
      return true;
    } catch (e) {
      const d = e?.response?.data?.detail;
      const msg = (d && typeof d === "object" && d.message)
                    ? d.message
                    : (typeof d === "string" ? d : "Couldn't pair this TV.");
      set({ claiming: false, pairingError: msg });
      return false;
    }
  },

  unpair: () => {
    const ws = get().ws;
    if (ws) { try { ws.close(); } catch (_) { /* */ } }
    writeToken(null);
    set({ token: null, ws: null, connected: false, venue: null, tvId: null,
            activeRooms: [], currentRoom: null, question: null, reveal: null,
            leaderboard: [], finalScores: [], phase: "lobby", deadlineMs: null,
            announcement: null, revoked: false, pairingError: null });
  },

  // ─── WebSocket ─────────────────────────────────────────────────────
  connect: () => {
    const token = get().token;
    if (!token) return;
    const old = get().ws;
    if (old) { try { old.close(); } catch (_) { /* */ } }
    const url = `${API.replace(/^http/, "ws")}/api/tv/ws?token=${encodeURIComponent(token)}`;
    const ws = new WebSocket(url);
    set({ ws });
    ws.onopen = () => set({ connected: true });
    ws.onclose = (ev) => {
      set({ connected: false });
      if (ev && ev.code === 4001) {
        writeToken(null);
        set({ token: null, revoked: true, venue: null });
        return;
      }
      if (ev && ev.code === 4401) {
        // Token bad on the server (probably revoked while we were offline).
        writeToken(null);
        set({ token: null, revoked: true });
        return;
      }
      if (get().token) {
        setTimeout(() => get().connect(), RECONNECT_MS);
      }
    };
    ws.onmessage = (e) => { try { dispatch(set, get, JSON.parse(e.data)); }
                                  catch (err) { /* swallow */ } };
  },
}));

function dispatch(set, get, msg) {
  switch (msg.type) {
    case "hello": {
      const skew = Date.now() - (msg.server_now || Date.now());
      set({ serverSkewMs: skew, venue: msg.venue, tvId: msg.tv_id,
              activeRooms: msg.active_rooms || [] });
      const live = (msg.active_rooms || [])[0];
      if (live) {
        set({ currentRoom: live, phase: live.phase });
      }
      break;
    }
    case "venue_room_started": {
      set({ currentRoom: msg.room, phase: msg.room.phase || "lobby",
              activeRooms: [...(get().activeRooms || []), msg.room] });
      break;
    }
    case "phase_change": {
      const skew = get().serverSkewMs;
      set({
        phase:        msg.phase,
        deadlineMs:  msg.deadline_ms ? (msg.deadline_ms + skew) : null,
        question:    msg.phase === "question" ? msg.question : (msg.phase === "reveal" ? get().question : null),
        reveal:       msg.phase === "reveal" ? msg : null,
        leaderboard: msg.leaderboard || get().leaderboard,
        finalScores: msg.phase === "done" ? (msg.final_scores || []) : get().finalScores,
      });
      break;
    }
    case "leaderboard_update": {
      set({ leaderboard: msg.leaderboard || [] });
      break;
    }
    case "venue_announcement": {
      set({ announcement: { emoji: msg.emoji, message: msg.message,
                                    id: msg.id, broadcast_at: msg.broadcast_at } });
      // Auto-clear after 10 s so the TV returns to game state.
      setTimeout(() => {
        if (get().announcement && get().announcement.id === msg.id) {
          set({ announcement: null });
        }
      }, 10000);
      break;
    }
    case "tv_revoked": {
      set({ revoked: true, token: null });
      try { localStorage.removeItem(TOKEN_KEY); } catch (_) { /* */ }
      break;
    }
    default: break;
  }
}
