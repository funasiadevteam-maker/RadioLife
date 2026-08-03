// Phase 18c — 3 frontend smoke tests covering analytics-side surfaces.
import React from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";

jest.mock("react-router-dom", () => ({
  __esModule: true,
  useNavigate: () => jest.fn(),
  useParams:   () => ({}),
  useSearchParams: () => [{ get: () => null }, jest.fn()],
  Link:  ({ children, to, ...rest }) => <a href={to} {...rest}>{children}</a>,
  NavLink: ({ children, to, ...rest }) => <a href={to} {...rest}>{children}</a>,
}), { virtual: true });
jest.mock("sonner", () => ({ toast: { error: jest.fn(), success: jest.fn() } }));

// Mock axios for the three components.
const _attribution = {
  impressions: 240, coupon_saves: 12, redemptions: 4, checkins: 1,
  save_rate: 0.05, redeem_rate: 0.333, cpc_estimate: 0.6,
  cost_per_save: 0.6, cost_per_redeem: 1.8,
};
const _pacing_health = {
  ahead: [{ campaign_id: "cmp_ahead_1", name: "BBQ Pit Mega Push",
                  advertiser_id: "adv_bbq", spend_progress: 0.65,
                  time_progress: 0.40, status: "ahead",
                  projected_eob: 1762128000 }],
  behind: [{ campaign_id: "cmp_behind_1", name: "Karak Slow Burn",
                    advertiser_id: "adv_demo_karak", spend_progress: 0.10,
                    time_progress: 0.40, status: "behind", projected_eob: null }],
};
const _analytics = { range_days: 30, total_uploads: 12,
  auto_approve_rate: 0.667,
  verdict_counts: { approved: 8, review: 2, rejected: 2 },
  source_counts:    { ai_generated: 5, manual_upload: 7 },
  rejection_categories: {},
  stage_latency_ms_avg: {},
  pending_review_queue_depth: 3 };

jest.mock("axios", () => {
  const get  = jest.fn();
  const post = jest.fn();
  return { __esModule: true, default: { get, post, defaults: {} },
              get, post, defaults: {} };
});

beforeEach(() => {
  const axios = require("axios").default;
  axios.get.mockImplementation(async (url) => {
    if (url.includes("/pacing-health"))             return { data: _pacing_health };
    if (url.includes("/attribution"))                  return { data: _attribution };
    if (url.includes("/admin/advertiser/analytics")) return { data: _analytics };
    return { data: {} };
  });
});


test("1) Conversions tab renders the funnel numbers", async () => {
  const Conversions = require("../advertiser/ConversionsTab").default;
  render(<Conversions advertiserId="adv_demo_karak" campaignId="cmp_x" />);
  expect(await screen.findByTestId("conv-impressions")).toBeTruthy();
  expect(screen.getByTestId("conv-saves")).toBeTruthy();
  expect(screen.getByTestId("conv-redemptions")).toBeTruthy();
  expect(document.body.textContent).toMatch(/240/);
  expect(document.body.textContent).toMatch(/12/);
  expect(document.body.textContent).toMatch(/4/);
});


test("2) Pacing health panel lists at least one ahead campaign with throttle CTA", async () => {
  const PacingPanel = require("../advertiser/PacingHealthPanel").default;
  render(<PacingPanel />);
  expect(await screen.findByTestId("pacing-health-panel")).toBeTruthy();
  expect(await screen.findByTestId("pacing-ahead-cmp_ahead_1")).toBeTruthy();
  expect(await screen.findByTestId("pacing-behind-cmp_behind_1")).toBeTruthy();
});


test("3) Freq-cap editor (caps form) renders 5 default fields on campaign wizard", async () => {
  const CapsEditor = require("../advertiser/FreqCapsEditor").default;
  const onChange = jest.fn();
  render(<CapsEditor value={{}} onChange={onChange} />);
  expect(screen.getByTestId("cap-min_seconds_between")).toBeTruthy();
  expect(screen.getByTestId("cap-max_impressions_per_hour")).toBeTruthy();
  expect(screen.getByTestId("cap-max_impressions_per_day")).toBeTruthy();
  expect(screen.getByTestId("cap-max_per_advertiser_per_week")).toBeTruthy();
  expect(screen.getByTestId("cap-max_per_channel_cadence")).toBeTruthy();
  await act(async () => {
    fireEvent.change(screen.getByTestId("cap-max_impressions_per_hour"),
                                  { target: { value: "5" } });
  });
  await waitFor(() => expect(onChange).toHaveBeenCalled());
});
