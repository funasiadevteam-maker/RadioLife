// Phase 36e Turn 2 — Frontend tests for Conversion Funnel Dashboard.

import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";

process.env.REACT_APP_BACKEND_URL = "http://localhost:8001";

jest.mock("react-router-dom", () => ({
  __esModule: true,
  Link:                ({children,to,...r}) => <a href={to} {...r}>{children}</a>,
  useNavigate:    () => jest.fn(),
  useLocation:    () => ({pathname: "/"}),
  useParams:        () => ({creator_id: "crt_t"}),
}), { virtual: true });

const mockAxios = { get: jest.fn(), post: jest.fn() };
jest.mock("axios", () => ({__esModule: true, default: mockAxios}));

// Recharts requires DOM measurement APIs jsdom lacks — stub the wrapper.
jest.mock("recharts", () => {
  const M = {
    ResponsiveContainer: ({children}) => (
      <div data-testid="rc-stub">{children}</div>),
    LineChart:                  ({children}) => <div>{children}</div>,
    Line:                              () => null,
    XAxis:                            () => null,
    YAxis:                            () => null,
    Tooltip:                          () => null,
    CartesianGrid:            () => null,
    Legend:                          () => null,
  };
  return M;
});

beforeEach(() => {
  mockAxios.get.mockReset(); mockAxios.post.mockReset();
  localStorage.setItem("session_token", "test_token");
});

const SUMMARY_WITH_DATA = {
  window_days: 7,
  overall: {
    visits: 100, plays: 50, cta_clicks: 20, trials: 10, conversions: 4,
    visit_to_play: 0.5, play_to_cta: 0.4, cta_to_trial: 0.5, trial_to_paid: 0.4,
  },
  per_channel: [
    {channel_id: "pch_a", channel_name: "Channel A",
      visits: 60, plays: 30, cta_clicks: 12, trials: 6, conversions: 3,
      trial_to_paid: 0.5},
    {channel_id: "pch_b", channel_name: "Channel B",
      visits: 40, plays: 20, cta_clicks: 8, trials: 4, conversions: 1,
      trial_to_paid: 0.25},
  ],
};
const SERIES_7D = Array.from({length: 7}, (_, i) => ({
  date: `2026-06-${String(i + 1).padStart(2, "0")}`,
  visits: 10 + i, plays: 5 + i, cta_clicks: 2,
  trials: 1, conversions: 0,
}));

test("5 stage cards render with right counts + dropoff annotations", async () => {
  mockAxios.get.mockResolvedValueOnce({data: SUMMARY_WITH_DATA});
  mockAxios.get.mockResolvedValueOnce({data: {series: SERIES_7D}});
  const Dash = require("../CreatorFunnelDashboard").default;
  render(<Dash/>);
  await waitFor(() => screen.getByTestId("funnel-stage-strip"));
  // Counts.
  expect(screen.getByTestId("funnel-stage-visits-count")).toHaveTextContent("100");
  expect(screen.getByTestId("funnel-stage-plays-count")).toHaveTextContent("50");
  expect(screen.getByTestId("funnel-stage-cta_clicks-count")).toHaveTextContent("20");
  expect(screen.getByTestId("funnel-stage-trials-count")).toHaveTextContent("10");
  expect(screen.getByTestId("funnel-stage-conversions-count")).toHaveTextContent("4");
  // Dropoffs: 100→50 = 50%; 50→20 = 60%; 20→10 = 50%; 10→4 = 60%.
  expect(screen.getByTestId("funnel-stage-visits-dropoff")).toHaveTextContent(/50%/);
  expect(screen.getByTestId("funnel-stage-plays-dropoff")).toHaveTextContent(/60%/);
  expect(screen.getByTestId("funnel-stage-cta_clicks-dropoff")).toHaveTextContent(/50%/);
  expect(screen.getByTestId("funnel-stage-trials-dropoff")).toHaveTextContent(/60%/);
});

test("per-channel table sorts by column on header click", async () => {
  mockAxios.get.mockResolvedValueOnce({data: SUMMARY_WITH_DATA});
  mockAxios.get.mockResolvedValueOnce({data: {series: SERIES_7D}});
  const Dash = require("../CreatorFunnelDashboard").default;
  render(<Dash/>);
  await waitFor(() => screen.getByTestId("channel-table"));
  // Default sort: visits desc → Channel A (60) above Channel B (40).
  const rowsInit = screen.getAllByTestId(/^channel-row-/);
  expect(rowsInit[0]).toHaveAttribute("data-testid", "channel-row-pch_a");
  // Click conversions header → desc → A (3) above B (1).
  fireEvent.click(screen.getByTestId("channel-th-conversions"));
  const rows1 = screen.getAllByTestId(/^channel-row-/);
  expect(rows1[0]).toHaveAttribute("data-testid", "channel-row-pch_a");
  // Click again → asc → B (1) above A (3).
  fireEvent.click(screen.getByTestId("channel-th-conversions"));
  const rows2 = screen.getAllByTestId(/^channel-row-/);
  expect(rows2[0]).toHaveAttribute("data-testid", "channel-row-pch_b");
});

test("empty state shows when summary returns all-zero counts", async () => {
  const EMPTY = {
    window_days: 7,
    overall: {visits: 0, plays: 0, cta_clicks: 0, trials: 0, conversions: 0,
                          visit_to_play: 0, play_to_cta: 0, cta_to_trial: 0, trial_to_paid: 0},
    per_channel: [],
  };
  mockAxios.get.mockResolvedValueOnce({data: EMPTY});
  mockAxios.get.mockResolvedValueOnce({data: {series: []}});
  const Dash = require("../CreatorFunnelDashboard").default;
  render(<Dash/>);
  await waitFor(() => screen.getByTestId("funnel-empty-state"));
  expect(screen.getByTestId("funnel-empty-state"))
      .toHaveTextContent(/Your first .* days will appear here/);
  // Stage strip should NOT render in empty mode.
  expect(screen.queryByTestId("funnel-stage-strip")).toBeNull();
});
