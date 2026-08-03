// Phase 36c Stage 2 — Guest invites + Lobby + GuestJoin FE tests.

import React from "react";
import {render, screen, waitFor, fireEvent, act} from "@testing-library/react";
import "@testing-library/jest-dom";

process.env.REACT_APP_BACKEND_URL = "http://localhost:8001";

// react-router-dom is a peer module that's not always resolvable from
// jest's module map in this project. Mirror Phase36c.test.jsx's virtual mock.
// `mock` prefix lets it cross the jest factory boundary.
let mockToken = "tok_x";
jest.mock("react-router-dom", () => ({
  __esModule: true,
  useParams:    () => ({ sid: "prs_x", token: mockToken }),
  useNavigate: () => jest.fn(),
  Link: ({children, ...p}) => <a {...p}>{children}</a>,
}), {virtual: true});

jest.mock("axios", () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn() },
}));
const axios = require("axios").default;

// MediaRecorder + getUserMedia stubs (GuestJoin uses both).
beforeAll(() => {
  global.MediaRecorder = function MediaRecorder() {};
  global.MediaRecorder.isTypeSupported = () => true;
  Object.defineProperty(navigator, "mediaDevices", {
    writable: true, value: {
      getUserMedia: () => Promise.resolve({getTracks: () => []})}});
});

const baseSession = {
  id:                                  "prs_x",
  livekit_room_name:    "bigfm-prs_x",
  status:                            "recording",
  participants:                [{id: "host_x", role: "host", lobby_status: "admitted"}],
};

const seedStudio = (sess = baseSession, invites = [], partOverrides = []) => {
  const merged = {...sess, participants: [...sess.participants, ...partOverrides]};
  axios.get.mockImplementation((url) => {
    if (url.endsWith(`/podcasts/recording-sessions/prs_x/invites`))
      return Promise.resolve({data: {invites}});
    if (url.endsWith(`/podcasts/recording-sessions/prs_x`))
      return Promise.resolve({data: merged});
    if (url.endsWith("/integrations/livekit/status"))
      return Promise.resolve({data: {is_live: false}});
    return Promise.resolve({data: {}});
  });
  axios.post.mockResolvedValue({data: {
    ok: true, invite_id: "pgi_new", invite_token: "tok_new",
    invite_url: "https://example.com/studio/join/tok_new"}});
};

