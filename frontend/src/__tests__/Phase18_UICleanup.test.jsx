/**
 * Phase 18 UI cleanup batch — 7 frontend tests.
 *   A. Bottom-bar strip renders chips + chip click triggers switch.
 *   A. Mini-player play with no session calls autoplay-suggestion.
 *   B. Wallet GamesTab renders friendly empty state.
 *   C. Commute explainer hero renders headline + 3 bullets + CTA.
 *   D. Top-game rec card renders name + Play again.
 *   D. Top-channel rec card renders + Resume.
 *   D. Favorites strip + picker add → toast + chip appears.
 */
import React from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";

// ---------- shared mocks ----------
const mockNavigate = jest.fn();
jest.mock("react-router-dom", () => ({
  __esModule: true,
  useNavigate:     () => mockNavigate,
  useParams:       () => ({}),
  useSearchParams: () => [{ get: () => null }, jest.fn()],
  NavLink:          ({ children, to, ...rest }) => <a href={to} {...rest}>{children}</a>,
  Link:             ({ children, to, ...rest }) => <a href={to} {...rest}>{children}</a>,
}), { virtual: true });
jest.mock("sonner", () => ({ toast: { error: jest.fn(), success: jest.fn() },
                                              Toaster: () => null }));
jest.mock("../AuthContext", () => ({
  API: "/api",
  useAuth: () => ({ user: { first_name: "Karak" }, loading: false }),
}));

jest.mock("axios", () => {
  const get = jest.fn();
  const post = jest.fn();
  const del = jest.fn();
  const fn = { get, post, delete: del, defaults: { withCredentials: true } };
  return { __esModule: true, default: fn, get, post, delete: del,
              defaults: { withCredentials: true } };
});

// Heavy deps used by Commute.js — stub so jest can parse the file.
jest.mock("react-leaflet", () => ({
  __esModule: true,
  MapContainer: ({ children }) => <div data-testid="mock-map">{children}</div>,
  TileLayer:    () => <div />,
  Polyline:     () => <div />,
  Marker:        () => <div />,
  useMap:        () => ({ fitBounds: () => {} }),
}), { virtual: true });
jest.mock("leaflet",                     () => ({ divIcon: () => ({}) }), { virtual: true });
jest.mock("leaflet/dist/leaflet.css", () => ({}),                                       { virtual: true });
jest.mock("@googlemaps/polyline-codec", () => ({ decode: () => [] }),    { virtual: true });
jest.mock("../Commute.css", () => ({}), { virtual: true });
jest.mock("../Wallet.css",   () => ({}), { virtual: true });

// recharts is not used in 18 components but lazy-loaded elsewhere; stub to avoid noise.
jest.mock("recharts", () => ({
  __esModule: true,
  ResponsiveContainer: ({ children }) => <div>{children}</div>,
  BarChart: ({ children }) => <div>{children}</div>,
  Bar: () => <div />, XAxis: () => <div />, YAxis: () => <div />,
  Tooltip: () => <div />, Legend: () => <div />, CartesianGrid: () => <div />,
}));

const ALL_CHANNELS = [
  { slug: "bollywood_mehfil",  name: "Bollywood Mehfil",  thumbnail_url: "/cdn/c1.png" },
  { slug: "morning_masala",    name: "Morning Masala",    thumbnail_url: "/cdn/c2.png" },
  { slug: "late_night_drive", name: "Late Night Drive", thumbnail_url: "/cdn/c3.png" },
];

beforeEach(() => {
  const axios = require("axios").default;
  axios.get.mockReset();   axios.post.mockReset();   axios.delete.mockReset();
  mockNavigate.mockReset = mockNavigate.mockReset;
  mockNavigate.mockReset();
  // Reset the shared zustand favorites store across tests.
  const { useFavoritesStore } = require("../store/useFavoritesStore");
  useFavoritesStore.setState({ favorites: [], cap: 8, loaded: false });
});


