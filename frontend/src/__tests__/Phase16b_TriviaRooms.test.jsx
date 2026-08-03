/**
 * Phase 16b — Multiplayer trivia room frontend smoke tests.
 *
 * Four acceptance criteria (per requirements):
 *   1. Lobby renders players + the host's "Start round" button.
 *   2. Countdown bar respects server clock skew (server_now baseline).
 *   3. WS reconnects after a transient disconnect (back-off path).
 *   4. "Copy room code" copies the active room code via clipboard API.
 *
 * The room component lives at /app/frontend/src/TriviaRoom.jsx (named export
 * `TriviaRoom`) and is driven by the zustand store at
 * /app/frontend/src/store/useTriviaRoom.js.
 */
import React from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";

// ─── Router shim (CRA's Jest can't resolve react-router-dom v7 subpath exports) ─
jest.mock("react-router-dom", () => ({
  __esModule: true,
  useNavigate:     () => jest.fn(),
  useParams:       () => ({ code: "BFM-TEST01" }),
  useSearchParams: () => [{ get: () => null }, jest.fn()],
  MemoryRouter:    ({ children }) => <>{children}</>,
  Routes:           ({ children }) => <>{children}</>,
  Route:            ({ element }) => element,
  Link:             ({ children, to, ...rest }) => <a href={to} {...rest}>{children}</a>,
}), { virtual: true });

// ─── Sonner + auth context mocks ────────────────────────────────────────────
jest.mock("sonner", () => ({ toast: { error: jest.fn(), success: jest.fn() } }));
jest.mock("../AuthContext", () => ({ API: "/api" }));

// axios isn't used in the lobby render path, but TriviaRoom imports it.
jest.mock("axios", () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn(), delete: jest.fn() },
  get: jest.fn(), post: jest.fn(), delete: jest.fn(),
}));

import { TriviaRoom } from "../TriviaRoom";
import { useTriviaRoom } from "../store/useTriviaRoom";

// ─── Manual WebSocket fake (sync open / message dispatch) ───────────────────
class FakeWS {
  static instances = [];
  constructor(url) {
    this.url        = url;
    this.readyState = 0;
    FakeWS.instances.push(this);
  }
  send  = jest.fn();
  close = jest.fn(function () {
    this.readyState = 3;
    this.onclose && this.onclose({});
  });
  // Helpers for tests.
  _open()           { this.readyState = 1; this.onopen && this.onopen({}); }
  _push(msg)        { this.onmessage && this.onmessage({ data: JSON.stringify(msg) }); }
}

// Snapshot pristine store state so we can fully reset between tests.
const initialState = useTriviaRoom.getState();
beforeEach(() => {
  FakeWS.instances = [];
  global.WebSocket = FakeWS;
  // Reset the store between tests so prior connect()s don't leak.
  act(() => { useTriviaRoom.setState(initialState, true); });
});

// ─── Acceptance 1: Lobby renders + host sees "Start round" ──────────────────
test("Phase 16b lobby renders players + start button for host", async () => {
  render(<TriviaRoom />);
  // Connect was called inside useEffect; flush the WS open.
  const ws = FakeWS.instances[0];
  expect(ws).toBeDefined();
  act(() => { ws._open(); });

  // Push the hello frame — host is alice; one player so far.
  act(() => {
    ws._push({
      type:       "hello",
      server_now: Date.now(),
      you:         { user_id: "alice", name: "Alice" },
      room:        {
        code:         "BFM-TEST01",
        host_user_id: "alice",
        category_slug: "music",
        market:       "dfw",
        phase:        "lobby",
        players:     [
          { user_id: "alice", name: "Alice", connected: true,
            score: 0, rank: 0 },
        ],
        max_players:    20,
        current_index: -1,
        total_questions: 0,
      },
    });
  });

  await waitFor(() => {
    expect(screen.getByTestId("trivia-room-lobby")).toBeTruthy();
  });
  expect(screen.getByTestId("trivia-room-player-alice")).toBeTruthy();
  // Host should see the Start button (Alice is host).
  expect(screen.getByTestId("trivia-room-start")).toBeTruthy();
});

