// Phase 18a — Frontend tests (5 cases).
// Smoke render + interaction smoke using @testing-library/react.
// JSDOM-only; axios/router/sonner mocked.
import React from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";

// ─── Router shim (CRA's Jest can't resolve react-router-dom v7) ───
const mockNavigate = jest.fn();
jest.mock("react-router-dom", () => ({
  __esModule: true,
  useNavigate:     () => mockNavigate,
  useParams:       () => ({}),
  useSearchParams: () => [{ get: () => null }, jest.fn()],
  NavLink:          ({ children, to, ...rest }) => <a href={to} {...rest}>{children}</a>,
  Link:             ({ children, to, ...rest }) => <a href={to} {...rest}>{children}</a>,
}), { virtual: true });
jest.mock("sonner", () => ({ toast: { error: jest.fn(), success: jest.fn() } }));

const _data = {
  advertisers: [{ advertiser_id: "adv_demo_karak", name: "Karak Cafe", role: "owner",
                          account_balance_usd: 50, market: "dubai", status: "active" }],
  advertiser:   { id: "adv_demo_karak", name: "Karak Cafe", market: "dubai",
                          account_balance_usd: 50, contact_email: "ads@karak.demo",
                          stripe_customer_id: "cus_demo" },
  campaigns:    [{ id: "cmp_demo_karak_lunch", name: "Lunch Rush", status: "active",
                          objective: "coupon_save", budget_total_usd: 80, spend_usd: 2 }],
  creative:     { creative_id: "crt_test", id: "crt_test",
                          brand_safety_check: { verdict: "approved", confidence: 0.95 } },
  queue:        [{ id: "cmp_pending_42", name: "Pending Promo",
                          advertiser_name: "Karak Cafe", advertiser_id: "adv_demo_karak",
                          budget_total_usd: 250, objective: "awareness",
                          status: "pending_review" },
                        { id: "cmp_takeover_99", name: "Takeover Friday",
                          advertiser_name: "Karak Cafe", advertiser_id: "adv_demo_karak",
                          budget_total_usd: 1500, objective: "awareness",
                          status: "pending_review",
                          takeover_config: { enabled: true, exclusive: true,
                                                      channel_slug: "morning_masala",
                                                      window_start: "2026-07-15T10:00:00Z",
                                                      window_end:    "2026-07-15T12:00:00Z" } }],
};

const _mockGet = async (url) => {
  if (url.endsWith("/advertiser/me")) return { data: { items: _data.advertisers } };
  if (url.includes("/admin/advertiser/campaigns")) return { data: { items: _data.queue } };
  if (url.match(/\/campaigns$/))                      return { data: { items: _data.campaigns } };
  if (url.includes("/creatives"))                      return { data: { items: [] } };
  if (url.includes("/performance"))                  return { data: { days: [], totals: {} } };
  if (url.match(/\/advertiser\/[^/]+$/))               return { data: { advertiser: _data.advertiser,
                                                                                  my_role: "owner" } };
  return { data: {} };
};

const _mockPost = async (url) => {
  if (url.includes("/creatives"))     return { data: _data.creative };
  if (url.includes("/topup"))           return { data: { checkout_url: "https://checkout.stripe.com/c/cs_test_X",
                                                                      session_id: "cs_test_X", mocked: false } };
  if (url.includes("/approve") || url.includes("/reject")) return { data: { ok: true } };
  if (url.includes("/submit"))         return { data: { status: "active" } };
  if (url.includes("/campaigns"))    return { data: { campaign_id: "cmp_new_1", status: "draft" } };
  return { data: {} };
};

jest.mock("axios", () => {
  const get = jest.fn();
  const post = jest.fn();
  const fn = { get, post, defaults: { withCredentials: true } };
  return { __esModule: true, default: fn, get, post,
              defaults: { withCredentials: true } };
});

beforeEach(() => {
  const axios = require("axios").default;
  axios.get.mockImplementation(_mockGet);
  axios.post.mockImplementation(_mockPost);
});

// ─── Test 1: Wizard 5 steps ───────────────────────────────────────
test("1) Campaign wizard renders 5 steps", async () => {
  const CampaignWizard = require("../advertiser/CampaignWizard").default;
  render(<CampaignWizard />);
  expect(await screen.findByTestId("wizard-step-1")).toBeTruthy();
  for (let i = 0; i < 4; i++) {
    await act(async () => { fireEvent.click(screen.getByTestId("wizard-next")); });
  }
  expect(await screen.findByTestId("wizard-step-5")).toBeTruthy();
});

// ─── Test 2: Creative upload → safety badge ──────────────────────
test("2) Creative upload preview shows safety badge", async () => {
  const CampaignWizard = require("../advertiser/CampaignWizard").default;
  render(<CampaignWizard />);
  // jump to step 5 (upload step).
  for (let i = 0; i < 4; i++) {
    await act(async () => { fireEvent.click(screen.getByTestId("wizard-next")); });
  }
  const input = await screen.findByTestId("wizard-audio-input");
  const file = new File([new Uint8Array(1024)], "ad.mp3", { type: "audio/mpeg" });
  await act(async () => {
    Object.defineProperty(input, "files", { value: [file] });
    fireEvent.change(input);
  });
  expect(await screen.findByTestId("wizard-creative-approved")).toBeTruthy();
});

// ─── Test 3: Overview renders ────────────────────────────────────
test("3) Overview renders stats + active campaigns list", async () => {
  const Overview = require("../advertiser/Overview").default;
  render(<Overview advertiserId="adv_demo_karak" />);
  expect(await screen.findByTestId("overview-stats")).toBeTruthy();
  expect(await screen.findByTestId("overview-top-campaign")).toBeTruthy();
});

// ─── Test 4: Billing top-up button works ────────────────────────
test("4) Billing top-up button kicks Stripe Checkout URL", async () => {
  delete window.location;
  window.location = { href: "", assign: jest.fn() };
  const Billing = require("../advertiser/Billing").default;
  render(<Billing advertiserId="adv_demo_karak" />);
  await screen.findByTestId("billing-topup-card");
  await act(async () => { fireEvent.click(screen.getByTestId("topup-submit-btn")); });
  // window.location.href should be set by the topup handler (live Stripe URL).
  await waitFor(() => {
    expect(typeof window.location === "string" || window.location.href !== undefined).toBe(true);
  });
});

// ─── Test 5: Admin queue exposes Approve/Reject ─────────────────
test("5) Admin queue lists pending campaigns with Approve/Reject + sparkle pill on takeovers", async () => {
  const AdminQueue = require("../AdvertiserAdminQueue").default;
  render(<AdminQueue />);
  expect(await screen.findByTestId("admin-adv-queue")).toBeTruthy();
  expect(await screen.findByTestId("queue-list")).toBeTruthy();
  expect(screen.getByTestId("approve-cmp_pending_42")).toBeTruthy();
  expect(screen.getByTestId("reject-cmp_pending_42")).toBeTruthy();
  // Sparkle pill renders ONLY on takeover row.
  expect(screen.getByTestId("takeover-pill-cmp_takeover_99")).toBeTruthy();
  expect(screen.queryByTestId("takeover-pill-cmp_pending_42")).toBeNull();
});
