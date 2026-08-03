/**
 * Phase 36a — Podcasts FE smoke tests.
 */
import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";

process.env.REACT_APP_BACKEND_URL = "http://localhost:8001";

jest.mock("axios", () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn(), patch: jest.fn() },
}));

const axios = require("axios").default;

describe("Phase 36a — Podcasts surface", () => {
  beforeEach(() => {
    axios.get.mockReset(); axios.post.mockReset();
  });

  test("Podcasts tab renders discovery grid with channels", async () => {
    axios.get.mockResolvedValue({data: {channels: [
      {id: "ch1", slug: "test-show", title: "Test Show",
        category: "tech", follower_count: 42},
      {id: "ch2", slug: "comedy-hour", title: "Comedy Hour",
        category: "comedy", follower_count: 12},
    ]}});
    const Podcasts = require("../Podcasts").default;
    render(<Podcasts />);
    await waitFor(() => {
      expect(screen.getByTestId("podcasts-tab")).toBeInTheDocument();
      expect(screen.getByTestId("podcast-card-test-show")).toBeInTheDocument();
      expect(screen.getByTestId("podcast-card-comedy-hour")).toBeInTheDocument();
    });
    expect(screen.getByText("Test Show")).toBeInTheDocument();
  });

  test("Podcasts tab search input filters via API call", async () => {
    axios.get.mockResolvedValue({data: {channels: []}});
    const Podcasts = require("../Podcasts").default;
    render(<Podcasts />);
    const search = await screen.findByTestId("podcasts-search");
    fireEvent.change(search, {target: {value: "comedy"}});
    await waitFor(() => {
      const calls = axios.get.mock.calls.map((c) => c[0]);
      expect(calls.some((u) => u.includes("q=comedy"))).toBe(true);
    });
  });

  test("Creator dashboard shows apply CTA for new user", async () => {
    axios.get.mockResolvedValue({data: {creator: null}});
    const Creator = require("../Creator").default;
    render(<Creator />);
    await waitFor(() => {
      expect(screen.getByTestId("creator-apply-cta")).toBeInTheDocument();
    });
  });

  test("Creator dashboard shows pending banner when application pending",
        async () => {
    axios.get.mockResolvedValue({data: {creator: {
      id: "crt_x", application_status: "pending",
      contact_email: "x@bigfm.dubai"}}});
    const Creator = require("../Creator").default;
    render(<Creator />);
    await waitFor(() => {
      expect(screen.getByTestId("creator-pending")).toBeInTheDocument();
      expect(screen.getByText(/being reviewed/i)).toBeInTheDocument();
    });
  });

  test("Admin Podcasts page lists pending applications with approve / reject "
        + "buttons", async () => {
    axios.get.mockResolvedValue({data: {applications: [
      {id: "crt_pending_1", display_name: "Alice Host",
        contact_email: "a@x.com", market: "dubai",
        bio: "Veteran broadcaster"},
    ]}});
    const AdminPodcasts = require("../AdminPodcasts").default;
    render(<AdminPodcasts />);
    await waitFor(() => {
      expect(screen.getByTestId("application-crt_pending_1")).toBeInTheDocument();
      expect(screen.getByTestId("approve-crt_pending_1")).toBeInTheDocument();
      expect(screen.getByTestId("reject-crt_pending_1")).toBeInTheDocument();
    });
  });
});
