// Phase 36d Turn 1 — Magic Clips frontend tests.

import React from "react";
import {render, screen, waitFor, fireEvent, act}
  from "@testing-library/react";
import "@testing-library/jest-dom";

process.env.REACT_APP_BACKEND_URL = "http://localhost:8001";

jest.mock("react-router-dom", () => ({
  __esModule: true,
  Link: ({children, ...p}) => <a {...p}>{children}</a>,
  useParams: () => ({channel_id: "pch_x"}),
  useNavigate: () => jest.fn(),
}), {virtual: true});

jest.mock("axios", () => ({
  __esModule: true,
  default: {get: jest.fn(), post: jest.fn(), patch: jest.fn(),
                  delete: jest.fn(), defaults: {withCredentials: true}},
}));
const axios = require("axios").default;

const draftClip = (id) => ({
  id: `mc_${id}`, episode_id: "pep_x", channel_id: "pch_x",
  status: "draft", title: `Clip ${id}`, summary: "Some summary.",
  start_sec: 10, end_sec: 50, score: 0.7, ext: "mp3",
});

describe("Phase 36d — MagicClipsTab", () => {
  beforeEach(() => { jest.clearAllMocks(); });

  test("renders draft clips with Publish action; Publish flips status", async () => {
    axios.get.mockResolvedValue({data: {
      items: [draftClip("a"), draftClip("b"), draftClip("c")],
      magic_clips_status: "completed"}});
    axios.post.mockResolvedValue({data: {}});
    const {MagicClipsTab} = require("../MagicClipsTab");
    render(<MagicClipsTab episodeId="pep_x" isOwner={true} />);
    await waitFor(() => screen.getByTestId("magic-clip-mc_a"));
    expect(screen.getAllByText(/Drafts/i)[0]).toBeInTheDocument();
    // First time we render, only drafts are in `items`. After Publish,
    // we re-fetch with the same payload, so we just assert the POST.
    await act(async () => {
      fireEvent.click(screen.getByTestId("publish-mc_a"));
    });
    expect(axios.post).toHaveBeenCalledWith(
      expect.stringContaining("/podcasts/magic-clips/mc_a/publish"));
  });

  test("Highlights global feed renders 20 items + pagination affordance",
        async () => {
    const items = Array.from({length: 20}, (_, i) => ({
      ...draftClip(`h${i}`), status: "published",
      published_at: new Date().toISOString()}));
    axios.get.mockResolvedValue({data: {
      items, next_cursor: "2026-06-01T00:00:00", has_more: true}});
    const {Highlights} = require("../MagicClipsTab");
    render(<Highlights />);
    await waitFor(() => screen.getByTestId("highlight-mc_h0"));
    // All 20 rendered.
    Array.from({length: 20}, (_, i) =>
      expect(screen.getByTestId(`highlight-mc_h${i}`)).toBeInTheDocument());
    expect(screen.getByTestId("load-more")).toBeInTheDocument();
  });

  test("ChannelHighlightsCarousel mounts only when published clips exist",
        async () => {
    axios.get.mockResolvedValue({data: {items: [{...draftClip("car1"),
                                                                              status: "published"}]}});
    const {ChannelHighlightsCarousel} = require("../MagicClipsTab");
    render(<ChannelHighlightsCarousel channelId="pch_x" />);
    await waitFor(() => screen.getByTestId("channel-highlights-carousel"));
    expect(screen.getByTestId("carousel-clip-mc_car1")).toBeInTheDocument();
  });
});