// ─── Acceptance 2: Countdown bar uses server-relative deadline ──────────────
test("Phase 16b timer bar respects server clock skew", async () => {
  render(<TriviaRoom />);
  const ws = FakeWS.instances[0];
  act(() => { ws._open(); });

  // Pretend our local clock is 5 s ahead of the server.
  const clientNow = Date.now();
  const serverNow = clientNow - 5000;

  act(() => {
    ws._push({
      type:       "hello",
      server_now: serverNow,
      you:         { user_id: "bob", name: "Bob" },
      room:        {
        code: "BFM-TEST01", host_user_id: "alice",
        phase: "lobby", players: [
          { user_id: "alice", name: "Alice", connected: true, score: 0, rank: 0 },
          { user_id: "bob",    name: "Bob",    connected: true, score: 0, rank: 0 },
        ],
        max_players: 20, current_index: -1, total_questions: 0,
      },
    });
  });

  // Advance into a question phase whose deadline is 15 s after the
  // server clock.  The component must compute remainingMs against
  // (now - serverSkew), giving ~15 s instead of ~10 s.
  act(() => {
    ws._push({
      type:        "phase_change",
      phase:       "question",
      deadline_ms: serverNow + 15000,
      question: {
        id: "q_1", prompt: "Capital of Spain?",
        choices: [
          { id: "a", text: "Madrid" }, { id: "b", text: "Lisbon" },
          { id: "c", text: "Rome"   }, { id: "d", text: "Paris"  },
        ],
        category: "geography", difficulty: 2,
      },
    });
  });

  await waitFor(() => {
    expect(screen.getByTestId("trivia-room-question")).toBeTruthy();
  });
  const timer = screen.getByTestId("trivia-room-timer");
  const pct   = parseFloat(timer.style.width); // "97.3%" → 97.3
  // 15 s remaining of a 15 s phase → ~100 %.  If skew was ignored,
  // remainingMs would be 10000 → ~67 %.  Allow a generous lower
  // bound (>= 90 %) to stay tolerant of the 100 ms timer cadence
  // and a few ms of microtask jitter.
  expect(pct).toBeGreaterThanOrEqual(90);
});

// ─── Acceptance 3: WS reconnects on transient disconnect ────────────────────
test("Phase 16b store reconnects after WS close while phase != done", async () => {
  jest.useFakeTimers();
  try {
    act(() => { useTriviaRoom.getState().connect("BFM-TEST01"); });
    expect(FakeWS.instances.length).toBe(1);
    const first = FakeWS.instances[0];

    // Trigger onopen → connected = true.
    act(() => { first._open(); });
    expect(useTriviaRoom.getState().connected).toBe(true);

    // Simulate transient drop.  Phase is "lobby" (default) so onclose
    // must schedule a 2-s reconnect.
    act(() => { first.onclose({}); });
    expect(useTriviaRoom.getState().connected).toBe(false);

    act(() => { jest.advanceTimersByTime(2100); });

    // A second WS instance should now exist.
    expect(FakeWS.instances.length).toBeGreaterThanOrEqual(2);
  } finally {
    // Cleanup: clear pending reconnect timers + disconnect.
    act(() => { useTriviaRoom.getState().disconnect(); });
    jest.clearAllTimers();
    jest.useRealTimers();
  }
});

// ─── Acceptance 4: Copy-room-code uses navigator.clipboard ──────────────────
test("Phase 16b copy room-code button calls clipboard.writeText", async () => {
  const writeText = jest.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", {
    value: { writeText }, configurable: true, writable: true,
  });

  render(<TriviaRoom />);
  const ws = FakeWS.instances[0];
  act(() => { ws._open(); });

  act(() => {
    ws._push({
      type:       "hello",
      server_now: Date.now(),
      you:         { user_id: "carol", name: "Carol" },
      room:        {
        code: "BFM-TEST01", host_user_id: "carol",
        phase: "lobby", players: [
          { user_id: "carol", name: "Carol", connected: true, score: 0, rank: 0 },
        ],
        max_players: 20, current_index: -1, total_questions: 0,
      },
    });
  });

  const copyBtn = await screen.findByTestId("trivia-room-copy");
  await act(async () => { fireEvent.click(copyBtn); });

  expect(writeText).toHaveBeenCalledTimes(1);
  expect(writeText).toHaveBeenCalledWith("BFM-TEST01");
});


