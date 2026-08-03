// Phase 36d Turn 2 — Shoppable cards frontend tests.

import React from "react";
import {render, screen, waitFor, fireEvent, act}
  from "@testing-library/react";
import "@testing-library/jest-dom";

process.env.REACT_APP_BACKEND_URL = "http://localhost:8001";

jest.mock("axios", () => ({
  __esModule: true,
  default: {get: jest.fn(), post: jest.fn(), patch: jest.fn(),
                  delete: jest.fn(), defaults: {withCredentials: true}},
}));
const axios = require("axios").default;


const card = (id, overrides = {}) => ({
  id: `shc_${id}`, owner_creator_id: "cr_x",
  episode_id: "pep_x", magic_clip_id: null,
  title: `Card ${id}`, image_url: "https://img.example/x.png",
  product_url: "https://shop.example/" + id,
  price_cents: 2999, currency: "USD",
  description: "A premium product worth buying.",
  display_order: 0, active: true, ...overrides,
});


describe("Phase 36d Turn 2 — ShoppableCards", () => {
  beforeEach(() => { jest.clearAllMocks(); });

  test("Creator form: renders, submits multipart, triggers refresh",
        async () => {
    axios.get.mockResolvedValueOnce({data: {items: [], count: 0}});
    axios.post.mockResolvedValueOnce({data: card("a")});
    axios.get.mockResolvedValueOnce({data: {items: [card("a")], count: 1}});
    const {ShoppableCardsCreator} = require("../ShoppableCards");
    render(<ShoppableCardsCreator episodeId="pep_x" isOwner={true} />);
    await waitFor(() => screen.getByTestId("shoppable-empty"));
    fireEvent.click(screen.getByTestId("shoppable-add-btn"));
    await waitFor(() => screen.getByTestId("shoppable-form"));
    fireEvent.change(screen.getByTestId("sh-title"),
                                  {target: {value: "Test Hat"}});
    fireEvent.change(screen.getByTestId("sh-url"),
                                  {target: {value: "https://shop.example/hat"}});
    fireEvent.change(screen.getByTestId("sh-price"),
                                  {target: {value: "29.99"}});
    await act(async () => {
      fireEvent.click(screen.getByTestId("sh-form-submit"));
    });
    expect(axios.post).toHaveBeenCalledTimes(1);
    const [postUrl, fd, opts] = axios.post.mock.calls[0];
    expect(postUrl).toContain("/podcasts/episodes/pep_x/shoppable-cards");
    expect(fd).toBeInstanceOf(FormData);
    expect(fd.get("title")).toBe("Test Hat");
    expect(fd.get("product_url")).toBe("https://shop.example/hat");
    expect(fd.get("price_cents")).toBe("2999");
    expect(opts.headers["Content-Type"]).toBe("multipart/form-data");
  });

  test("Sidebar widget: renders cards from API, anchors go through /click",
        async () => {
    axios.get.mockResolvedValue({data: {items: [card("a"), card("b")],
                                                                        count: 2}});
    const {ShoppableCardsSidebar} = require("../ShoppableCards");
    render(<ShoppableCardsSidebar episodeId="pep_x" />);
    await waitFor(() => screen.getByTestId("shoppable-sidebar"));
    const tileA = screen.getByTestId("shoppable-tile-shc_a");
    expect(tileA).toBeInTheDocument();
    // CRITICAL: click target must be the /click proxy, NOT product_url.
    expect(tileA.getAttribute("href")).toContain(
      "/podcasts/shoppable-cards/shc_a/click");
    expect(tileA.getAttribute("href")).not.toContain("shop.example");
    // Compact variant renders 2-col grid.
    expect(screen.getByTestId("shoppable-tile-shc_b")).toBeInTheDocument();
  });

  test("Sidebar: empty list renders nothing (returns null)", async () => {
    axios.get.mockResolvedValue({data: {items: [], count: 0}});
    const {ShoppableCardsSidebar} = require("../ShoppableCards");
    const {container} = render(<ShoppableCardsSidebar episodeId="pep_x" />);
    await waitFor(() => {
      expect(axios.get).toHaveBeenCalled();
    });
    // Component returns null → no sidebar element rendered.
    expect(container.querySelector("[data-testid='shoppable-sidebar']"))
      .toBeNull();
  });

  test("Show all toggles when >3 cards", async () => {
    const many = Array.from({length: 5}, (_, i) => card(`m${i}`));
    axios.get.mockResolvedValue({data: {items: many, count: 5}});
    const {ShoppableCardsSidebar} = require("../ShoppableCards");
    render(<ShoppableCardsSidebar episodeId="pep_x" />);
    await waitFor(() => screen.getByTestId("shoppable-sidebar"));
    // Only 3 visible initially.
    expect(screen.queryByTestId("shoppable-tile-shc_m3")).toBeNull();
    fireEvent.click(screen.getByTestId("shoppable-show-all"));
    expect(screen.getByTestId("shoppable-tile-shc_m3")).toBeInTheDocument();
  });
});
