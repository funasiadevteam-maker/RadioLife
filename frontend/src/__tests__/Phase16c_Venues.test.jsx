/**
 * Phase 16c — Venue dashboard + TV display frontend smoke tests (6).
 */
import React from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";

// Router shim (CRA Jest can't resolve react-router-dom v7 subpath exports).
const mockNavigate = jest.fn();
jest.mock("react-router-dom", () => ({
  __esModule: true,
  useNavigate:     () => mockNavigate,
  useParams:       () => ({}),
  useSearchParams: () => [{ get: () => null }, jest.fn()],
  NavLink:          ({ children, to, ...rest }) => <a href={to} {...rest}>{children}</a>,
  Link:             ({ children, to, ...rest }) => <a href={to} {...rest}>{children}</a>,
  MemoryRouter:    ({ children }) => <>{children}</>,
  Routes:           ({ children }) => <>{children}</>,
  Route:            ({ element }) => element,
}), { virtual: true });
jest.mock("sonner",       () => ({ toast: { error: jest.fn(), success: jest.fn() } }));
jest.mock("../AuthContext", () => ({ API: "/api" }));

// axios is used by every venue sub-route — return shape they expect.
const _mockGet = async (url) => {
    if (url.endsWith("/venue/me")) {
      return { data: { venues: [{ id: "venue_demo_karak", name: "Demo Karak Cafe",
                                            plan_tier: "growth", market: "dubai",
                                            address: "Al Wasl Road", my_role: "owner" }] } };
    }
    if (url.includes("/stats")) {
      return { data: { live_players: 3, live_rooms: 1, rooms: 4, coupons: 2,
                              announcements: 1, period: "today" } };
    }
    if (url.endsWith("/tvs")) {
      return { data: { tvs: [{ id: "tvp_1", status: "active",
                                          last_seen: "2026-06-01T12:00:00Z",
                                          paired_at: "2026-06-01T11:00:00Z" }] } };
    }
    if (url.endsWith("/trivia/categories")) {
      return { data: { categories: [{ id: "c1", slug: "music",  name: "Music",  market: "global" },
                                                { id: "c2", slug: "movies", name: "Movies", market: "global" }] } };
    }
    if (url.endsWith("/venue/venue_demo_karak")) {
      return { data: { venue: {}, staff: [
        { user_id: "u1", role: "owner",  name: "Admin",  email: "admin@bigfm.dubai" },
        { user_id: "u2", role: "staff",  name: "Test",   email: "test@bigfm.dubai"  },
      ] } };
    }
    if (url.endsWith("/players")) {
      return { data: { players: [] } };
    }
    return { data: {} };
};
const _mockPost = async (url) => {
    if (url.endsWith("/tvs/pair")) {
      return { data: { pairing_code: "483-921",
                              expires_at:   "2026-06-01T13:00:00Z",
                              ttl_sec:      600 } };
    }
    if (url.endsWith("/announcement")) {
      return { data: { ok: true, id: "ann_1", rooms: ["BFM-TEST"], tvs: ["tvp_1"] } };
    }
    return { data: { ok: true } };
};
const _mockDel = async () => ({ data: { ok: true } });

jest.mock("axios", () => {
  const get = jest.fn();
  const post = jest.fn();
  const del = jest.fn();
  const fn = { get, post, delete: del, defaults: { withCredentials: true } };
  return { __esModule: true, default: fn, get, post, delete: del,
              defaults: { withCredentials: true } };
});

beforeEach(() => {
  const axios = require("axios").default;
  axios.get.mockImplementation(_mockGet);
  axios.post.mockImplementation(_mockPost);
  axios.delete.mockImplementation(_mockDel);
});

// ─── Frontend test 1: Venue dashboard nav renders ────────────────────
test("Phase 16c venue dashboard renders nav + stats", async () => {
  const { VenueDashboard } = require("../Venue");
  render(<VenueDashboard />);
  // Stats panel shows the fetched numbers (waits for the second fetch).
  const stats = await screen.findByTestId("venue-overview-stats", {}, { timeout: 4000 });
  await waitFor(() => expect(stats.textContent).toContain("3"));
  // The 5 nav links rendered (subset).
  expect(screen.getByTestId("venue-nav-home")).toBeTruthy();
  expect(screen.getByTestId("venue-nav-tvs")).toBeTruthy();
  expect(screen.getByTestId("venue-nav-trivia")).toBeTruthy();
  expect(screen.getByTestId("venue-nav-announcements")).toBeTruthy();
  expect(screen.getByTestId("venue-nav-redeem")).toBeTruthy();
});

