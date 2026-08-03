// Phase 18b — 4 frontend smoke tests for AI Ad Creator + Takeover SKU + analytics.
import React from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";

// ─── Router shim (CRA's Jest can't resolve react-router-dom v7) ───
const mockNavigate = jest.fn();
jest.mock("react-router-dom", () => ({
  __esModule: true,
  useNavigate:     () => mockNavigate,
  useParams:       () => ({}),
  useSearchParams: () => [{ get: () => null }, jest.fn()],
  NavLink:         ({ children, to, ...rest }) => <a href={to} {...rest}>{children}</a>,
  Link:            ({ children, to, ...rest }) => <a href={to} {...rest}>{children}</a>,
}), { virtual: true });
jest.mock("sonner", () => ({ toast: { error: jest.fn(), success: jest.fn() } }));

const _preview = {
  creative_id: "crt_ai_xx",
  script: "Karak Cafe — bring the family for lunch.",
  transcript: "Karak Cafe — bring the family for lunch.",
  audio_url:  "/api/static/ad_creatives/crt_ai_xx.mp3",
  audio_path: "/app/backend/static/ad_creatives/crt_ai_xx.mp3",
  audio_source: "elevenlabs",
  duration_sec: 14.8,
  image_url:  "/api/static/ad_creatives/crt_ai_xx.webp",
  image_skipped: false,
  voice_id: "maya",  voice_label: "Maya",
  tone: "friendly",  audio_length_sec: 15,
  brand_safety_check: { verdict: "approved", confidence: 0.95, issues: [] },
  verdict: "approved",
  vast_xml:  "<VAST/>",
  stage_latency_ms: { script: 900, voice: 1200, image: 1500, safety: 400 },
  total_latency_ms: 4000,
};

const _voices = [
  { id: "maya",  label: "Maya",  persona: "warm female" },
  { id: "aiden", label: "Aiden", persona: "smooth male" },
];

const _analytics = {
  range_days: 30, total_uploads: 12,
  auto_approve_rate: 0.667,
  verdict_counts: { approved: 8, review: 2, rejected: 2 },
  source_counts:    { ai_generated: 5, manual_upload: 7 },
  rejection_categories: { profanity: 1, gambling: 1 },
  stage_latency_ms_avg: { script: 900, voice: 1200, image: 1500 },
  pending_review_queue_depth: 3,
};

const _mockGet = async (url) => {
  if (url.endsWith("/advertiser/me"))
    return { data: { items: [{ advertiser_id: "adv_demo_karak",
                                                name: "Karak Cafe", market: "dubai" }] } };
  if (url.match(/\/ai\/voices$/))                  return { data: { items: _voices } };
  if (url.includes("/admin/advertiser/analytics")) return { data: _analytics };
  return { data: {} };
};
const _mockPost = async (url) => {
  if (url.endsWith("/ai/generate")) return { data: _preview };
  if (url.endsWith("/ai/save"))         return { data: { creative_id: "crt_ai_xx",
                                                                              status: "approved",
                                                                              brand_safety_check: _preview.brand_safety_check } };
  return { data: {} };
};

jest.mock("axios", () => {
  const get  = jest.fn();
  const post = jest.fn();
  return { __esModule: true, default: { get, post, defaults: { withCredentials: true } },
              get, post, defaults: { withCredentials: true } };
});

beforeEach(() => {
  const axios = require("axios").default;
  axios.get.mockImplementation(_mockGet);
  axios.post.mockImplementation(_mockPost);
});


// ─── Test 1: AI Ad Creator wizard renders + submit → preview ──────
test("1) AI Ad Creator renders form, generates, and shows preview", async () => {
  const AIAdCreator = require("../advertiser/AIAdCreator").default;
  render(<AIAdCreator />);
  expect(await screen.findByTestId("ai-form")).toBeTruthy();
  // Fill business + description.
  await act(async () => {
    fireEvent.change(screen.getByTestId("ai-business"),
                                  { target: { value: "Karak Cafe" } });
    fireEvent.change(screen.getByTestId("ai-description"),
                                  { target: { value: "Free dessert with any lunch combo." } });
  });
  await act(async () => { fireEvent.click(screen.getByTestId("ai-generate-btn")); });
  expect(await screen.findByTestId("ai-preview")).toBeTruthy();
  expect(screen.getByTestId("ai-transcript")).toBeTruthy();
  expect(screen.getByTestId("ai-audio")).toBeTruthy();
  expect(screen.getByTestId("ai-image")).toBeTruthy();
  expect(screen.getByTestId("ai-safety")).toBeTruthy();
});


// ─── Test 2: Regenerate calls the generate endpoint again ───────
test("2) Regenerate triggers a second generate call (re-roll)", async () => {
  const axios = require("axios").default;
  const AIAdCreator = require("../advertiser/AIAdCreator").default;
  render(<AIAdCreator />);
  await act(async () => {
    fireEvent.change(screen.getByTestId("ai-business"),
                                  { target: { value: "Karak" } });
    fireEvent.change(screen.getByTestId("ai-description"),
                                  { target: { value: "Lunch combo" } });
  });
  await act(async () => { fireEvent.click(screen.getByTestId("ai-generate-btn")); });
  await screen.findByTestId("ai-preview");
  const before = axios.post.mock.calls.filter((c) => c[0].endsWith("/ai/generate")).length;
  await act(async () => { fireEvent.click(screen.getByTestId("ai-regenerate")); });
  await waitFor(() => {
    const after = axios.post.mock.calls.filter((c) => c[0].endsWith("/ai/generate")).length;
    expect(after).toBeGreaterThan(before);
  });
});


// ─── Test 3: Takeover SKU unlocks only at $1000+ + awareness ─────
test("3) Takeover SKU card is locked below $1000 and unlocks at $1000+", async () => {
  const Wizard = require("../advertiser/CampaignWizard").default;
  const { rerender } = render(<Wizard />);
  // Default budget is $80 → locked card visible.
  expect(await screen.findByTestId("wizard-takeover-locked")).toBeTruthy();
  // Re-render forces no remount, but we can simulate the budget unlock by
  // navigating to step 4 (budget) and bumping it. Quick path: programmatically
  // tweak via the budget UI: jump to step 4.
  for (let i = 0; i < 3; i++) {
    await act(async () => { fireEvent.click(screen.getByTestId("wizard-next")); });
  }
  // step 4 has budget inputs. Find first number input and set it >= 1000.
  const numInputs = document.querySelectorAll('input[type="number"]');
  await act(async () => {
    fireEvent.change(numInputs[0], { target: { value: "1500" } });
  });
  // Step back to step 1 to see the unlocked card.
  for (let i = 0; i < 3; i++) {
    await act(async () => { fireEvent.click(screen.getByTestId("wizard-prev")); });
  }
  expect(await screen.findByTestId("wizard-obj-channel_takeover")).toBeTruthy();
});


// ─── Test 4: Admin analytics renders KPI cards + breakdown ────────
test("4) Admin analytics dashboard renders KPI cards + rejection breakdown", async () => {
  const Analytics = require("../AdvertiserAnalytics").default;
  render(<Analytics />);
  expect(await screen.findByTestId("kpi-approve-rate")).toBeTruthy();
  expect(screen.getByTestId("kpi-queue-depth")).toBeTruthy();
  expect(screen.getByTestId("kpi-ai-share")).toBeTruthy();
  expect(screen.getByTestId("kpi-rejections")).toBeTruthy();
  expect(screen.getByTestId("kpi-latency")).toBeTruthy();
  // Numbers
  expect(screen.getByText("67%")).toBeTruthy();
  expect(screen.getByText("3")).toBeTruthy();
});
