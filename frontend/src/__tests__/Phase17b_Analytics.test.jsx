/**
 * Phase 17b — Analytics, Variants, Org rollup, Payouts (4 tests).
 */
import React from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";

jest.mock("react-router-dom", () => ({
  __esModule: true,
  useNavigate:     () => jest.fn(),
  useParams:       () => ({ offerId: "ofr_test_001",
                                    venueId: "venue_demo_karak",
                                    orgId:    "org_karak_chain" }),
  useSearchParams: () => [{ get: () => null }, jest.fn()],
  NavLink:          ({ children, to, ...rest }) => <a href={to} {...rest}>{children}</a>,
  Link:             ({ children, to, ...rest }) => <a href={to} {...rest}>{children}</a>,
}), { virtual: true });
jest.mock("sonner", () => ({ toast: { error: jest.fn(), success: jest.fn() } }));
jest.mock("../AuthContext", () => ({ API: "/api" }));
// Mock recharts (no DOM rendering, just placeholders so dynamic import resolves).
jest.mock("recharts", () => ({
  __esModule: true,
  ResponsiveContainer: ({ children }) => <div>{children}</div>,
  BarChart:    ({ children }) => <div data-testid="mock-barchart">{children}</div>,
  Bar:          () => <div />,
  XAxis:        () => <div />,
  YAxis:        () => <div />,
  Tooltip:     () => <div />,
  Legend:      () => <div />,
  CartesianGrid: () => <div />,
}));

jest.mock("axios", () => {
  const get = jest.fn();
  const post = jest.fn();
  const del = jest.fn();
  const patch = jest.fn();
  const fn = { get, post, delete: del, patch, defaults: { withCredentials: true } };
  return { __esModule: true, default: fn, get, post, delete: del, patch,
              defaults: { withCredentials: true } };
});

const FUNNEL = {
  impressions: 100, saves: 60, scans: 24, redeems: 6,
  save_rate: 0.6, scan_rate: 0.4, redeem_rate: 0.25,
  time_buckets: [
    { day: "2026-06-01", impression: 50, save: 30, scan: 12, redeem: 3 },
    { day: "2026-06-02", impression: 50, save: 30, scan: 12, redeem: 3 },
  ],
  top_drop: { from: "save", to: "scan", drop_pct: 60.0,
                  hint: "Add a reminder push 1 hr before expiry." },
};

const VARIANTS = {
  variants: [
    { slug: "control", headline: "Hot karak — 25% off", weight: 50, status: "active",
      impressions: 100, saves: 20, scans: 10, redeems: 4, redeem_rate: 0.04,
      ci_lo: 0.01, ci_hi: 0.10 },
    { slug: "v1", headline: "Late-night 30% off karak", weight: 50, status: "active",
      impressions: 100, saves: 30, scans: 15, redeems: 8, redeem_rate: 0.08,
      ci_lo: 0.04, ci_hi: 0.15 },
  ],
  auto_winner_slug: null,
};

const ORG_ROLLUP = {
  org: { id: "org_karak_chain", name: "Karak Chain", primary_color: "#FF2D8A" },
  total_venues: 2,
  total_redemptions: 17,
  total_revenue_usd: 245.50,
  total_rooms: 1,
  best_offer: { id: "ofr_x", title: "Happy hour 50% off", venue_id: "venue_demo_karak",
                      redeemed: 12 },
  best_venue_id: "venue_demo_karak",
  venues: [
    { id: "venue_demo_karak", name: "Demo Karak Cafe", market: "dubai",
      redeems: 12, revenue_usd: 180.0, top_offer_title: "Happy hour 50% off" },
    { id: "venue_demo_karak_frisco", name: "Demo Karak Cafe — Frisco", market: "dfw",
      redeems: 5, revenue_usd: 65.5, top_offer_title: null },
  ],
};

const PAYOUTS = {
  period: { from: "2026-05-01", to: "2026-06-01" },
  bigcoin_liability_usd:              42.50,
  cash_redemptions_count:           17,
  cash_redemptions_value_usd:     245.50,
  ad_spend_net_usd:                   0.0,
  ad_spend_note:                      "Tracking arrives in Phase 18.",
  platform_cut_pct:                    5.0,
  net_platform_revenue_share_usd: 12.28,
  expected_payout_to_venue_usd:    233.22,
  time_buckets: [
    { day: "2026-05-30", redemptions: 8,  value_usd: 100.0, bigcoin_usd: 20.0 },
    { day: "2026-05-31", redemptions: 9,  value_usd: 145.5, bigcoin_usd: 22.5 },
  ],
};

beforeEach(() => {
  const axios = require("axios").default;
  axios.get.mockReset();
  axios.post.mockReset();
  axios.get.mockImplementation(async (url) => {
    if (url.includes("/funnel"))            return { data: FUNNEL };
    if (url.includes("/variants/results")) return { data: VARIANTS };
    if (url.includes("/orgs/") && url.includes("/rollup")) return { data: ORG_ROLLUP };
    if (url.includes("/payouts"))         return { data: PAYOUTS };
    if (url.endsWith("/venue/me"))
      return { data: { venues: [{ id: "venue_demo_karak", name: "Demo Karak Cafe",
                                              market: "dubai", plan_tier: "growth" }] } };
    if (url.includes("/offers/ofr_test_001"))
      return { data: { offer: { id: "ofr_test_001", title: "Test offer",
                                            offer_type: "percent", discount_value: 25,
                                            status: "active", issued_count: 0, redeemed_count: 0,
                                            max_redemptions: 100, redemption_method: "qr_scan" },
                          coupon_count: 0 } };
    return { data: {} };
  });
  axios.post.mockResolvedValue({ data: { ok: true } });
});