// ─── Test 1: BottomBarChannelStrip renders chips + click switches ──
test("Phase 18 bottom-bar channel strip renders chips + chip click switches channel", async () => {
  const axios = require("axios").default;
  axios.get.mockImplementation(async (url) => {
    if (url.endsWith("/favorites"))                 return { data: { favorites: [
      { channel_slug: "bollywood_mehfil",
        channel: { slug: "bollywood_mehfil", name: "Bollywood Mehfil",
                      thumbnail_url: "/cdn/c1.png" } },
    ], cap: 8 } };
    if (url.includes("/autoplay/suggestion"))
      return { data: { suggested_channel_slug: "morning_masala", is_cold_start: false,
                          top5: [
                            { channel_slug: "morning_masala", name: "Morning Masala",
                              thumbnail_url: "/cdn/c2.png" },
                            { channel_slug: "late_night_drive", name: "Late Night Drive",
                              thumbnail_url: "/cdn/c3.png" },
                          ] } };
    return { data: {} };
  });

  const { BottomBarChannelStrip } = require("../components/Phase18Home");
  // Bootstrap favorites store (component reads from it).
  const { useFavoritesStore } = require("../store/useFavoritesStore");
  await act(async () => { await useFavoritesStore.getState().bootstrap(); });
  const onSwitch = jest.fn();
  render(<BottomBarChannelStrip currentSlug="morning_masala" onSwitch={onSwitch} />);
  await waitFor(() => expect(screen.getByTestId("bottombar-chip-morning_masala")).toBeTruthy());
  // Chips: 1 favorite + 2 from autoplay top5 = 3.
  expect(screen.getByTestId("bottombar-chip-bollywood_mehfil")).toBeTruthy();
  expect(screen.getByTestId("bottombar-chip-late_night_drive")).toBeTruthy();
  // Click triggers onSwitch with the slug.
  fireEvent.click(screen.getByTestId("bottombar-chip-late_night_drive"));
  expect(onSwitch).toHaveBeenCalledWith("late_night_drive");
});


// ─── Test 2: MiniPlayer cold-start play hits autoplay/suggestion ────
test("Phase 18 mini-player cold-start play fetches /api/me/autoplay/suggestion", async () => {
  const axios = require("axios").default;
  axios.get.mockImplementation(async (url) => {
    if (url.includes("/autoplay/suggestion"))
      return { data: { suggested_channel_slug: "morning_masala", top5: [] } };
    if (url.endsWith("/favorites"))     return { data: { favorites: [], cap: 8 } };
    return { data: {} };
  });
  // Stub window.location.assign / href setter.
  delete window.location;
  window.location = { href: "" };

  // MUST mock zustand BEFORE the import — MiniPlayer subscribes at module-load.
  jest.doMock("../store/usePlayerStore", () => ({
    usePlayerStore: (sel) => sel({
      currentSeg: null, activeChannelName: null, activeChannelThumb: null,
      activeChannel: null, sessionId: null, playing: false,
    }),
  }));
  const { MiniPlayer } = require("../shell/primitives");
  render(<MiniPlayer />);
  await waitFor(() => expect(screen.getByTestId("bottom-player-play-button")).toBeTruthy());
  await act(async () => { fireEvent.click(screen.getByTestId("bottom-player-play-button")); });
  await waitFor(() => {
    expect(axios.get).toHaveBeenCalledWith(expect.stringContaining("/autoplay/suggestion"));
  });
  expect(window.location.href).toMatch(/\/radio\?ch=morning_masala/);
});


// ─── Test 3: Wallet GamesTab empty state ──────────────────────────
test("Phase 18 wallet GamesTab renders friendly empty state when no games", async () => {
  const axios = require("axios").default;
  axios.get.mockImplementation(async (url) => {
    if (url.includes("/games/state"))    return { data: { items: [], total: 0 } };
    if (url.endsWith("/bigcoin/me"))    return { data: { balance: 0 } };
    return { data: {} };
  });
  // Import lazily so the axios mock applies.
  const Wallet = require("../Wallet").default;
  await act(async () => { render(<Wallet />); });
  // The Wallet has tabs; click "Games" tab if it exists.
  const gamesTab = await waitFor(() => screen.getByTestId("tab-games"));
  await act(async () => { fireEvent.click(gamesTab); });
  await waitFor(() => expect(screen.getByTestId("games-empty-title")).toBeTruthy());
  expect(screen.getByTestId("games-empty-title").textContent).toMatch(/No games available/i);
  // CTA navigates to trivia.
  fireEvent.click(screen.getByTestId("games-empty-trivia-cta"));
  expect(mockNavigate).toHaveBeenCalledWith("/trivia");
});


// ─── Test 4: Commute explainer hero ───────────────────────────────
test("Phase 18 commute explainer hero renders headline + 3 bullets + CTA", async () => {
  const { CommuteExplainerHero } = require("../Commute");
  render(<CommuteExplainerHero />);
  await waitFor(() => expect(screen.getByTestId("commute-explainer-hero")).toBeTruthy());
  expect(screen.getByTestId("commute-hero-headline").textContent).toMatch(/Drive smarter/i);
  expect(screen.getByTestId("commute-hero-bullet-lunch")).toBeTruthy();
  expect(screen.getByTestId("commute-hero-bullet-rain")).toBeTruthy();
  expect(screen.getByTestId("commute-hero-bullet-friday")).toBeTruthy();
  expect(screen.getByTestId("commute-hero-cta")).toBeTruthy();
});


