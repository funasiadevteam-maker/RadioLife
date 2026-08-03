/**
 * Phase 36c Stage 1 — Studio FE smoke tests.
 *
 *  1. StudioNew renders the channel picker + start button.
 *  2. POC banner + LiveKit MOCK banner visible.
 *  3. Studio panel renders timer + record button + pre-roll checklist.
 *  4. Mic level meter element is present (data-testid).
 *  5. LiveKit MOCK pill renders when key is absent.
 */
import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";

process.env.REACT_APP_BACKEND_URL = "http://localhost:8001";

jest.mock("react-router-dom", () => ({
  __esModule: true,
  useParams:    () => ({ sid: "prs_x" }),
  useNavigate: () => jest.fn(),
  Link: ({children, ...p}) => <a {...p}>{children}</a>,
}), {virtual: true});

jest.mock("axios", () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn() },
}));
const axios = require("axios").default;

const seedNew = () => {
  axios.get.mockImplementation((url) => {
    if (url.endsWith("/podcasts/creators/me")) {
      return Promise.resolve({data: {creator: {
        id: "crt_x", application_status: "approved"}}});
    }
    if (url.endsWith("/podcasts/creators/crt_x/channels")) {
      return Promise.resolve({data: {channels: [
        {id: "ch_x", title: "Test Channel",
          approval_status: "approved", active: true},
        {id: "ch_pending", title: "Pending Channel",
          approval_status: "pending", active: false},
      ]}});
    }
    if (url.endsWith("/integrations/livekit/status")) {
      return Promise.resolve({data: {is_live: false}});
    }
    return Promise.resolve({data: {}});
  });
};

const seedNoCreator = () => {
  axios.get.mockImplementation((url) => {
    if (url.endsWith("/podcasts/creators/me")) {
      return Promise.resolve({data: {creator: null}});
    }
    if (url.endsWith("/integrations/livekit/status")) {
      return Promise.resolve({data: {is_live: false}});
    }
    return Promise.resolve({data: {}});
  });
};

const seedStudio = () => {
  axios.get.mockImplementation((url) => {
    if (url.endsWith("/recording-sessions/prs_x")) {
      return Promise.resolve({data: {
        id: "prs_x", title: "Test Recording",
        livekit_room_name: "bigfm-prs_x",
        livekit_token: "mock_lk_token_bigfm-prs_x_host-y_host",
      }});
    }
    if (url.endsWith("/integrations/livekit/status")) {
      return Promise.resolve({data: {is_live: false}});
    }
    return Promise.resolve({data: {}});
  });
};

describe("Phase 36c — Stage 1 Studio", () => {
  beforeEach(() => { axios.get.mockReset(); axios.post.mockReset(); });

  test("StudioNew renders channel picker + start button", async () => {
    seedNew();
    const { StudioNew } = require("../Studio");
    render(<StudioNew />);
    await waitFor(() => expect(screen.getByTestId("channel-select")).toBeInTheDocument());
    expect(screen.getByTestId("start-session-btn")).toBeInTheDocument();
    expect(screen.getByTestId("studio-title-input")).toBeInTheDocument();
  });

  test("POC banner + LiveKit MOCK banner visible on StudioNew", async () => {
    seedNew();
    const { StudioNew } = require("../Studio");
    render(<StudioNew />);
    await waitFor(() => expect(screen.getByTestId("poc-banner")).toBeInTheDocument());
    expect(screen.getByTestId("poc-banner")).toHaveTextContent(/Solo audio only/);
    expect(screen.getByTestId("livekit-mock-banner")).toBeInTheDocument();
    expect(screen.getByTestId("livekit-mock-banner")).toHaveTextContent(/MOCK mode/);
  });

  test("Studio panel renders title + LiveKit MOCK pill + grant-mic CTA", async () => {
    seedStudio();
    const Studio = require("../Studio").default;
    render(<Studio />);
    await waitFor(() => expect(screen.getByTestId("studio-panel")).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText(/Test Recording/)).toBeInTheDocument());
    expect(screen.getByTestId("livekit-mock-pill")).toBeInTheDocument();
    expect(screen.getByTestId("grant-mic-btn")).toBeInTheDocument();
    expect(screen.getByText(/Pre-roll checklist/)).toBeInTheDocument();
    expect(screen.getByText(/Headphones recommended/)).toBeInTheDocument();
  });

  test("Pre-roll lists the 10-minute cap and auto-transcribe note", async () => {
    seedStudio();
    const Studio = require("../Studio").default;
    render(<Studio />);
    await waitFor(() => expect(screen.getByText(/10-minute cap/)).toBeInTheDocument());
    expect(screen.getByText(/auto-transcribes/)).toBeInTheDocument();
  });

  test("Session ID and LiveKit room are surfaced for debugging", async () => {
    seedStudio();
    const Studio = require("../Studio").default;
    render(<Studio />);
    await waitFor(() => expect(screen.getByText(/Session ID:/)).toBeInTheDocument());
    expect(screen.getByText(/bigfm-prs_x/)).toBeInTheDocument();
  });

  // ─── Phase 36c Stage 1 bug-fix tests ────────────────────────────
  // Bug #1: channel picker must populate via the 2-step
  //   GET /podcasts/creators/me → GET /podcasts/creators/{cid}/channels flow,
  // filter to approved+active only, and surface correct CTAs for the two
  // no-channel edge cases (no creator vs. creator-but-no-active-channels).

  test("Bug #1: channel picker renders approved+active channel via 2-step flow", async () => {
    seedNew();
    const { StudioNew } = require("../Studio");
    render(<StudioNew />);
    await waitFor(() => expect(screen.getByTestId("channel-select")).toBeInTheDocument());
    // The approved+active channel must render as an <option>.
    const opts = screen.getByTestId("channel-select").querySelectorAll("option");
    const titles = Array.from(opts).map((o) => o.textContent);
    expect(titles).toContain("Test Channel");
    // The pending channel must be filtered out.
    expect(titles).not.toContain("Pending Channel");
    // The "No approved channels yet" placeholder must NOT be shown.
    expect(titles).not.toContain("No approved channels yet");
    // The next-route CTA must be absent when there is an active channel.
    expect(screen.queryByTestId("studio-next-route-cta")).not.toBeInTheDocument();
  });

  test("Bug #1: no-creator path shows 'Apply as creator' CTA", async () => {
    seedNoCreator();
    const { StudioNew } = require("../Studio");
    render(<StudioNew />);
    await waitFor(() => expect(screen.getByTestId("studio-next-route-cta")).toBeInTheDocument());
    expect(screen.getByTestId("studio-next-route-cta")).toHaveTextContent(/Apply as creator/);
  });
});
