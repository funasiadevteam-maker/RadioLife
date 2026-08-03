// Phase 19a — Discoverability nav tests.
//
// Verifies role-aware sidebar entries (AppShell) and Home quick-actions
// strip render correctly for admin / creator / listener.

import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";

process.env.REACT_APP_BACKEND_URL = "http://localhost:8001";

// Mock react-router-dom (it ships ESM-only on v7 — Jest can't parse it).
jest.mock("react-router-dom", () => ({
  __esModule: true,
  Link:             ({ children, to, ...rest }) => <a href={to} {...rest}>{children}</a>,
  NavLink:          ({ children, to, ...rest }) => <a href={to} {...rest}>{children}</a>,
  useNavigate:     () => jest.fn(),
  useLocation:     () => ({ pathname: "/" }),
  useParams:       () => ({}),
  useSearchParams: () => [{ get: () => null }, jest.fn()],
}), { virtual: true });

// Mock AuthContext so we can vary role per test.
const mockAuth = { user: null, loading: false };
jest.mock("@/AuthContext", () => ({
  __esModule: true,
  useAuth:    () => mockAuth,
  API:                "http://localhost:8001/api",
  AuthProvider: ({ children }) => children,
}));

// Stub out heavy peripherals that AppShell + Home import.
jest.mock("framer-motion", () => {
  const R = require("react");
  return {
    __esModule: true,
    motion:                  new Proxy({}, { get: () => (p) => R.createElement("div", p, p.children) }),
    AnimatePresence: ({ children }) => R.createElement(R.Fragment, null, children),
  };
});
jest.mock("@/store/useGeoStore", () => ({
  __esModule: true,
  useGeoStore: (sel) => sel({ city: "Dubai", ready: true,
                                                  bootstrap: jest.fn() }),
}));
jest.mock("@/components/CityChip", () => ({
  __esModule: true, default: () => null }));
jest.mock("@/shell/useViewport", () => ({
  __esModule: true,
  useViewport: () => ({ layout: "desktop", width: 1920 }),
}));
jest.mock("@/shell/useKeyboardShortcuts", () => ({
  __esModule: true, useKeyboardShortcuts: jest.fn() }));
jest.mock("@/shell/primitives", () => {
  const R = require("react");
  return {
    __esModule: true,
    MiniPlayer:        () => null,
    Chip:                  ({ children }) => R.createElement("span", null, children),
    Button:             ({ children, onClick, ...p }) => R.createElement("button",
                                                                  { onClick, ...p }, children),
    Card:                  ({ children, ...p }) => R.createElement("div", p, children),
    StationTile:      () => null,
    GameTile:           () => null,
    WalletItemCard: () => null,
    LiveDot:             () => null,
  };
});
jest.mock("@/components/LocalNewsWidget", () => ({
  __esModule: true, default: () => null }));
jest.mock("@/components/Phase18Home", () => ({
  __esModule: true,
  TopGameRecCard:    () => null,
  TopChannelRecCard: () => null,
  FavoritesStrip:        () => null,
}));
// Home reaches axios for /channels + /bigcoin/me; stub to no-op.
jest.mock("axios", () => ({
  __esModule: true,
  default: {
    get:        () => new Promise(() => {}),    // never resolves → no state writes
    post:      () => new Promise(() => {}),
    delete: () => new Promise(() => {}),
  },
}));

describe("Phase 19a — role-aware sidebar nav", () => {
  let AppShell;
  beforeAll(() => { AppShell = require("@/shell/AppShell").default; });

  test("admin sees Highlights + Studio + Advertiser + Admin nav items", () => {
    mockAuth.user = { user_id: "u1", role: "admin",
                                  onboarding_complete: true };
    render(<AppShell><div>page</div></AppShell>);
    expect(screen.getByTestId("nav-highlights")).toBeInTheDocument();
    expect(screen.getByTestId("nav-studio")).toBeInTheDocument();
    expect(screen.getByTestId("nav-advertiser")).toBeInTheDocument();
    expect(screen.getByTestId("nav-admin")).toBeInTheDocument();
  });

  test("creator sees Highlights + Studio only", () => {
    mockAuth.user = { user_id: "u2", role: "creator",
                                  onboarding_complete: true };
    render(<AppShell><div>page</div></AppShell>);
    expect(screen.getByTestId("nav-highlights")).toBeInTheDocument();
    expect(screen.getByTestId("nav-studio")).toBeInTheDocument();
    expect(screen.queryByTestId("nav-advertiser")).toBeNull();
    expect(screen.queryByTestId("nav-admin")).toBeNull();
  });

  test("pure listener sees zero new nav items (unchanged)", () => {
    mockAuth.user = { user_id: "u3", role: "listener",
                                  onboarding_complete: true };
    render(<AppShell><div>page</div></AppShell>);
    expect(screen.queryByTestId("nav-highlights")).toBeNull();
    expect(screen.queryByTestId("nav-studio")).toBeNull();
    expect(screen.queryByTestId("nav-advertiser")).toBeNull();
    expect(screen.queryByTestId("nav-admin")).toBeNull();
    // sanity: existing listener nav still mounted
    expect(screen.getByTestId("nav-home")).toBeInTheDocument();
  });

  test("Home quick-actions strip is role-aware", () => {
    const Home = require("@/Home").default;
    // Admin → all 3 tiles.
    mockAuth.user = { user_id: "u1", role: "admin", name: "Admin",
                                  onboarding_complete: true };
    const { unmount } = render(<Home />);
    expect(screen.getByTestId("home-quick-admin")).toBeInTheDocument();
    expect(screen.getByTestId("home-quick-studio")).toBeInTheDocument();
    expect(screen.getByTestId("home-quick-advertiser")).toBeInTheDocument();
    unmount();
    // Creator → studio tile only.
    mockAuth.user = { user_id: "u2", role: "creator", name: "C",
                                  onboarding_complete: true };
    const { unmount: u2 } = render(<Home />);
    expect(screen.queryByTestId("home-quick-admin")).toBeNull();
    expect(screen.getByTestId("home-quick-studio")).toBeInTheDocument();
    expect(screen.queryByTestId("home-quick-advertiser")).toBeNull();
    u2();
    // Listener → no quick-actions strip at all.
    mockAuth.user = { user_id: "u3", role: "listener", name: "L",
                                  onboarding_complete: true };
    render(<Home />);
    expect(screen.queryByTestId("home-quick-actions")).toBeNull();
  });
});
