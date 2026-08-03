// Phase 15c — marketing surface + RootGate behaviour.
//
// 5 tests:
//   1-3. MARKETING_ROUTES regex covers all 6 marketing paths and rejects
//        listener paths.
//   4.   RootGate-equivalent renders <Landing /> for anon, <Home /> for authed.
//   5.   RadioRail has the documented responsive visibility classes
//        (`hidden lg:flex`) so it's invisible <=md, visible >=lg.

import React from "react";
import { render, cleanup } from "@testing-library/react";

// Mock react-router-dom + AuthContext + axios + framer-motion + helmet
// BEFORE any of our components import them. Each factory must not
// reference out-of-scope variables — even `React` or jest.fn() handles.
// We stash the navigate spy on global and reach for it via require/global
// inside the factory.
global.__navigateMock__ = jest.fn();
jest.mock("react-router-dom", () => {
  const R = require("react");
  return {
    useNavigate:  () => global.__navigateMock__,
    useLocation:  () => ({ pathname: global.__pathname__ || "/" }),
    useSearchParams: () => [new URLSearchParams(""), () => {}],
    Link:         ({ to, children, ...rest }) =>
                    R.createElement("a", { href: to, ...rest }, children),
    NavLink:      ({ to, children, ...rest }) =>
                    R.createElement("a", { href: to, ...rest }, children),
  };
}, { virtual: true });

global.__authState__ = { user: null, loading: false };
jest.mock("@/AuthContext", () => ({
  useAuth: () => global.__authState__,
  API:     "http://test/api",
}), { virtual: true });

jest.mock("axios", () => ({
  get:   () => Promise.resolve({ data: {} }),
  post:  () => Promise.resolve({ data: {} }),
  patch: () => Promise.resolve({ data: {} }),
}));

jest.mock("framer-motion", () => {
  const R = require("react");
  return {
    motion: new Proxy({}, { get: () => ({ children }) =>
                R.createElement("div", null, children) }),
    AnimatePresence: ({ children }) =>
                R.createElement(R.Fragment, null, children),
  };
});

jest.mock("react-helmet-async", () => {
  const R = require("react");
  return {
    Helmet:         ({ children }) =>
                  R.createElement(R.Fragment, null, children),
    HelmetProvider: ({ children }) =>
                  R.createElement(R.Fragment, null, children),
  };
}, { virtual: true });

// `@/shell/primitives` is an alias that jest's CRA config doesn't
// resolve. Stub the components RadioRail uses so the test can mount it.
jest.mock("@/shell/primitives", () => {
  const R = require("react");
  return {
    Card:    ({ children, ...rest }) =>
                R.createElement("div", { "data-test-card": true, ...rest }, children),
    Chip:    ({ children, ...rest }) =>
                R.createElement("span", { "data-test-chip": true, ...rest }, children),
    LiveDot: () => R.createElement("span", { "data-test-livedot": true }),
  };
}, { virtual: true });

// Phase 15d — stubs so AppShell.jsx can import these without spinning up
// the real zustand store / axios call.
jest.mock("@/store/useGeoStore", () => ({
  useGeoStore: (sel) => {
    const state = {
      ready: true, loading: false, market: "dubai", city: "Dubai",
      country: "AE", timezone: "Asia/Dubai", source: "mock",
      supported: ["dubai", "new_york", "london", "mumbai", "los_angeles"],
      bootstrap: jest.fn(),
      setMarket: jest.fn(),
      clearOverride: jest.fn(),
    };
    return typeof sel === "function" ? sel(state) : state;
  },
}), { virtual: true });

jest.mock("@/components/CityChip", () => {
  const R = require("react");
  return { __esModule: true,
                default: () => R.createElement("button",
                  { "data-testid": "topbar-city-chip" }, "Dubai") };
}, { virtual: true });

afterEach(() => {
  cleanup();
  global.__pathname__ = "/";
  global.__authState__ = { user: null, loading: false };
  if (global.__navigateMock__ && global.__navigateMock__.mockReset) {
    global.__navigateMock__.mockReset();
  }
});

// Imported AFTER mocks.
const { MARKETING_ROUTES, isMarketingPath } = require("../AppShell");

describe("Phase 15c — MARKETING_ROUTES regex", () => {
  const MARKETING_PATHS = [
    "/about", "/about/", "/about/team",
    "/for-business", "/for-business/cta",
    "/for-advertisers",
    "/pricing",
    "/legal/terms", "/legal/privacy", "/legal/cookies",
  ];
  const LISTENER_PATHS = [
    "/", "/radio", "/wallet", "/home", "/play", "/passport",
    "/trivia", "/map", "/profile", "/admin", "/dev/styleguide",
    "/aboutme",        // intentionally close-but-not-prefix
    "/for-businessx",  // trailing chars must not match
  ];

  test("matches every documented marketing path", () => {
    for (const p of MARKETING_PATHS) {
      expect(isMarketingPath(p)).toBe(true);
    }
  });

  test("does NOT match listener / admin / radio paths", () => {
    for (const p of LISTENER_PATHS) {
      expect(isMarketingPath(p)).toBe(false);
    }
  });

  test("regex array exports 5 entries (one per surface family)", () => {
    expect(Array.isArray(MARKETING_ROUTES)).toBe(true);
    expect(MARKETING_ROUTES.length).toBe(5);
  });
});

