/**
 * Phase 17a — Offer manager + scanner frontend tests (4).
 */
import React from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";

const mockNavigate = jest.fn();
jest.mock("react-router-dom", () => ({
  __esModule: true,
  useNavigate:     () => mockNavigate,
  useParams:       () => ({ offerId: "ofr_test_001" }),
  useSearchParams: () => [{ get: () => null }, jest.fn()],
  NavLink:          ({ children, to, ...rest }) => <a href={to} {...rest}>{children}</a>,
  Link:             ({ children, to, ...rest }) => <a href={to} {...rest}>{children}</a>,
}), { virtual: true });
jest.mock("sonner", () => ({ toast: { error: jest.fn(), success: jest.fn() } }));
jest.mock("../AuthContext", () => ({ API: "/api" }));

const _mockGet = async (url) => {
  if (url.endsWith("/venue/me")) {
    return { data: { venues: [{ id: "venue_demo_karak", name: "Demo Karak Cafe",
                                            market: "dubai", plan_tier: "growth" }] } };
  }
  if (url.endsWith("/offers?status=exhausted&limit=10")) {
    return { data: { offers: [{
      id: "ofr_ex1", title: "Free karak refill",
      auto_paused_reason: "daily_cap", status: "exhausted",
    }] } };
  }
  if (url.includes("/offers/ofr_test_001")) {
    return { data: { offer: {
      id: "ofr_test_001", title: "Happy hour 50% off",
      description: "All drinks half price", offer_type: "percent",
      discount_value: 50, status: "active", issued_count: 12,
      redeemed_count: 4, max_redemptions: 100, daily_cap: null,
      budget_cap_usd: null, redemption_method: "qr_scan",
      terms: "Dine-in only", start_time: null, end_time: null,
    }, coupon_count: 12 } };
  }
  return { data: { offers: [] } };
};

const _mockPost = async () => ({ data: {
  dry_run: true,
  would_create: 2, failed: 1,
  results: [
    { row: 2, status: "created", offer_id: "ofr_AAA" },
    { row: 3, status: "failed",  error: "title is required" },
    { row: 4, status: "created", offer_id: "ofr_BBB" },
  ],
} });

jest.mock("axios", () => {
  const get = jest.fn();
  const post = jest.fn();
  const del = jest.fn();
  const patch = jest.fn();
  const fn = { get, post, delete: del, patch, defaults: { withCredentials: true } };
  return { __esModule: true, default: fn, get, post, delete: del, patch,
              defaults: { withCredentials: true } };
});

beforeEach(() => {
  const axios = require("axios").default;
  axios.get.mockImplementation(_mockGet);
  axios.post.mockImplementation(_mockPost);
  axios.patch.mockImplementation(async () => ({ data: { ok: true } }));
  axios.delete.mockImplementation(async () => ({ data: { ok: true } }));
});

// ─── Test 1: bulk import dry-run shows per-row preview ───────────────
test("Phase 17a bulk import shows per-row preview with errors", async () => {
  const { VenueOfferImport } = require("../VenueOffers");
  render(<VenueOfferImport venue={{ id: "venue_demo_karak" }} />);
  // Simulate the file picker (browser-native input).
  const input = screen.getByTestId("offer-import-file");
  const file = new File(["title,offer_type,discount_value\n,percent,5"],
                                  "x.csv", { type: "text/csv" });
  await act(async () => {
    Object.defineProperty(input, "files", { value: [file] });
    fireEvent.change(input);
  });
  await act(async () => { fireEvent.click(screen.getByTestId("offer-import-dry-btn")); });
  const preview = await screen.findByTestId("offer-import-preview");
  expect(preview.textContent).toMatch(/Row 2.*created/);
  expect(preview.textContent).toMatch(/Row 3.*failed/);
  expect(preview.textContent).toContain("title is required");
});

// ─── Test 2: Scanner page renders viewfinder + manual fallback ──────
test("Phase 17a scan page renders viewfinder + manual fallback works", async () => {
  // getUserMedia mock so startCamera() doesn't blow up.
  Object.defineProperty(navigator, "mediaDevices", {
    value: { getUserMedia: jest.fn().mockResolvedValue({ getTracks: () => [] }) },
    configurable: true,
  });
  const { VenueScanRedeem } = require("../VenueOffers");
  render(<VenueScanRedeem venue={{ id: "venue_demo_karak" }} />);
  expect(screen.getByTestId("scan-viewfinder")).toBeTruthy();
  expect(screen.getByTestId("scan-start-btn")).toBeTruthy();
  expect(screen.getByTestId("scan-manual-input")).toBeTruthy();

  const axios = require("axios").default;
  axios.post.mockImplementationOnce(async () => ({
    data: { ok: true, coupon_id: "cpn_AAA", redeemed_at: "2026-06-02T00:00:00Z" },
  }));
  await act(async () => {
    fireEvent.change(screen.getByTestId("scan-manual-input"),
                              { target: { value: "cpn_AAA" } });
    fireEvent.click(screen.getByTestId("scan-manual-submit"));
  });
  expect(axios.post).toHaveBeenCalledWith(
    expect.stringContaining("/coupons/redeem"), { code: "cpn_AAA" },
  );
});

// ─── Test 3: Offer detail page tabs render ──────────────────────────
test("Phase 17a offer detail page renders Detail/Coupons/Analytics tabs", async () => {
  const { VenueOfferDetail } = require("../VenueOffers");
  render(<VenueOfferDetail venue={{ id: "venue_demo_karak" }} />);
  await waitFor(() => expect(screen.getByTestId("venue-offer-detail")).toBeTruthy());
  expect(screen.getByTestId("venue-offer-title").textContent).toContain("Happy hour 50% off");
  expect(screen.getByTestId("offer-tab-detail")).toBeTruthy();
  expect(screen.getByTestId("offer-tab-coupons")).toBeTruthy();
  expect(screen.getByTestId("offer-tab-analytics")).toBeTruthy();
  // Detail tab is default — switch to Analytics.
  await act(async () => { fireEvent.click(screen.getByTestId("offer-tab-analytics")); });
  expect(screen.getByTestId("offer-tab-analytics-body").textContent)
    .toContain("Funnel analytics");
});

// ─── Test 4: Auto-pause banner renders with resume CTA ───────────────
test("Phase 17a exhausted-offers banner renders + resume CTA", async () => {
  const { ExhaustedOffersBanner } = require("../VenueOffers");
  render(<ExhaustedOffersBanner venueId="venue_demo_karak" />);
  const banner = await screen.findByTestId("venue-exhausted-banner");
  expect(banner.textContent).toContain("Free karak refill");
  expect(banner.textContent).toContain("daily cap");
  // Resume button posts to the resume endpoint.
  const axios = require("axios").default;
  await act(async () => {
    fireEvent.click(screen.getByTestId("venue-exhausted-resume-ofr_ex1"));
  });
  expect(axios.post).toHaveBeenCalledWith(
    expect.stringContaining("/offers/ofr_ex1/resume"),
  );
});
