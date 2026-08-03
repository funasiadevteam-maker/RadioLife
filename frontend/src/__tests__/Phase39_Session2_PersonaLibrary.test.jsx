/**
 * Phase 39 Session 2 — Persona library + chat modal smoke tests.
 *
 * Mounts PersonaLibrary with mocked axios responses for /library + /me,
 * verifies rendering of 10 cards, sample-clip play, select call, and
 * the chat modal round-trip.
 */
import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";

process.env.REACT_APP_BACKEND_URL = "http://localhost:8001";

jest.mock("sonner", () => ({
  Toaster: () => null,
  toast:    { success: jest.fn(), error: jest.fn(), warning: jest.fn() },
}));
jest.mock("axios");
const axios = require("axios");

function mkPersona(idx, extra = {}) {
  return {
    persona_id: `p39_test_${idx}`,
    display_name: `Test Persona ${idx}`,
    archetype:    "test_archetype",
    description: `Description for ${idx}`,
    language_mix: ["English"],
    daypart_affinity: ["morning_drive"],
    signature_phrases_preview: ["a", "b"],
    sample_clip_url: `https://example.com/sample_${idx}.mp3`,
    ...extra,
  };
}

beforeEach(() => {
  jest.clearAllMocks();
  // Stub window.Audio so the JSDOM player doesn't throw.
  window.HTMLMediaElement.prototype.play = jest.fn().mockResolvedValue();
  window.HTMLMediaElement.prototype.pause = jest.fn();
});


describe("Phase 39 Session 2 — Persona library + chat", () => {
  test("renders 10 persona cards from /library", async () => {
    const personas = [...Array(10)].map((_, i) => mkPersona(i));
    axios.get.mockImplementation((url) => {
      if (url.endsWith("/api/personas/library"))
        return Promise.resolve({ data: { personas, count: 10 } });
      if (url.endsWith("/api/personas/me"))
        return Promise.resolve({ data: { persona: null,
                                                                    selected_persona_id: null,
                                                                    source: "no_selection" } });
      return Promise.reject(new Error("unexpected url"));
    });
    const PersonaLibrary = require("../PersonaLibrary").default;
    render(<PersonaLibrary />);
    await waitFor(() => screen.getByTestId("persona-library-page"));
    for (let i = 0; i < 10; i++) {
      expect(screen.getByTestId(`persona-card-p39_test_${i}`))
          .toBeInTheDocument();
    }
  });

  test("clicking sample triggers audio play", async () => {
    const personas = [mkPersona(0)];
    axios.get.mockImplementation((url) => {
      if (url.endsWith("/api/personas/library"))
        return Promise.resolve({ data: { personas, count: 1 } });
      return Promise.resolve({ data: { persona: null,
                                                                  selected_persona_id: null,
                                                                  source: "no_selection" } });
    });
    const PersonaLibrary = require("../PersonaLibrary").default;
    render(<PersonaLibrary />);
    await waitFor(() => screen.getByTestId("persona-card-p39_test_0"));
    fireEvent.click(screen.getByTestId("persona-sample-btn-p39_test_0"));
    expect(window.HTMLMediaElement.prototype.play).toHaveBeenCalled();
  });

  test("clicking Select calls /personas/select and shows badge",
        async () => {
    const personas = [mkPersona(0)];
    axios.get.mockImplementation((url) => {
      if (url.endsWith("/api/personas/library"))
        return Promise.resolve({ data: { personas, count: 1 } });
      return Promise.resolve({ data: { persona: null,
                                                                  selected_persona_id: null,
                                                                  source: "no_selection" } });
    });
    axios.post.mockResolvedValue({ data: {
      ok: true, selected_persona_id: "p39_test_0",
      persona: personas[0] }});
    const PersonaLibrary = require("../PersonaLibrary").default;
    render(<PersonaLibrary />);
    await waitFor(() => screen.getByTestId("persona-card-p39_test_0"));
    fireEvent.click(screen.getByTestId("persona-select-btn-p39_test_0"));
    await waitFor(() =>
      expect(axios.post).toHaveBeenCalledWith(
        expect.stringContaining("/api/personas/select"),
        { persona_id: "p39_test_0" },
        expect.any(Object)));
    await waitFor(() =>
      expect(screen.getByTestId("persona-selected-badge-p39_test_0"))
          .toBeInTheDocument());
  });

  test("chat modal opens, sends, and renders the response turn",
        async () => {
    const personas = [mkPersona(0)];
    axios.get.mockImplementation((url) => {
      if (url.endsWith("/api/personas/library"))
        return Promise.resolve({ data: { personas, count: 1 } });
      return Promise.resolve({ data: { persona: null,
                                                                  selected_persona_id: null,
                                                                  source: "no_selection" } });
    });
    axios.post.mockResolvedValue({ data: {
      ok: true,
      persona_id: "p39_test_0",
      persona_display_name: "Test Persona 0",
      response_text: "Good morning, friend!",
      response_audio_url: "https://example.com/resp.mp3",
    }});
    const PersonaLibrary = require("../PersonaLibrary").default;
    render(<PersonaLibrary />);
    await waitFor(() => screen.getByTestId("persona-card-p39_test_0"));
    fireEvent.click(screen.getByTestId("persona-chat-btn-p39_test_0"));
    expect(screen.getByTestId("persona-chat-modal")).toBeInTheDocument();
    const input = screen.getByTestId("persona-chat-input");
    fireEvent.change(input, { target: { value: "What time is it?" } });
    fireEvent.click(screen.getByTestId("persona-chat-send"));
    await waitFor(() =>
      expect(axios.post).toHaveBeenCalledWith(
        expect.stringContaining("/api/personas/chat"),
        expect.objectContaining({
          persona_id: "p39_test_0",
          listener_input_text: "What time is it?" }),
        expect.any(Object)));
    await waitFor(() =>
      expect(screen.getByText("Good morning, friend!"))
          .toBeInTheDocument());
    // Listener turn also visible.
    expect(screen.getByText("What time is it?")).toBeInTheDocument();
  });
});