// ─── Test 4b: Coachmark mounts on first visit only ────────────────
test("Phase 18b commute coachmark mounts on first visit only", async () => {
  const CommuteCoachmark = require("../components/CommuteCoachmark").default;
  // 1️⃣  First visit: open=true → coachmark is in DOM.
  const onDismiss = jest.fn();
  const { rerender, unmount } = render(
    <CommuteCoachmark open={true} onDismiss={onDismiss} />);
  await waitFor(() => expect(screen.getByTestId("commute-coachmark")).toBeTruthy());
  // Step 1 title.
  expect(screen.getByTestId("commute-coachmark-title-0").textContent)
    .toMatch(/where you're headed/i);
  // Click Next → step 2 title.
  fireEvent.click(screen.getByTestId("commute-coachmark-next"));
  await waitFor(() => expect(screen.getByTestId("commute-coachmark-title-1")).toBeTruthy());
  fireEvent.click(screen.getByTestId("commute-coachmark-next"));
  await waitFor(() => expect(screen.getByTestId("commute-coachmark-title-2")).toBeTruthy());
  // Got it button on last step.
  fireEvent.click(screen.getByTestId("commute-coachmark-got-it"));
  expect(onDismiss).toHaveBeenCalled();
  // 2️⃣  Returning visit: open=false → coachmark NOT in DOM.
  rerender(<CommuteCoachmark open={false} onDismiss={onDismiss} />);
  expect(screen.queryByTestId("commute-coachmark")).toBeNull();
  unmount();
});


// ─── Test 5: Top-game rec card ─────────────────────────────────────
test("Phase 18 home top-game rec card renders name + Play again navigates", async () => {
  const axios = require("axios").default;
  axios.get.mockImplementation(async (url) => {
    if (url.includes("/top-game"))
      return { data: { game_id: "cmp_x123", name: "Karak Quiz Night",
                          last_played_at: new Date(Date.now() - 86400000).toISOString(),
                          play_count: 4, cold_start: false } };
    return { data: {} };
  });
  const { TopGameRecCard } = require("../components/Phase18Home");
  render(<TopGameRecCard />);
  await waitFor(() => expect(screen.getByTestId("home-rec-top-game")).toBeTruthy());
  expect(screen.getByTestId("home-rec-top-game-name").textContent).toMatch(/Karak Quiz Night/);
  fireEvent.click(screen.getByTestId("home-rec-top-game-play"));
  expect(mockNavigate).toHaveBeenCalledWith("/play-and-win?game=cmp_x123");
});


// ─── Test 6: Top-channel rec card ──────────────────────────────────
test("Phase 18 home top-channel rec card renders name + Resume navigates", async () => {
  const axios = require("axios").default;
  axios.get.mockImplementation(async (url) => {
    if (url.includes("/top-channel"))
      return { data: { slug: "morning_masala", name: "Morning Masala",
                          thumbnail_url: "/cdn/mm.png",
                          minutes_listened_30d: 252.0, cold_start: false } };
    return { data: {} };
  });
  const { TopChannelRecCard } = require("../components/Phase18Home");
  render(<TopChannelRecCard />);
  await waitFor(() => expect(screen.getByTestId("home-rec-top-channel")).toBeTruthy());
  expect(screen.getByTestId("home-rec-top-channel-name").textContent).toMatch(/Morning Masala/);
  fireEvent.click(screen.getByTestId("home-rec-top-channel-resume"));
  expect(mockNavigate).toHaveBeenCalledWith("/radio?ch=morning_masala");
});


// ─── Test 8: Boost CTA renders when eligible + confirm modal opens ──
test("Phase 17c Boost CTA renders when offer is boost_eligible", async () => {
  const axios = require("axios").default;
  axios.get.mockImplementation(async (url) => {
    if (url.includes("/funnel"))
      return { data: { impressions: 168, saves: 50, scans: 20, redeems: 5,
                                save_rate: 0.30, scan_rate: 0.40, redeem_rate: 0.25,
                                time_buckets: [], boost_eligible: true,
                                top_drop: { from: "impression", to: "save",
                                                  drop_pct: 70.2,
                                                  hint: "Push to wallet users to lift saves." } } };
    if (url.includes("/offers/ofr_test_001") && !url.includes("/boosts") && !url.includes("/funnel"))
      return { data: { offer: { id: "ofr_test_001", title: "Boostable",
                                          offer_type: "percent", discount_value: 15,
                                          status: "active" }, coupon_count: 0 } };
    if (url.includes("/boosts")) return { data: { boosts: [] } };
    return { data: {} };
  });
  const { OfferAnalyticsPanel } = require("../VenueOffers");
  render(<OfferAnalyticsPanel venue={{ id: "venue_demo_karak" }} offerId="ofr_test_001" />);
  await waitFor(() => expect(screen.getByTestId("analytics-boost-cta")).toBeTruthy());
  await act(async () => {
    fireEvent.click(screen.getByTestId("analytics-boost-cta"));
  });
  await waitFor(() => expect(screen.getByTestId("analytics-boost-confirm")).toBeTruthy());
  expect(screen.getByTestId("analytics-boost-confirm").textContent)
    .toMatch(/Fire a boost\?/i);
});


// ─── Test 9: Boost banner + countdown render after confirm ──────────
test("Phase 17c Boost banner with countdown renders after confirm", async () => {
  const axios = require("axios").default;
  const future = new Date(Date.now() + 23 * 3600 * 1000).toISOString();
  axios.get.mockImplementation(async (url) => {
    if (url.includes("/funnel"))
      return { data: { impressions: 200, saves: 60, scans: 25, redeems: 8,
                                save_rate: 0.30, scan_rate: 0.42, redeem_rate: 0.32,
                                time_buckets: [], boost_eligible: false,
                                top_drop: null } };
    if (url.includes("/boosts")) return { data: { boosts: [] } };
    if (url.includes("/offers/ofr_b") && !url.includes("/funnel"))
      return { data: { offer: { id: "ofr_b", title: "Already boosted",
                                          offer_type: "percent", discount_value: 20,
                                          status: "active", boost_active: true,
                                          boost_ends_at: future } } };
    return { data: {} };
  });
  const { OfferAnalyticsPanel } = require("../VenueOffers");
  render(<OfferAnalyticsPanel venue={{ id: "venue_demo_karak" }} offerId="ofr_b" />);
  await waitFor(() => expect(screen.getByTestId("analytics-boost-banner")).toBeTruthy());
  expect(screen.getByTestId("analytics-boost-banner").textContent).toMatch(/🔥 Boosted/);
  // Countdown element renders ("in Xh Ym").
  await waitFor(() => expect(screen.getByTestId("boost-countdown")).toBeTruthy());
  expect(screen.getByTestId("boost-countdown").textContent).toMatch(/in \d+h/);
});

test("Phase 18 favorites + icon opens picker + add updates strip", async () => {
  const axios = require("axios").default;
  let stored = [];
  axios.get.mockImplementation(async (url) => {
    if (url.endsWith("/favorites"))
      return { data: { favorites: stored.map((s) => ({
        channel_slug: s,
        channel: ALL_CHANNELS.find((c) => c.slug === s) })), cap: 8 } };
    return { data: {} };
  });
  axios.post.mockImplementation(async (url, body) => {
    if (url.endsWith("/favorites")) { stored.push(body.channel_slug); }
    return { data: { ok: true } };
  });
  const { FavoritesStrip, useFavoritesStore } =
    Object.assign({}, require("../components/Phase18Home"),
                                require("../store/useFavoritesStore"));
  render(<FavoritesStrip allChannels={ALL_CHANNELS} />);
  await waitFor(() => expect(screen.getByTestId("home-favorites-strip")).toBeTruthy());
  // Initial: empty strip + add button.
  expect(screen.getByTestId("home-favorites-add")).toBeTruthy();
  // Open picker.
  await act(async () => { fireEvent.click(screen.getByTestId("home-favorites-add")); });
  await waitFor(() => expect(screen.getByTestId("home-favorites-picker")).toBeTruthy());
  // Pick "bollywood_mehfil".
  await act(async () => {
    fireEvent.click(screen.getByTestId("home-favorites-picker-bollywood_mehfil"));
  });
  // axios.post called.
  expect(axios.post).toHaveBeenCalledWith(
    expect.stringContaining("/favorites"),
    expect.objectContaining({ channel_slug: "bollywood_mehfil" }),
  );
  // Strip now contains the chip.
  await waitFor(() => {
    expect(screen.getByTestId("home-favorite-chip-bollywood_mehfil")).toBeTruthy();
  });
});
