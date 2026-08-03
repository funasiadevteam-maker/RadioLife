/**
 * useTriviaRoom — Zustand store for multiplayer trivia WebSocket.
 * Mirrors /app/frontend/src/store/useTriviaRoom.js
 */
import { create } from 'zustand';
import { BACKEND, getToken } from '../api/client';

const WS_BACKOFF_MS = 2000;

interface Player {
  user_id: string;
  name: string;
  connected: boolean;
}

interface Room {
  room_code: string;
  host_user_id: string;
  players: Player[];
  max_players: number;
  phase: string;
  current_index?: number;
  total_questions?: number;
}

interface Choice {
  id: string;
  text: string;
}

interface Question {
  id: string;
  prompt: string;
  choices: Choice[];
  category?: string;
  difficulty?: number;
}

interface Reveal {
  correct_choice_id: string;
  points_awarded?: number;
}

interface LBEntry {
  user_id: string;
  name: string;
  score: number;
  rank: number;
  bigcoin_awarded?: number;
}

interface Announcement {
  id: string;
  venue_name: string;
  emoji?: string;
  message: string;
  broadcast_at?: string;
}

interface TriviaRoomState {
  code: string | null;
  ws: WebSocket | null;
  connected: boolean;
  serverSkewMs: number;
  you: { user_id: string; name: string } | null;
  room: Room | null;
  phase: string;
  question: Question | null;
  deadlineMs: number | null;
  leaderboard: LBEntry[];
  finalScores: LBEntry[];
  reveal: Reveal | null;
  answersIn: number;
  totalPlayers: number;
  error: { code: string; message: string } | null;
  kicked: { reason: string; room_code: string; kicked_at?: string } | null;
  announcement: Announcement | null;
  connect: (code: string) => void;
  sendAnswer: (questionId: string, choiceId: string) => void;
  disconnect: () => void;
  _dispatch: (msg: any) => void;
}

export const useTriviaRoom = create<TriviaRoomState>((set, get) => ({
  code: null,
  ws: null,
  connected: false,
  serverSkewMs: 0,
  you: null,
  room: null,
  phase: 'lobby',
  question: null,
  deadlineMs: null,
  leaderboard: [],
  finalScores: [],
  reveal: null,
  answersIn: 0,
  totalPlayers: 0,
  error: null,
  kicked: null,
  announcement: null,

  connect: (code: string) => {
    const existing = get().ws;
    if (existing) {
      try { existing.close(); } catch {}
    }
    set({ code, error: null, kicked: null });

    const backend = BACKEND || '';
    const proto = backend.startsWith('https') ? 'wss' : 'ws';
    const host = backend.replace(/^https?:\/\//, '');
    const token = getToken();
    const wsUrl = `${proto}://${host}/api/trivia/ws/${code}${token ? `?token=${token}` : ''}`;
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => set({ connected: true });
    ws.onclose = (ev: any) => {
      set({ connected: false });
      const { code: c, phase, kicked } = get();
      const closeCode = ev?.code;

      if (closeCode === 4001 || kicked) {
        if (!kicked) set({ kicked: { reason: 'removed_by_host', room_code: c || '' } });
        return;
      }
      if (closeCode === 4404 || closeCode === 4409 || closeCode === 4401) {
        return;
      }
      if (c && phase !== 'done') {
        setTimeout(() => get().connect(c), WS_BACKOFF_MS);
      }
    };
    ws.onerror = () => {};
    ws.onmessage = (ev: any) => {
      let msg;
      try { msg = JSON.parse(ev.data); } catch { return; }
      get()._dispatch(msg);
    };
    set({ ws });
  },

  _dispatch: (msg: any) => {
    switch (msg.type) {
      case 'hello': {
        const skew = Date.now() - (msg.server_now || Date.now());
        set({
          serverSkewMs: skew,
          you: msg.you,
          room: msg.room || null,
          phase: msg.room?.phase || 'lobby',
        });
        break;
      }
      case 'player_joined':
      case 'player_left': {
        const c = get().code;
        if (c) {
          const backend = BACKEND || '';
          const token = getToken();
          fetch(`${backend}/api/trivia/rooms/${c}`, {
            headers: token ? { Authorization: `Bearer ${token}` } : {},
          })
            .then((r) => r.json())
            .then((d) => {
              if (d.room) set({ room: d.room });
            })
            .catch(() => {});
        }
        break;
      }
      case 'phase_change': {
        set({
          phase: msg.phase,
          deadlineMs: msg.deadline_ms,
          question: msg.question || null,
          leaderboard: msg.leaderboard || get().leaderboard,
          finalScores: msg.final_scores || get().finalScores,
          reveal: msg.phase === 'reveal' ? msg : null,
          answersIn: 0,
        });
        break;
      }
      case 'answer_received': {
        set({ answersIn: msg.answers_in || 0, totalPlayers: msg.total || 0 });
        break;
      }
      case 'error': {
        set({ error: { code: msg.code, message: msg.message } });
        break;
      }
      case 'kicked': {
        set({
          kicked: {
            reason: msg.reason || 'removed_by_host',
            room_code: msg.room_code,
            kicked_at: msg.kicked_at,
          },
        });
        break;
      }
      case 'venue_announcement': {
        set({
          announcement: {
            id: msg.id,
            venue_name: msg.venue_name,
            emoji: msg.emoji,
            message: msg.message,
            broadcast_at: msg.broadcast_at,
          },
        });
        // Auto-clear after 6s
        setTimeout(() => {
          const cur = get().announcement;
          if (cur?.id === msg.id) set({ announcement: null });
        }, 6000);
        break;
      }
      default:
        break;
    }
  },

  sendAnswer: (questionId: string, choiceId: string) => {
    const ws = get().ws;
    if (!ws || ws.readyState !== 1) return;
    ws.send(JSON.stringify({ type: 'answer', question_id: questionId, choice_id: choiceId }));
  },

  disconnect: () => {
    const ws = get().ws;
    if (ws) { try { ws.close(); } catch {} }
    set({
      ws: null, code: null, connected: false, room: null, phase: 'lobby',
      question: null, deadlineMs: null, reveal: null, kicked: null,
      announcement: null, error: null,
    });
  },
}));