// ─── Frontend test 2: TV pairing prompt renders ──────────────────────
test("Phase 16c TV pairing prompt renders when no token", async () => {
  // Ensure no leftover token.
  try { localStorage.removeItem("bigfm_tv_token"); } catch (_) { /* */ }
  const TVDisplay = require("../TV").default;
  render(<TVDisplay />);
  const prompt = await screen.findByTestId("tv-pairing");
  expect(prompt).toBeTruthy();
  expect(screen.getByTestId("tv-pairing-input")).toBeTruthy();
  expect(screen.getByTestId("tv-pairing-submit")).toBeTruthy();
});

// ─── Frontend test 3: Announcement form submits ──────────────────────
test("Phase 16c announcement form submits with message + emoji", async () => {
  const axios = require("axios").default;
  const { VenueAnnounce } = require("../Venue");
  render(<VenueAnnounce />);
  await waitFor(() => expect(screen.getByTestId("venue-ann-textarea")).toBeTruthy());
  // Pick an emoji + type a message.
  await act(async () => {
    fireEvent.click(screen.getByTestId("venue-ann-emoji-🍰"));
    fireEvent.change(screen.getByTestId("venue-ann-textarea"),
                              { target: { value: "Free dessert for top 3" } });
  });
  await act(async () => { fireEvent.click(screen.getByTestId("venue-ann-send-btn")); });
  // Assert the POST hit our mocked axios.
  expect(axios.post).toHaveBeenCalledWith(
    expect.stringContaining("/announcement"),
    expect.objectContaining({ message: "Free dessert for top 3",
                                    emoji:    "🍰",
                                    target:   "all_rooms" }),
  );
});

// ─── Frontend test 4: Redeem input renders + posts ───────────────────
test("Phase 16c redeem screen renders input + posts on submit", async () => {
  const axios = require("axios").default;
  const { VenueRedeem } = require("../Venue");
  render(<VenueRedeem />);
  const input = await screen.findByTestId("venue-redeem-input");
  await act(async () => {
    fireEvent.change(input, { target: { value: "cpn_test_123" } });
    fireEvent.click(screen.getByTestId("venue-redeem-btn"));
  });
  expect(axios.post).toHaveBeenCalledWith(
    expect.stringContaining("/coupons/redeem"),
    { code: "cpn_test_123" },
  );
});

// ─── Frontend test 5: Settings staff list renders ────────────────────
test("Phase 16c settings page lists current staff", async () => {
  const { VenueSettings } = require("../Venue");
  render(<VenueSettings />);
  const list = await screen.findByTestId("venue-staff-list");
  await waitFor(() => {
    expect(list.textContent).toContain("admin@bigfm.dubai");
    expect(list.textContent).toContain("test@bigfm.dubai");
  });
});

// ─── Frontend test 6: TV pairing input claims via axios ──────────────
test("Phase 16c TV pairing input calls /api/tv/claim", async () => {
  // Override axios.post to capture the claim call specifically.
  const axios = require("axios").default;
  axios.post.mockImplementationOnce(async () => ({
    data: { tv_token: "tv_xxx", tv_id: "tvp_1",
              venue: { id: "venue_demo_karak", name: "Demo Karak Cafe" } },
  }));
  // Stub WebSocket so the post-claim connect() doesn't blow up.
  class FakeWS { constructor() { setTimeout(() => this.onopen && this.onopen({}), 0); }
                          send = jest.fn(); close = jest.fn(); }
  global.WebSocket = FakeWS;
  try { localStorage.removeItem("bigfm_tv_token"); } catch (_) {/* */}
  const TVDisplay = require("../TV").default;
  render(<TVDisplay />);
  const input = await screen.findByTestId("tv-pairing-input");
  await act(async () => {
    fireEvent.change(input, { target: { value: "483-921" } });
    fireEvent.click(screen.getByTestId("tv-pairing-submit"));
  });
  expect(axios.post).toHaveBeenCalledWith(
    expect.stringContaining("/tv/claim"),
    { pairing_code: "483-921" },
  );
});
