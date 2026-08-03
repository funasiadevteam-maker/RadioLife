// Phase 36c Stage 4 polish — frontend regression tests.
//
// Covers the three new pieces dispatched:
//   1. Studio control row: resolution / camera-quality selector dispatch.
//   2. Grid-layout dropdown exposes the actual backend enum.
//   3. ConnectionQualityPill maps scores correctly (boundary cases).

import React from "react";
import {render, screen, fireEvent, waitFor, act}
  from "@testing-library/react";
import "@testing-library/jest-dom";

process.env.REACT_APP_BACKEND_URL = "http://localhost:8001";

const mockNav = jest.fn();
jest.mock("react-router-dom", () => ({
  __esModule: true,
  useParams:    () => ({sid: "prs_x"}),
  useNavigate: () => mockNav,
  Link: ({children, ...p}) => <a {...p}>{children}</a>,
}), {virtual: true});

jest.mock("axios", () => ({
  __esModule: true,
  default: {get: jest.fn(), post: jest.fn()},
}));
const axios = require("axios").default;

beforeAll(() => {
  // Polyfill mediaDevices for the StudioNew enumerate() call on mount.
  Object.defineProperty(navigator, "mediaDevices", {
    writable: true, value: {
      enumerateDevices: () => Promise.resolve([]),
      getUserMedia:        () => Promise.resolve({getTracks: () => []})}});
});

const seedStudioNew = () => {
  // creators/me → approved creator with channels[0].
  axios.get.mockImplementation((url) => {
    if (url.endsWith("/podcasts/creators/me"))
      return Promise.resolve({data: {creator: {id: "cr_x",
        application_status: "approved"}}});
    if (url.endsWith("/podcasts/creators/cr_x/channels"))
      return Promise.resolve({data: {channels: [{id: "pch_x",
        title: "Channel X", approval_status: "approved", active: true}]}});
    if (url.endsWith("/integrations/livekit/status"))
      return Promise.resolve({data: {is_live: false}});
    return Promise.resolve({data: {}});
  });
  axios.post.mockResolvedValue({data: {session_id: "prs_new"}});
};

describe("Phase 36c Stage 4 polish — Studio control row", () => {
  beforeEach(() => { jest.clearAllMocks(); });

  test("Grid-layout dropdown renders all 4 backend-enum options and "
            + "dispatches the chosen value on session-create", async () => {
    seedStudioNew();
    const {StudioNew} = require("../Studio");
    render(<StudioNew />);
    await waitFor(() => expect(screen.getByTestId("grid-layout-select"))
                                              .toBeInTheDocument());
    const sel = screen.getByTestId("grid-layout-select");
    const opts = Array.from(sel.querySelectorAll("option")).map((o) => o.value);
    expect(opts).toEqual(["auto", "side_by_side", "speaker_view", "2x2"]);
    expect(sel.value).toBe("auto");
    fireEvent.change(sel, {target: {value: "2x2"}});
    await act(async () => {
      fireEvent.click(screen.getByTestId("start-session-btn"));
    });
    expect(axios.post).toHaveBeenCalledWith(
      expect.stringContaining("/podcasts/creators/cr_x/recording-sessions"),
      expect.objectContaining({grid_layout: "2x2", video_enabled: false,
                                                    recording_mode: "solo"}),
      expect.any(Object));
    expect(screen.getByTestId("grid-layout-help")).toHaveTextContent(
      /screen-priority automatically/i);
  });

  test("Record-video toggle + Camera-quality selector render both options "
            + "(default 1080p) and forward video_enabled on create", async () => {
    seedStudioNew();
    const {StudioNew} = require("../Studio");
    render(<StudioNew />);
    await waitFor(() => expect(screen.getByTestId("record-video-toggle"))
                                              .toBeInTheDocument());
    // Initially hidden — only visible after toggle.
    expect(screen.queryByTestId("camera-quality-select")).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("record-video-toggle"));
    const sel = await screen.findByTestId("camera-quality-select");
    const opts = Array.from(sel.querySelectorAll("option")).map((o) => o.value);
    expect(opts).toEqual(["1080p", "720p"]);
    expect(sel.value).toBe("1080p");
    expect(screen.getByTestId("camera-quality-help")).toHaveTextContent(
      /Final mix is always 1080p/i);
    // Switch to 720p and start a session.
    fireEvent.change(sel, {target: {value: "720p"}});
    await act(async () => {
      fireEvent.click(screen.getByTestId("start-session-btn"));
    });
    expect(axios.post).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({video_enabled: true}),
      expect.any(Object));
  });
});

describe("Phase 36c Stage 4 polish — ConnectionQualityPill", () => {
  test("scoreToBand boundary cases: 0.75/0.74/0.40/0.39/null map correctly",
        () => {
    const {scoreToBand, QUALITY_BANDS} =
        require("../components/ConnectionQualityPill");
    expect(scoreToBand(0.75)).toBe(QUALITY_BANDS.GOOD);     // inclusive
    expect(scoreToBand(0.74)).toBe(QUALITY_BANDS.FAIR);
    expect(scoreToBand(0.40)).toBe(QUALITY_BANDS.FAIR);     // inclusive
    expect(scoreToBand(0.39)).toBe(QUALITY_BANDS.POOR);
    expect(scoreToBand(0.00)).toBe(QUALITY_BANDS.POOR);
    expect(scoreToBand(1.00)).toBe(QUALITY_BANDS.GOOD);
    expect(scoreToBand(null)).toBe(QUALITY_BANDS.UNKNOWN);
    expect(scoreToBand(undefined)).toBe(QUALITY_BANDS.UNKNOWN);
    expect(scoreToBand(NaN)).toBe(QUALITY_BANDS.UNKNOWN);
  });

  test("Pill renders Good / Fair / Poor + tooltip with rtt/jitter/loss", () => {
    const Pill = require("../components/ConnectionQualityPill").default;
    const {rerender} = render(<Pill score={0.9} rtt_ms={42} jitter_ms={6}
                                                      packet_loss_pct={0.1}
                                                      testid="pill" />);
    let el = screen.getByTestId("pill");
    expect(el).toHaveTextContent(/Good/i);
    expect(el.getAttribute("data-band")).toBe("good");
    expect(el.getAttribute("title")).toMatch(
      /RTT 42ms.+jitter 6ms.+loss 0\.1%/);
    rerender(<Pill score={0.5} rtt_ms={120} jitter_ms={15}
                            packet_loss_pct={1.2} testid="pill" />);
    el = screen.getByTestId("pill");
    expect(el).toHaveTextContent(/Fair/i);
    expect(el.getAttribute("data-band")).toBe("fair");
    rerender(<Pill score={0.2} rtt_ms={400} jitter_ms={120}
                            packet_loss_pct={8.7} testid="pill" />);
    el = screen.getByTestId("pill");
    expect(el).toHaveTextContent(/Poor/i);
    expect(el.getAttribute("data-band")).toBe("poor");
    expect(el.getAttribute("title")).toMatch(/loss 8\.7%/);
  });
});