describe("Phase 36c Stage 2 — Studio Guests + Lobby panel", () => {
  beforeEach(() => { jest.clearAllMocks(); });

  test("Invite modal renders + submit creates invite + copy link banner", async () => {
    seedStudio();
    const Studio = require("../Studio").default;
    render(<Studio />);
    await waitFor(() => expect(screen.getByTestId("guests-panel")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("open-invite-modal-btn"));
    expect(screen.getByTestId("invite-modal")).toBeInTheDocument();
    fireEvent.change(screen.getByTestId("invite-name-input"),
      {target: {value: "Alex Guest"}});
    fireEvent.change(screen.getByTestId("invite-email-input"),
      {target: {value: "alex@example.com"}});
    await act(async () => {
      fireEvent.click(screen.getByTestId("invite-modal-submit"));
    });
    expect(axios.post).toHaveBeenCalledWith(
      expect.stringContaining("/podcasts/recording-sessions/prs_x/invite-guest"),
      expect.objectContaining({guest_name: "Alex Guest", guest_email: "alex@example.com"}),
      expect.any(Object));
    await waitFor(() => expect(screen.getByTestId("copy-link-banner")).toBeInTheDocument());
    expect(screen.getByTestId("copy-link-banner")).toHaveTextContent(/studio\/join\/tok_new/);
  });

  test("Active invites list shows status pills + cancel control", async () => {
    seedStudio(baseSession, [
      {id: "pgi_1", guest_name: "G1", guest_email: "g1@e.com",
        invite_token: "tok1", invite_status: "pending"},
      {id: "pgi_2", guest_name: "G2", guest_email: "g2@e.com",
        invite_token: "tok2", invite_status: "cancelled"},
    ]);
    const Studio = require("../Studio").default;
    render(<Studio />);
    await waitFor(() => expect(screen.getByTestId("invite-row-pgi_1")).toBeInTheDocument());
    expect(screen.getByTestId("invite-row-pgi_1")).toHaveTextContent(/pending/);
    expect(screen.getByTestId("invite-row-pgi_2")).toHaveTextContent(/cancelled/);
    expect(screen.getByTestId("cancel-invite-pgi_1")).toBeInTheDocument();
    expect(screen.queryByTestId("cancel-invite-pgi_2")).not.toBeInTheDocument();
    await act(async () => {
      fireEvent.click(screen.getByTestId("cancel-invite-pgi_1"));
    });
    expect(axios.post).toHaveBeenCalledWith(
      expect.stringContaining("/invites/pgi_1/cancel"),
      expect.any(Object), expect.any(Object));
  });

  test("Lobby ribbon shows waiting guests + admit/kick fire backend", async () => {
    seedStudio(baseSession, [], [
      {id: "p_g1", role: "guest", display_name: "Alex G",
        lobby_status: "lobby"},
    ]);
    const Studio = require("../Studio").default;
    render(<Studio />);
    await waitFor(() => expect(screen.getByTestId("lobby-ribbon")).toBeInTheDocument());
    expect(screen.getByTestId("lobby-row-p_g1")).toHaveTextContent("Alex G");
    await act(async () => {
      fireEvent.click(screen.getByTestId("admit-p_g1"));
    });
    expect(axios.post).toHaveBeenCalledWith(
      expect.stringContaining("/lobby/admit/p_g1"),
      expect.any(Object), expect.any(Object));
    await act(async () => {
      fireEvent.click(screen.getByTestId("kick-p_g1"));
    });
    expect(axios.post).toHaveBeenCalledWith(
      expect.stringContaining("/lobby/kick/p_g1"),
      expect.any(Object), expect.any(Object));
  });

  test("4-participant cap disables the Invite-guest button", async () => {
    seedStudio(baseSession, [], [
      {id: "p_g1", role: "guest", lobby_status: "admitted", display_name: "G1"},
      {id: "p_g2", role: "guest", lobby_status: "admitted", display_name: "G2"},
      {id: "p_g3", role: "guest", lobby_status: "lobby",      display_name: "G3"},
    ]);
    const Studio = require("../Studio").default;
    render(<Studio />);
    await waitFor(() =>
      expect(screen.getByTestId("open-invite-modal-btn")).toHaveTextContent(/Session full/));
    expect(screen.getByTestId("open-invite-modal-btn")).toBeDisabled();
  });
});

describe("Phase 36c Stage 2 — Public Guest landing", () => {
  beforeEach(() => { jest.clearAllMocks(); mockToken = "tok_x"; });

  test("GuestJoin renders consent text + inputs + Test-mic + Join-lobby (disabled until valid)", async () => {
    axios.get.mockImplementation((url) => {
      if (url.endsWith("/podcasts/studio/invites/tok_x"))
        return Promise.resolve({data: {
          invite_status: "pending",
          channel_title: "Morning Masala",
          recording_title: "Episode 7",
          host_display_name: "DJ Test",
          consent_required: true,
          consent_version: 1,
          consent_text: "By joining this recording, you grant DJ Test permission…",
          guest_email_prefilled: "alex@e.com",
          guest_name_prefilled: "",
        }});
      return Promise.resolve({data: {}});
    });
    const GuestJoin = require("../GuestJoin").default;
    render(<GuestJoin />);
    await waitFor(() => expect(screen.getByTestId("gjoin-heading")).toBeInTheDocument());
    expect(screen.getByTestId("gjoin-heading")).toHaveTextContent(/Morning Masala/);
    expect(screen.getByTestId("gjoin-heading")).toHaveTextContent(/DJ Test/);
    expect(screen.getByTestId("gjoin-consent-text")).toHaveTextContent(/By joining this recording/);
    expect(screen.getByTestId("gjoin-name-input")).toBeInTheDocument();
    expect(screen.getByTestId("gjoin-email-input")).toBeInTheDocument();
    expect(screen.getByTestId("gjoin-test-mic")).toBeInTheDocument();
    expect(screen.getByTestId("gjoin-submit")).toBeInTheDocument();
    expect(screen.getByTestId("gjoin-submit")).toBeDisabled();
    fireEvent.change(screen.getByTestId("gjoin-name-input"),
      {target: {value: "Alex Guest"}});
    fireEvent.click(screen.getByTestId("gjoin-consent-checkbox"));
    expect(screen.getByTestId("gjoin-submit")).not.toBeDisabled();
  });

  test("GuestJoin: expired invite → friendly error message", async () => {
    mockToken = "expired_tok";
    axios.get.mockRejectedValueOnce({
      response: {status: 410, data: {detail: {code: "invite_expired",
        message: "This invite has expired. Ask the host for a new one."}}}});
    const GuestJoin = require("../GuestJoin").default;
    render(<GuestJoin />);
    await waitFor(() => expect(screen.getByTestId("gjoin-error")).toBeInTheDocument());
    expect(screen.getByTestId("gjoin-error")).toHaveTextContent(/expired/i);
  });
});
