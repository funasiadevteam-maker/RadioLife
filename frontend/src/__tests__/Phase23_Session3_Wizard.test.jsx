// Phase 23 Session 3 — Wizard frontend tests.  Covers:
//   1. Wizard renders 9-step indicator with the current step highlighted
//   2. Step advance / retreat changes the current step
//   3. Step 1 fetches templates and renders the cards
//   4. Step 7 publish button posts to the correct endpoint with the
//      creator_type derived from the URL (admin vs advertiser)
//   5. Admin-create entry on AdminGamesApproval shows the link to
//      /admin/games/new (and the route resolves to a wizard with the
//      admin creator-type pill visible)
import React from "react";
import { render, screen, fireEvent, act, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";

process.env.REACT_APP_BACKEND_URL = "http://localhost:8001";

const mockNavigate = jest.fn();
let mockPath = "/advertiser/games/new";
jest.mock("react-router-dom", () => ({
  __esModule: true,
  Link:              ({ children, to, ...rest }) => <a href={to} {...rest}>{children}</a>,
  useNavigate:      () => mockNavigate,
  useLocation:      () => ({ pathname: mockPath }),
  useParams:        () => ({}),
  useSearchParams: () => [new URLSearchParams(""), () => {}],
}), { virtual: true });

let mockUser = { user_id: "user_admin1", role: "admin", is_advertiser: true };
jest.mock("@/AuthContext", () => ({
  __esModule: true,
  useAuth: () => ({ user: mockUser, loading: false }),
  API: "http://localhost:8001/api",
}));

const mockCalls = { get: [], post: [], patch: [] };
jest.mock("axios", () => ({
  __esModule: true,
  default: {
    get:   (url) => { mockCalls.get.push(url);
                              if (url.includes("/advertiser/templates")) {
                                return Promise.resolve({ data: { templates: [
                                  { template_id: "tpl_spin_wheel",
                                      name: "Spin Wheel",
                                      description: "Daily spin",
                                      game_type: "spin_wheel",
                                      min_prizes: 2, max_prizes: 8,
                                      default_config_json: { segments: [] },
                                      active: true },
                                  { template_id: "tpl_scratch_card",
                                      name: "Scratch Card", description: "Reveal",
                                      game_type: "scratch_card", min_prizes: 1,
                                      max_prizes: 4,
                                      default_config_json: {}, active: true },
                                  { template_id: "tpl_quiz", name: "Quiz",
                                      description: "Trivia", game_type: "quiz",
                                      min_prizes: 1, max_prizes: 4,
                                      default_config_json: {}, active: true },
                                  { template_id: "tpl_mystery_box",
                                      name: "Mystery Box", description: "Pick a box",
                                      game_type: "mystery_box", min_prizes: 3,
                                      max_prizes: 9,
                                      default_config_json: {}, active: true },
                                  { template_id: "tpl_slot_machine",
                                      name: "Slot Machine", description: "Three reels",
                                      game_type: "slot_machine", min_prizes: 1,
                                      max_prizes: 5,
                                      default_config_json: {}, active: false },
                                ] } });
                              }
                              if (url.includes("/games_v2/admin/queue")) {
                                return Promise.resolve({ data: { items: [] } });
                              }
                              return Promise.resolve({ data: { items: [] } }); },
    post:  (url, body) => { mockCalls.post.push([url, body]);
                                          return Promise.resolve({
                                            data: { campaign_id: "cmp_x123" }
                                          }); },
    patch: (url, body) => { mockCalls.patch.push([url, body]);
                                          return Promise.resolve({ data: {} }); },
  },
}));

jest.mock("sonner", () => ({
  __esModule: true,
  Toaster: () => null,
  toast: { error: () => {}, success: () => {} },
}), { virtual: true });

beforeEach(() => {
  mockCalls.get.length = 0;
  mockCalls.post.length = 0;
  mockCalls.patch.length = 0;
  mockNavigate.mockClear();
});


describe("Phase 23 Session 3 — wizard frontend", () => {
  test("renders 9-step progress indicator and highlights step 1", async () => {
    mockPath = "/advertiser/games/new";
    const { AdvertiserGameWizard } = require("@/AdvertiserGames");
    await act(async () => { render(<AdvertiserGameWizard />); });
    const progress = await screen.findByTestId("wizard-progress");
    // Expect 9 step labels rendered (Template ... Placement & rules ... Review).
    const labels = progress.querySelectorAll(".wp-step");
    expect(labels.length).toBe(9);
    expect(labels[0].className).toMatch(/current/);
    // The 8th label (index 7) is the new step.
    expect(labels[7].textContent).toMatch(/Placement/);
  });

  test("fetches templates and renders 5 visible cards on Step 1 " +
                  "(slot_machine re-included as of Session 7)",
            async () => {
    mockPath = "/advertiser/games/new";
    const { AdvertiserGameWizard } = require("@/AdvertiserGames");
    await act(async () => { render(<AdvertiserGameWizard />); });
    await waitFor(() => {
      expect(screen.getByTestId("tpl-card-tpl_spin_wheel")).toBeInTheDocument();
    });
    expect(screen.getByTestId("tpl-card-tpl_scratch_card")).toBeInTheDocument();
    expect(screen.getByTestId("tpl-card-tpl_quiz")).toBeInTheDocument();
    expect(screen.getByTestId("tpl-card-tpl_mystery_box")).toBeInTheDocument();
    // Session 7 added slot_machine back to LISTENER_VISIBLE_TEMPLATES.
    expect(screen.getByTestId("tpl-card-tpl_slot_machine")).toBeInTheDocument();
    expect(mockCalls.get.some((u) =>
      u.includes("/games_v2/advertiser/templates"))).toBe(true);
  });

  test("step advance: clicking Next moves from Template to Branding",
            async () => {
    mockPath = "/advertiser/games/new";
    const { AdvertiserGameWizard } = require("@/AdvertiserGames");
    await act(async () => { render(<AdvertiserGameWizard />); });
    await waitFor(() =>
      expect(screen.getByTestId("tpl-card-tpl_spin_wheel"))
            .toBeInTheDocument());
    // Pick a template so Next is enabled.
    await act(async () => {
      fireEvent.click(screen.getByTestId("tpl-card-tpl_spin_wheel"));
    });
    expect(screen.getByTestId("wizard-next-btn")).not.toBeDisabled();
    await act(async () => {
      fireEvent.click(screen.getByTestId("wizard-next-btn"));
    });
    await waitFor(() => {
      expect(screen.getByTestId("wiz-title")).toBeInTheDocument();
    });
    // POST to /advertiser/campaigns happened for the advertiser path.
    expect(mockCalls.post.some(([u]) =>
      u.endsWith("/games_v2/advertiser/campaigns"))).toBe(true);
  });

  test("admin-create wizard sets creator_type=admin and posts to /admin/campaigns",
            async () => {
    mockPath = "/admin/games/new";
    const { AdvertiserGameWizard } = require("@/AdvertiserGames");
    await act(async () => { render(<AdvertiserGameWizard />); });
    await waitFor(() =>
      expect(screen.getByTestId("tpl-card-tpl_spin_wheel"))
            .toBeInTheDocument());
    await act(async () => {
      fireEvent.click(screen.getByTestId("tpl-card-tpl_spin_wheel"));
    });
    await act(async () => {
      fireEvent.click(screen.getByTestId("wizard-next-btn"));
    });
    // Admin-creator path posts to /games_v2/admin/campaigns and the
    // body carries creator_type="admin".
    const adminPost = mockCalls.post.find(([u]) =>
      u.endsWith("/games_v2/admin/campaigns"));
    expect(adminPost).toBeTruthy();
    expect(adminPost[1].creator_type).toBe("admin");
  });

  test("AdminGamesApproval shows '+ Admin create game' link",
            async () => {
    mockPath = "/admin/games-approval";
    const AdminGamesApproval = require("@/AdminGamesApproval").default;
    await act(async () => { render(<AdminGamesApproval />); });
    const btn = await screen.findByTestId("admin-create-game-btn");
    expect(btn).toHaveAttribute("href", "/admin/games/new");
  });
});
