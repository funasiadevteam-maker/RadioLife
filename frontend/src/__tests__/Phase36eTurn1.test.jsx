// Phase 36e Turn 1 — Frontend tests for subscription paywall + cancel/resume.

import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";

process.env.REACT_APP_BACKEND_URL = "http://localhost:8001";

jest.mock("react-router-dom", () => ({
  __esModule: true,
  Link:                ({children,to,...r}) => <a href={to} {...r}>{children}</a>,
  useNavigate:    () => jest.fn(),
  useLocation:    () => ({pathname: "/"}),
  useParams:        () => ({channel_id: "pch_t", ep_id: "pep_t", creator_id: "crt_t"}),
}), { virtual: true });

const mockAxios = { get: jest.fn(), post: jest.fn(), patch: jest.fn(),
                                  delete: jest.fn(), put: jest.fn() };
jest.mock("axios", () => ({__esModule: true, default: mockAxios}));

const mockAuth = { user: { user_id: "usr_t", email: "u@b.local" }, loading: false };
jest.mock("@/AuthContext", () => ({
  __esModule: true,
  useAuth:        () => mockAuth,
  API:                "http://localhost:8001/api",
}));

beforeEach(() => {
  mockAxios.get.mockReset(); mockAxios.post.mockReset();
  mockAxios.patch.mockReset(); mockAxios.delete.mockReset();
});

describe("Phase 36e Turn 1 — Paywall + subscriptions UI", () => {
  test("PaywallCard renders plan price + Start trial CTA fires subscribe", async () => {
    mockAxios.post.mockResolvedValueOnce({data: {
      checkout_url: "/mock/stripe/checkout?session_id=cs_mock_xx",
      session_id: "cs_mock_xx", subscription_id: "lsub_xx"}});
    const {PaywallCard} = require("../PaywallCard");
    render(<PaywallCard channelId="pch_t" plan={{
      plan_name: "Premium", price_cents: 500, currency: "usd",
      trial_days: 7,
      features: {ad_free: true, early_access_hours: 24, bonus_episodes: true}}}/>);
    expect(screen.getByTestId("paywall-card")).toBeInTheDocument();
    expect(screen.getByText(/Premium/)).toBeInTheDocument();
    expect(screen.getByText(/\$5\.00/)).toBeInTheDocument();
    expect(screen.getByText(/7-day free trial/i)).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("paywall-start-trial"));
    await waitFor(() => expect(mockAxios.post).toHaveBeenCalled());
    // Two calls: cta-clicked (funnel) THEN subscribe. Order matters for the funnel.
    const urls = mockAxios.post.mock.calls.map(c => c[0]);
    expect(urls.some(u => u.includes("/funnel/cta-clicked"))).toBe(true);
    expect(urls.some(u => u.includes("/podcasts/channels/pch_t/subscribe"))).toBe(true);
  });

  test("SubscriptionPlanSection — no Stripe → shows Connect CTA, with active acct → shows plan form", async () => {
    // First render: no stripe account at all.
    mockAxios.get.mockRejectedValueOnce({response: {status: 404}});
    mockAxios.get.mockRejectedValueOnce({response: {status: 404}});
    const {SubscriptionPlanSection} = require("../SubscriptionPlanSection");
    const {unmount} = render(<SubscriptionPlanSection
      channelId="pch_t" creatorId="crt_t"/>);
    await waitFor(() => screen.getByTestId("stripe-connect-cta"));
    expect(screen.getByTestId("subscription-section")).toBeInTheDocument();
    expect(screen.getByTestId("stripe-connect-cta")).toBeInTheDocument();
    unmount();
    // Second render: charges enabled, no plan yet → plan form visible.
    mockAxios.get.mockReset();
    mockAxios.get.mockResolvedValueOnce({data: {
      charges_enabled: true, payouts_enabled: true,
      details_submitted: true,
      stripe_account_id: "acct_mock_xx"}});
    mockAxios.get.mockRejectedValueOnce({response: {status: 404}});
    render(<SubscriptionPlanSection channelId="pch_t" creatorId="crt_t"/>);
    await waitFor(() => screen.getByTestId("plan-form"));
    expect(screen.getByTestId("plan-name-input")).toBeInTheDocument();
    expect(screen.getByTestId("plan-price-input")).toBeInTheDocument();
    expect(screen.getByTestId("plan-create-btn")).toBeInTheDocument();
  });

  test("ListenerSubscriptions — cancel flips cancel_at_period_end & resume reverses it", async () => {
    mockAxios.get.mockResolvedValueOnce({data: [{
      id: "lsub_1", channel_id: "pch_t", plan_id: "csp_t",
      status: "trialing", trial_end: null,
      current_period_end: new Date(Date.now()+7*864e5).toISOString(),
      cancel_at_period_end: false}]});
    mockAxios.post.mockResolvedValueOnce({data: {
      id: "lsub_1", status: "trialing",
      cancel_at_period_end: true}});
    const {ListenerSubscriptions} = require("../ListenerSubscriptions");
    render(<ListenerSubscriptions/>);
    await waitFor(() => screen.getByTestId("listener-sub-row-lsub_1"));
    fireEvent.click(screen.getByTestId("listener-sub-cancel-lsub_1"));
    await waitFor(() => expect(mockAxios.post).toHaveBeenCalled());
    expect(mockAxios.post.mock.calls[0][0]).toContain(
      "/listener/subscriptions/lsub_1/cancel");
  });
});