// ─── Acceptance 5 (16b kick-bug regression): kicked → no reconnect ─────────
test("Phase 16b kicked frame + close 4001 sets kicked, skips reconnect", async () => {
  jest.useFakeTimers();
  try {
    act(() => { useTriviaRoom.getState().connect("BFM-TEST01"); });
    const ws = FakeWS.instances[0];
    act(() => { ws._open(); });
    expect(useTriviaRoom.getState().connected).toBe(true);

    // Server sends the targeted `kicked` frame, then closes with 4001.
    act(() => {
      ws._push({
        type:       "kicked",
        reason:     "removed_by_host",
        room_code:  "BFM-TEST01",
        kicked_at:  Date.now(),
      });
      ws.onclose({ code: 4001, reason: "kicked" });
    });

    // Kicked flag set.
    const kicked = useTriviaRoom.getState().kicked;
    expect(kicked).toBeTruthy();
    expect(kicked.reason).toBe("removed_by_host");
    expect(kicked.room_code).toBe("BFM-TEST01");

    // After the 2-s backoff window, NO reconnect attempt was scheduled.
    const wsCountBefore = FakeWS.instances.length;
    act(() => { jest.advanceTimersByTime(3000); });
    expect(FakeWS.instances.length).toBe(wsCountBefore);
    expect(useTriviaRoom.getState().connected).toBe(false);
  } finally {
    act(() => { useTriviaRoom.getState().disconnect(); });
    jest.clearAllTimers();
    jest.useRealTimers();
  }
});


// ─── Acceptance 6: P0 regression — Start disabled when alone ──────────────
test("Phase 16b Start button is disabled + hint shown when alone in lobby", async () => {
  render(<TriviaRoom />);
  const ws = FakeWS.instances[0];
  act(() => { ws._open(); });

  act(() => {
    ws._push({
      type:       "hello",
      server_now: Date.now(),
      you:         { user_id: "alice", name: "Alice" },
      room:        {
        code: "BFM-TEST01", host_user_id: "alice", category_slug: "music",
        market: "dfw", phase: "lobby",
        players: [
          { user_id: "alice", name: "Alice", connected: true, score: 0, rank: 0 },
        ],
        max_players: 20, current_index: -1, total_questions: 0,
      },
    });
  });

  const startBtn = await screen.findByTestId("trivia-room-start");
  expect(startBtn.disabled).toBe(true);
  const hint = screen.getByTestId("trivia-room-start-hint");
  expect(hint.textContent).toContain("Need");
  expect(hint.textContent).toContain("1 more player");
  expect(hint.textContent).toContain("BFM-TEST01");

  // Add a second player → server pushes a fresh hello-style snapshot
  // (the real server does this via REST refetch on `player_joined`;
  // we simulate it directly here for the unit test).
  act(() => {
    ws._push({
      type:       "hello",
      server_now: Date.now(),
      you:         { user_id: "alice", name: "Alice" },
      room:        {
        code: "BFM-TEST01", host_user_id: "alice", category_slug: "music",
        market: "dfw", phase: "lobby",
        players: [
          { user_id: "alice", name: "Alice", connected: true, score: 0, rank: 0 },
          { user_id: "bob",    name: "Bob",    connected: true, score: 0, rank: 0 },
        ],
        max_players: 20, current_index: -1, total_questions: 0,
      },
    });
  });

  await waitFor(() => {
    const btn = screen.getByTestId("trivia-room-start");
    expect(btn.disabled).toBe(false);
  });
  expect(screen.queryByTestId("trivia-room-start-hint")).toBeNull();
});

// ─── Acceptance 7: Join input normalizes variants identically ─────────────
test("Phase 16b join input normalizes variants to canonical BFM-XXXXXX", async () => {
  const { TriviaJoin } = require("../TriviaRoom");
  // Each variant of the same code should produce the same canonical
  // preview line and let the user submit.
  const variants = [
    "BFM-9U32KK",
    "bfm-9u32kk",
    "BFM9U32KK",
    "9u32kk",
    "  bfm 9u32kk  ",
  ];
  for (const v of variants) {
    const { unmount } = render(<TriviaJoin />);
    const input = screen.getByTestId("trivia-join-input");
    await act(async () => { fireEvent.change(input, { target: { value: v } }); });
    const preview = screen.getByTestId("trivia-join-preview");
    expect(preview.textContent).toContain("BFM-9U32KK");
    const btn = screen.getByTestId("trivia-join-btn");
    expect(btn.disabled).toBe(false);
    unmount();
  }
});