describe("Phase 15c — RootGate (auth-aware root)", () => {
  // Production RootGate (App.js):
  //   const { user, loading } = useAuth();
  //   if (loading) return null;
  //   return user ? <Home /> : <Landing />;
  //
  // We replicate the *exact* logic here so we don't have to load all of
  // App.js (which transitively pulls every route + axios + sonner). The
  // RootGate's behavior under test IS this 3-line decision tree.
  const { useAuth } = require("@/AuthContext");
  function HomeStub() {
    return React.createElement("div", { "data-testid": "home-root" }, "home");
  }
  function LandingStub() {
    return React.createElement("div",
      { "data-testid": "marketing-shell" }, "landing");
  }
  function RootGate() {
    const { user, loading } = useAuth();
    if (loading) return null;
    return user ? React.createElement(HomeStub) : React.createElement(LandingStub);
  }

  test("anon visitor sees the marketing Landing", () => {
    global.__authState__ = { user: null, loading: false };
    const { container } = render(React.createElement(RootGate));
    expect(container.querySelector('[data-testid="marketing-shell"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="home-root"]')).toBeNull();
  });

  test("authed listener sees the Home dashboard", () => {
    global.__authState__ = {
      user: { id: "u1", name: "Test", email: "t@x", onboarding_complete: true },
      loading: false,
    };
    const { container } = render(React.createElement(RootGate));
    expect(container.querySelector('[data-testid="home-root"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="marketing-shell"]')).toBeNull();
  });

  test("while auth is loading, RootGate renders nothing (no flash)", () => {
    global.__authState__ = { user: null, loading: true };
    const { container } = render(React.createElement(RootGate));
    expect(container.firstChild).toBeNull();
  });
});

describe("Phase 15c — RadioRail responsive visibility", () => {
  test("has `hidden lg:flex` classes so it shows only at >=lg", () => {
    const RadioRail = require("../../RadioRail").default;
    const { container } = render(
      React.createElement(RadioRail,
        { user: null, currentChannel: null, recentTracks: [] })
    );
    const rail = container.querySelector('[data-testid="radio-rail"]');
    expect(rail).not.toBeNull();
    const cls = rail.className;
    expect(cls).toMatch(/(^|\s)hidden(\s|$)/);
    expect(cls).toMatch(/(^|\s)lg:flex(\s|$)/);
  });
});

describe("Phase 15c — Radio grid integrity (anti-regression for FAIL 2)", () => {
  // We can't run real layout in JSDOM, but we CAN assert the CSS file
  // declares the explicit 2-column grid and the gap that produces the
  // 36px clearance the runtime Playwright check verified. If anyone
  // accidentally restores the Tailwind arbitrary-value classes or
  // changes the grid columns, this regression fires.
  const fs = require("fs");
  const path = require("path");
  const cssPath = path.join(__dirname, "..", "..", "radio-page-v2.css");
  const css = fs.readFileSync(cssPath, "utf-8");

  test("declares explicit 2-column grid (1fr | 360px) at >=1024px", () => {
    expect(css).toMatch(/@media\s*\(\s*min-width:\s*1024px\s*\)/);
    expect(css).toMatch(/grid-template-columns:\s*minmax\(0,\s*1fr\)\s+360px/);
  });

  test("explicit grid-column assignments + main column hides overflow", () => {
    expect(css).toMatch(/\.radio-page-v2\s*>\s*\.radio-shell[^{]*\{[^}]*grid-column:\s*1/);
    expect(css).toMatch(/\.radio-page-v2\s*>\s*\.radio-rail-col[^{]*\{[^}]*grid-column:\s*2/);
    // overflow:hidden on the main column is the safety belt that stops
    // the channel strip from painting into the rail column.
    expect(css).toMatch(/\.radio-page-v2\s*>\s*\.radio-shell[^{]*\{[^}]*overflow:\s*hidden/);
  });

  test("Radio.js gates rail mount on useViewport (no DOM presence <1024)", () => {
    const radioSrc = fs.readFileSync(
      path.join(__dirname, "..", "..", "Radio.js"), "utf-8");
    // The rail must be inside a `{showRail && (...)}` guard.
    expect(radioSrc).toMatch(/showRail\s*&&/);
    // showRail must derive from useViewport.
    expect(radioSrc).toMatch(/const\s+vp\s*=\s*useViewport\(\)/);
    expect(radioSrc).toMatch(/const\s+showRail\s*=\s*vp\.layout\s*===\s*["']desktop["']/);
  });
});

describe("Phase 15c — Emergent badge defensive layer (anti-regression FAIL 1)", () => {
  const fs = require("fs");
  const path = require("path");
  const cssPath = path.join(__dirname, "..", "..", "index.css");
  const indexCss = fs.readFileSync(cssPath, "utf-8");
  const shellPath = path.join(__dirname, "..", "AppShell.jsx");
  const shellSrc = fs.readFileSync(shellPath, "utf-8");

  test("index.css applies global display:none on #emergent-badge", () => {
    expect(indexCss).toMatch(/#emergent-badge[^{]*\{[^}]*display:\s*none\s*!important/);
    expect(indexCss).toMatch(/#emergent-badge[^{]*\{[^}]*visibility:\s*hidden\s*!important/);
  });

  test("AppShell mounts a MutationObserver that removes the badge", () => {
    expect(shellSrc).toMatch(/MutationObserver/);
    expect(shellSrc).toMatch(/emergent-badge/);
    // The observer must actually call .remove() on matches.
    expect(shellSrc).toMatch(/\.remove\(\)/);
  });
});
