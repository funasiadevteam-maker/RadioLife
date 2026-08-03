// Phase 36e Turn 3 — Frontend tests for FirstEpisodeNudgeBanner.

import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";

process.env.REACT_APP_BACKEND_URL = "http://localhost:8001";

jest.mock("react-router-dom", () => ({
  __esModule: true,
  Link:                ({children,to,...r}) => <a href={to} {...r}>{children}</a>,
  useNavigate:    () => jest.fn(),
  useParams:        () => ({}),
}), { virtual: true });

const mockAxios = { get: jest.fn(), post: jest.fn() };
jest.mock("axios", () => ({__esModule: true, default: mockAxios}));

beforeEach(() => {
  mockAxios.get.mockReset(); mockAxios.post.mockReset();
});

test("banner renders for qualifying creator + hidden for non-qualifying", async () => {
  // Qualifying.
  mockAxios.get.mockResolvedValueOnce({data: {
    qualifies: true, nudges_paused: false,
    banner_message: "🎙️ Record your first episode to start building your audience",
    last_event: null}});
  const {FirstEpisodeNudgeBanner} = require("../FirstEpisodeNudgeBanner");
  const {unmount, container} = render(<FirstEpisodeNudgeBanner creatorId="crt_t"/>);
  await waitFor(() => screen.getByTestId("first-episode-nudge-banner"));
  expect(screen.getByTestId("nudge-banner-cta")).toBeInTheDocument();
  expect(screen.getByTestId("nudge-banner-pause")).toBeInTheDocument();
  expect(screen.getByText(/Record your first episode/i)).toBeInTheDocument();
  unmount();

  // Non-qualifying → renders nothing (null).
  mockAxios.get.mockResolvedValueOnce({data: {
    qualifies: false, reason: "already_published",
    nudges_paused: false, banner_message: null, last_event: null}});
  const {container: c2} = render(<FirstEpisodeNudgeBanner creatorId="crt_t"/>);
  await waitFor(() => expect(mockAxios.get).toHaveBeenCalledTimes(2));
  expect(screen.queryByTestId("first-episode-nudge-banner")).toBeNull();
});

test("pause button calls API + hides banner on next refresh", async () => {
  // Initial: qualifies=true.
  mockAxios.get.mockResolvedValueOnce({data: {
    qualifies: true, nudges_paused: false,
    banner_message: "🎙️ Record your first episode",
    last_event: null}});
  mockAxios.post.mockResolvedValueOnce({data: {nudges_paused: true}});
  // After pause: qualifies=false (paused).
  mockAxios.get.mockResolvedValueOnce({data: {
    qualifies: false, reason: "paused", nudges_paused: true,
    banner_message: null, last_event: null}});

  const {FirstEpisodeNudgeBanner} = require("../FirstEpisodeNudgeBanner");
  render(<FirstEpisodeNudgeBanner creatorId="crt_t"/>);
  await waitFor(() => screen.getByTestId("first-episode-nudge-banner"));

  fireEvent.click(screen.getByTestId("nudge-banner-pause"));
  await waitFor(() => expect(mockAxios.post).toHaveBeenCalled());
  expect(mockAxios.post.mock.calls[0][0]).toContain(
    "/podcasts/creators/crt_t/nudge-status/pause");
  // After pause, banner should be removed.
  await waitFor(() => expect(
    screen.queryByTestId("first-episode-nudge-banner")).toBeNull());
});