// ─── Test 1: Analytics tab renders 4 stat cards + bar chart ──────
test("Phase 17b analytics tab renders funnel stat cards + bar chart + top-drop", async () => {
  const { OfferAnalyticsPanel } = require("../VenueOffers");
  render(<OfferAnalyticsPanel venue={{ id: "venue_demo_karak" }} offerId="ofr_test_001" />);
  await waitFor(() => expect(screen.getByTestId("offer-tab-analytics-body")).toBeTruthy());
  // 4 stat cards.
  expect(screen.getByTestId("analytics-stat-impressions").textContent).toMatch(/100/);
  expect(screen.getByTestId("analytics-stat-saves").textContent).toMatch(/60/);
  expect(screen.getByTestId("analytics-stat-scans").textContent).toMatch(/24/);
  expect(screen.getByTestId("analytics-stat-redeems").textContent).toMatch(/6/);
  // Top-drop callout.
  const td = screen.getByTestId("analytics-top-drop");
  expect(td.textContent).toMatch(/60/);
  expect(td.textContent).toMatch(/reminder push/i);
  // Bar chart container present (lazy import resolved via mock).
  await waitFor(() => expect(screen.getByTestId("analytics-chart")).toBeTruthy());
});


// ─── Test 2: Variants tab — create + side-by-side preview ────────
test("Phase 17b variants tab renders variants + create form submits", async () => {
  const { OfferVariantsPanel } = require("../VenueOffers");
  render(<OfferVariantsPanel venue={{ id: "venue_demo_karak" }} offerId="ofr_test_001" />);
  await waitFor(() => expect(screen.getByTestId("offer-tab-variants-body")).toBeTruthy());
  // Both variant cards render side-by-side.
  expect(screen.getByTestId("variant-card-control")).toBeTruthy();
  expect(screen.getByTestId("variant-card-v1")).toBeTruthy();
  expect(screen.getByTestId("variant-card-v1").textContent).toMatch(/Late-night/);
  // Create-form submit.
  const axios = require("axios").default;
  await act(async () => {
    fireEvent.change(screen.getByTestId("variants-headline-input"),
                              { target: { value: "Buy 1 karak get 1 free" } });
    fireEvent.click(screen.getByTestId("variants-create-submit"));
  });
  expect(axios.post).toHaveBeenCalledWith(
    expect.stringContaining("/offers/ofr_test_001/variants"),
    expect.objectContaining({ headline: "Buy 1 karak get 1 free" }),
  );
});


// ─── Test 3: Org rollup page renders venue cards ──────────────────
test("Phase 17b org rollup renders 4 stat cards + venue list cards", async () => {
  const VenueOrgRollup = require("../VenueOrg").default;
  render(<VenueOrgRollup />);
  await waitFor(() => expect(screen.getByTestId("venue-org-rollup")).toBeTruthy());
  expect(screen.getByTestId("org-name").textContent).toMatch(/Karak Chain/);
  const cards = screen.getByTestId("org-stat-cards");
  expect(cards.textContent).toMatch(/Total venues/);
  expect(cards.textContent).toMatch(/Redemptions/);
  expect(cards.textContent).toMatch(/Cash redeemed/);
  expect(cards.textContent).toMatch(/Best offer/);
  // 2 venue cards rendered with their names.
  expect(screen.getByTestId("org-venue-card-venue_demo_karak")).toBeTruthy();
  expect(screen.getByTestId("org-venue-card-venue_demo_karak_frisco")).toBeTruthy();
  expect(screen.getByTestId("org-venue-card-venue_demo_karak").textContent).toMatch(/Demo Karak Cafe/);
});


// ─── Test 4: Payouts CSV export button triggers download ──────────
test("Phase 17b payouts CSV export button triggers a download", async () => {
  // window.open mock.
  const openSpy = jest.spyOn(window, "open").mockImplementation(() => null);
  const { VenuePayouts } = require("../VenueOrg");
  render(<VenuePayouts />);
  await waitFor(() => expect(screen.getByTestId("venue-payouts-page")).toBeTruthy());
  // 4 stat cards.
  const stats = screen.getByTestId("payouts-stats");
  expect(stats.textContent).toMatch(/233\.22/);
  expect(stats.textContent).toMatch(/245\.5/);
  // Click export → window.open hit with /export.csv.
  await act(async () => {
    fireEvent.click(screen.getByTestId("payouts-export-csv"));
  });
  expect(openSpy).toHaveBeenCalledWith(
    expect.stringMatching(/\/venue\/venue_demo_karak\/payouts\/export\.csv/),
    "_blank",
  );
  openSpy.mockRestore();
});
