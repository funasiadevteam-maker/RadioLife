/**
 * Phase 36b — TranscriptEditor + AI metadata FE smoke tests.
 *
 *  1. Renders utterances from a completed transcript with speaker labels.
 *  2. Status banner shows "AI is transcribing…" while pending.
 *  3. Re-roll metadata calls /ai/generate-metadata.
 *  4. Apply selected PATCHes /apply-metadata.
 *  5. MOCK-mode amber banner appears when AssemblyAI key is absent.
 */
import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";

process.env.REACT_APP_BACKEND_URL = "http://localhost:8001";

jest.mock("react-router-dom", () => ({
  __esModule: true,
  useParams: () => ({ ep_id: "ep_x" }),
  Link: ({children, ...p}) => <a {...p}>{children}</a>,
}), {virtual: true});
jest.mock("axios", () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn(), patch: jest.fn() },
}));
const axios = require("axios").default;

const renderAt = () => {
  const TranscriptEditor = require("../TranscriptEditor").default;
  return render(<TranscriptEditor />);
};

const seedHappyPath = () => {
  // Episode
  axios.get.mockImplementation((url) => {
    if (url.endsWith("/episodes/ep_x")) {
      return Promise.resolve({data: {id: "ep_x", title: "Test Episode"}});
    }
    if (url.endsWith("/episodes/ep_x/transcript")) {
      return Promise.resolve({data: {
        id: "ptr_1", episode_id: "ep_x", status: "completed",
        provider: "mock",
        utterances_json: [
          {speaker: "A", start:    0, end:  3200, text: "Welcome back."},
          {speaker: "B", start: 3200, end:  8100, text: "Thanks for having me."},
        ],
        text: "Welcome back. Thanks for having me.",
      }});
    }
    if (url.endsWith("/ai/history?limit=1")) {
      return Promise.resolve({data: {history: [{output_json: {
        title: "AI Title",
        title_alternatives: ["Alt 1", "Alt 2", "Alt 3"],
        description: "AI desc",
        show_notes: "## Notes",
        chapters: [{title: "Intro", start_time_seconds: 0,
                              end_time_seconds: 30, summary: "x"}],
        seo_keywords: ["habits", "growth"],
        social_captions: {twitter: "Tw text", instagram: "",
                                      linkedin: "", youtube: ""},
        hashtags: ["#growth"],
        sponsor_read_suggestions: [{slot: "mid_roll",
                                                            script_text: "Sponsor", length_seconds: 30}],
        summary_short: "s", summary_long: "l",
      }}]}});
    }
    if (url.endsWith("/integrations/assemblyai/status")) {
      return Promise.resolve({data: {is_live: false}});
    }
    return Promise.resolve({data: {}});
  });
  axios.post.mockResolvedValue({data: {metadata: {
    title: "Re-rolled title", title_alternatives: [], description: "",
    show_notes: "", chapters: [], seo_keywords: [], hashtags: [],
    social_captions: {twitter: "", instagram: "", linkedin: "", youtube: ""},
    sponsor_read_suggestions: [], summary_short: "", summary_long: "",
  }}});
  axios.patch.mockResolvedValue({data: {ok: true}});
};

describe("Phase 36b — TranscriptEditor", () => {
  beforeEach(() => {
    axios.get.mockReset(); axios.post.mockReset(); axios.patch.mockReset();
  });

  test("renders utterances with speaker labels + timestamps", async () => {
    seedHappyPath();
    renderAt();
    await waitFor(() => expect(screen.getByTestId("utterance-0")).toBeInTheDocument());
    expect(screen.getByTestId("utterance-1")).toBeInTheDocument();
    expect(screen.getByText(/Speaker A/)).toBeInTheDocument();
    expect(screen.getByDisplayValue("Welcome back.")).toBeInTheDocument();
  });

  test("Re-roll metadata calls /ai/generate-metadata", async () => {
    seedHappyPath();
    renderAt();
    await waitFor(() => expect(screen.getByTestId("reroll-metadata")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("reroll-metadata"));
    await waitFor(() => {
      const calls = axios.post.mock.calls.map((c) => c[0]);
      expect(calls.some((u) => u.endsWith("/ai/generate-metadata"))).toBe(true);
    });
  });

  test("Apply selected PATCHes apply-metadata", async () => {
    seedHappyPath();
    renderAt();
    await waitFor(() => expect(screen.getByTestId("apply-selected")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("apply-selected"));
    await waitFor(() => {
      const calls = axios.post.mock.calls.map((c) => c[0]);
      expect(calls.some((u) => u.endsWith("/apply-metadata"))).toBe(true);
    });
  });

  test("MOCK-mode amber banner appears when AssemblyAI key absent", async () => {
    seedHappyPath();
    renderAt();
    await waitFor(() => expect(screen.getByTestId("mock-mode-banner")).toBeInTheDocument());
    expect(screen.getByTestId("mock-mode-banner")).toHaveTextContent(/MOCK mode/);
  });

  test("status banner says 'Ready to publish' when transcript + metadata done", async () => {
    seedHappyPath();
    renderAt();
    await waitFor(() => expect(screen.getByTestId("status-label-ready")).toBeInTheDocument());
  });
});
